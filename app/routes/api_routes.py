from flask import Blueprint, jsonify, request
import pymssql
import os
from dotenv import load_dotenv
from datetime import date, datetime

api_bp = Blueprint("api_bp", __name__)

load_dotenv()
DB_SERVER = os.getenv("DB_SERVER")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

@api_bp.route("/api/historical_data", methods=["GET"])
def get_historical_data():
    """
    從資料庫撈歷史資料(例如全部或部分欄位)並以JSON回傳
    """
    conn = pymssql.connect(server=DB_SERVER, user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
    cursor = conn.cursor(as_dict=True)

    try:
        query = """
            SELECT 日期 AS ds, CPC AS y, PredictedCPC AS y_pred
            FROM oooiiilll
            ORDER BY 日期
        """
        cursor.execute(query)
        rows = cursor.fetchall() # list of dict, 每筆資料是個 dict

        # 轉換日期格式
        for row in rows:
            if isinstance(row["ds"], (datetime,date)):
                row["ds"] = row["ds"].strftime("%Y-%m-%d")

        # 直接以 JSON 格式回傳
        return jsonify(rows)
    except Exception as e:
        print("get_historical_data 發生錯誤:", e)
        # 可回傳錯誤訊息或空資料
        return jsonify({"error" : str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@api_bp.route("/api/metrics_data", methods=["GET"])
def get_metrics_data():
    """
    從資料表 oooiiilll_metrics 撈出 timestamp, MAE, MAPE, 並以 JSON 格式返回
    讓前端 chart.js 可直接使用
    """
    conn = pymssql.connect(server=DB_SERVER, user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
    cursor = conn.cursor(as_dict=True)

    try:
        query = """
            SELECT timestamp, MAE, MAPE, RMSE
            FROM oooiiilll_metrics
            ORDER BY timestamp
        """
        cursor.execute(query)
        rows = cursor.fetchall() # list of dict, 每筆資料是個 dict

        results = []
        # 轉換日期格式
        for row in rows:
            # 1) 取得原本的timestamp
            ts = row["timestamp"]
            mae_val = row["MAE"]
            mape_val = row["MAPE"]
            rmse_val = row["RMSE"]

            # 2) 若 ts 是 datetime, 轉成字串
            if isinstance(ts, (datetime, date)):
                ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")
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
        return jsonify(rows)
    except Exception as e:
        print("get_metrics_data 發生錯誤:", e)
        # 可回傳錯誤訊息或空資料
        return jsonify({"error" : str(e)}), 500
    finally:
        cursor.close()
        conn.close()