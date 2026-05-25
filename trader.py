import threading
import logging
import time
import pybithumb

class Worker(threading.Thread):
    """
    개별 자산의 매수/매도를 처리하는 스레드 클래스 (자원 동기화 강화 버전)
    """
    def __init__(self, ticker, amount, trader):
        super().__init__()
        self.ticker = ticker
        self.amount = amount
        self.trader = trader
        self.logger = logging.getLogger(f"Worker-{ticker}")
        self.is_bought = False
        self.buy_price = 0
        self.buy_amount = 0
        self.buy_time = 0
        self.max_profit_rate = -1.0
        self.stop_signal = False

    def run(self):
        self.logger.info(f"Started optimized worker for {self.ticker}")
        fee_rate = self.trader.operator.args.fee
        dp = self.trader.operator.data_provider
        
        try:
            self.logger.info(f"Sending market BUY request for {self.ticker}")
            req_price = dp.latest_prices.get(self.ticker, {}).get('closing_price')
            if not req_price:
                req_price = pybithumb.get_current_price(self.ticker)
            
            start_time = time.time()
            self.buy_price = dp.latest_prices.get(self.ticker, {}).get('closing_price')
            while not self.buy_price and (time.time() - start_time) < 10:
                time.sleep(0.1)
                self.buy_price = dp.latest_prices.get(self.ticker, {}).get('closing_price')
            
            if self.buy_price and req_price:
                slippage = (self.buy_price - req_price) / req_price
                if slippage > 0.002:
                    self.logger.warning(f"BUY order ABORTED: Slippage too high ({slippage:.2%})")
                    self._cleanup_and_exit()
                    return

            if self.buy_price and (time.time() - start_time) < 10:
                self.is_bought = True
                self.buy_time = time.time()
                self.buy_amount = self.amount / (self.buy_price * (1 + fee_rate))
                self.logger.info(f"BUY order COMPLETED: {self.ticker} at {self.buy_price:,.0f}")
                
                buy_fee = self.amount - (self.buy_price * self.buy_amount)
                self.trader.analyzer.put_trading_info(self.ticker, 'buy', self.buy_price, self.buy_amount, fee=buy_fee)
                self.trader.operator.send_notification(f"[매수완료] {self.ticker}\n가격: {self.buy_price:,.0f}\n수량: {self.buy_amount:.4f}")
            else:
                self.logger.warning(f"BUY order CANCELLED: Timeout or Price missing.")
                self._cleanup_and_exit()
                return

        except Exception as e:
            self.logger.error(f"Error during BUY: {e}")
            self._cleanup_and_exit()
            return

        stagnation_count = 0
        last_check_price = self.buy_price

        while not self.stop_signal:
            try:
                current_price = dp.latest_prices.get(self.ticker, {}).get('closing_price')
                if not current_price:
                    time.sleep(0.1)
                    continue
                
                expected_sell_value = self.buy_amount * current_price * (1 - fee_rate)
                profit_rate = (expected_sell_value - self.amount) / self.amount
                self.max_profit_rate = max(self.max_profit_rate, profit_rate)
                
                elapsed_time = time.time() - self.buy_time
                
                if elapsed_time > 30:
                    price_move = abs(current_price - last_check_price) / last_check_price
                    if price_move < 0.0005:
                        stagnation_count += 1
                    if stagnation_count >= 50:
                        self._execute_sell(current_price, profit_rate, "Stagnation Exit")
                        break
                last_check_price = current_price

                is_sell_triggered = False
                reason = ""
                
                if profit_rate <= -0.002: # -0.2% 손절
                    is_sell_triggered = True
                    reason = "Stop-loss"
                elif profit_rate >= 0.007: # +0.7% 익절
                    is_sell_triggered = True
                    reason = "Take-profit"
                elif self.max_profit_rate >= 0.005 and (self.max_profit_rate - profit_rate) >= 0.002:
                    is_sell_triggered = True
                    reason = "Trailing Stop"
                elif elapsed_time >= 60:
                    is_sell_triggered = True
                    reason = "Time-out (1m)"
                
                if is_sell_triggered:
                    self._execute_sell(current_price, profit_rate, reason)
                    break
                
                time.sleep(0.1)
            except Exception as e:
                self.logger.error(f"Error during monitoring: {e}")
                break
        
        self._cleanup_and_exit()

    def _execute_sell(self, price, rate, reason):
        fee_rate = self.trader.operator.args.fee
        self.logger.info(f"Sending market SELL request for {self.ticker} | Reason: {reason}")
        sell_fee = self.buy_amount * price * fee_rate
        self.trader.analyzer.put_trading_info(self.ticker, 'sell', price, self.buy_amount, fee=sell_fee)
        self.trader.operator.send_notification(f"[{reason} 완료] {self.ticker}\n수익률: {rate:.2%}\n매도가: {price:,.0f}")

    def _cleanup_and_exit(self):
        """[방어 1] Thread-safe하게 딕셔너리에서 본인 제거"""
        with self.trader.lock:
            if self.ticker in self.trader.workers:
                del self.trader.workers[self.ticker]
        self.logger.info(f"Worker for {self.ticker} finished and cleaned up.")

class Trader:
    """
    거래 실행 및 Worker 관리 클래스
    """
    def __init__(self, operator, analyzer):
        self.logger = logging.getLogger("Trader")
        self.workers = {}
        self.lock = threading.Lock() # [방어 1] 자원 접근 동기화를 위한 락
        self.operator = operator
        self.analyzer = analyzer

    def execute_trade(self, ticker, amount):
        """Worker를 통한 병렬 거래 실행 (락 사용)"""
        with self.lock:
            if ticker not in self.workers:
                worker = Worker(ticker, amount, self)
                self.workers[ticker] = worker
                worker.start()
                return True
        return False
