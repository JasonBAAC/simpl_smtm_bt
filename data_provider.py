import time
import sqlite3
import pandas as pd
import pybithumb
import logging
import threading
import json
import asyncio
import websockets
from datetime import datetime, timedelta, timezone

class DataProvider:
    """
    Bithumb Websocket을 직접 연결하여 실시간 데이터를 수신하는 클래스
    (자동 재연결 및 예외 처리 강화 버전)
    """
    def __init__(self, db_path="smtm_data.db", use_db=False):
        self.db_path = db_path
        self.use_db = use_db
        self.logger = logging.getLogger("DataProvider")
        self.kst = timezone(timedelta(hours=9))
        
        self.latest_prices = {} 
        self.ws_running = False
        
        if self.use_db:
            self._init_db()

    def _init_db(self):
        """데이터베이스 및 테이블 초기화"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS price_data (
                timestamp TEXT,
                ticker TEXT,
                closing_price REAL,
                units_traded REAL
            )
        ''')
        cursor.execute('DELETE FROM price_data')
        conn.commit()
        conn.close()
        self.logger.info("Database initialized.")

    def start_websocket(self):
        """웹소켓 수신 시작"""
        if self.ws_running: return
        self.ws_running = True
        thread = threading.Thread(target=self._run_async_ws, daemon=True)
        thread.start()
        self.logger.info("Custom Websocket sub-system started with Auto-reconnect.")

    def _run_async_ws(self):
        """비동기 루프 가동 및 재연결 관리"""
        while self.ws_running:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._ws_handler())
            except Exception as e:
                self.logger.error(f"Websocket loop crashed: {e}. Reconnecting in 5s...")
                time.sleep(5) # 재연결 대기
            finally:
                loop.close()

    async def _ws_handler(self):
        """빗썸 웹소켓 연결 및 데이터 처리"""
        uri = "wss://pubwss.bithumb.com/pub/ws"
        async with websockets.connect(uri, ping_interval=20, ping_timeout=20) as websocket:
            subscribe_fmt = {
                "type": "ticker", 
                "symbols": ["ALL_KRW"], 
                "tickTypes": ["30M"]
            }
            await websocket.send(json.dumps(subscribe_fmt))
            self.logger.info("Websocket connection established.")
            
            while self.ws_running:
                try:
                    data = await asyncio.wait_for(websocket.recv(), timeout=30)
                    data = json.loads(data)
                    
                    if data.get('type') == 'ticker':
                        content = data.get('content', {})
                        symbol = content.get('symbol')
                        if symbol:
                            ticker = symbol.split('_')[0]
                            self.latest_prices[ticker] = {
                                'closing_price': float(content.get('closePrice', 0)),
                                'units_traded': float(content.get('volume', 0)),
                                'time': content.get('time')
                            }
                except asyncio.TimeoutError:
                    self.logger.warning("Websocket receive timeout. Sending ping...")
                    # 타임아웃 발생 시 연결 확인을 위해 루프 재시도 (상위 루프에서 재연결)
                    break 

    def get_realtime_data(self):
        """전략용 데이터 반환 (스냅샷)"""
        if self.latest_prices:
            prices_snapshot = self.latest_prices.copy()
            if self.use_db:
                self._save_to_db(prices_snapshot)
            return prices_snapshot
        
        try:
            prices = pybithumb.get_current_price("ALL")
            if prices:
                if self.use_db: self._save_to_db(prices)
                return prices
        except:
            pass
        return None

    def _save_to_db(self, prices):
        """KST 시간으로 DB 저장"""
        try:
            timestamp = datetime.now(self.kst).strftime('%Y-%m-%d %H:%M:%S')
            conn = sqlite3.connect(self.db_path)
            data_list = []
            for ticker, info in prices.items():
                if isinstance(info, dict):
                    data_list.append((timestamp, ticker, info.get('closing_price'), info.get('units_traded')))
            
            cursor = conn.cursor()
            cursor.executemany(
                "INSERT INTO price_data (timestamp, ticker, closing_price, units_traded) VALUES (?, ?, ?, ?)",
                data_list
            )
            conn.commit()
            conn.close()
        except Exception as e:
            self.logger.error(f"DB Save Error: {e}")
