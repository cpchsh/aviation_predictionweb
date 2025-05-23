#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每天 09:00 執行
  1) 找 DB 最新日期 latest_date
  2) 逐日補到昨天，週末自動跳過
  3) 每日先送六港口，再 sleep(5) 送 CPC
"""
import os, time, logging, requests, pymssql
from datetime import date, timedelta
from dotenv import load_dotenv

# ---------- 環境 ----------
load_dotenv()
DB_SERVER = os.getenv("DB_SERVER")
DB_USER   = os.getenv("DB_USER")
DB_PWD    = os.getenv("DB_PASSWORD")
DB_NAME   = os.getenv("DB_NAME")

API_URL   = "http://127.0.0.1:5000/update"
LOG_FILE  = "dailypushoil.log"

logging.basicConfig(filename=LOG_FILE,
                    level=logging.INFO,
                    format="%(asctime)s %(levelname)s | %(message)s")

def nz(v): return "" if v is None else v

# ---------- DB ----------
def get_latest_date():
    with pymssql.connect(server=DB_SERVER, user=DB_USER,
                         password=DB_PWD, database=DB_NAME) as conn:
        with conn.cursor(as_dict=True) as cur:
            cur.execute("SELECT MAX(日期) AS d FROM LSMF_Prediction")
            return cur.fetchone()["d"]

# ---------- 報價來源 (請換成真資料或 API) ----------
def fetch_price(d: date):
    if d.weekday() >= 5:      # 週末沒有報價
        return None
    return {
        "日本": 700.0, "南韓": 702.5, "香港": 698.0,
        "新加坡": 699.0, "上海": 700.0, "舟山": 701.1,
        "CPC": 720.0
    }

# ---------- POST ----------
def call_update(payload: dict) -> bool:
    try:
        r = requests.post(API_URL, data=payload, timeout=20)
        r.raise_for_status()
        status = r.json().get("status")
        logging.info("POST %s -> %s", payload["date"], status)
        return status in ("insert_success", "update_success")
    except Exception as e:
        logging.error("POST FAIL %s | %s", payload.get("date"), e)
        return False

# ---------- 主流程 ----------
def main():
    latest = get_latest_date()
    if not latest:
        logging.error("DB 無資料，結束")
        return

    today = date.today()
    day   = latest + timedelta(days=1)

    while day < today:
        # 週末：直接跳過
        if day.weekday() >= 5:
            logging.info("%s 週末跳過", day)
            day += timedelta(days=1)
            continue

        prices = fetch_price(day)
        if prices is None:        # 假日 or 沒抓到資料
            logging.warning("%s 無報價，跳過", day)
            day += timedelta(days=1)
            continue

        # -------- 1) 先送六港口 --------
        port_payload = {
            "date": day.strftime("%Y-%m-%d"),
            "japan": nz(prices["日本"]), "korea": nz(prices["南韓"]),
            "hongkong": nz(prices["香港"]), "singapore": nz(prices["新加坡"]),
            "shanghai": nz(prices["上海"]), "zhoushan": nz(prices["舟山"]),
            "cpc": ""
        }
        if not call_update(port_payload):
            logging.error("六港口寫入失敗 %s，中止", day)
            return

        time.sleep(5)             # 等 Tukey 完成預測 & 解鎖

        # -------- 2) 再送 CPC --------
        cpc_payload = {
            "date": day.strftime("%Y-%m-%d"),
            "japan":"","korea":"","hongkong":"","singapore":"",
            "shanghai":"","zhoushan":"",
            "cpc": prices["CPC"]
        }
        if not call_update(cpc_payload):
            logging.error("CPC 寫入失敗 %s，中止", day)
            return

        logging.info("完成補值 %s", day)
        day += timedelta(days=1)   # 下一天

if __name__ == "__main__":
    main()
