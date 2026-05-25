import sqlite3
import pandas as pd
from datetime import datetime

def analyze_non_selected_candidates():
    conn = sqlite3.connect('smtm_data.db')
    
    # 1. 2026-05-23 01:10:15 시점의 후보군 리스트 (로그 기반)
    # Selected: ['XYO', 'UP', 'ROA', 'FLUX']
    # Non-selected candidates (Candidates - Selected):
    non_selected = [
        'BTC', 'ETH', 'COMP', 'XLM', 'MLK', 'EGLD', 'INJ', 'HFT', 'CFX', 'FRAX', 
        'ID', 'OSMO', 'SPURS', 'USDC', 'NEAR', 'PEAQ', 'EIGEN', 'CFG', 'SWELL', 
        'PONKE', 'VIRTUAL', 'MORPHO', 'VANA', 'DKA', 'BIO', 'SOON', 'AVL', 
        'XTER', 'BTR', 'SYRUP', 'CAMP', 'XAN', 'IN', 'RECALL', 'ZBT', 'CYS'
    ]
    
    timestamp = "2026-05-23 01:10:15"
    
    print(f"--- [Non-Selected Candidates Analysis at {timestamp}] ---")
    
    results = []
    for ticker in non_selected:
        # DB에서 해당 시간 이후 1분간의 가격 데이터 조회
        query = f"""
            SELECT closing_price FROM price_data 
            WHERE ticker = '{ticker}' AND timestamp >= '{timestamp}' 
            ORDER BY timestamp ASC LIMIT 13
        """
        df = pd.read_sql(query, conn)
        
        if len(df) < 2: continue
        
        start_price = df.iloc[0]['closing_price']
        max_price = df['closing_price'].max()
        min_price = df['closing_price'].min()
        
        max_ret = (max_price - start_price) / start_price * 100
        min_ret = (min_price - start_price) / start_price * 100
        
        # 실제 매수했다면 결과 시뮬레이션
        outcome = "Timeout"
        if min_ret <= -0.3: outcome = "Stop-loss"
        elif max_ret >= 1.0: outcome = "Take-profit"
        
        results.append({
            'ticker': ticker,
            'max_ret': max_ret,
            'min_ret': min_ret,
            'outcome': outcome
        })
    
    res_df = pd.DataFrame(results)
    print("\n[Simulated Outcome if we had bought non-selected candidates]")
    print(res_df['outcome'].value_counts())
    
    print("\n[Top 5 Potential Performers we missed]")
    print(res_df.sort_values(by='max_ret', ascending=False).head(5))

    print("\n[Top 5 Traps we avoided (Stop-loss candidates)]")
    print(res_df.sort_values(by='min_ret').head(5))

    conn.close()

if __name__ == "__main__":
    analyze_non_selected_candidates()
