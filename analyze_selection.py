import sqlite3
import pandas as pd
from datetime import datetime, timedelta

def analyze_db():
    conn = sqlite3.connect('smtm_data.db')
    
    # 1. Get all tickers that were in the logs as "Stop-loss"
    # For simulation purposes, let's just look at the price trend of tickers in the DB
    
    print("--- [Selection Optimization Analysis] ---")
    
    # Get unique tickers in DB
    tickers = pd.read_sql("SELECT DISTINCT ticker FROM price_data", conn)['ticker'].tolist()
    print(f"Total tickers in DB: {len(tickers)}")
    
    analysis_results = []
    
    for ticker in tickers:
        df = pd.read_sql(f"SELECT * FROM price_data WHERE ticker='{ticker}' ORDER BY timestamp", conn)
        if len(df) < 10: continue
        
        # Calculate price change over time
        df['price_change'] = df['closing_price'].pct_change()
        
        # Check if selection was good (i.e., did it go up at all?)
        # Let's assume a "buy" happened at index 4 (after 20s windowing)
        buy_index = 4
        if len(df) > buy_index + 5:
            start_price = df.iloc[buy_index]['closing_price']
            max_price_after = df.iloc[buy_index+1:buy_index+12]['closing_price'].max() # next 1 min
            min_price_after = df.iloc[buy_index+1:buy_index+12]['closing_price'].min()
            
            max_return = (max_price_after - start_price) / start_price * 100
            min_return = (min_price_after - start_price) / start_price * 100
            
            analysis_results.append({
                'ticker': ticker,
                'max_return': max_return,
                'min_return': min_return,
                'volatility': df['price_change'].std() * 100
            })
            
    res_df = pd.DataFrame(analysis_results)
    if not res_df.empty:
        print("\n[Price Movement Summary after Selection]")
        print(res_df.describe())
        
        # Bad candidates (went down immediately)
        bad_candidates = res_df[res_df['max_return'] < 0.1].sort_values(by='min_return')
        print(f"\n[Bad Candidates (Immediate Drop or Flat)]: {len(bad_candidates)}")
        print(bad_candidates.head(5))
        
        # Good candidates (hit TP target 1% if existed)
        good_candidates = res_df[res_df['max_return'] >= 1.0]
        print(f"\n[Good Candidates (Reached +1% within 1m)]: {len(good_candidates)}")
        print(good_candidates.head(5))

    conn.close()

if __name__ == "__main__":
    analyze_db()
