from flask import Blueprint, render_template, request, render_template, jsonify,url_for
import pandas as pd
import os
import time
import requests
import pymssql
from datetime import date,datetime, timedelta
from dotenv import load_dotenv

tukey_bp = Blueprint('tukey_bp', __name__)

# 讀取 .env 文件
load_dotenv()
server = os.getenv("DB_SERVER")
user = os.getenv("DB_USER")
password = os.getenv("DB_PASSWORD")
database = os.getenv("DB_NAME")
api_token = os.getenv("TUKEY_API") # 0502_2025 bys->訓練到20250402


def getInput():
    record = {
        "日期": request.form.get("date"),
        "日本": request.form.get("japan"),
        "南韓": request.form.get("korea"),
        "香港": request.form.get("hongkong"),
        "新加坡": request.form.get("singapore"),
        "上海": request.form.get("shanghai"),
        "舟山": request.form.get("zhoushan"),
        "CPC": request.form.get("cpc")
    }
    print(record)
    return record

def update_CPC_ylag(record,latest_data):
    latest_data = latest_data[0]
    print(latest_data)
    if latest_data["CPC"] is None:
        return {"status": "error", "message": f"❌ 空值錯誤：尚未更新{latest_data["日期"]}的CPC值，請確認！"}

    # 新增 y_lag 欄位
    record["y_lag_1"] = float(latest_data["CPC"])
    record["y_lag_2"] = float(latest_data["y_lag_1"])
    record["y_lag_3"] = float(latest_data["y_lag_2"])
    return record

def fetch_latest_data(cursor, date, limit=1, condition="<"):
    """ 查詢最新 N 筆資料，條件可變 """
    query = f"""
        SELECT TOP {limit} 日期, 日本, 南韓, 香港, 新加坡, 上海, 舟山, y_lag_1, y_lag_2, y_lag_3, CPC
        FROM LSMF_Prediction
        WHERE 日期 {condition} %s
        ORDER BY 日期 DESC
    """
    cursor.execute(query, (date,))
    return cursor.fetchall()

def insert_or_update(cursor, input_data):
    """ 檢查資料是否存在，若無則插入，否則更新 """
    
    # 將空字串或 0 轉換為 None（SQL 的 NULL）
    for key in input_data:
        if input_data[key] == "" or input_data[key] == 0:
            input_data[key] = None

    query_check = """
        SELECT COUNT(*) FROM LSMF_Prediction WHERE 日期 = %s
    """
    cursor.execute(query_check, (input_data["日期"],))
    exists = cursor.fetchone()[0] > 0  # 檢查是否有資料

    if exists:
        # **動態生成更新 SQL**
        update_fields = []
        update_values = []
        
        for key, value in input_data.items():
            if key != "日期" and value is not None:  # 忽略日期，且只更新有輸入的欄位
                update_fields.append(f"{key} = %s")
                update_values.append(value)

        if update_fields:
            query_update = f"""
                UPDATE LSMF_Prediction
                SET {", ".join(update_fields)}
                WHERE 日期 = %s
            """
            update_values.append(input_data["日期"])  # 日期作為 WHERE 條件
            cursor.execute(query_update, tuple(update_values))
            print(f"✅ 已更新 {input_data['日期']} 的數據")

    else:
        # **動態生成插入 SQL**
        columns = []
        values_placeholder = []
        values = []

        for key, value in input_data.items():
            if value is not None:  # 只插入有輸入的欄位，未輸入的為 NULL
                columns.append(key)
                values_placeholder.append("%s")
                values.append(value)

        query_insert = f"""
            INSERT INTO LSMF_Prediction ({", ".join(columns)})
            VALUES ({", ".join(values_placeholder)})
        """
        cursor.execute(query_insert, tuple(values))
        print(f"✅ 已插入新數據：{input_data['日期']}")


def DB_update_null_values(cursor, conn, record):
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
        UPDATE LSMF_Prediction
        SET {", ".join(f"{col} = ISNULL({col}, %s)" for col in null_columns)}
        WHERE 日期 = %s
    """
    cursor.execute(update_query, tuple([avg_value] * len(null_columns) + [record["日期"]]))
    conn.commit()
    return True  

def update_null_values(record):
   
    fields = ["日本", "南韓", "香港", "新加坡", "上海", "舟山"]

    # 轉換空字串為 None，確保能正確篩選空值
    for key in fields:
        if record[key] == "":
            record[key] = None

    # 找出非空值並轉換為 float
    non_null_values = [float(record[col]) for col in fields if record[col] is not None]

    # 計算平均值
    avg_value = sum(non_null_values) / len(non_null_values) if non_null_values else 0  # 避免除以 0

    # 填補空值
    for col in fields:
        if record[col] is None:
            record[col] = avg_value  # 確保數值統一為 float
    return record

def update_ylag(cursor, conn, latest, second_latest):
    """ 更新 `y_lag` 欄位 """
    if not second_latest or all(latest[key] is not None for key in ["y_lag_1", "y_lag_2", "y_lag_3"]):
        return False  # 無需更新

    update_query = """
        UPDATE LSMF_Prediction
        SET y_lag_1 = %s, y_lag_2 = %s, y_lag_3 = %s
        WHERE 日期 = %s
    """    
    cursor.execute(update_query, (second_latest["CPC"], second_latest["y_lag_1"], second_latest["y_lag_2"], latest["日期"]))
    conn.commit()
    return True  

def update_predictCPC(cursor, conn, predictCPC, latest):
    update_query = """
        UPDATE LSMF_Prediction
        SET predictCPC = %s
        WHERE 日期 = %s
    """    
    cursor.execute(update_query, (predictCPC, latest["日期"]))
    conn.commit()
    return True

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

def close_connection(conn, cursor):
    """ 關閉資料庫連線 """
    try:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    except Exception as e:
        print(f"⚠️ 關閉連線時發生錯誤: {e}")

"""
新增/更新資料
"""
@tukey_bp.route("/update_form", methods=["GET"])
def update_form():
    conn = pymssql.connect(server=server, user=user, password=password, database=database)
    cursor = conn.cursor(as_dict=True)
    # today = date.today().strftime("%Y-%m-%d")
    today = date.today()
   
    print(today)
    data=fetch_latest_data(cursor,today)
    # print(data)
    # print(data[0])
    if data[0]['CPC'] is not None:
        description="更新"
        maxDate=today - timedelta(days=1)
        minDate=data[0]['日期']
    else:
        description="新增"
        maxDate=data[0]['日期']
        minDate=maxDate
    cpcDate=data[0]['日期']


    return render_template("update_form.html",description=description,cpcDate=cpcDate,price=data[0]['CPC'],maxDate=maxDate,minDate=minDate)

@tukey_bp.route("/update", methods=["POST"])
def update():
    conn = pymssql.connect(server=server, user=user, password=password,  database=database)
    cursor = conn.cursor(as_dict=True)  # 以字典格式獲取結果，方便處理

    today = date.today().strftime("%Y-%m-%d")

    input=getInput()
    confirmUpdate = request.form.get("confirmUpdate") == "true"

    try:
        if "CPC" in input and input["CPC"]:
            print(input["CPC"])
            latest_data = fetch_latest_data(cursor, today)
            input["日期"] = latest_data[0]["日期"]

            # **更新最新一筆的 CPC 值**
            query_update_cpc = """
                UPDATE LSMF_Prediction
                SET CPC = %s
                WHERE 日期 = %s
            """
            cursor.execute(query_update_cpc, (input["CPC"], input["日期"]))
            conn.commit()  
            # print(f"✅ 已更新 {input['日期']} 的 CPC 值為 {input['CPC']}")
            return jsonify({
                        "status": "insert_success",
                        # "message": f"✅ 已更新 {input['日期']} 的 CPC 值為 {input['CPC']}",
                        "message": f"✅ 已更新決策的 CPC 值為 {input['CPC']}",
                        "redirect": url_for("main_bp.index")
                    })
            
        else:
            checkInput = datetime.strptime(input["日期"], "%Y-%m-%d").date()
            latest_data = fetch_latest_data(cursor, today)
            latest_data = latest_data[0]["日期"]
            
            if checkInput<latest_data:
                return jsonify({"status": "error","message": f"❌ 日期不可比{latest_data}還小"}) 
            else:
                cursor = conn.cursor()
                check=fetch_latest_data(cursor,input['日期'],condition='=')
             
                if check and not confirmUpdate:
                    check=check[0]
                    headers = ["日期", "日本", "南韓", "香港", "新加坡", "上海", "舟山"]
                    table_html = "<table class='table' style='color: black; font-size: 11pt; '>"
                    table_html += f"<tr><td class='table-secondary' style='width: 100px; text-align: left; '>{headers[0]}</td><td>{check[0]}</td></tr>"
                    table_html += f"<tr><td class='table-secondary' style='width: 100px; text-align: left; '>{headers[1]}</td><td>{check[1]}</td></tr>"
                    table_html += f"<tr><td class='table-secondary' style='width: 100px; text-align: left; '>{headers[2]}</td><td>{check[2]}</td></tr>"
                    table_html += f"<tr><td class='table-secondary' style='width: 100px; text-align: left; '>{headers[3]}</td><td>{check[3]}</td></tr>"
                    table_html += f"<tr><td class='table-secondary' style='width: 100px; text-align: left; '>{headers[4]}</td><td>{check[4]}</td></tr>"
                    table_html += f"<tr><td class='table-secondary' style='width: 100px; text-align: left; '>{headers[5]}</td><td>{check[5]}</td></tr>"
                    table_html += f"<tr><td class='table-secondary' style='width: 100px; text-align: left; '>{headers[6]}</td><td>{check[6]}</td></tr>"
                    table_html += "</table>"
                   
                    return jsonify({
                        "status": "update_check",
                        "message": f"⚠️ {check[0]} 已有資料，是否更新？(僅更新有輸入的欄位)<br><br>{table_html}",
                        # "redirect": url_for("main_bp.index")
                    })
                elif check and confirmUpdate:
                    insert_or_update(cursor, input)
                    conn.commit()  
                    return jsonify({
                        "status": "update_success",
                        "message": "✅ 更新成功",
                        "redirect": url_for("main_bp.index")
                    })
                else:
                    checkCPC=fetch_latest_data(cursor,input['日期'],condition='<')
                    print(checkCPC)
                    if checkCPC[0][-1] is not None:
                        insert_or_update(cursor, input)
                        conn.commit()  
                        return jsonify({
                            "status": "insert_success",
                            "message": "✅ 插入成功",
                            "redirect": url_for("main_bp.index")
                        })
                    else:
                        return jsonify({
                            "status": "error",
                            "message": f"請先新增 {checkCPC[0][0]} CPC油價",
                        })


    except Exception as e:
        conn.rollback()
        print(f"❌ 操作失敗: {e}")
    finally:
        close_connection(conn, cursor)

    return render_template("index.html")         
        
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
        result = fetch_latest_data(cursor, today,2)
        if not result:
            print("❌ 找不到符合的資料")
            return None
        else:
            print('📜 最新兩筆資料:',"\n",today,result[0],"\n",result[1])

        latest_record, second_latest = result[0], result[1] if len(result) > 1 else None
        # predicted_results.append(latest_record["日期"])
        predicted_results.append(today)

        # **更新空值**
        if DB_update_null_values(cursor, conn, latest_record):
            print("✅ 成功更新空值")
        else:
            print("📌 無需更新空值")

        # **更新 ylag**
        if update_ylag(cursor, conn, latest_record, second_latest):
            print("✅ 成功更新 ylag")
        else:
            print("📌 無需更新 ylag")

        # 2.取得更新後資料進行預測
        predict_info = fetch_latest_data(cursor, today)
        for key in ["日期", "CPC"]:
            predict_info[0].pop(key, None)

       
        if not predict_info:
            print("❌ 無法查詢最新數據")
            return None
        else:
            print("📜 predict_info",predict_info)

        # 3.發送 API 請求並獲取預測結果
        # api_token = "37d9fd65-77d5-464f-8038-3cfee4d525de" #無ylag
        # "3babb936-d258-44bc-981e-e4c358055ad7" 有ylag old knn

        get_api_path = send_api_request(predict_info,api_token)
        predicted_value = poll_prediction_result(get_api_path)
        if predicted_value:
            update_predictCPC(cursor, conn,predicted_value,latest_record)
            print("✅ 成功更新預測值")

            predicted_results.append(predicted_value)
        return predicted_results

    except Exception as e:
        print(f"❌ 發生錯誤: {e}")
        return None

    finally:
        close_connection(conn, cursor)
       

        
"""
自訂 Tukey 輸入表單(含日期)
"""
@tukey_bp.route("/tukey_form", methods=["GET"])
def tukey_input_form():
    
    return render_template("tukey_form.html")

@tukey_bp.route("/tukey_predict", methods=["POST"])
def tukey_predict_custom():

    # conn = pymssql.connect(server='REMOVED_INFORMATION', user=r'cpc\REMOVED_NUM', password=r'REMOVED_INFO',  database='BDC_TEST')
    conn = pymssql.connect(server=server, user=user, password=password,  database=database)
    cursor = conn.cursor(as_dict=True)  # 以字典格式獲取結果，方便處理

    input=getInput()
    latest_data = fetch_latest_data(cursor, input["日期"])   #這邊待確

    predict_info=update_null_values(input.copy())  
    
    predict_info=update_CPC_ylag(predict_info,latest_data)

    if isinstance(predict_info, dict) and predict_info.get("status") == "error":    #CPC 欄位為空值
        return jsonify(predict_info)  
    
    print("📜 predict_info",predict_info)

    # 發送 API 請求並獲取預測結果
    predict_info.pop("日期", None)  # 移除 "日期"
    predict_info = [predict_info]

    get_api_path = send_api_request(predict_info,api_token)
    predicted_value = poll_prediction_result(get_api_path)

    #用input顯示值，非predic_info
    return render_template("tukey_result.html",date=input["日期"],
                result_val=predicted_value,
                j=input["日本"],k=input["南韓"],h=input["香港"],
                 s=input["新加坡"],sh=input["上海"],zh=input["舟山"])  



"""
自訂 Tukey 輸入表單(不含日期)
"""
@tukey_bp.route("/tukey_form_noDate", methods=["GET"])
def tukey_input_form_noDate():
    """
    顯示自訂 Tukey 預測的表單
    """
    return render_template("tukey_form_noDate.html")

@tukey_bp.route("/tukey_predict_noDate", methods=["POST"])
def tukey_predict_noDate():
   
    input=getInput()
   
    predict_info=update_null_values(input.copy())  
    
    print("📜 predict_info",predict_info)

    # 發送 API 請求並獲取預測結果
    api_token = "37d9fd65-77d5-464f-8038-3cfee4d525de" #無ylag

    predict_info.pop("日期", None)  # 移除 "日期"
    predict_info = [predict_info]

    get_api_path = send_api_request(predict_info,api_token)
    predicted_value = poll_prediction_result(get_api_path)

    #用input顯示值，非predic_info
    return render_template("tukey_result.html",
                result_val=predicted_value,
                j=input["日本"],k=input["南韓"],h=input["香港"],
                 s=input["新加坡"],sh=input["上海"],zh=input["舟山"])  



# """
# 新增/更新"最新"資料並預測
# """
# @tukey_bp.route("/tukey_append", methods=["POST"])
# def tukey_append():

#     # conn = pymssql.connect(server='REMOVED_INFORMATION', user=r'cpc\REMOVED_NUM', password=r'REMOVED_INFO',  database='BDC_TEST')
#     conn = pymssql.connect(server=server, user=user, password=password,  database=database)
#     cursor = conn.cursor(as_dict=True)  # 以字典格式獲取結果，方便處理

#     today = date.today().strftime("%Y-%m-%d")

#     input=getInput()
#     latest_data = fetch_latest_data(cursor, today)  

#     predict_info=update_null_values(input.copy())
   
#     predict_info=update_CPC_ylag(predict_info,latest_data)

#     if isinstance(predict_info, dict) and predict_info.get("status") == "error":
#         return jsonify(predict_info)
#     else:

#     # print("predict_info",predict_info)

#         # 發送 API 請求並獲取預測結果
#         api_token = "3babb936-d258-44bc-981e-e4c358055ad7"
#         insertData = predict_info.copy()


#         predict_info.pop("日期", None)  # 移除 "日期"
#         predict_info = [predict_info]

#         get_api_path = send_api_request(predict_info,api_token)
#         predicted_value = poll_prediction_result(get_api_path)

#         # SQL 插入語句
#         query = """
#         INSERT INTO aviation_prediction (
#             日期, 日本, 南韓, 香港, 新加坡, 上海, 舟山, y_lag_1, y_lag_2, y_lag_3
#         ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
#         """

#         # 轉換 predict_info 為 tuple，並確保數據類型正確
#         values = [
#             insertData["日期"],
#             float(insertData["日本"]),
#             float(insertData["南韓"]),
#             float(insertData["香港"]),
#             float(insertData["新加坡"]),
#             float(insertData["上海"]),
#             float(insertData["舟山"]),
#             float(insertData["y_lag_1"]),
#             float(insertData["y_lag_2"]),
#             float(insertData["y_lag_3"]),
#         ]

#         try:
#             cursor.execute(query, values)
#             conn.commit()  # 提交變更
#             print("✅ 資料成功寫入資料庫！")
            

#         except Exception as e:
#             conn.rollback()
#             error_msg = str(e)

#             if "duplicate" in error_msg.lower() or "primary key" in error_msg.lower():
#                 return jsonify({
#                     "status": "error",
#                     "message": f"❌ 該日期已存在，請使用其他日期！<br> <span style='color: red; '>預測值: {predicted_value}</span>"
#                 })
#             else:
#                 return jsonify({
#                     "status": "error",
#                     "message": f"❌ 發生錯誤：{error_msg} <br> <span style='color: red; '>預測值: {predicted_value}</span>"
#                 })

#         finally:
#             try:
#                 if 'cursor' in locals() and cursor:
#                     cursor.close()
#                 if 'conn' in locals() and conn:
#                     conn.close()
#             except Exception as e:
#                 print(f"⚠️ 關閉連線時發生錯誤: {e}")

#     #用input顯示值，非predic_info
#     return render_template("tukey_result.html",date=input["日期"],
#                 result_val=predicted_value,
#                 j=input["日本"],k=input["南韓"],h=input["香港"],
#                 s=input["新加坡"],sh=input["上海"],zh=input["舟山"])  





