# xgb_routes.py
from flask import Blueprint, render_template, request, redirect, jsonify
import pandas as pd
import os
import pymssql
import joblib
from datetime import date, datetime, timedelta
from dotenv import load_dotenv

# 自訂的 function, service
from app.services.db_service import get_error_metrics, save_error_metrics_to_db, get_db_max_date

xgb_bp = Blueprint('xgb_bp', __name__)

# 載入環境變數
load_dotenv()
server = os.getenv("DB_SERVER")
user = os.getenv("DB_USER")
password = os.getenv("DB_PASSWORD")
database = os.getenv("DB_NAME")


# 載入 XGBoost 模型 (全域)
xgb_model_path = "./xgb_models/xgb_model.pkl"
xgb_model = joblib.load(xgb_model_path)

def update_ylag_for_latest(cursor, conn, latest_date):
    """
    將 latest_date 這筆資料的 y_lag_1, y_lag_2, y_lag_3
    更新成「比 latest_date 更舊的最近一筆(= second_latest)」的CPC, y_lag_1, y_lag_2
    """
    # 查「比latest_date小的最近一筆」 => second_Latest
    query_sec = """
        SELECT TOP 1
             日期, CPC, y_lag_1, y_lag_2, y_lag_3
        FROM oooiiilll_new
        WHERE 日期 < %s
        ORDER BY 日期 DESC
    """
    cursor.execute(query_sec, (latest_date,))
    row_sec = cursor.fetchone()
    if not row_sec:
        print(f"[WARN]找不到比 {latest_date} 更舊的紀錄，無法更新y_lag")
        return

    # second_latest => row_sec
    sql_update_lag = """
        UPDATE oooiiilll_new
           SET y_lag_1 = %s,
               y_lag_2 = %s,
               y_lag_3 = %s
        WHERE 日期 = %s 
    """
    cursor.execute(sql_update_lag, (
        row_sec["CPC"],      # -> latest_date.y_lag_1
        row_sec["y_lag_1"],  # -> latest_date.y_lag_2
        row_sec["y_lag_2"],  # -> latest_date.y_lag_3
        latest_date
    ))
    conn.commit()
    print(f"[INFO] 已更新 {latest_date} 的y_lag_1/2/3 來源 {row_sec['日期']}")
    
def update_next_3_lags(cursor, conn, base_date, cpc_val):
    """
    依序找:
      1) 後面第1筆日期 => y_lag_1 = cpc_val
      2) 後面第2筆日期 => y_lag_2 = cpc_val
      3) 後面第3筆日期 => y_lag_3 = cpc_val
    若中間任意一步找不到下一筆，就停止
    """
    # 以當天為基準
    current_date = base_date
    for i in range(1, 4):
        sql = """
            SELECT TOP 1 日期
            FROM oooiiilll_new
            WHERE 日期 > %s
            ORDER BY 日期 ASC
        """
        cursor.execute(sql, (current_date,))
        row = cursor.fetchone()
        if not row:
            print(f"[INFO] 無第{i}個連續日期 (在 {current_date} 之後無新日期)，停止更新 y_lag")
            break

        next_date = row["日期"]
        update_sql = f"""
            UPDATE oooiiilll_new
               SET y_lag_{i} = %s
            WHERE 日期 = %s
        """
        cursor.execute(update_sql, (cpc_val, next_date))
        conn.commit()

        print(f"[INFO] 已更新{next_date} 的 y_lag_{i} = {cpc_val}")
        # 更新 current_data 為這個 next_date，讓下一輪找 "後面第2筆" 其實是
        # "在 next_date 之後的下一筆日期"
        current_date = next_date

def get_two_latest_rows(cursor):
    """
    從資料表抓取「最新2筆」資料（以日期DESC), 回傳 list of disc
    """
    query = """
        SELECT TOP 2
             日期, 日本, 南韓, 香港, 新加坡, 上海, 舟山,
             CPC, y_lag_1, y_lag_2, y_lag_3, is_final_cpc
        FROM oooiiilll_new
        ORDER BY 日期 DESC
    """
    cursor.execute(query)
    rows = cursor.fetchall()
    return rows

def fill_null_ports(cursor, conn, row_data):
    """
    檢查 row_data(一筆) 的 [日本, 南韓, 香港, 新加坡, 上海, 舟山]，若有None就用平均值補
    row_data => dict
    """
    columns_to_check = ["日本", "南韓", "香港", "新加坡", "上海", "舟山"]
    null_columns = [c for c in columns_to_check if row_data.get(c) is None]

    if not null_columns:
        print("[INFO] 這筆資料無港口空值")
        return
    
    non_null_values = [row_data[c] for c in columns_to_check if row_data[c] is not None]
    avg_val = sum(non_null_values) / len(non_null_values) if non_null_values else 0

    update_query = f"""
        UPDATE oooiiilll_new
        SET {', '.join(f"{c} = ISNULL({c}, %s)" for c in null_columns)}
        WHERE 日期 = %s
    """
    cursor.execute(update_query, tuple([avg_val] * len(null_columns) + [row_data["日期"]]))
    conn.commit()
    print(f"[INFO] 已補上空值 => 平均值={avg_val}, for 日期={row_data['日期']}")

def predict_next_day_xgb_db():
    """
    1) 連線 MSSQL
    2) 抓最新 2 筆資料(含 CPC, 航油價格, y_lag_x等)
    3) 若次新那筆 is_final_cpc=1 就跳過預測
    4) 若港口有空值 => 用平均值補
    5) 用該筆 (最新) 準備特徵 X => XGB預測
    6) 寫回 PredictedCPC, CPC
    7) 回傳 (日期, 預測值)
    """

    try:
        with pymssql.connect(server=server, user=user, password=password, database=database) as conn:
            with conn.cursor(as_dict=True) as cursor:
                rows = get_two_latest_rows(cursor)
                if len(rows) < 1:
                    print("資料表不足1筆資料，無法預測")
                    return None
        
                first_latest = rows[0] # 最新那筆
                # second_latest = rows[1] if len(rows) > 1 else None
                if first_latest.get("is_final_cpc") == 1:
                    print(f"[INFO] latest日期 {first_latest['日期']} 的 is_final_cpc=1, 跳過自動預測更新。")
                    return (first_latest["日期"], first_latest["CPC"])

                # 2) 若港口價格有空值，做適度填補(用當筆港口價格的平均值來補)
                fill_null_ports(cursor, conn, first_latest)

                #3)準備特徵x
                X = pd.DataFrame([{
                    'japan': first_latest["日本"],
                    'korea': first_latest["南韓"],
                    "hongkong": first_latest["香港"],
                    "singapore": first_latest["新加坡"],
                    "shanghai": first_latest["上海"],
                    "zhoushan": first_latest["舟山"],
                    # y_lag_1 =  最新一筆CPC, y_lag_2 ...
                    'y_lag_1': first_latest["y_lag_1"],
                    'y_lag_2': first_latest["y_lag_2"],
                    'y_lag_3': first_latest["y_lag_3"]
                }])

                #4) 執行 XGBoost預測
                y_pred = xgb_model.predict(X)[0]
                y_pred_rounded = round(float(y_pred), 2)
                print(f"[INFO] XGB預測完成 => {first_latest['日期']} => {y_pred_rounded}")

                # (4) 更新CPC, PredictedCPC
                upd_sql = """
                    UPDATE oooiiilll_new
                    SET PredictedCPC = %s, CPC = %s
                    WHERE 日期 = %s
                """
                cursor.execute(upd_sql, (y_pred_rounded, y_pred_rounded, first_latest["日期"]))
                conn.commit()
                print("[INFO] 預測值已寫回DB =>", y_pred_rounded)

                return (first_latest["日期"], y_pred_rounded)
    
    except Exception as e:
        print("predict_next_day_xgb_db 發生錯誤", e)
        return None

# def predict_next_day_xgb_db():
#     """
#     1) 連線 MSSQL
#     2) 抓最新 2 筆資料(含 CPC, 航油價格, y_lag_x等)
#     3) 若次新那筆 is_final_cpc=1 就跳過預測
#     4) 若港口有空值 => 用平均值補
#     5) 用該筆 (次新) 準備特徵 X => XGB預測
#     6) 寫回 PredictedCPC, CPC
#     7) 回傳 (日期, 預測值)
#     """

#     try:
#         with pymssql.connect(server=server, user=user, password=password, database=database) as conn:
#             with conn.cursor(as_dict=True) as cursor:
#                 rows = get_two_latest_rows(cursor)
#                 if len(rows) < 1:
#                     print("資料表不足1筆資料，無法預測")
#                     return None
        
#                 second_latest = rows[1] # 次新那筆
#                 # second_latest = rows[1] if len(rows) > 1 else None
#                 if second_latest.get("is_final_cpc") == 1:
#                     print(f"[INFO] latest日期 {second_latest['日期']} 的 is_final_cpc=1, 跳過自動預測更新。")
#                     return (second_latest["日期"], second_latest["CPC"])

#                 # 2) 若港口價格有空值，做適度填補(用當筆港口價格的平均值來補)
#                 fill_null_ports(cursor, conn, second_latest)

#                 #3)準備特徵x
#                 X = pd.DataFrame([{
#                     'japan': second_latest["日本"],
#                     'korea': second_latest["南韓"],
#                     "hongkong": second_latest["香港"],
#                     "singapore": second_latest["新加坡"],
#                     "shanghai": second_latest["上海"],
#                     "zhoushan": second_latest["舟山"],
#                     # y_lag_1 =  最新一筆CPC, y_lag_2 ...
#                     'y_lag_1': second_latest["y_lag_1"],
#                     'y_lag_2': second_latest["y_lag_2"],
#                     'y_lag_3': second_latest["y_lag_3"]
#                 }])

#                 #4) 執行 XGBoost預測
#                 y_pred = xgb_model.predict(X)[0]
#                 y_pred_rounded = round(float(y_pred), 2)
#                 print(f"[INFO] XGB預測完成 => {second_latest['日期']} => {y_pred_rounded}")

#                 # (4) 更新CPC, PredictedCPC
#                 upd_sql = """
#                     UPDATE oooiiilll_new
#                     SET PredictedCPC = %s, CPC = %s
#                     WHERE 日期 = %s
#                 """
#                 cursor.execute(upd_sql, (y_pred_rounded, y_pred_rounded, second_latest["日期"]))
#                 conn.commit()
#                 print("[INFO] 預測值已寫回DB =>", y_pred_rounded)

#                 return (second_latest["日期"], y_pred_rounded)
    
#     except Exception as e:
#         print("predict_next_day_xgb_db 發生錯誤", e)
#         return None


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
     顯示一個表單，可讓使用者輸入 date, CPC；並把 DB 最大日期帶到前端
    """
    max_date_str = get_db_max_date()
    return render_template("update_cpc_form.html", db_max_date=max_date_str)


@xgb_bp.route("/update_cpc", methods=["POST"])
def update_cpc():
    """
    使用者在表單裡輸入 cpc_date 與 cpc_val，
    1) 先檢查 cpc_date <= 資料庫 max_date
    2) 找比 cpc_date 更早的一筆 => target_date
    3) 更新 target_date 的 CPC
    4) 更新 cpc_date => is_final_cpc=1 & CPC
    5) 更新 y_lag
    6) 計算誤差 & 寫入DB
    """
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

    try:
        with pymssql.connect(server=server, user=user, password=password, database=database) as conn:
            with conn.cursor(as_dict=True) as cursor:

                # A) 檢查 cpc_date 是否超過資料庫最大日期
                cursor.execute("SELECT MAX(日期) AS max_date FROM oooiiilll_new")
                row = cursor.fetchone()
                db_max_date = row["max_date"]
                if db_max_date and cpc_date > db_max_date:
                    return f"不可輸入超過資料庫最新日期 {db_max_date}"

                # B) 找 target_date => 比 cpc_date 更早且最近的一筆
                sql_prev = """
                    SELECT TOP 1 日期
                    FROM oooiiilll_new
                    WHERE 日期 < %s
                    ORDER BY 日期 DESC
                """
                cursor.execute(sql_prev, (cpc_date,))
                prev_row = cursor.fetchone()
                if not prev_row:
                    return f"找不到比 {cpc_date} 更早的日期，無法更新CPC"
                
                target_date = prev_row["日期"]
                print(f"[INFO] target_date={target_date}, cpc_date={cpc_date}")

                # C) 更新 (target_date) 的 CPC
                cursor.execute("SELECT TOP 1 * FROM oooiiilll_new WHERE 日期 = %s", (target_date,))
                exist_target = cursor.fetchone()
                if exist_target:
                    upd_sql = """ UPDATE oooiiilll_new SET CPC = %s WHERE 日期 = %s """
                    cursor.execute(upd_sql, (cpc_val, target_date))
                    conn.commit()
                    print(f"[INFO] 已更新 {target_date} 的 CPC={cpc_val}")
                else:
                    # 不太可能發生，但以防
                    ins_sql = """ INSERT INTO oooiiilll_new (日期, CPC) VALUES (%s, %s)"""
                    cursor.execute(ins_sql, (target_date, cpc_val))
                    conn.commit()
                    print(f"[INFO] 新增 {target_date}, CPC={cpc_val}")

                # D) 同時更新 cpc_date => is_final_cpc=1, CPC
                cursor.execute("SELECT TOP 1 * FROM oooiiilll_new WHERE 日期 = %s", (cpc_date,))
                exist_cpcdate = cursor.fetchone()
                if exist_cpcdate:
                    upd_sql = """
                        UPDATE oooiiilll_new
                        SET CPC = %s,
                            is_final_cpc = 1
                        WHERE 日期 = %s
                    """
                    cursor.execute(upd_sql, (cpc_val, cpc_date))
                    conn.commit()
                    print(f"[INFO] 已更新 {cpc_date} 的 CPC={cpc_val}, is_final_cpc=1")
                else:
                    ins_sql = """
                        INSERT INTO oooiiilll_new (日期, CPC, is_final_cpc)
                        VALUES (%s, %s, 1)
                    """
                    cursor.execute(ins_sql, (cpc_date, cpc_val))
                    conn.commit()
                    print(f"[INFO] 新增 {cpc_date}, CPC={cpc_val}, is_final_cpc=1")

                # E) 更新連續3天 y_lag => 以 target_date 為基準
                update_next_3_lags(cursor, conn, target_date, cpc_val)

                # F) 計算 MAE / MAPE / RMSE => 寫入 DB
                mae, mape, rmse = get_error_metrics()
                if mae is not None and mape is not None and rmse is not None:
                    save_error_metrics_to_db(mae, mape, rmse)
                    print(f"[INFO] Inserted metrics: MAE={mae}, MAPE={mape}, RMSE={rmse}")

        return redirect("/")
    except Exception as e:
        print("update_cpc 錯誤", e)
        return f"資料庫操作錯誤:  {e}"

@xgb_bp.route("/xgb_form", methods=["GET"])
def xgb_input_form_db():
    """
    顯示自訂 XGB 表單
    """
    max_date_str = get_db_max_date()
    try:
        db_max_date = datetime.strptime(max_date_str, "%Y-%m-%d").date()
    except:
        # 萬一parse失敗=>預設
        db_max_date = date(2023, 12, 4)

    # 計算 min_date = (db_max_date + 1)
    min_date  = db_max_date + timedelta(days=1)
    # 計算 max_date_form_form = (今天 -1)
    today = datetime.now().date()
    max_date_for_form = today - timedelta(days=1)
    

    # 轉成字串
    min_date_str = min_date.isoformat()
    max_date_str_input = max_date_for_form.isoformat()
    return render_template("xgb_form.html", 
                           db_max_date=max_date_str,
                           min_date_str=min_date_str,
                           max_date_str=max_date_str_input)

@xgb_bp.route("/xgb_predict_db_form", methods=["POST"])
def xgb_predict_db_form():
    """
    需求：
    1) 使用者輸入 form_date & 港口 -> 先寫進 DB (upsert)，但不拿來預測
    2) 預測時要用「插入之前的 max_date」那筆當最新
    3) 預測結果仍然寫回 old_db_max_date
    """

    form_date = request.form.get("date")
    japan = float(request.form.get("japan", 0))
    korea = float(request.form.get("korea", 0))
    hongkong = float(request.form.get("hongkong", 0))
    singapore = float(request.form.get("singapore", 0))
    shanghai = float(request.form.get("shanghai", 0))
    zhoushan = float(request.form.get("zhoushan", 0))

    conn = pymssql.connect(server=server, user=user, password=password, database=database)
    cursor = conn.cursor(as_dict=True)

    try:
        with pymssql.connect(server=server, user=user, password=password, database=database) as conn:
            with conn.cursor(as_dict=True) as cursor:

                # (A) 先查舊的 max_date (插入前)
                cursor.execute("SELECT MAX(日期) AS max_date FROM oooiiilll_new")
                row = cursor.fetchone()
                old_db_max_date = row["max_date"]
                if not old_db_max_date:
                    return "資料庫中沒有任何資料 => 無法預測"

                print(f"[INFO] 舊的DB最大日期 = {old_db_max_date} (將用來做 XGB)")

                # (B) Upsert form_date => 先寫(不拿來預測)
                check_sql = "SELECT TOP 1 * FROM oooiiilll_new WHERE 日期 = %s"
                cursor.execute(check_sql, (form_date,))
                exist_row = cursor.fetchone()

                if exist_row:
                    upd_sql = """
                        UPDATE oooiiilll_new
                        SET 日本 = %s, 南韓 = %s, 香港 = %s, 新加坡 = %s, 上海 = %s, 舟山 = %s
                        WHERE 日期 = %s
                    """
                    cursor.execute(upd_sql, (japan, korea, hongkong, singapore, shanghai, zhoushan, form_date))
                    conn.commit()
                    print(f"[INFO] 已更新 {form_date} (但預測時不使用)")
                else:
                    ins_sql = """
                        INSERT INTO oooiiilll_new (日期, 日本, 南韓, 香港, 新加坡, 上海, 舟山)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """
                    cursor.execute(ins_sql, (form_date, japan, korea, hongkong, singapore, shanghai, zhoushan))
                    conn.commit()
                    print(f"[INFO] 已插入 {form_date} (預測時不使用)")

                # (B.1) 如需更新 form_date 這筆 y_lag, 可以呼叫
                update_ylag_for_latest(cursor, conn, form_date)

                # (C) 改用 old_db_max_date 來做 XGB 預測
                sql_oldmax = """
                    SELECT TOP 1
                        日期,
                        日本, 南韓, 香港, 新加坡, 上海, 舟山,
                        CPC, y_lag_1, y_lag_2, y_lag_3
                    FROM oooiiilll_new
                    WHERE 日期 = %s
                """
                cursor.execute(sql_oldmax, (old_db_max_date,))
                row_oldmax = cursor.fetchone()
                if not row_oldmax:
                    return f"[ERR] 找不到 {old_db_max_date} => 無法預測"

                # 組建特徵
                def safe_float(v):
                    return float(v) if v is not None else 0.0

                X = pd.DataFrame([{
                    "japan":     safe_float(row_oldmax["日本"]),
                    "korea":     safe_float(row_oldmax["南韓"]),
                    "hongkong":  safe_float(row_oldmax["香港"]),
                    "singapore": safe_float(row_oldmax["新加坡"]),
                    "shanghai":  safe_float(row_oldmax["上海"]),
                    "zhoushan":  safe_float(row_oldmax["舟山"]),
                    "y_lag_1":   safe_float(row_oldmax["y_lag_1"]),
                    "y_lag_2":   safe_float(row_oldmax["y_lag_2"]),
                    "y_lag_3":   safe_float(row_oldmax["y_lag_3"])
                }])

                pred_val = xgb_model.predict(X)[0]
                pred_rounded = round(float(pred_val), 2)
                print(f"[INFO] 預測值 => {pred_rounded}, 針對舊的 max_date={old_db_max_date}")

                # (C.1) 寫回 old_db_max_date => CPC, PredictedCPC
                # 寫回 old_db_max_date
                upd_pred_sql = """
                    UPDATE oooiiilll_new
                    SET CPC = %s,
                        PredictedCPC = %s
                    WHERE 日期 = %s
                """
                cursor.execute(upd_pred_sql, (pred_rounded, pred_rounded, old_db_max_date))
                conn.commit()
                print(f"[INFO] 已把預測值寫回 {old_db_max_date}")
                # (C.2) 若需要 => 同步更新 form_date => CPC, PredictedCPC
                cursor.execute("SELECT TOP 1 * FROM oooiiilll_new WHERE 日期 = %s", (form_date,))
                row_form = cursor.fetchone()
                if row_form:
                    upd_f_sql = """
                        UPDATE oooiiilll_new
                        SET CPC = %s,
                            PredictedCPC = %s, is_final_cpc = 0
                        WHERE 日期 = %s
                    """
                    cursor.execute(upd_f_sql, (pred_rounded, pred_rounded, form_date))
                    conn.commit()
                    print(f"[INFO] 已將同樣的預測值 => {pred_rounded}, 寫到 {form_date}")
                else:
                    # 理論上應該存在
                    pass

                # (D) 回傳模板
                return render_template(
                    "xgb_result.html",
                    result_val=pred_rounded,
                    date=old_db_max_date,
                    j=japan,
                    k=korea,
                    h=hongkong,
                    s=singapore,
                    sh=shanghai,
                    zh=zhoushan
                )

    except Exception as e:
        print("[ERR] xgb_predict_db_form 錯誤:", e)
        return f"資料庫操作錯誤: {e}"



@xgb_bp.route("/api/check_previous_final",methods=["GET"])
def check_previous_final():
    """
    檢查比傳入日期更小的最近一筆 is_final_cpc
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
        with pymssql.connect(server=server, user=user, password=password, database=database) as conn:
            with conn.cursor(as_dict=True) as cursor:
                sql = """
                    SELECT TOP 1 日期, is_final_cpc
                    FROM oooiiilll_new
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
        print("[ERR] check_previous_final error:", e)
        return jsonify({"error": str(e)}), 500





