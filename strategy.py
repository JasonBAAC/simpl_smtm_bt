import logging
from collections import deque
import numpy as np

class Strategy:
    """
    데이터를 분석하여 매수 대상 자산을 선정하는 클래스 (상세 추적 로깅 버전)
    """
    def __init__(self, n=4):
        self.n = n
        self.logger = logging.getLogger("Pocket")
        self.price_history = {} 
        self.units_history = {} 
        self.pocket = []

    def update_data(self, current_prices):
        """수신된 데이터를 바탕으로 지표 계산 및 상세 필터링 과정 기록"""
        candidates = []
        self.logger.info("--- [Asset Selection Detail Trace] ---")
        
        for ticker, info in current_prices.items():
            if not isinstance(info, dict): continue
            try:
                cur_price = float(info.get('closing_price', 0))
                cur_units = float(info.get('units_traded', 0))
            except (ValueError, TypeError): continue
            
            if ticker not in self.price_history:
                self.price_history[ticker] = deque(maxlen=12)
                self.units_history[ticker] = deque(maxlen=12)
            
            self.price_history[ticker].append(cur_price)
            self.units_history[ticker].append(cur_units)
            
            if len(self.price_history[ticker]) < 4: continue
                
            history_p = list(self.price_history[ticker])
            history_u = list(self.units_history[ticker])
            
            if history_p[-2] == 0: continue
            
            # [Filter 1] 최소 상승폭 (Price Rate > 0.1%)
            price_rate = (history_p[-1] - history_p[-2]) / history_p[-2]
            
            # 유의미한 움직임(0.1% 상승)이 있는 종목만 상세 추적 로깅 시작
            if price_rate > 0.001:
                trace_msg = f"[{ticker}] "
                trace_msg += f"Step 1(Price): {price_rate:.2%} (Pass) | "
                
                # [Filter 2] 거래량 가중치 (Units Rate > 50%)
                avg_units = np.mean(history_u[-5:-1]) if len(history_u) >= 5 else history_u[0]
                units_rate = (history_u[-1] - history_u[-2]) / history_u[-2] if history_u[-2] != 0 else 0
                
                if units_rate > 0.5:
                    trace_msg += f"Step 2(Vol): {units_rate:.2f}x (Pass) | "
                    
                    # [Filter 3] 변동성 필터 (Volatility < 1.0%)
                    p_slice = history_p[-4:]
                    p_mean = np.mean(p_slice)
                    volatility = np.std(p_slice) / p_mean * 100 if p_mean != 0 else 999
                    
                    if volatility <= 1.0:
                        trace_msg += f"Step 3(Volat): {volatility:.2f}% (Pass) | "
                        
                        # [Filter 4] 추세 필터 (Short/Long MA Alignment)
                        ma_short = np.mean(p_slice)
                        ma_long = np.mean(history_p)
                        
                        if cur_price >= ma_short and cur_price >= ma_long:
                            # 모든 필터 통과
                            trace_msg += "Step 4(Trend): Align (Pass) -> [SELECTED]"
                            self.logger.info(trace_msg)
                            
                            # MA 증가율 계산 (최종 순위용)
                            r1 = (history_p[-1] - history_p[-2]) / history_p[-2] if history_p[-2] != 0 else 0
                            r2 = (history_p[-2] - history_p[-3]) / history_p[-3] if history_p[-3] != 0 else 0
                            r3 = (history_p[-3] - history_p[-4]) / history_p[-4] if history_p[-4] != 0 else 0
                            ma_price_rate = (r1 + r2 + r3) / 3
                            
                            candidates.append({
                                'ticker': ticker,
                                'ma_rate': ma_price_rate,
                                'price': cur_price
                            })
                        else:
                            trace_msg += f"Step 4(Trend): Price < MA (Fail)"
                            self.logger.info(trace_msg)
                    else:
                        trace_msg += f"Step 3(Volat): {volatility:.2f}% (Fail: Too High)"
                        self.logger.info(trace_msg)
                else:
                    # 거래량 미달은 너무 많으므로 선택적으로 로깅하거나 생략 가능 (여기서는 추적을 위해 로깅)
                    trace_msg += f"Step 2(Vol): {units_rate:.2f}x (Fail: Low Vol)"
                    self.logger.info(trace_msg)

        # 상위 n개 최종 선정
        candidates.sort(key=lambda x: x['ma_rate'], reverse=True)
        self.pocket = [c['ticker'] for c in candidates[:self.n]]
        
        if self.pocket:
            self.logger.info(f"Final Pocket Round Winners: {self.pocket}")
        else:
            self.logger.info("No candidates passed all 4 filters in this round.")
        
        return self.pocket
