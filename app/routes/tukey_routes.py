from flask import Blueprint, render_template, request, redirect, render_template, flash
import pandas as pd
import os
import time
import requests
from datetime import datetime
import pymssql
from datetime import date, datetime
from dotenv import load_dotenv


tukey_bp = Blueprint('tukey_bp', __name__)

# 讀取 .env 文件
load_dotenv()
server = os.getenv("DB_SERVER")
user = os.getenv("DB_USER")
password = os.getenv("DB_PASSWORD")
database = os.getenv("DB_NAME")

def fetch_latest_data(cursor, today):
    """ 查詢最新兩筆資料 """
    query = """
        SELECT TOP 2 日期, 日本, 南韓, 香港, 新加坡, 上海, 舟山, y_lag_1, y_lag_2, y_lag_3, CPC
        FROM aviation_prediction
        WHERE 日期 < %s
        ORDER BY 日期 DESC
    """
    cursor.execute(query, (today,))
    return cursor.fetchall()

def update_null_values(cursor, conn, record):
    """ 更新 `None` 值為該筆資料的平均值 """
    fields = ["日本", "南韓", "香港", "新加坡", "上海", "舟山"]
    null_columns = [col for col in fields if record[col] is None]
    
    if not null_columns:
        return False  # 無需更新

    non_null_values = [record[col] for col in fields if record[col] is not None]
    avg_value = sum(non_null_values) / len(non_null_values) if non_null_values else None

    if avg_value is None:
        return False
    else:
        print("📌 平均值:",avg_value)

    update_query = f"""
        UPDATE aviation_prediction
        SET {", ".join(f"{col} = ISNULL({col}, %s)" for col in null_columns)}
        WHERE 日期 = %s
    """
    cursor.execute(update_query, tuple([avg_value] * len(null_columns) + [record["日期"]]))
    conn.commit()
    return True  

def update_ylag(cursor, conn, latest, second_latest):
    """ 更新 `y_lag` 欄位 """
    if not second_latest or all(latest[key] is not None for key in ["y_lag_1", "y_lag_2", "y_lag_3"]):
        return False  # 無需更新

    update_query = """
        UPDATE aviation_prediction
        SET y_lag_1 = %s, y_lag_2 = %s, y_lag_3 = %s
        WHERE 日期 = %s
    """    
    cursor.execute(update_query, (second_latest["CPC"], second_latest["y_lag_1"], second_latest["y_lag_2"], latest["日期"]))
    conn.commit()
    return True  

def fetch_latest_prediction_data(cursor, today):
    """ 查詢最新一筆預測所需的數據 """
    query = """
        SELECT TOP 1 日本, 南韓, 香港, 新加坡, 上海, 舟山, y_lag_1, y_lag_2, y_lag_3
        FROM aviation_prediction
        WHERE 日期 < %s
        ORDER BY 日期 DESC
    """
    cursor.execute(query, (today,))
    result = cursor.fetchone()
    
    if not result:
        return None
    
    return [{
        "日本": result["日本"], "南韓": result["南韓"], "香港": result["香港"],
        "新加坡": result["新加坡"], "上海": result["上海"], "舟山": result["舟山"],
        "y_lag_1": result["y_lag_1"], "y_lag_2": result["y_lag_2"], "y_lag_3": result["y_lag_3"],
    }]

def send_api_request(predict_info,api_token):
    """ 發送預測請求並獲取結果 """
    
    post_api_path = "http://10.16.32.97:8098/tukey/tukey/api/"
    request_json = {"api_token": api_token, "data": predict_info}

    print("開始發送 POST 請求...")
    post_result = requests.post(post_api_path, json=request_json, headers={"Content-Type": "application/json"})
    post_result.raise_for_status()
    response_json = post_result.json()

    get_api_path = response_json.get("link")
    if not get_api_path:
        raise Exception("❌ POST 請求未返回查詢連結！請檢查 API 回應格式。")
    
    print(f"✅ 查詢成功，連結: {get_api_path}")
    
    return get_api_path

def poll_prediction_result(get_api_path):
    """ 等待預測結果 """
    time_limit = 60 * 30  # 30 分鐘
    time_start = time.time()

    while True:
        if time.time() - time_start >= time_limit:
            raise Exception("❌ 預測失敗：超過時間限制")

        response = requests.get(get_api_path)
        response.raise_for_status()
        result_json = response.json()
        predicted_data = result_json.get("data")
        status = predicted_data.get("status") if predicted_data else None

        if status == "success":
            predicted_value = round(predicted_data['indv'][0]['value'], 2)
            print(f"✅ 預測成功，結果：{predicted_value}")
            return predicted_value
        elif status == "fail":
            raise Exception("❌ 預測失敗")
        else:
            print("⌛ 預測中...")
            time.sleep(3)


"""
預測隔日CPC價格(Tukey)
"""
def predict_next_day_tukey():
    today = date.today().strftime("%Y-%m-%d")
    predicted_results = []

    try:
        # **連線到資料庫**
        conn = pymssql.connect(server=server, user=user, password=password,  database=database)
        cursor = conn.cursor(as_dict=True)  

        '''
        這邊加上Plattes API
        '''

        # 1.查詢並更新資料
        result = fetch_latest_data(cursor, today)
        if not result:
            print("❌ 找不到符合的資料")
            return None
        else:
            print('最新兩筆資料',"\n",result[0],"\n",result[1])

        latest_record, second_latest = result[0], result[1] if len(result) > 1 else None
        predicted_results.append(latest_record["日期"])

        # **更新空值**
        if update_null_values(cursor, conn, latest_record):
            print("✅ 成功更新空值")
        else:
            print("📌 無需更新空值")

        # **更新 ylag**
        if update_ylag(cursor, conn, latest_record, second_latest):
            print("✅ 成功更新 ylag")
        else:
            print("📌 無需更新 ylag")

        # 2.取得更新後資料進行預測
        predict_info = fetch_latest_prediction_data(cursor, today)
        if not predict_info:
            print("❌ 無法查詢最新數據")
            return None
        else:
            print("predict_info",predict_info)

        # 3.發送 API 請求並獲取預測結果
        # api_token = "37d9fd65-77d5-464f-8038-3cfee4d525de" #無ylag
        api_token = "3babb936-d258-44bc-981e-e4c358055ad7"

        get_api_path = send_api_request(predict_info,api_token)
        predicted_value = poll_prediction_result(get_api_path)

        predicted_results.append(predicted_value)
        return predicted_results

    except Exception as e:
        print(f"❌ 發生錯誤: {e}")
        return None

    finally:
        cursor.close()
        conn.close()
        print("關閉連線...")

        
"""
自訂 Tukey 輸入表單(含日期)
"""
@tukey_bp.route("/tukey_form", methods=["GET"])
def tukey_input_form():
    
    return render_template("tukey_form.html")

@tukey_bp.route("/tukey_predict2", methods=["POST"])
def tukey_predict_custom():

    # 從表單中提取要預測的資料
    date=request.form.get("date")
    japan = request.form.get("japan")
    korea = request.form.get("korea")
    hongkong = request.form.get("hongkong")
    singapore = request.form.get("singapore")
    shanghai = request.form.get("shanghai")
    zhoushan = request.form.get("zhoushan")

   # 將表單日期轉換為 datetime 格式
    form_date = datetime.strptime(date, "%Y-%m-%d")
  

    # 讀取 CSV 檔案
    csv_file_path = "processed_data.csv"  # 替換為你的 CSV 路徑
    df = pd.read_csv(csv_file_path)

    # 確保日期欄位正確轉換為 datetime 格式
    df['date'] = pd.to_datetime(df['日期'], format="%Y/%m/%d")

    # 移除無效的日期值
    df = df.dropna(subset=['date'])

    # 過濾日期必須小於表單日期
    filtered_df = df[df['date'] < form_date]

    if filtered_df.empty:
        print("沒有找到小於表單日期的資料")
    else:
        # 找到與表單日期最近的日期資料
        nearest_row = filtered_df.iloc[(filtered_df['date'] - form_date).abs().argsort().iloc[0]]
        print("找到的最近日期資料：")
        print(nearest_row)
        nearest_row=nearest_row.tolist()
       
    # 將值儲存到字典，便於後續處理
    inputs = {
        "日本": float(japan) if japan else None,
        "南韓": float(korea) if korea else None,
        "香港": float(hongkong) if hongkong else None,
        "新加坡": float(singapore) if singapore else None,
        "上海": float(shanghai) if shanghai else None,
        "舟山": float(zhoushan) if zhoushan else None,
        
    }

    # 計算非空欄位的平均值
    non_empty_values = [value for value in inputs.values() if value is not None]
    average_value = sum(non_empty_values) / len(non_empty_values) if non_empty_values else 0

    # 將空值替換為平均值
    for key, value in inputs.items():
        if value is None:
            inputs[key] = average_value

    # 建立預測資訊
    predict_info = [{
        **inputs,  # 展開計算後的輸入值
        "y_lag_1": float(nearest_row[9]),  # 將 float64 轉換為普通的 float
        "y_lag_2": float(nearest_row[10]), 
        "y_lag_3": float(nearest_row[11]),
    }]

    # 發送 API 請求並獲取預測結果
    api_token = "3babb936-d258-44bc-981e-e4c358055ad7"

    get_api_path = send_api_request(predict_info,api_token)
    predicted_value = poll_prediction_result(get_api_path)

    return render_template("tukey_result.html",date=date,
                result_val=predicted_value,
                j=japan,k=korea,h=hongkong,
                s=singapore,sh=shanghai,zh=zhoushan)  

"""
自訂 Tukey 輸入表單(不含日期)
"""
@tukey_bp.route("/tukey_form_noDate", methods=["GET"])
def tukey_input_form_noDate():
    """
    顯示自訂 Tukey 預測的表單
    """
    return render_template("tukey_form_noDate.html")

@tukey_bp.route("/tukey_predict_noDate2", methods=["POST"])
def tukey_predict_noDate():
    
    # 從表單中提取要預測的資料
    japan = request.form.get("japan")
    korea = request.form.get("korea")
    hongkong = request.form.get("hongkong")
    singapore = request.form.get("singapore")
    shanghai = request.form.get("shanghai")
    zhoushan = request.form.get("zhoushan")


    # 讀取 CSV 檔案
    csv_file_path = "processed_data.csv"  # 替換為你的 CSV 路徑
    df = pd.read_csv(csv_file_path)

    # 確保日期欄位正確轉換為 datetime 格式
    df['date'] = pd.to_datetime(df['日期'], format="%Y/%m/%d")

    # 移除無效的日期值
    df = df.dropna(subset=['date'])
       
    # 將值儲存到字典，便於後續處理
    inputs = {
        "日本": float(japan) if japan else None,
        "南韓": float(korea) if korea else None,
        "香港": float(hongkong) if hongkong else None,
        "新加坡": float(singapore) if singapore else None,
        "上海": float(shanghai) if shanghai else None,
        "舟山": float(zhoushan) if zhoushan else None,
        
    }

    # 計算非空欄位的平均值
    non_empty_values = [value for value in inputs.values() if value is not None]
    average_value = sum(non_empty_values) / len(non_empty_values) if non_empty_values else 0

    # 將空值替換為平均值
    for key, value in inputs.items():
        if value is None:
            inputs[key] = average_value

    # 建立預測資訊
    predict_info = [{
        **inputs,  # 展開計算後的輸入值
       
    }]

    # 發送 API 請求並獲取預測結果
    api_token = "37d9fd65-77d5-464f-8038-3cfee4d525de"
    get_api_path = send_api_request(predict_info,api_token)
    predicted_value = poll_prediction_result(get_api_path)

    return render_template("tukey_result.html",
                result_val=predicted_value,
                j=japan,k=korea,h=hongkong,
                s=singapore,sh=shanghai,zh=zhoushan)



###################### tukey_append ################################
# @tukey_bp.route("/tukey_append", methods=["POST"])
# def tukey_append():

#     date = request.form.get("date")
#     japan = float(request.form.get("japan"))  # 假設日本欄位是浮點數
#     korea = float(request.form.get("korea"))
#     hongkong = float(request.form.get("hongkong"))
#     singapore = float(request.form.get("singapore"))
#     shanghai = float(request.form.get("shanghai"))
#     zhoushan = float(request.form.get("zhoushan"))


#     # 插入資料的 SQL
#     query = """
#         INSERT INTO aviation_prediction (日期, 日本, 南韓, 香港, 新加坡, 上海, 舟山, BRENT_Close, WTI_Close, CPC)
#         VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
#     """

#     try:
#         conn = pymssql.connect(
#         server='REMOVED_INFORMATION', user=r'cpc\REMOVED_NUM', password=r'REMOVED_INFO',  database='BDC_TEST'
#         )
#         cursor = conn.cursor()
#         cursor.execute(query, (date, japan, korea, hongkong, singapore, shanghai, zhoushan,600,600,600))
#         conn.commit()
#         flash("資料已成功新增到資料庫！", "success")
#     except Exception as e:
#         flash(f"新增資料時發生錯誤：{e}", "danger")
#     finally:
#         conn.close()

#     return render_template("index.html")



# @tukey_bp.route("/tukey_append", methods=["POST"])
# def tukey_append():
    
    # date=request.form.get("date")
    # japan = request.form.get("japan")
    # korea = request.form.get("korea")
    # hongkong = request.form.get("hongkong")
    # singapore = request.form.get("singapore")
    # shanghai = request.form.get("shanghai")
    # zhoushan = request.form.get("zhoushan")

    # conn = pymssql.connect(server='REMOVED_INFORMATION', user=r'cpc\REMOVED_NUM', password=r'REMOVED_INFO',  database='BDC_TEST')
    # cursor = conn.cursor(as_dict=True)  # 以字典格式獲取結果，方便處理

    # # 查詢最接近的日期的資料
    # query = """
    #     SELECT TOP 1 *
    #     FROM aviation_prediction
    #     WHERE 日期 < %s  -- 只選擇比輸入日期小的
    #     ORDER BY 日期 DESC
    # """

    # try:
    #     cursor.execute(query, (date,))
    #     result = cursor.fetchone()  # 取得最接近的那筆資料
    #     if result:
    #         print("最近的資料:", result)
    #     else:
    #         print("找不到符合的資料")

    # except Exception as e:
    #     print(f"查詢時發生錯誤: {e}")

    # finally:
    #     cursor.close()
    #     conn.close()

    # inputs = {
    #     "日本": float(japan) if japan else None,
    #     "南韓": float(korea) if korea else None,
    #     "香港": float(hongkong) if hongkong else None,
    #     "新加坡": float(singapore) if singapore else None,
    #     "上海": float(shanghai) if shanghai else None,
    #     "舟山": float(zhoushan) if zhoushan else None,
        
    # }

    # # 計算非空欄位的平均值
    # non_empty_values = [value for value in inputs.values() if value is not None]
    # average_value = sum(non_empty_values) / len(non_empty_values) if non_empty_values else 0

    # # 將空值替換為平均值
    # for key, value in inputs.items():
    #     if value is None:
    #         inputs[key] = average_value

    # # 建立預測資訊
    # predict_info = [{
    #     "日期": date,
    #     **inputs,  
    #     # "BRENT_Close":BRENT_Close,
    #     # "WTI_Close":WTI_Close,
    #     # "DUBAI_Close":DUBAI_Close,
    #     "y_lag_1": float(result['CPC']),  # 將 float64 轉換為普通的 float
    #     "y_lag_2": float(result['y_lag_1']), 
    #     "y_lag_3": float(result['y_lag_2']),
    # }]
    # print("predict_info",predict_info)




    # # 連接資料庫
    # # conn = pymssql.connect(
    # #     server='你的SQLServer伺服器',
    # #     user='你的帳號',
    # #     password='你的密碼',
    # #     database='你的資料庫'
    # # )
    # conn = pymssql.connect(server='REMOVED_INFORMATION', user=r'cpc\REMOVED_NUM', password=r'REMOVED_INFO',  database='BDC_TEST')
    # cursor = conn.cursor()

    # # 取得 predict_info 第一筆資料
    # data = predict_info[0]

    # # SQL 插入語句
    # query = """
    #     INSERT INTO aviation_prediction (
    #         日期, 日本, 南韓, 香港, 新加坡, 上海, 舟山, y_lag_1, y_lag_2, y_lag_3
    #     ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    # """

    # # 轉換日期格式（確保是字串）
    # # if isinstance(data["日期"], datetime):
    # #     data["日期"] = data["日期"].strftime("%Y-%m-%d")

    # # 執行 SQL 插入
    # try:
    #     cursor.execute(query, (
    #         data["日期"], 
    #         data["日本"], data["南韓"], data["香港"], 
    #         data["新加坡"], data["上海"], data["舟山"],
    #         data["y_lag_1"], data["y_lag_2"], data["y_lag_3"]
    #     ))

    #     conn.commit()  # 提交更改
    #     print("✅ 資料成功寫入資料庫！")

    # except Exception as e:
    #     print(f"❌ 插入資料時發生錯誤：{e}")
    #     conn.rollback()  # 取消更改（如果有錯誤）

    # finally:
    #     cursor.close()
    #     conn.close()  # 關閉連線

 


