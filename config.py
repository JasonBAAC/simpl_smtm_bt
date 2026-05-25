import os
from dotenv import load_dotenv
import pybithumb

# .env 파일 로드
load_dotenv()

# Bithumb API Key 설정
CON_KEY = os.getenv("BITHUMB_CON_KEY", "YOUR_CONNECT_KEY")
SEC_KEY = os.getenv("BITHUMB_SEC_KEY", "YOUR_SECRET_KEY")

def get_bithumb_instance():
    if CON_KEY == "YOUR_CONNECT_KEY" or SEC_KEY == "YOUR_SECRET_KEY":
        print("Warning: Bithumb API keys are not configured in .env file.")
    return pybithumb.Bithumb(CON_KEY, SEC_KEY)

if __name__ == "__main__":
    print("Bithumb API configuration helper.")
    # b = get_bithumb_instance()
    # print(b.get_balance("BTC"))
