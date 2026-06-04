import websocket
import json
import threading
import time

WEBSOCKET_URL = "wss://ws-api.bithumb.com/websocket/v1"

def on_open(ws):
    print("Websocket connection opened.")
    subscribe_fmt = [
        {
            "ticket": "test example"
        },
        {
            "type": "ticker",
            "codes": [
            "KRW-XRP",             "KRW-ETH"
            ]
        },
        {
            "format": "DEFAULT"
        }
    ]
    ws.send(json.dumps(subscribe_fmt))
    print("Subscribed to ticker data.")
    
def on_message(ws, message):
    data = json.loads(message)
    print("Received data: ", json.dumps(data, ensure_ascii=False, indent=4))

def on_error(ws, error):
    print("Error occurred: ", error)

def on_close(ws, close_status_code, close_msg):
    print("Websocket connection closed: ", close_status_code, close_msg)
    
if __name__ == "__main__":
    ws = websocket.WebSocketApp(WEBSOCKET_URL,
                                on_open=on_open,
                                on_message=on_message,
                                on_error=on_error,
                                on_close=on_close)
    
    wst = threading.Thread(target=ws.run_forever)
    wst.daemon = True
    wst.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Exiting...")
        ws.close()
        # wst.join()
        # exit()