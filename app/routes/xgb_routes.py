# xgb_routes.py
from flask import Blueprint, render_template, request, redirect, jsonify
import pandas as pd
import os
import pymssql
import joblib
from datetime import date, datetime
from dotenv import load_dotenv

xgb_bp = Blueprint('xgb_bp', __name__)

# 載入環境變數
load_dotenv()
server = os.getenv("DB_SERVER")
user = os.getenv("DB_USER")
password = os.getenv("DB_PASSWORD")
database = os.getenv("DB_NAME")


# 載入 XGBoost 模型 (全域)
xgb_model_path = "./xgb_model_processed0304.pkl"
xgb_model = joblib.load(xgb_model_path)

def update_ylag_for_latest(cursor, conn, latest_date):
    """
    將 "latest_date"這筆資料的 y_lag_1, y_lag_2, y_lag_3
    更新成 「second_latest」的CPC, y_lag_1, y_lag_2
    """
    # 查「比latest_date小的最近一筆」 => second_Latest
    query_sec = """
        SELECT TOP 1
             日期, CPC, y_lag_1, y_lag_2, y_lag_3
        FROM oooiiilll
        WHERE 日期 < %s
        ORDER BY 日期 DESC
    """
    cursor.execute(query_sec, (latest_date,))
    row_sec = cursor.fetchone()
    if not row_sec:
        print(f"無法找到 second_latest(比{latest_date} 更舊的紀錄)，無法更新y_lag")
        return

    # 用 second_latest.CPC => y_lag_1, second_latest.y_lag_1 => y_lag_2...
    sql_update_lag = """
        UPDATE oooiiilll
           SET y_lag_1 = %s,
               y_lag_2 = %s,
               y_lag_3 = %s
        WHERE 日期 = %s 
    """
    cursor.execute(sql_update_lag, (
        row_sec["CPC"],      # -> latest.y_lag_1
        row_sec["y_lag_1"],  # -> latest.y_lag_2
        row_sec["y_lag_2"],  # -> latest.y_lag_3
        latest_date
    ))
    conn.commit()
    print(f"已更新 {latest_date} 的y_lag_1, y_lag_2, y_lag_3 來自 {row_sec['日期']}")
    

def predict_next_day_xgb_db():
    """
    1) 連線 MSSQL
    2) 抓最新 2 筆資料(含 CPC, 航油價格, y_lag_x等)
    3) 若有空值則適度填補
    4) 用latest[y_lag_x]準備特徵 X -> XGB 模型預測
    5) 更新資料庫(PredictedCPC, CPC)
    6) 回傳 (最新日期, 預測值) or None
    """

    conn = pymssql.connect(server=server, user=user, password=password, database=database)
    cursor = conn.cursor(as_dict=True)

    try:
        # 1)先抓最新2筆資料(以日期DESC排序)
        query = """
            SELECT TOP 2
                 日期, 日本, 南韓, 香港, 新加坡, 上海, 舟山,
                 CPC, y_lag_1, y_lag_2, y_lag_3, is_final_cpc
            FROM oooiiilll
            ORDER BY 日期 DESC
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        if len(rows) < 1:
            print("資料表不足1筆資料，無法預測")
            return None
        
        latest = rows[0] # 最新那筆
        # second_latest = rows[1] if len(rows) > 1 else None
        if latest.get("is_final_cpc") == 1:
            print(f"[INFO] latest日期 {latest['日期']} 的 is_final_cpc=1, 跳過自動預測更新。")
            print("latest",latest)
            return (latest["日期"], latest["CPC"])

        # 2) 若港口價格有空值，做適度填補(用當筆港口價格的平均值來補)
        columns_to_check = ["日本", "南韓", "香港", "新加坡", "上海", "舟山"]
        null_columns=[c for c in columns_to_check if latest[c] is None]
        if null_columns:
            # 計算非空欄位平均
            non_null_values = [latest[c] for c in columns_to_check if latest[c] is not None]
            avg_val = sum(non_null_values) / len(non_null_values) if non_null_values else 0

            # 用平均值填補
            update_query = f"""
                UPDATE oooiiilll
                SET {', '.join(f"{c} = ISNULL({c}, %s)" for c in null_columns)}
                WHERE 日期 = %s
            """
            cursor.execute(update_query, tuple([avg_val]*len(null_columns) + [latest["日期"]]))
            conn.commit()
            print(f"已補上空值，平均值={avg_val}")
        else:
            print("最新這筆資料無空值")

        #3)準備特徵x
        X = pd.DataFrame([{
            'japan': latest["日本"],
            'korea': latest["南韓"],
            "hongkong": latest["香港"],
            "singapore": latest["新加坡"],
            "shanghai": latest["上海"],
            "zhoushan": latest["舟山"],
            # y_lag_1 =  最新一筆CPC, y_lag_2 ...
            'y_lag_1': latest["y_lag_1"],
            'y_lag_2': latest["y_lag_2"],
            'y_lag_3': latest["y_lag_3"]
        }])

        #4) 執行 XGBoost預測
        y_pred = xgb_model.predict(X)[0]
        y_pred_rounded = round(float(y_pred), 2)
        print(f"XGB預測完成: {y_pred_rounded}")

        #5) 更新資料庫:把預測結果塞到某個欄位
        update_sql = """
            UPDATE oooiiilll
            SET PredictedCPC = %s, CPC = %s
            WHERE 日期 = %s
        """
        cursor.execute(update_sql, (y_pred_rounded, y_pred_rounded, latest["日期"]))
        conn.commit()
        print("[INFO] 預測值已經寫回資料庫 PredictedCPC, CPC 欄位")

        return (latest["日期"], y_pred_rounded)
    
    except Exception as e:
        print("predict_next_day_xgb_db 發生錯誤", e)
        return None
    
    finally:
        cursor.close()
        conn.close()


@xgb_bp.route("/xgb_predict_db", methods=["GET"])
def xgb_predict_db():
    """在瀏覽器上直接觸發 predict_next_day_xgb_db()，測試用"""
    result = predict_next_day_xgb_db()
    if result is None:
        return "預測失敗或找不到資料"
    latest_date, pred_val = result
    return f"XGB 預測完成: {latest_date} => {pred_val}"


@xgb_bp.route("/update_cpc_form", methods=["GET"])
def update_cpc_form():
    """
    1) 從資料庫查詢 MAX(日期)
    2) 把該日期帶給前端模板，並將它設為 <input type="date"> 的 max
    """
    conn = pymssql.connect(server=server, user=user, password=password, database=database)
    cursor = conn.cursor()
    try:
        # 查詢資料表中最大的日期
        cursor.execute("SELECT MAX(日期) FROM oooiiilll")
        row = cursor.fetchone()
        db_max_date = row[0]  # 例如 2023-11-08 00:00:00

        # 將 datetime 轉成 YYYY-MM-DD 字串，以便套用在前端
        if db_max_date:
            max_date_str = db_max_date.strftime("%Y-%m-%d")
        else:
            # 若資料表沒資料，就給個預設吧，例如今天
            max_date_str = date.today().strftime("%Y-%m-%d")

    except Exception as e:
        print("取得資料庫最大日期錯誤:", e)
        # 若有錯，就給個預設
        max_date_str = date.today().strftime("%Y-%m-%d")
    finally:
        cursor.close()
        conn.close()

    # 帶到模板
    return render_template("update_cpc_form.html", db_max_date=max_date_str)

@xgb_bp.route("/update_cpc", methods=["POST"])
def update_cpc():
    # 1) 取得表單日期與CPC
    cpc_date_str = request.form.get("cpc_date", "")
    cpc_value_str = request.form.get("cpc_value", "")

    # 2) 把cpc_date_str parse 成 date
    try:
        cpc_date = datetime.strptime(cpc_date_str, "%Y-%m-%d").date()
    except:
        return "日期格式錯誤"
    
    try:
        cpc_val = float(cpc_value_str)
    except:
        return "CPC值格式錯誤"
   
    # 3) 從資料庫查出 max_date
    conn = pymssql.connect(server=server, user=user, password=password, database=database)
    cursor = conn.cursor(as_dict=True)

    try:
        # 查詢資料表中最大的日期
        cursor.execute("SELECT MAX(日期) AS max_date FROM oooiiilll")
        row = cursor.fetchone()
        db_max_date = row["max_date"]
        if db_max_date is None:
            # 若整個資料表都沒資料，就不限制
            pass
        else:
            # 若輸入的 cpc_date > db_max_date，就擋
            if cpc_date > db_max_date:
                return f"不可輸入超過資料庫最新日期 {db_max_date.strftime('%Y-%m-%d')}"
            
        # 4) 更新(或插入) DB
        cursor.execute("SELECT TOP 1 * FROM oooiiilll WHERE 日期 = %s", (cpc_date,))
        exist_row = cursor.fetchone()

        if exist_row:
            upd_sql = """
                UPDATE oooiiilll
                   SET CPC = %s,
                       is_final_cpc = 1
                WHERE 日期 = %s
            """
            cursor.execute(upd_sql, (cpc_val, cpc_date))
            conn.commit()
            print(f"[INFO] 已更新 {cpc_date} 的 CPC={cpc_val}，並設 is_final_cpc=1")
        else:
            ins_sql = """
                INSERT INTO oooiiilll (日期, CPC, is_final_cpc)
                VALUES (%s, %s, 1)
            """
            cursor.execute(ins_sql, (cpc_date, cpc_val))
            conn.commit()
            print(f"[INFO] 已插入新日期 {cpc_date}, CPC={cpc_val}, is_final_cpc=1")


        # 更新連續3天的 y_lag_1, y_lag_2, y_lag_3
        update_next_3_lags(cursor, conn, cpc_date, cpc_val)
        return redirect("/")
    except Exception as e:
        print("update_cpc 錯誤", e)
        return f"資料庫操作錯誤:  {e}"
    finally:
        cursor.close()
        conn.close()
    #     # 檢查該日期是否存在
    #     check_sql = "SELECT TOP 1 * FROM oooiiilll WHERE 日期 = %s"
    #     cursor.execute(check_sql, (cpc_date,))
    #     row = cursor.fetchone()

    #     if row:
    #         #UPDATE
    #         upd_sql = """
    #             UPDATE oooiiilll
    #                SET CPC = %s
    #             WHERE 日期 = %s
    #         """
    #         cursor.execute(upd_sql, (cpc_val, cpc_date))
    #         conn.commit()
    #         msg = f"已更新{cpc_date}的 CPC = {cpc_val}"
    #     else:
    #         # 若該日期不存在，插入
    #         ins_sql = """
    #             INSERT INTO oooiiilll (日期, CPC)
    #             VALUES (%s, %s)
    #         """
    #         cursor.execute(ins_sql, (cpc_date, cpc_val))
    #         conn.commit()
    #         flash(f"已更新{cpc_date}的CPC={cpc_val}")
    #     return redirect("/")
    #     #     msg = f"已插入新日期 {cpc_date}, {cpc_val}"
    #     # return msg
    # except Exception as e:
    #     print("update_cpc 錯誤:",e)
    #     return f"資料庫操作錯誤: {e}"
    # finally:
    #     cursor.close()
    #     conn.close()

def update_next_3_lags(cursor, conn, base_date, cpc_val):
    """
    依序找:
      1) 後面第1筆日期 => y_lag_1 = cpc_val
      2) 後面第2筆日期 => y_lag_2 = cpc_val
      3) 後面第3筆日期 => y_lag_3 = cpc_val
    若中間任意一步找不到下一筆，就不再繼續
    """
    # 以當天為基準
    current_date = base_date

    for i in range(1, 4):
        sql = """
            SELECT TOP 1 日期
            FROM oooiiilll
            WHERE 日期 > %s
            ORDER BY 日期 ASC
        """
        cursor.execute(sql, (current_date,))
        row = cursor.fetchone()
        if not row:
            print(f"[INFO] 找不到第{i}個連續日期在 {current_date} 之後無新日期),停止")
            break

        next_date = row["日期"]
        # i=1 => y_lag_1
        # i=2 => y_lag_2
        # i=3 => y_lag_3
        # 執行對應的UPDATE
        update_sql = f"""
            UPDATE oooiiilll
               SET y_lag_{i} = %s
            WHERE 日期 = %s
        """
        cursor.execute(update_sql, (cpc_val, next_date))
        conn.commit()

        print(f"[INFO] 已更新{next_date} 的 y_lag_{i} = {cpc_val}")
        # 更新 current_data 為這個 next_date，讓下一輪找 "後面第2筆" 其實是
        # "在 next_date 之後的下一筆日期"
        current_date = next_date
@xgb_bp.route("/xgb_form", methods=["GET"])
def xgb_input_form_db():
    """顯示自訂 XGB 表單"""
    conn = pymssql.connect(server=server, user=user, password=password, database=database)
    cursor = conn.cursor()
    try:
        # 查詢資料表中最大的日期
        cursor.execute("SELECT MAX(日期) FROM oooiiilll")
        row = cursor.fetchone()
        db_max_date = row[0]  # 例如 2023-11-08 00:00:00

        # 將 datetime 轉成 YYYY-MM-DD 字串，以便套用在前端
        if db_max_date:
            max_date_str = db_max_date.strftime("%Y-%m-%d")
        else:
            # 若資料表沒資料，就給個預設吧，例如今天
            max_date_str = date.today().strftime("%Y-%m-%d")

    except Exception as e:
        print("取得資料庫最大日期錯誤:", e)
        # 若有錯，就給個預設
        max_date_str = date.today().strftime("%Y-%m-%d")
    finally:
        cursor.close()
        conn.close()
    return render_template("xgb_form.html", db_max_date=max_date_str)

@xgb_bp.route("/xgb_predict_db_form", methods=["POST"])
def xgb_predict_db_form():
    """
    1) upsert 該日期的 [日本，南韓，香港，新加坡，上海，舟山]
    2) 立刻抓 y_lag => update_ylag_for_latest(dorm_date)
    3) 找出 < 該日期 最近一筆 (for lag)
    4) 建立特徵 X => XGB 預測
    5) 寫回資料庫 PredictedCPC, CPC
    6) 回傳結果 (渲染 xgb_result.html)
    """
    form_date = request.form.get("date")
    japan = float(request.form.get("japan", 0))
    korea = float(request.form.get("korea", 0))
    hongkong = float(request.form.get("hongkong", 0))
    singapore = float(request.form.get("singapore", 0))
    shanghai = float(request.form.get("shanghai", 0))
    zhoushan = float(request.form.get("zhoushan", 0))

    # 連線 MSSQL
    conn = pymssql.connect(server=server, user=user, password=password, database=database)
    cursor = conn.cursor(as_dict=True)

    try: 
        # ============= (A) upsert 該日期(寫入港口價格) ===============
        # 檢查該 date 是否已有紀錄
        check_sql = "SELECT TOP 1 * FROM oooiiilll WHERE 日期 = %s"
        cursor.execute(check_sql, (form_date,))
        exist_row = cursor.fetchone()

        if exist_row:
            # UPDATE 該日期的[日本, 南韓, 香港, 新加坡, 上海, 舟山]
            upd_sql = """
                UPDATE oooiiilll
                SET 日本 = %s, 南韓 = %s, 香港 = %s, 新加坡 = %s, 上海 = %s, 舟山 = %s, is_final_cpc = 0
                WHERE 日期 = %s
            """
            cursor.execute(upd_sql, (japan, korea, hongkong, singapore, shanghai, zhoushan, form_date))
            conn.commit()
            print(f"成功更新 {form_date} 之港口價格")
        else:
            # INSERT 一筆新的 row
            ins_sql = """
                INSERT INTO oooiiilll (日期, 日本, 南韓, 香港, 新加坡, 上海, 舟山)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(ins_sql, (form_date, japan, korea, hongkong, singapore, shanghai, zhoushan))
            conn.commit()
            print(f"已插入 {form_date} 的新日期紀錄(港口價格)")

        # (B) 立可補 y_lag，避免「最新資料沒有 y_lag」的問題
        update_ylag_for_latest(cursor, conn, form_date)

        # (C) 再抓 "< form_date 的最近一筆" (for y_lag) 來做 XGB 預測
        query = """
            SELECT TOP 1
                 日期, CPC, y_lag_1, y_lag_2, y_lag_3
            FROM oooiiilll
            WHERE 日期 < %s
            ORDER BY 日期 DESC
        """
        cursor.execute(query, (form_date,))
        row_old = cursor.fetchone()
        if not row_old:
            return "找不到較早的歷史紀錄，無法做lag或預測"
        

        #3) 建立特徵X
        X = pd.DataFrame([{
            "japan": japan,
            "korea": korea,
            "hongkong": hongkong,
            "singapore": singapore,
            "shanghai": shanghai,
            "zhoushan": zhoushan,
            "y_lag_1": row_old["CPC"],         # y_lag_1 = 昨天的cpc
            "y_lag_2": row_old["y_lag_1"],
            "y_lag_3": row_old["y_lag_2"]
        }])
        print("[DEBUG] X", X)

        # D) 執行 XGB 預測
        pred_val = xgb_model.predict(X)[0]
        pred_rounded = round(float(pred_val), 2)
        print(f"[DEBUG] 預測結果 = {pred_rounded}")

        # E) 寫回 (form_date) 的 PredictedCPC, CPC
        cursor.execute("SELECT TOP 1 * FROM oooiiilll WHERE 日期 = %s", (form_date,))
        new_row = cursor.fetchone()

        if new_row:
            # 更新
            upd_p_sql = """
                UPDATE oooiiilll
                SET PredictedCPC = %s, CPC = %s
                WHERE 日期 = %s
            """
            cursor.execute(upd_p_sql, (pred_rounded, pred_rounded, form_date))
            conn.commit()
            print(f"已更新 {form_date} 的 PredictedCPC = {pred_rounded}")
        else:
            # 插入
            ins_p_sql = """
                INSERT INTO oooiiilll (日期, PredictedCPC, CPC)
                VALUES (%s, %s, %s)
            """
            cursor.execute(ins_p_sql, (form_date, pred_rounded, pred_rounded))
            conn.commit()
            print(f"已插入新日期{form_date}, CPC= {pred_rounded}")

        # (F) 回傳至 xgb_result.html
        return render_template(
            "xgb_result.html",
            result_val=pred_rounded,
            date=form_date,
            j=japan, k=korea, h=hongkong,
            s=singapore, sh=shanghai, zh=zhoushan        
        )
    
    finally:
        cursor.close()
        conn.close()

@xgb_bp.route("/api/check_previous_final",methods=["GET"])
def check_previous_final():
    """
    給前端 AJAX: 檢查比傳入日期更小的最近一筆 is_final_cpc
    回傳 JSON: { "hasRecord": bool, "date": "YYYY-MM-DD", "isFinal": bool}
    """
    input_date_str = request.args.get("date", "")
    if not input_date_str:
        return jsonify({"hasRecord": False}), 200
    
    try:
        input_date = datetime.strptime(input_date_str, "%Y-%m-%d").date()
    except:
        return jsonify({"hasRecord": False}), 200
    
    conn = pymssql.connect(server=server, user=user, password=password, database=database)
    cursor = conn.cursor(as_dict=True)
    try:
        sql = """
            SELECT TOP 1 日期, is_final_cpc
            FROM oooiiilll
            WHERE 日期 < %s
            ORDER BY 日期 DESC
        """
        cursor.execute(sql, (input_date,))
        row = cursor.fetchone()
        if not row:
            # 沒找到任何更早的 => 就視為 pass
            return jsonify({"hasRecord": False}), 200
        else:
            # 找到一筆 => 回傳 date 與 is_final_cpc
            return jsonify({
                "hasRecord" : True,
                "date": str(row["日期"]), # e.g. "2023-11-09"
                "isFinal": bool(row["is_final_cpc"]) # MSSQL BIT => 0/1
            }), 200
    except Exception as e:
        print("check_previous_final error", e)
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()





