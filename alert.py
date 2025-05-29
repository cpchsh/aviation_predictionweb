# alert.py  ── 共用的小工具
import os, json, requests, logging
from dotenv import load_dotenv; load_dotenv()

WEBHOOK_URL = os.getenv("ALERT_WEBHOOK")   # 放在 .env / GitHub Secrets

def notify(text: str, color: str = None):
    """
    送出最簡單 Teams 訊息。
    color: 6 碼 HEX（無 #），缺省不帶顏色
    """
    if not WEBHOOK_URL:
        logging.warning("WEBHOOK_URL 未設定，訊息未送出")
        return False

    # 基本格式 → Teams 會自動渲染「MessageCard」
    payload = {
        "@type":    "MessageCard",
        "@context": "https://schema.org/extensions",
        "text": text
    }
    if color:
        payload["themeColor"] = color.upper()

    try:
        r = requests.post(WEBHOOK_URL, json=payload, timeout=5)
        r.raise_for_status()
        return True
    except Exception as e:
        logging.error("Teams Webhook 送出失敗：%s", e)
        return False
