# app/services/db_service.py
import os
import pymssql
from dotenv import load_dotenv

load_dotenv()  # 若已在其他地方 load 也可以省略
DB_SERVER   = os.getenv("DB_SERVER")
DB_USER     = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME     = os.getenv("DB_NAME")

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
