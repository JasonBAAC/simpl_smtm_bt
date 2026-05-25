import logging
import pandas as pd
from datetime import datetime, timedelta, timezone

class Analyzer:
    """
    거래 성과를 분석하고 리포트를 생성하는 클래스
    smtm의 주요 로직(수익률, 자산 상태 관리)을 리팩토링하여 반영
    """
    def __init__(self):
        self.logger = logging.getLogger("Analyzer")
        self.trade_history = []  # 거래 내역 (buy/sell)
        self.asset_history = []  # 자산 상태 히스토리 (스냅샷)
        self.initial_budget = 0
        self.current_cash = 0
        self.total_fees = 0      # 전체 수수료 총액
        self.win_count = 0       # 수익 회차 (손익 > 0)
        self.loss_count = 0      # 손실 회차 (손익 <= 0)
        self.kst = timezone(timedelta(hours=9))

    def set_initial_config(self, budget):
        self.initial_budget = budget
        self.current_cash = budget
        self.logger.info(f"Initial budget set to {budget}")

    def put_trading_info(self, ticker, p_type, price, amount, fee=0):
        """거래 발생 시 정보 기록 (put_trading_info)"""
        timestamp = datetime.now(self.kst).strftime('%Y-%m-%d %H:%M:%S')
        self.total_fees += fee
        
        trade_record = {
            'timestamp': timestamp,
            'ticker': ticker,
            'type': p_type,  # 'buy' or 'sell'
            'price': price,
            'amount': amount,
            'fee': fee
        }
        self.trade_history.append(trade_record)
        
        # 현금 잔고 업데이트
        if p_type == 'buy':
            self.current_cash -= (price * amount + fee)
        else:
            self.current_cash += (price * amount - fee)
            self._update_win_loss(ticker, price, amount, fee)
            
        self.logger.info(f"Trade recorded: {p_type} {ticker} at {price:,.0f}, Fee: {fee:.2f}")

    def _update_win_loss(self, ticker, sell_price, amount, sell_fee):
        """매도 시 해당 종목의 수익 여부를 판단하여 카운트 업데이트"""
        # 가장 최근의 해당 종목 매수 기록 찾기
        for i in range(len(self.trade_history)-2, -1, -1):
            trade = self.trade_history[i]
            if trade['ticker'] == ticker and trade['type'] == 'buy':
                buy_cost = (trade['price'] * trade['amount']) + trade['fee']
                sell_revenue = (sell_price * amount) - sell_fee
                if sell_revenue > buy_cost:
                    self.win_count += 1
                else:
                    self.loss_count += 1
                break

    def put_asset_snapshot(self, current_prices, workers):
        """현재 전체 자산 가치 기록 (put_asset_info 리팩토링)"""
        timestamp = datetime.now(self.kst).strftime('%Y-%m-%d %H:%M:%S')
        total_asset_value = self.current_cash
        
        # 현재 보유 중인(Worker가 관리 중인) 자산 가치 합산
        for ticker, worker in workers.items():
            if worker.is_bought:
                try:
                    price = float(current_prices.get(ticker, {}).get('closing_price', worker.buy_price))
                except (ValueError, TypeError):
                    price = float(worker.buy_price)
                
                amount = worker.amount / worker.buy_price
                total_asset_value += (price * amount)
        
        return_rate = ((total_asset_value - self.initial_budget) / self.initial_budget) * 100
        
        snapshot = {
            'timestamp': timestamp,
            'total_value': total_asset_value,
            'cash': self.current_cash,
            'return_rate': return_rate
        }
        self.asset_history.append(snapshot)
        return snapshot

    def get_report(self, pocket_count=0):
        """최종 또는 중간 리포트 생성"""
        if not self.asset_history:
            return "No data to analyze."
        
        latest = self.asset_history[-1]
        summary = (
            f"\n--- [SMTM-Lite Performance Report] ---\n"
            f"Budget: {self.initial_budget:,.0f}\n"
            f"Current Balance: {latest['total_value']:,.0f}\n"
            f"Return Rate: {latest['return_rate']:.2f}%\n"
            f"Total Fees: {self.total_fees:,.2f}\n"
            f"Total Pockets: {pocket_count}\n"
            f"Winning Rounds: {self.win_count}\n"
            f"Losing Rounds: {self.loss_count}\n"
            f"Total Trades: {len(self.trade_history)}\n"
            f"--------------------------------------"
        )
        return summary
