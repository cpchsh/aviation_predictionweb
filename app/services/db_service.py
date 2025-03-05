# app/services/db_service.py
import os
import pymssql
from dotenv import load_dotenv
import joblib

load_dotenv()  # 若已在其他地方 load 也可以省略
DB_SERVER   = os.getenv("DB_SERVER")
DB_USER     = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME     = os.getenv("DB_NAME")

xgb_model_path = "./xgb_model_processed0304.pkl"
xgb_model = joblib.load(xgb_model_path)

def get_recent_7_records(filter_date=None):
    """
    查詢「最新 7 筆」或「指定日期(含當天) 前 7 筆」的紀錄 (依日期DESC)
    回傳 list of dict
    """
    conn = pymssql.connect(server=DB_SERVER, user=DB_USER, 
                           password=DB_PASSWORD, database=DB_NAME)
    cursor = conn.cursor(as_dict=True)
    try:
        if filter_date:
            query = """
                SELECT TOP 7
                    日期, 日本, 南韓, 香港, 新加坡, 上海, 舟山,
                    CPC, PredictedCPC, is_final_cpc
                FROM oooiiilll
                WHERE 日期 <= %s
                ORDER BY 日期 DESC
            """
            cursor.execute(query, (filter_date,))
        else:
            query = """
                SELECT TOP 7
                    日期, 日本, 南韓, 香港, 新加坡, 上海, 舟山,
                    CPC, PredictedCPC, is_final_cpc
                FROM oooiiilll
                ORDER BY 日期 DESC
            """
            cursor.execute(query)

        rows = cursor.fetchall()  # list of dict
        return rows
    finally:
        cursor.close()
        conn.close()

def get_error_metrics():
    """
    從資料表 oooiiilll 中撈出 CPC, PredictedCPC 不為 NULL 的紀錄，
    計算 MAE, MAPE 並回傳 (mae, mape)，皆為 float 或 None
    """
    conn = pymssql.connect(server=DB_SERVER, user=DB_USER,
                           password=DB_PASSWORD, database=DB_NAME)
    cursor = conn.cursor(as_dict=True)
    try:
        sql = """
              SELECT CPC, PredictedCPC
              FROM oooiiilll
              WHERE CPC IS NOT NULL
              AND PredictedCPC IS NOT NULL  
        """
        cursor.execute(sql)
        rows = cursor.fetchall()
        if not rows:
            print("[INFO] 沒有任何 CPC, PredcitedCPC 同時存在的資料，無法計算誤差")
            return None, None
        
        abs_errors = []
        abs_pct_errors = []
        for row in rows:
            actual = row["CPC"]
            pred = row["PredictedCPC"]
            if actual is None or pred is None:
                continue
            if actual == 0:
                # 避免除以 0 => 這筆就略過或做其他處理
                continue

            ae = abs(actual - pred) # absolute error
            ape = ae / actual * 100 # absolute percentage error

            abs_errors.append(ae)
            abs_pct_errors.append(ape)
        if not abs_errors:
            return None, None
        
        mae = sum(abs_errors) / len(abs_errors)
        mape = sum(abs_pct_errors) / len(abs_pct_errors)

        return mae, mape
    except Exception as e:
        print("get_error_metrics發生錯誤", e)
        return None, None
    
    finally:
        cursor.close()
        conn.close()
