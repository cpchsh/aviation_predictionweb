from flask import Blueprint, jsonify, request
import pymssql
import os
from dotenv import load_dotenv
from datetime import date, datetime, timedelta

api_bp = Blueprint("api_bp", __name__)

load_dotenv()
DB_SERVER = os.getenv("DB_SERVER")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

# @api_bp.route("/api/historical_data", methods=["GET"])
# def get_historical_data():
#     """
#     從資料庫撈歷史資料(例如全部或部分欄位)並以JSON回傳
#     """
#     conn = pymssql.connect(server=DB_SERVER, user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
#     cursor = conn.cursor(as_dict=True)

#     try:
#         query = """
#             SELECT 日期 AS ds, CPC AS y, PredictedCPC AS y_pred
#             FROM oooiiilll_new
#             ORDER BY 日期
#         """
#         cursor.execute(query)
#         rows = cursor.fetchall() # list of dict, 每筆資料是個 dict

#         # 轉換日期格式
#         for row in rows:
#             if isinstance(row["ds"], (datetime,date)):
#                 row["ds"] = row["ds"].strftime("%Y-%m-%d")

#         # 直接以 JSON 格式回傳
#         return jsonify(rows)
#     except Exception as e:
#         print("get_historical_data 發生錯誤:", e)
#         # 可回傳錯誤訊息或空資料
#         return jsonify({"error" : str(e)}), 500
#     finally:
#         cursor.close()
#         conn.close()

@api_bp.route("/api/historical_data", methods=["GET"])
def get_historical_data():
    """
    從資料庫撈歷史資料，並將 y, y_pred 用「上一筆」的資料覆蓋，
    若是第一筆(沒有上一筆)，就補 0
    """
    conn = pymssql.connect(server=DB_SERVER, user=DB_USER, 
                           password=DB_PASSWORD, database=DB_NAME)
    cursor = conn.cursor(as_dict=True)
    try:
        # query = """
        #     SELECT 日期 AS ds, CPC AS y, PredictedCPC AS y_pred
        #     FROM oooiiilll
        #     ORDER BY 日期
        # """
        query = """
            SELECT 
                日期 AS ds,
                CPC AS y,
                predictCPC AS y_pred
            FROM LSMF_Prediction

            ORDER BY 日期
        """
        cursor.execute(query)
        rows = cursor.fetchall()  # list of dict

        # 1) 轉換日期格式 (原程式流程)
        for row in rows:
            if isinstance(row["ds"], (datetime, date)):
                row["ds"] = row["ds"].strftime("%Y-%m-%d")

        # 2) 在 Python 端做「往下位移一格」的轉換
        #    create a new list, or 直接原地修改
        prev_y = 0
        prev_y_pred = 0

        for i, row in enumerate(rows):
            # 用 temp 暫存當前的 y, y_pred
            current_y = row["y"]
            current_y_pred = row["y_pred"]

            if i == 0:
                # 第一筆 => 沒有上一筆 => 全補None
                row["y"] = None
                row["y_pred"] = None
            else:
                # 其餘 => 用上一筆的 y, y_pred
                row["y"] = prev_y
                row["y_pred"] = prev_y_pred

            # 更新 prev_xxx 為當前原始值 (給下一筆使用)
            prev_y = current_y
            prev_y_pred = current_y_pred

        # rows 內容就已經完成「位移」，第一筆=0, 之後每筆 = 上一筆的原值

        return jsonify(rows)
    except Exception as e:
        print("get_historical_data 錯誤:", e)
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@api_bp.route("/api/historical_alldata", methods=["GET"])
def get_historical_alldata():
    """
    從資料庫撈歷史資料，並將 y, y_pred 用「上一筆」的資料覆蓋，
    若是第一筆(沒有上一筆)，就補 0
    """
    conn = pymssql.connect(server=DB_SERVER, user=DB_USER, 
                           password=DB_PASSWORD, database=DB_NAME)
    cursor = conn.cursor(as_dict=True)
    try:
        # query = """
        #     SELECT 日期 AS ds, CPC AS y, PredictedCPC AS y_pred
        #     FROM oooiiilll
        #     ORDER BY 日期
        # """
        query = """
            SELECT 
                日期 AS ds,
				日本 AS japan,
				南韓 AS korea,
				香港 AS hongkong,
				新加坡 AS singapore,
				上海 AS shanghai,
				舟山 AS zhoushan,
                CPC AS y,
                predictCPC AS y_pred
            FROM LSMF_Prediction

            ORDER BY 日期
        """
        cursor.execute(query)
        rows = cursor.fetchall()  # list of dict

        # 1) 轉換日期格式 (原程式流程)
        for row in rows:
            if isinstance(row["ds"], (datetime, date)):
                row["ds"] = row["ds"].strftime("%Y-%m-%d")

        # 2) 在 Python 端做「往下位移一格」的轉換
        #    create a new list, or 直接原地修改
        prev_y = 0
        prev_y_pred = 0

        for i, row in enumerate(rows):
            # 用 temp 暫存當前的 y, y_pred
            current_y = row["y"]
            current_y_pred = row["y_pred"]

            if i == 0:
                # 第一筆 => 沒有上一筆 => 全補None
                row["y"] = None
                row["y_pred"] = None
            else:
                # 其餘 => 用上一筆的 y, y_pred
                row["y"] = prev_y
                row["y_pred"] = prev_y_pred

            # 更新 prev_xxx 為當前原始值 (給下一筆使用)
            prev_y = current_y
            prev_y_pred = current_y_pred

        # rows 內容就已經完成「位移」，第一筆=0, 之後每筆 = 上一筆的原值

        return jsonify(rows)
    except Exception as e:
        print("get_historical_data 錯誤:", e)
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@api_bp.route("/api/metrics_data", methods=["GET"])
def get_metrics_data():
    """
    從資料表 LSMF_Prediction 撈出 timestamp, MAE, MAPE, 並以 JSON 格式返回
    讓前端 chart.js 可直接使用
    """
    conn = pymssql.connect(server=DB_SERVER, user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
    cursor = conn.cursor(as_dict=True)

    try:
        query = """
            SELECT 日期 AS ds, mae, mape, rmse
            FROM LSMF_Prediction
            WHERE rmse IS NOT NULL
            ORDER BY 日期
        """
        cursor.execute(query)
        rows = cursor.fetchall() # list of dict, 每筆資料是個 dict

        results = []
        # 轉換日期格式
        for row in rows:
            # 1) 取得原本的timestamp
            ts = row["ds"]
            mae_val = row["mae"]
            mape_val = row["mape"]
            rmse_val = row["rmse"]

            # 2) 若 ts 是 datetime, 轉成字串
            if isinstance(ts, (datetime, date)):
                ts_str = ts.strftime("%Y-%m-%d")
            else:
                ts_str = str(ts)

            # 3) 建立要返回給前端的欄位(例如 "ds" = time, "mae", "mape")
            results.append({
                "ds": ts_str,
                "mae": float(mae_val) if mae_val is not None else None,
                "mape": float(mape_val) if mape_val is not None else None,
                "rmse": float(rmse_val) if rmse_val is not None else None
            })

        # 直接以 JSON 格式回傳
        return jsonify(results)
    except Exception as e:
        print("get_metrics_data 發生錯誤:", e)
        # 可回傳錯誤訊息或空資料
        return jsonify({"error" : str(e)}), 500
    finally:
        cursor.close()
        conn.close()

# @api_bp.route("/api/latest_log_time", methods=["GET"])
# def get_latest_log_time():
#     """
#     讀取 /xgb_models/training_log.txt 中最新一筆的 log 時間，
#     轉換為本地時間 (UTC+8)，格式化為 "YYYY-MM-DD HH:MM"，並以 JSON 回傳。
#     """
#     #本地測試用
#     #log_file_path = "./xgb_models/training_log.txt"  
#     log_file_path = "/shared_volume/training_log.txt"# 調整此路徑，確保與容器內掛載的路徑一致
#     try:
#         with open(log_file_path, "r", encoding="utf-8") as f:
#             lines = f.readlines()
#         # 從所有行中找出以 '[' 開頭的 log 時間行
#         timestamps = []
#         for line in lines:
#             line = line.strip()
#             if line.startswith("[") and "]" in line:
#                 ts_str = line.split("]")[0].lstrip("[")
#                 # 依照 log 格式解析 (例如 "%Y%m%d%H%M%S")
#                 try:
#                     dt = datetime.strptime(ts_str, "%Y%m%d%H%M%S")
#                     timestamps.append(dt)
#                 except Exception as e:
#                     # 解析失敗則忽略
#                     print(f"解析時間 {ts_str} 失敗: {e}")
#         if timestamps:
#             # 取最新的 log 時間
#             latest_ts = max(timestamps)
#             # 假設 log 時間是 UTC，轉換到本地 (UTC+8)
#             latest_ts_local = latest_ts + timedelta(hours=8)
#             # 格式化時間 (僅到分鐘)
#             display_str = latest_ts_local.strftime("%Y-%m-%d %H:%M")
#         else:
#             display_str = None

#         return jsonify({"latest_log_time": display_str})
#     except Exception as e:
#         print("讀取最新 log 時間發生錯誤:", e)
#         return jsonify({"error": str(e)}), 500


@api_bp.route("/api/historical_backenddata", methods=["GET"])
def get_historical_backenddata_html():
    """
    查最近7日，不做 shift，以表格HTML回傳
    """
    conn = pymssql.connect(server=DB_SERVER, user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
    cursor = conn.cursor(as_dict=True)
    try:
        query = """
            SELECT TOP 7
                日期 AS ds,
                日本 AS japan,
                南韓 AS korea,
                香港 AS hongkong,
                新加坡 AS singapore,
                上海 AS shanghai,
                舟山 AS zhoushan,
                CPC,
                PredictedCPC
            FROM oooiiilll_new
            ORDER BY 日期 DESC
        """
        cursor.execute(query)
        rows = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    # 做HTML表
    html = "<table border='1'>"
    html += "<tr><th>日期</th><th>日本</th><th>南韓</th><th>香港</th><th>新加坡</th><th>上海</th><th>舟山</th><th>CPC</th><th>PredictedCPC</th></tr>"
    for r in rows:
        ds_str = r["ds"].strftime("%Y-%m-%d") if isinstance(r["ds"], datetime) else str(r["ds"])
        japan_val = r["japan"] if r["japan"] else ""
        korea_val = r["korea"] if r["korea"] else ""
        hongkong_val = r["hongkong"] if r["hongkong"] else ""
        singapore_val = r["singapore"] if r["singapore"] else ""
        shanghai_val = r["shanghai"] if r["shanghai"] else ""
        zhoushan_val = r["zhoushan"] if r["zhoushan"] else ""
        cpc_val = r["CPC"] if r["CPC"] else ""
        pred_val = r["PredictedCPC"] if r["PredictedCPC"] else ""
        html += f"<tr><td>{ds_str}</td><td>{japan_val}</td><td>{korea_val}</td><td>{hongkong_val}</td><td>{singapore_val}</td><td>{shanghai_val}</td><td>{zhoushan_val}</td><td>{cpc_val}</td><td>{pred_val}</td></tr>"
    html += "</table>"

    return html