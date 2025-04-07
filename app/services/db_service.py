# app/services/db_service.py
import os
import pymssql
from dotenv import load_dotenv
import joblib
import math
from datetime import date

load_dotenv()  # 若已在其他地方 load 也可以省略
DB_SERVER   = os.getenv("DB_SERVER")
DB_USER     = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME     = os.getenv("DB_NAME")

xgb_model_path = "./xgb_models/xgb_model.pkl"
xgb_model = joblib.load(xgb_model_path)

# def get_recent_7_records(filter_date=None):
#     """
#     查詢「最新 7 筆」或「指定日期(含當天) 前 7 筆」的紀錄 (依日期DESC)
#     - 港口數據往前錯位一行
#     - CPC、PredictedCPC、is_final_cpc 維持不變
#     - 資料庫最新日期的港口數據為 NULL
#     回傳 list of dict
#     """
#     conn = pymssql.connect(server=DB_SERVER, user=DB_USER, 
#                            password=DB_PASSWORD, database=DB_NAME)
#     cursor = conn.cursor(as_dict=True)
    
#     try:
#         query = """
#             WITH latest_date AS (
#                 SELECT MAX(日期) AS max_date FROM oooiiilll_new
#             ),
#             shifted_data AS (
#                 SELECT 
#                     日期,
#                     LAG(日本) OVER (ORDER BY 日期 DESC) AS 日本,
#                     LAG(南韓) OVER (ORDER BY 日期 DESC) AS 南韓,
#                     LAG(香港) OVER (ORDER BY 日期 DESC) AS 香港,
#                     LAG(新加坡) OVER (ORDER BY 日期 DESC) AS 新加坡,
#                     LAG(上海) OVER (ORDER BY 日期 DESC) AS 上海,
#                     LAG(舟山) OVER (ORDER BY 日期 DESC) AS 舟山,
#                     CPC,
#                     PredictedCPC,
#                     is_final_cpc
#                 FROM oooiiilll_new
#             )
#             SELECT TOP 7
#                 sd.日期,
#                 CASE WHEN sd.日期 = ld.max_date THEN NULL ELSE sd.日本 END AS 日本,
#                 CASE WHEN sd.日期 = ld.max_date THEN NULL ELSE sd.南韓 END AS 南韓,
#                 CASE WHEN sd.日期 = ld.max_date THEN NULL ELSE sd.香港 END AS 香港,
#                 CASE WHEN sd.日期 = ld.max_date THEN NULL ELSE sd.新加坡 END AS 新加坡,
#                 CASE WHEN sd.日期 = ld.max_date THEN NULL ELSE sd.上海 END AS 上海,
#                 CASE WHEN sd.日期 = ld.max_date THEN NULL ELSE sd.舟山 END AS 舟山,
#                 sd.CPC,
#                 sd.PredictedCPC,
#                 sd.is_final_cpc
#             FROM shifted_data sd
#             CROSS JOIN latest_date ld
#         """

#         if filter_date:
#             query += " WHERE sd.日期 <= %s"
#             query += " ORDER BY sd.日期 DESC;"
#             cursor.execute(query, (filter_date,))
#         else:
#             query += " ORDER BY sd.日期 DESC;"
#             cursor.execute(query)

#         rows = cursor.fetchall()  # list of dict
#         return rows
#     finally:
#         cursor.close()
#         conn.close()


# def get_recent_7_records(filter_date=None):
#     """
#     查詢「最新 7 筆」或「指定日期(含當天) 前 7 筆」的紀錄 (依日期 DESC)
#     - 第 1 筆：今日日期(ports=Null)，CPC/PredictedCPC/is_final_cpc=原始最新那筆的值
#     - 後續(7筆)：保留自己港口，CPC等 3 欄位用 LEAD(下一筆)
#     - 最後共 8 筆
#     """
#     conn = pymssql.connect(DB_SERVER, DB_USER, DB_PASSWORD, DB_NAME)
#     cursor = conn.cursor(as_dict=True)

#     try:
#         query = """
#             WITH cte AS (
#                 SELECT
#                     ROW_NUMBER() OVER (ORDER BY 日期 DESC) AS rn,
#                     日期,
#                     [日本],
#                     [南韓],
#                     [香港],
#                     [新加坡],
#                     [上海],
#                     [舟山],
#                     LEAD(CPC) OVER (ORDER BY 日期 DESC) AS next_CPC,
#                     LEAD(PredictedCPC) OVER (ORDER BY 日期 DESC) AS next_PredictedCPC,
#                     LEAD(is_final_cpc) OVER (ORDER BY 日期 DESC) AS next_is_final_cpc,
#                     CPC,
#                     PredictedCPC,
#                     is_final_cpc
#                 FROM oooiiilll_new
#         """

#         # 有日期篩選時加
#         if filter_date:
#             query += " WHERE 日期 <= %s "

#         query += """
#             )
#             SELECT
#                 sort_order,
#                 rn,
#                 日期,
#                 [日本],
#                 [南韓],
#                 [香港],
#                 [新加坡],
#                 [上海],
#                 [舟山],
#                 CPC,
#                 PredictedCPC,
#                 is_final_cpc
#             FROM
#             (
#                 SELECT
#                     0 AS sort_order,
#                     0 AS rn,
#                     CONVERT(date, GETDATE()) AS 日期,
#                     NULL AS [日本],
#                     NULL AS [南韓],
#                     NULL AS [香港],
#                     NULL AS [新加坡],
#                     NULL AS [上海],
#                     NULL AS [舟山],
#                     (SELECT TOP 1 c2.CPC
#                      FROM cte c2
#                      WHERE c2.rn=1) AS CPC,
#                     (SELECT TOP 1 c2.PredictedCPC
#                      FROM cte c2
#                      WHERE c2.rn=1) AS PredictedCPC,
#                     (SELECT TOP 1 c2.is_final_cpc
#                      FROM cte c2
#                      WHERE c2.rn=1) AS is_final_cpc

#                 UNION ALL

#                 SELECT
#                     1 AS sort_order,
#                     c.rn,
#                     c.日期,
#                     c.[日本],
#                     c.[南韓],
#                     c.[香港],
#                     c.[新加坡],
#                     c.[上海],
#                     c.[舟山],
#                     COALESCE(c.next_CPC, c.CPC) AS CPC,
#                     COALESCE(c.next_PredictedCPC, c.PredictedCPC) AS PredictedCPC,
#                     COALESCE(c.next_is_final_cpc, c.is_final_cpc) AS is_final_cpc
#                 FROM cte c
#                 WHERE c.rn <= 7
#             ) AS unioned
#             ORDER BY sort_order, rn;
#         """

#         if filter_date:
#             cursor.execute(query, (filter_date,))
#         else:
#             cursor.execute(query)

#         rows = cursor.fetchall()
#         return rows

#     finally:
#         cursor.close()
#         conn.close()

def get_recent_7_records(filter_date=None):
    """
    查詢「最新 7 筆」或「指定日期(含當天) 前 7 筆」的紀錄 (依日期 DESC)
    - 第 1 筆：今日日期(ports=Null)，CPC/PredictedCPC/is_final_cpc=原始最新那筆的值
    - 後續(7筆)：保留自己港口，CPC等 3 欄位用 LEAD(下一筆)
    - 最後共 8 筆
    """
    conn = pymssql.connect(DB_SERVER, DB_USER, DB_PASSWORD, DB_NAME)
    cursor = conn.cursor(as_dict=True)

    try:
        query = """
            WITH cte AS (
                SELECT
                    ROW_NUMBER() OVER (ORDER BY 日期 DESC) AS rn,
                    日期,
                    [日本],
                    [南韓],
                    [香港],
                    [新加坡],
                    [上海],
                    [舟山],
                    LEAD(CPC) OVER (ORDER BY 日期 DESC) AS next_CPC,
                    LEAD(PredictedCPC) OVER (ORDER BY 日期 DESC) AS next_PredictedCPC,
                    CPC,
                    PredictedCPC,
                    is_final_cpc
                FROM oooiiilll_new
        """

        # 有日期篩選時加
        if filter_date:
            query += " WHERE 日期 <= %s "

        query += """
            )
            SELECT
                sort_order,
                rn,
                日期,
                [日本],
                [南韓],
                [香港],
                [新加坡],
                [上海],
                [舟山],
                CPC,
                PredictedCPC,
                is_final_cpc
            FROM
            (
                SELECT
                    0 AS sort_order,
                    0 AS rn,
                    CONVERT(date, GETDATE()) AS 日期,
                    NULL AS [日本],
                    NULL AS [南韓],
                    NULL AS [香港],
                    NULL AS [新加坡],
                    NULL AS [上海],
                    NULL AS [舟山],
                    NULL AS [CPC],
                    (SELECT TOP 1 c2.PredictedCPC
                     FROM cte c2
                     WHERE c2.rn=1) AS PredictedCPC,
                    (SELECT TOP 1 c2.is_final_cpc
                     FROM cte c2
                     WHERE c2.rn=1) AS is_final_cpc

                UNION ALL

                SELECT
                    1 AS sort_order,
                    c.rn,
                    c.日期,
                    c.[日本],
                    c.[南韓],
                    c.[香港],
                    c.[新加坡],
                    c.[上海],
                    c.[舟山],
                    COALESCE(c.next_CPC, c.CPC) AS CPC,
                    COALESCE(c.next_PredictedCPC, c.PredictedCPC) AS PredictedCPC,
                    c.[is_final_cpc]
                FROM cte c
                WHERE c.rn <= 7
            ) AS unioned
            ORDER BY sort_order, rn;
        """

        if filter_date:
            cursor.execute(query, (filter_date,))
        else:
            cursor.execute(query)

        rows = cursor.fetchall()
        return rows

    finally:
        cursor.close()
        conn.close()


def get_error_metrics():
    """
    從資料表 oooiiilll_new 中撈出 CPC, PredictedCPC 不為 NULL 的紀錄，
    計算 MAE, MAPE, RMSE 並回傳 (mae, mape, rmse)，皆為 float 或 None
    """
    conn = pymssql.connect(server=DB_SERVER, user=DB_USER,
                           password=DB_PASSWORD, database=DB_NAME)
    cursor = conn.cursor(as_dict=True)
    try:
        sql = """
              SELECT CPC, PredictedCPC
              FROM oooiiilll_new
              WHERE CPC IS NOT NULL
              AND PredictedCPC IS NOT NULL  
        """
        cursor.execute(sql)
        rows = cursor.fetchall()
        if not rows:
            print("[INFO] 沒有任何 CPC, PredictedCPC 同時存在的資料，無法計算誤差")
            return None, None, None
        
        abs_errors = []
        abs_pct_errors = []
        squared_errors = []
        
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
            se = (actual - pred) ** 2 # squared error

            abs_errors.append(ae)
            abs_pct_errors.append(ape)
            squared_errors.append(se)
        
        if not abs_errors:
            return None, None, None
        
        mae = sum(abs_errors) / len(abs_errors)
        mape = sum(abs_pct_errors) / len(abs_pct_errors)
        rmse = math.sqrt(sum(squared_errors) / len(squared_errors))

        return mae, mape, rmse
    except Exception as e:
        print("get_error_metrics 發生錯誤", e)
        return None, None, None
    
    finally:
        cursor.close()
        conn.close()


def save_error_metrics_to_db(mae, mape, rmse):
    """
    將 mae, mape, rmse 寫入資料表 oooiiilll_newmetrics
      欄位: timestamp(datetime), MAE(float), MAPE(float), RMSE(float)
    使用 GETDATE() 取得資料庫當下時間
    """
    conn = pymssql.connect(server=DB_SERVER, user=DB_USER,
                           password=DB_PASSWORD, database=DB_NAME)
    cursor = conn.cursor()
    try:
        sql = """
          INSERT INTO oooiiilll_newmetrics ([timestamp], [MAE], [MAPE], [RMSE])
          VALUES (GETDATE(), %s, %s, %s)
        """
        cursor.execute(sql, (mae, mape, rmse))
        conn.commit()
        print(f"[INFO] 已插入 oooiiilll_newmetrics: MAE={mae}, MAPE={mape}, RMSE={rmse}")
    except Exception as e:
        print("save_error_metrics_to_db 錯誤:", e)
    finally:
        cursor.close()
        conn.close()


def get_db_max_date():
    """
    從資料表 oooiiilll 中撈出 最大資料庫日期紀錄，
    """
    conn = pymssql.connect(server=DB_SERVER, user=DB_USER,password=DB_PASSWORD, database=DB_NAME)
    cursor = conn.cursor()
    try:
        # 查詢資料表中最大的日期
        cursor.execute("SELECT MAX(日期) FROM oooiiilll_new")
        row = cursor.fetchone()
        db_max_date = row[0]  # 例如 2023-11-08 00:00:00

        # 將 datetime 轉成 YYYY-MM-DD 字串，以便套用在前端
        if db_max_date:
            max_date_str = db_max_date.strftime("%Y-%m-%d")
        else:
            # 若資料表沒資料，就給個預設吧，例如今天
            max_date_str = date.today().strftime("%Y-%m-%d")
        return max_date_str
    except Exception as e:
        print("取得資料庫最大日期錯誤:", e)
        # 若有錯，就給個預設
        max_date_str = date.today().strftime("%Y-%m-%d")
        return max_date_str
    
    finally:
        cursor.close()
        conn.close()


def fetch_is_final(db_date):
    try:
        with pymssql.connect(server=DB_SERVER, user=DB_USER, password=DB_PASSWORD, database=DB_NAME) as conn:
            with conn.cursor(as_dict=True) as cur:
                cur.execute("""
                    SELECT is_final_cpc
                    FROM oooiiilll_new
                    WHERE 日期 = %s
                """, (db_date,))
                row = cur.fetchone()
                return bool(row and row["is_final_cpc"])
    except Exception as e:
        print("[ERR] fetch_is_final:", e)
        return None