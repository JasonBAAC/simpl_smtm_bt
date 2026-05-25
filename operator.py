import time
import logging
import argparse
import asyncio
import os
import sys
import threading
import queue
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta, timezone
from telegram import Bot
from data_provider import DataProvider
from strategy import Strategy
from trader import Trader
from analyzer import Analyzer

import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

class Operator:
    """
    시스템 전체 운영 및 모듈 간 조율 클래스 (Sim 모드 추적성 강화 버전)
    """
    def __init__(self, args):
        self.args = args
        self.args.fee = args.fee / 100
        self.mode_prefix = f"[{args.mode.upper()}]"
        self.kst = timezone(timedelta(hours=9))
        self.logger, self.pocket_logger = self._setup_logger()
        
        # [Sim 모드 추적성] save_db 옵션이 없더라도 Sim 모드면 강제로 DB 저장 활성화 고려 가능
        # 여기서는 명시적으로 --save_db를 사용하는 것으로 유지하되, 필요 시 자동 활성화 로직 추가 가능
        self.data_provider = DataProvider(use_db=args.save_db)
        self.strategy = Strategy(n=args.n)
        
        # Strategy 로거 설정: Sim 모드일 경우 Pocket 로거가 메인 로그 파일에도 기록하도록 _setup_logger에서 처리됨
        self.strategy.logger = self.pocket_logger
        
        self.analyzer = Analyzer()
        self.analyzer.set_initial_config(args.budget)
        self.trader = Trader(self, self.analyzer)
        
        self.round_count = 0 
        self.msg_queue = queue.Queue(maxsize=100)
        self.telegram_enabled = False
        
        token = args.token or os.getenv("TELEGRAM_TOKEN")
        chat_id = args.chat_id or os.getenv("TELEGRAM_CHAT_ID")
        
        if token and chat_id:
            try:
                token = token.strip()
                chat_id = chat_id.strip()
                self.bot = Bot(token=token)
                self.chat_id = chat_id
                self.telegram_enabled = True
                self.tg_thread = threading.Thread(target=self._tg_worker, daemon=True)
                self.tg_thread.start()
                
                status_text = "enabled" if args.msg.lower() == 'yes' else "essential only"
                self.logger.info(f"{self.mode_prefix} Telegram notification {status_text}.")
            except Exception as e:
                self.logger.error(f"Failed to initialize Telegram bot: {e}")

    def _setup_logger(self):
        """로깅 설정: Sim 모드 시 전략 계산 과정을 메인 로그에 통합"""
        if not os.path.exists("log"):
            os.makedirs("log")
        timestamp = datetime.now(self.kst).strftime('%Y%m%d_%H%M%S')
        log_filename = f"log/smtm_{timestamp}.log"
        pocket_log_filename = f"log/pocket_{timestamp}.log"
        formatter = logging.Formatter(f'%(asctime)s [%(levelname)s] {self.mode_prefix} %(name)s: %(message)s')
        
        logger = logging.getLogger("Operator")
        logger.setLevel(logging.INFO)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        # 메인 로그 파일 핸들러
        main_file_handler = RotatingFileHandler(log_filename, maxBytes=2*1024*1024, backupCount=5, encoding='utf-8')
        main_file_handler.setFormatter(formatter)
        logger.addHandler(main_file_handler)
        
        # 포켓 상세 로거
        pocket_logger = logging.getLogger("Pocket")
        pocket_logger.setLevel(logging.INFO)
        p_file_handler = logging.FileHandler(pocket_log_filename, encoding='utf-8')
        p_file_handler.setFormatter(formatter)
        pocket_logger.addHandler(p_file_handler)
        pocket_logger.addHandler(console_handler)
        
        # [요청 반영] Sim 모드일 경우 포켓 계산 과정을 메인 smtm...log 에도 기록
        if self.args.mode == 'sim':
            pocket_logger.addHandler(main_file_handler)
            logger.info("Simulation mode: Detailed pocketing process will be recorded in main log.")

        pocket_logger.propagate = False
        
        for module in ["DataProvider", "Trader", "Analyzer"]:
            m_logger = logging.getLogger(module)
            m_logger.setLevel(logging.INFO)
            m_logger.addHandler(console_handler)
            m_logger.addHandler(main_file_handler)
            m_logger.propagate = False
        return logger, pocket_logger

    def _tg_worker(self):
        """텔레그램 워커"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        async def _send_msg(text):
            try:
                await self.bot.send_message(chat_id=self.chat_id, text=f"{self.mode_prefix} {text}")
                return True
            except Exception as e:
                self.logger.error(f"TG Worker Error: {e}")
                return False
        while True:
            text = self.msg_queue.get()
            if text is None: break
            for i in range(3):
                if loop.run_until_complete(_send_msg(text)): break
                time.sleep(1)
            self.msg_queue.task_done()
        loop.close()

    def send_notification(self, text, force=False):
        if self.telegram_enabled:
            if self.args.msg.lower() == 'yes' or force:
                try:
                    self.msg_queue.put(text, block=False)
                except queue.Full:
                    self.logger.warning("Telegram msg queue is full.")

    def run(self):
        self.logger.info(f"Starting SMTM-Lite in {self.args.mode} mode...")
        self.data_provider.start_websocket()
        
        start_msg = (
            f"🚀 SMTM-Lite 거래 시작\n"
            f"예산: {self.args.budget:,.0f} | 종목수: {self.args.n}\n"
            f"수수료: {self.args.fee*100:.2f}% | 모드: {self.args.mode}"
        )
        self.send_notification(start_msg, force=True)
        last_report_time = time.time()
        
        try:
            while True:
                # [웹소켓 기반] 실시간 데이터 수신
                prices = self.data_provider.get_realtime_data()
                if prices:
                    snapshot = self.analyzer.put_asset_snapshot(prices, self.trader.workers)
                    if snapshot['return_rate'] <= -5.0:
                        self.logger.critical("!!! Emergency Stop: -5% Loss !!!")
                        report = self.analyzer.get_report(self.round_count)
                        self.send_notification(f"🚨 긴급 정지: 누적 손익 -5% 도달\n{report}", force=True)
                        time.sleep(5)
                        sys.exit(1)
                    
                    with self.trader.lock:
                        current_active_workers = len(self.trader.workers)
                        active_tickers = list(self.trader.workers.keys())
                    
                    available_slots = self.args.n - current_active_workers
                    if available_slots > 0:
                        # [Sim 모드] 전략 선정 시 계산 과정이 로그에 출력됨 (setup_logger 설정에 의해)
                        self.round_count += 1
                        pocket = self.strategy.update_data(prices)
                        if pocket:
                            amount_per_ticker = self.args.budget / self.args.n
                            for ticker in pocket:
                                if self.trader.execute_trade(ticker, amount_per_ticker):
                                    available_slots -= 1
                                    if available_slots <= 0: break
                    
                    if active_tickers:
                        status = []
                        for t in active_tickers:
                            p_info = prices.get(t, {})
                            p = p_info.get('closing_price', 0) if isinstance(p_info, dict) else p_info
                            status.append(f"{t} {float(p):,.0f}")
                        self.logger.info(f"Status: {len(active_tickers)} active ({', '.join(status)}). Value: {snapshot['total_value']:,.0f} ({snapshot['return_rate']:.2f}%)")

                if time.time() - last_report_time > 3600:
                    self.send_notification(self.analyzer.get_report(self.round_count))
                    last_report_time = time.time()
                time.sleep(5)
        except KeyboardInterrupt:
            self.logger.info("Stopping SMTM-Lite...")
            report = self.analyzer.get_report(self.round_count)
            self.send_notification(f"🛑 사용자 종료 리포트\n{report}", force=True)
            time.sleep(3)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Optimized SMTM-Lite")
    parser.add_argument("--mode", choices=["sim", "live"], default="sim")
    parser.add_argument("--save_db", action="store_true")
    parser.add_argument("--n", type=int, default=4)
    parser.add_argument("--budget", type=float, default=100000)
    parser.add_argument("--fee", type=float, default=0.04)
    parser.add_argument("--msg", choices=["yes", "no"], default="yes")
    parser.add_argument("--token", type=str)
    parser.add_argument("--chat_id", type=str)
    args = parser.parse_args()
    Operator(args).run()
