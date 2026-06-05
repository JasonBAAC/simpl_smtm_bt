import websocket
import json
import threading
import time
import sqlite3
import pandas as pd
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))

WEBSOCKET_URL = "wss://ws-api.bithumb.com/websocket/v1"
DB_PATH = "bithumb_data.db"


def save_to_db(record: dict):
    row = {"received_at": datetime.now(KST).isoformat(), **record}
    df = pd.DataFrame([row])

    con = sqlite3.connect(DB_PATH)
    # 테이블이 존재하면 누락된 컬럼을 자동으로 추가
    table_exists = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='ticker'"
    ).fetchone()
    if table_exists:
        existing_cols = {r[1] for r in con.execute("PRAGMA table_info(ticker)")}
        for col in df.columns:
            if col not in existing_cols:
                con.execute(f"ALTER TABLE ticker ADD COLUMN \"{col}\" TEXT")
        con.commit()

    df.to_sql("ticker", con, if_exists="append", index=False)
    con.close()


def on_open(ws):
    print("Websocket connection opened.")
    subscribe_fmt = [
        {"ticket": "test example"},
        {
            "type": "ticker",
            "codes": ["KRW-XRP"],
        },
        {"format": "DEFAULT"},
    ]
    ws.send(json.dumps(subscribe_fmt))
    print("Subscribed to ticker data.")


def on_message(ws, message):
    data = json.loads(message)
    print(f"[{data.get('code')}] price={data.get('trade_price')} "
          f"change={data.get('change_rate')} ask_bid={data.get('ask_bid')}")
    save_to_db(data)


def on_error(ws, error):
    print("Error occurred:", error)


def on_close(ws, close_status_code, close_msg):
    print("Websocket connection closed:", close_status_code, close_msg)


if __name__ == "__main__":
    ws = websocket.WebSocketApp(
        WEBSOCKET_URL,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )

    wst = threading.Thread(target=ws.run_forever)
    wst.daemon = True
    wst.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Exiting...")
        ws.close()
