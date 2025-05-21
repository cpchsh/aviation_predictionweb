import os, sys, json, requests, logging
from datetime import date, timedelta, datetime
import pymssql
from dotenv import load_dotenv; load_dotenv()
import time
import pandas as pd
from app.routes.tukey_routes import predict_next_day_tukey
# 自訂的 function, service
from app.services.db_service import get_error_metrics, save_error_metrics_to_db

DB_SERVER = os.getenv("DB_SERVER")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
EIS_SERVER = os.getenv("EIS_SERVER")
EIS_NAME = os.getenv("EIS_NAME")

API_URL = "http://10.168.230.33:5001/update"
LOG_FILE = "dailypushoil.log"

logging.basicConfig(filename=LOG_FILE,
                    level=logging.INFO,
                    format="%(asctime)s %(levelname)s | %(message)s")

def nz(v):    #None->""
    return "" if v is None else v

# 取得資料庫最新、次新日期
def get_latest_two_dates():
    """
    回傳 (latest_date, second_latest_date)
    若資料表只有 1 筆，second_latest 會是 None
    """
    sql = """
        SELECT TOP 2 日期
          FROM oil_prediction_shift
         ORDER BY 日期 DESC
    """
    with pymssql.connect(server=DB_SERVER,
                         user=DB_USER,
                         password=DB_PASSWORD,
                         database=DB_NAME) as conn:
        with conn.cursor(as_dict=True) as cur:
            cur.execute(sql)
            rows = cur.fetchall()               # 最多兩筆

    latest   = rows[0]["日期"] if rows else None
    second   = rows[1]["日期"] if len(rows) > 1 else None
    return latest, second

        

# 取得昨日報價
def fetch_yesterday_prices(ydate: date) -> dict | None:
    dummy = {
        "日本": 700.0,
        "南韓": 702.5,
        "香港": 698.0,
        "新加坡": 699.0,
        "上海": 700.0,
        "舟山": 701.1,
        "CPC": 720.0
    }
    return dummy


# post 到 update
def post_to_update(payload: dict) -> bool:
    try:
        r = requests.post(API_URL, data=payload, timeout=15)
        r.raise_for_status()
        resp = r.json()
        logging.info("POST OK %s -> %s", payload["date"], resp.get("status"))
        return resp.get("status") in ("insert_success", "update_success")
    except Exception as e:
        logging.error("POST FAIL %s | %s", payload.get("date"), e)
        return False


def get_price_for_date(d: date) -> dict | None:
    sql = """
        SELECT [DATE], [NAME], [CLOSE]
          FROM dbo.MARKET_DATA
         WHERE [DATE] = %s AND [NAME] LIKE '%%MarineFuel%%'
    """

    with pymssql.connect(server=EIS_SERVER,
                         user=DB_USER,
                         password=DB_PASSWORD,
                         database=EIS_NAME) as conn:
        df = pd.read_sql(sql, conn, params=(d,))

    if df.empty:                         # 沒任何報價
        return None

    df = (df.pivot(index='DATE', columns='NAME', values='CLOSE')
            .sort_index(axis=1))

    # 映射原始 NAME → 中文欄
    name_map = {
        'MarineFuel_CPC'      : 'CPC',
        'MarineFuel_HongKong' : '香港',
        'MarineFuel_Japan'    : '日本',
        'MarineFuel_Shanghai' : '上海',
        'MarineFuel_Singapore': '新加坡',
        'MarineFuel_SouthKorea'    : '南韓',
        'MarineFuel_Zhoushan' : '舟山'
    }

    # 只對存在的欄位 rename
    exist_cols = {col: name_map[col] for col in df.columns if col in name_map}
    df = df.rename(columns=exist_cols)

    rec_raw = df.iloc[0].to_dict()       # e.g. 只有 {'CPC': 720}

    # 若 CPC 缺失視為假日
    if 'CPC' not in rec_raw or pd.isna(rec_raw['CPC']):
        return None

    # 建立完整欄位 dict，缺欄一律 None
    blank = {'CPC': None, '香港': None, '日本': None,
             '上海': None, '新加坡': None, '南韓': None, '舟山': None}
    for k, v in rec_raw.items():
        blank[k] = None if pd.isna(v) else float(v)

    return blank       

## TODO 
# def main():
#     latest_date, _ = get_latest_two_dates()
#     if latest_date is None:
#         logging.error("DB 無任何資料，結束")
#         return

#     today = date.today()

#     # ─── Step 0. 讀最新列，判斷欄位缺失狀態 ───
#     need_cpc = False
#     need_ports = False
#     with pymssql.connect(server=DB_SERVER, user=DB_USER,
#                          password=DB_PASSWORD, database=DB_NAME) as conn:
#         with conn.cursor(as_dict=True) as cur:
#             cur.execute("SELECT * FROM oil_prediction_shift WHERE 日期=%s", (latest_date,))
#             row_latest = cur.fetchone()
#             if row_latest is None:
#                 logging.error("找不到最新列？")
#                 return
#             need_cpc   = row_latest["CPC"] is None
#             # 只要六個港口有任何一個是 None，就視為需要補
#             need_ports = any(row_latest[col] is None
#                              for col in ("日本","南韓","香港","新加坡","上海","舟山"))

#     # ─── Step 1. 先補 CPC（若最新列缺 CPC） ───
#     if need_cpc:
#         cpc_day = latest_date + timedelta(days=1)
#         cpc_price = None
#         while cpc_day <= today:
#             tmp = get_price_for_date(cpc_day)
#             if tmp and tmp["CPC"] is not None:
#                 cpc_price = tmp["CPC"]
#                 break
#             cpc_day += timedelta(days=1)

#         if cpc_price is None:
#             logging.info("仍找不到 %s 之後的 CPC，等待下次排程", latest_date)
#             return

#         # 寫回「最新列」的 CPC
#         payload = {
#             "date": latest_date.strftime("%Y-%m-%d"),
#             "japan":"","korea":"","hongkong":"","singapore":"",
#             "shanghai":"","zhoushan":"",
#             "cpc": cpc_price
#         }
#         if post_to_update(payload):
#             logging.info("填補完成：%s 的 CPC = %.2f", latest_date, cpc_price)
#         return                 # 本輪只做一件事

#     # ─── Step 2. 若 CPC 已齊，去補下一天的六港口 ───
#     ports_day = latest_date + timedelta(days=1)
#     while ports_day < today:
#         ports_price = get_price_for_date(ports_day)
#         if ports_price is not None:
#             break
#         logging.info("%s 無六港口報價，跳過", ports_day)
#         ports_day += timedelta(days=1)

#     if ports_day >= today:
#         logging.info("今日之前沒有新的六港口資料")
#         return

#     payload = {
#         "date": ports_day.strftime("%Y-%m-%d"),
#         "japan": nz(ports_price["日本"]),
#         "korea": nz(ports_price["南韓"]),
#         "hongkong": nz(ports_price["香港"]),
#         "singapore": nz(ports_price["新加坡"]),
#         "shanghai": nz(ports_price["上海"]),
#         "zhoushan": nz(ports_price["舟山"]),
#         "cpc": ""
#     }

#     next_day_tukey = predict_next_day_tukey()
#     print("next day predcit", next_day_tukey)

#     # # 誤差指標寫入
#     # mae, mape, rmse = get_error_metrics()
#     # if mae is not None and mape is not None and rmse is not None:
#     #     save_error_metrics_to_db(ports_day, mae, mape, rmse)
#     #     print(f"[INFO] Update the day {ports_day}'s metrics: MAE={mae}, MAPE={mape}, RMSE={rmse}")
#     if post_to_update(payload):
#         logging.info("已寫入 %s 的六港口報價", ports_day)



def main():
    latest, _ = get_latest_two_dates()
    if latest is None:
        logging.error("DB 無任何資料，結束")
        return

    today = date.today()
    ports_day = latest + timedelta(days=1)

    # ---------- A. 找下一個有「六港口」資料的日期 ----------
    while ports_day < today:
        ports_price = get_price_for_date(ports_day)
        if ports_price is not None:
            break
        logging.info("%s 無六港口報價，跳過", ports_day)
        ports_day += timedelta(days=1)

    # 已追到今天還是沒有資料 → 結束
    if ports_day >= today:
        logging.info("無可補的六港口資料")
        return

    # ---------- B. 找之後第一個有 CPC 的日期 ----------
    cpc_day = ports_day + timedelta(days=1)
    cpc_price = None
    while cpc_day <= today:
        tmp = get_price_for_date(cpc_day)
        if tmp and tmp["CPC"] is not None:
            cpc_price = tmp["CPC"]
            break
        cpc_day += timedelta(days=1)

    # ---------- C. 先寫 ports_day 的六港口 ----------
    port_payload = {
        "date": ports_day.strftime("%Y-%m-%d"),
        "japan": nz(ports_price["日本"]),
        "korea": nz(ports_price["南韓"]),
        "hongkong": nz(ports_price["香港"]),
        "singapore": nz(ports_price["新加坡"]),
        "shanghai": nz(ports_price["上海"]),
        "zhoushan": nz(ports_price["舟山"]),
        "cpc": ""
    }
    if not post_to_update(port_payload):
        logging.error("六港口寫入失敗 %s，結束", ports_day)
        return
    logging.info("六港口已寫入 %s", ports_day)

    next_day_tukey = predict_next_day_tukey()
    print("next day predcit", next_day_tukey)

    # 誤差指標寫入
    mae, mape, rmse = get_error_metrics()
    if mae is not None and mape is not None and rmse is not None:
        save_error_metrics_to_db(ports_day, mae, mape, rmse)
        print(f"[INFO] Update the day {ports_day}'s metrics: MAE={mae}, MAPE={mape}, RMSE={rmse}")

    # ---------- D. 若找得到 CPC，再寫一次 ports_day 的 CPC ----------
    if cpc_price is None:
        logging.info("到 %s 仍無 CPC，可等待下次排程再補", today)
        return

    time.sleep(5)        # 等 Tukey 資料庫解鎖

    cpc_payload = {
        "date": ports_day.strftime("%Y-%m-%d"),   # 寫在 ports_day 那列
        "japan":"","korea":"","hongkong":"","singapore":"",
        "shanghai":"","zhoushan":"",
        "cpc": cpc_price
    }
    if post_to_update(cpc_payload):
        logging.info("CPC(%s) 已寫入 %s", cpc_day, ports_day)


if __name__ == "__main__":
    main()