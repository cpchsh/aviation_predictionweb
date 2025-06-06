import os, sys, json, requests, logging
from datetime import date, timedelta, datetime
import pymssql
from dotenv import load_dotenv; load_dotenv()
import time
import pandas as pd
from app.routes.tukey_routes import predict_next_day_tukey, update_ylag
# 自訂的 function, service
from app.services.db_service import get_error_metrics, save_error_metrics_to_db

DB_SERVER = os.getenv("DB_SERVER")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
EIS_SERVER = os.getenv("EIS_SERVER")
EIS_NAME = os.getenv("EIS_NAME")
WEBHOOK_URL = os.getenv("ALERT_WEBHOOK")

API_URL = "http://127.0.0.1:5000/update"
#API_URL = "http://10.168.230.33:5001/update"
LOG_FILE = "dailypushoil.log"

logging.basicConfig(filename=LOG_FILE,
                    level=logging.INFO,
                    format="%(asctime)s %(levelname)s | %(message)s")

# --- 載入假日 -----------------------------------------------------
holidays_dir = os.path.join(os.path.dirname(__file__), "data")

with open(os.path.join(holidays_dir, "holidays.sg.json"),  encoding="utf-8") as fp:
    SG_HOLIDAYS = {h["date"] for h in json.load(fp)}

with open(os.path.join(holidays_dir, "holidays.tw.json"),  encoding="utf-8") as fp:
    TW_HOLIDAYS = {h["date"] for h in json.load(fp)}

# --------------------------------------------------------------------

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
          FROM LSMF_Prediction
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


def update_ylag_for_latest(the_date: date):
    with pymssql.connect(server=DB_SERVER, user=DB_USER,
                         password=DB_PASSWORD, database=DB_NAME) as conn:
        with conn.cursor(as_dict=True) as cur:

            # 找 second_latest ↓↓↓
            cur.execute("""
               SELECT TOP 1 CPC, y_lag_1, y_lag_2
               FROM LSMF_Prediction
               WHERE 日期 < %s
               ORDER BY 日期 DESC
            """, (the_date,))
            row = cur.fetchone()
            if row is None or row["CPC"] is None:
                logging.warning("找不到 %s 之前可用的 CPC，ylag 不更新", the_date)
                return False

            cur.execute("""
               UPDATE LSMF_Prediction
                  SET y_lag_1 = %s,
                      y_lag_2 = %s,
                      y_lag_3 = %s
                WHERE 日期 = %s
            """, (row["CPC"], row["y_lag_1"], row["y_lag_2"], the_date))
            conn.commit()
            logging.info("已更新 %s 的 y-lag", the_date)
            return True

def notify_error(msg: str):
    """發 Teams webhook 告警"""
    if not WEBHOOK_URL:     
        logging.warning("Webhook URL 未設置，略過告警")
        return
    try:
        payload = {"text": msg.replace("\n", "<br>")}
        r = requests.post(WEBHOOK_URL,
                          headers={"Content-Type": "application/json"},
                          data=json.dumps(payload), timeout=5)
        r.raise_for_status()
    except Exception as e:
        logging.error("Webhook 發送失敗: %s", e)

def is_sg_holiday(d: date) -> bool:
    """d 為 date 物件，若是新加坡假日就回傳 True"""
    return d.isoformat() in SG_HOLIDAYS       

def is_tw_holiday(d: date) -> bool:
    """若為台灣國定假日回傳 True"""
    return d.isoformat() in TW_HOLIDAYS

# post 到 update
def post_to_update(payload: dict) -> bool:
    """
    送 POST 到 /update，並在三種情況觸發額外處理:
      1) 各港口更新成功 -> 呼叫預測
      2) CPC 更新成功   -> 更新 y-lag / 再預測 / 寫指標
      3) 後端回傳 update_check 或 error -> 發 Teams 警告
    """
    try:
        r = requests.post(API_URL, data=payload, timeout=15)
        r.raise_for_status()
        resp = r.json()

        ok = resp.get("status") in ("insert_success", "update_success")
        logging.info("POST OK %s -> %s - %s",
             payload["date"],
             resp.get("status"),
             resp.get("message"))       
        
        # ---- 回傳 update_check / error 立即警告 ------------
        status = resp.get("status", "")
        if status in {"update_check", "error"}:
            msg = (f"⚠️  LS Marine Fuel POST 回傳 {status}\n"
                   f"‣ 日期：{payload['date']}\n"
                   f"‣ 回應：{resp.get('message', '')}") 
            logging.warning(msg.replace("\n", " | "))
            notify_error(msg)
                

        # --- 判斷兩種情況 ---
        has_cpc = bool(payload.get("cpc"))
        has_any_port = any(payload.get(col)
                           for col in ("japan","korea","hongkong",
                                       "singapore","shanghai","zhoushan"))
        
        is_ports_update = (not has_cpc) and has_any_port
        is_cpc_update = has_cpc and (not has_any_port)

        # --- A.各港口更新 -> 預測 ---
        if ok and is_ports_update:
            pred = predict_next_day_tukey()
            if pred is not None:
                logging.info("Tukey 預測完成: %s -> %.2f",
                             pred[0], pred[1] if len(pred) > 1 else float("nan"))
            else:
                logging.warning("呼叫 Tukey 預測失敗或回傳 None")

        # --- B.CPC更新 -> 指標計算 ---
        if ok and is_cpc_update:
            # 1) y-lag 遞移
            if update_ylag_for_latest(datetime.strptime(payload["date"], "%Y-%m-%d").date()):
                logging.info("CPC 更新後已同步 y-lag")

            # 2) Tukey 預測（現在最新列完整了）
            pred = predict_next_day_tukey()
            if pred:
                logging.info("Tukey 預測完成: %s -> %.2f", pred[0], pred[1])

            # 3) 計算誤差指標
            mae, mape, rmse = get_error_metrics()
            if None not in (mae, mape, rmse):
                # payload["date"] 是 'YYYY-MM-DD' 字串 -> 轉成 date 物件
                dt = datetime.strptime(payload["date"], "%Y-%m-%d").date()
                save_error_metrics_to_db(dt, mae, mape, rmse)
                logging.info("Error metrics 寫入 : %s MAE=%.4f MAPE=%.2f RMSE=%.4f", dt, mae, mape, rmse)
            else:
                logging.warning("計算指標失敗")
        return ok
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

def main():
    latest_date, _ = get_latest_two_dates()
    if latest_date is None:
        logging.error("DB 無任何資料，結束")
        return

    today = date.today()

    # ─── Step 0. 讀最新列，判斷欄位缺失狀態 ───
    with pymssql.connect(server=DB_SERVER, user=DB_USER,
                         password=DB_PASSWORD, database=DB_NAME) as conn:
        with conn.cursor(as_dict=True) as cur:
            cur.execute("SELECT * FROM LSMF_Prediction WHERE 日期=%s", (latest_date,))
            row_latest = cur.fetchone()
            ## 取得前一資料日
            cur.execute("""SELECT TOP 1 * FROM LSMF_Prediction
                       WHERE 日期 < %s ORDER BY 日期 DESC""", (latest_date,))
            row_prev = cur.fetchone()

    if row_latest is None:
        logging.error("找不到最新列？")
        return
    need_cpc   = row_latest["CPC"] is None
    # 只要六個港口有任何一個是 None，就視為需要補
    need_ports = any(row_latest[col] is None
                    for col in ("日本","南韓","香港","新加坡","上海","舟山"))
    
    if (not need_cpc) and need_ports and (latest_date.isoformat() not in SG_HOLIDAYS):
        msg = (f"⚠️  LS Marine Fuel dailypushoil\n"
               f"‣ 日期：{latest_date}\n"
               f"‣ 異常：CPC 已匯入，但 6 港口仍為 None\n"
               f"‣ 動作：請人工確認行情或 API")            
        logging.warning(msg.replace("\n", " | "))
        notify_error(msg)

    # ─── Step 1. 先補 CPC（若最新列缺 CPC） ───
    if need_cpc:
        ### 若 TW 假日 & 非SG假日 -> 直接複製前一日CPC
        if is_tw_holiday(latest_date) and not is_sg_holiday(latest_date) and row_latest:
            payload = {
                "date": latest_date.strftime("%Y-%m-%d"),
                "japan":"","korea":"","hongkong":"","singapore":"",
                "shanghai":"","zhoushan":"",
                "cpc":nz(row_prev["CPC"])
            }
            if post_to_update(payload):
                logging.info("TW 假日，複製前一日 CPC 完成")
            return                         # 本輪結束

        cpc_day = latest_date + timedelta(days=1)
        cpc_price = None
        while cpc_day <= today:
            if is_sg_holiday(cpc_day):
                cpc_day += timedelta(days=1)
                continue
            tmp = get_price_for_date(cpc_day)
            if tmp and tmp["CPC"] is not None:
                cpc_price = tmp["CPC"]
                break
            cpc_day += timedelta(days=1)

        if cpc_price is None:
            logging.info("仍找不到 %s 之後的 CPC，等待下次排程", latest_date)
            return

        # 寫回「最新列」的 CPC
        payload = {
            "date": latest_date.strftime("%Y-%m-%d"),
            "japan":"","korea":"","hongkong":"","singapore":"",
            "shanghai":"","zhoushan":"",
            "cpc": cpc_price
        }
        if post_to_update(payload):
            logging.info("填補完成：%s 的 CPC = %.2f", latest_date, cpc_price)
        return                 # 本輪只做一件事

    # ─── Step 2. 若 CPC 已齊，去補下一天的六港口 ───
    ports_day = latest_date if need_ports else latest_date + timedelta(days=1)
    while ports_day < today:

        ### 若 SG 假日 % 非 TW 假日，直接複製前一日六港口
        if is_sg_holiday(ports_day) and not is_tw_holiday(ports_day):
            if row_latest:
                payload = {
                    "date": ports_day.strftime("%Y-%m-%d"),
                    "japan": nz(row_latest["日本"]),
                    "korea": nz(row_latest["南韓"]),
                    "hongkong": nz(row_latest["香港"]),
                    "singapore": nz(row_latest["新加坡"]),
                    "shanghai": nz(row_latest["上海"]),
                    "zhoushan": nz(row_latest["舟山"]),
                    "cpc": ""
                }
                if post_to_update(payload):
                    logging.info("SG 假日，複製前一日六港口完成")
                return
            # 若意外沒有 row_prev 資料 -> 視同無報價，往後找
            ports_day += timedelta(days = 1)
            continue

        # 兩國同休:直接跳過
        if is_sg_holiday(ports_day) and is_tw_holiday(ports_day):
            logging.info("%s 兩國同休，跳過",ports_day)
            ports_day += timedelta(days=1)
            continue

        ports_price = get_price_for_date(ports_day)
        if ports_price is not None:
            break
        logging.info("%s 無六港口報價，跳過", ports_day)
        ports_day += timedelta(days=1)

    if ports_day >= today:
        logging.info("今日之前沒有新的六港口資料")
        return

    payload = {
        "date": ports_day.strftime("%Y-%m-%d"),
        "japan": nz(ports_price["日本"]),
        "korea": nz(ports_price["南韓"]),
        "hongkong": nz(ports_price["香港"]),
        "singapore": nz(ports_price["新加坡"]),
        "shanghai": nz(ports_price["上海"]),
        "zhoushan": nz(ports_price["舟山"]),
        "cpc": ""
    }

    # next_day_tukey = predict_next_day_tukey()
    # print("next day predcit", next_day_tukey)

    # # 誤差指標寫入
    # mae, mape, rmse = get_error_metrics()
    # if mae is not None and mape is not None and rmse is not None:
    #     save_error_metrics_to_db(ports_day, mae, mape, rmse)
    #     print(f"[INFO] Update the day {ports_day}'s metrics: MAE={mae}, MAPE={mape}, RMSE={rmse}")
    if post_to_update(payload):
        logging.info("已寫入 %s 的六港口報價", ports_day)






if __name__ == "__main__":
    main()