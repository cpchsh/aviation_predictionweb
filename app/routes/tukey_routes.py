from flask import Blueprint, render_template, request,session
import joblib
import pandas as pd
import os
import time
import requests
from datetime import datetime
tukey_bp = Blueprint('tukey_bp', __name__)


############# 含日期 ####################
@tukey_bp.route("/tukey_form", methods=["GET"])
def tukey_input_form():
    """
    顯示自訂 Tukey 預測的表單
    """
    return render_template("tukey_form.html")

@tukey_bp.route("/tukey_predict", methods=["POST"])
def tukey_predict_custom():
     # Step 1: 輸入api_token
    api_token = "3babb936-d258-44bc-981e-e4c358055ad7"  # 請替換成您的 api_token

    # Step 2: 載入要預測的資料
    # 從表單中提取數值
    date=request.form.get("date")
    japan = request.form.get("japan")
    korea = request.form.get("korea")
    hongkong = request.form.get("hongkong")
    singapore = request.form.get("singapore")
    shanghai = request.form.get("shanghai")
    zhoushan = request.form.get("zhoushan")

    print(date)


   # 將表單日期轉換為 datetime 格式
    form_date = datetime.strptime(date, "%Y-%m-%d")
    print(date)

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

    # Step 3: 發送 POST 請求
    # 設定您的 API 網址 (例如內網服務或域名)
    post_api_path = "http://10.16.32.97:8098/tukey/tukey/api/"
    request_json = {"api_token": api_token, "data": predict_info}

    print("開始發送 POST 請求...")
    print(predict_info)
    post_result = requests.post(post_api_path, json=request_json, headers={"Content-Type": "application/json"})
    post_result.raise_for_status()  # 若請求出現 HTTP 錯誤則拋出例外
    post_result_json = post_result.json()

    # 取得返回的查詢連結 (假設 API 返回的 JSON 格式中有 "link" 項)
    get_api_path = post_result_json.get("link")
    if not get_api_path:
        raise Exception("POST 請求未返回查詢連結！請檢查 API 回應格式。")

    print("POST 請求成功，查詢連結：", get_api_path)

    # Step 4: 輪詢獲取結果，等待預測完成，超過 30 分鐘則拋出例外
    time_limit = 60 * 30  # 30 分鐘
    time_start = time.time()

    while True:
        current_time = time.time()
        if current_time - time_start >= time_limit:
            raise Exception("預測失敗：請求超過時間限制")

        response = requests.get(get_api_path)
        response.raise_for_status()
        result_json = response.json()

        predicted_data = result_json.get("data")
        status = predicted_data.get("status") if predicted_data else None

        if status == "success":
            print("預測成功：")
            print(predicted_data)
            result = predicted_data['indv'][0]['value']
            print(result)  # 642.8
            break
        elif status == "fail":
            raise Exception("預測失敗")
        else:
            print("預測中，等待中...")
            time.sleep(3)  # 每 3 秒輪詢一次
    return render_template("tukey_result.html",date=date,
                result_val=result,
                j=japan,k=korea,h=hongkong,
                s=singapore,sh=shanghai,zh=zhoushan)

############# 不含日期 ####################
@tukey_bp.route("/tukey_form_noDate", methods=["GET"])
def tukey_input_form_noDate():
    """
    顯示自訂 Tukey 預測的表單
    """
    return render_template("tukey_form_noDate.html")

@tukey_bp.route("/tukey_predict_noDate", methods=["POST"])
def tukey_predict_noDate():
     # Step 1: 輸入api_token
    api_token = "37d9fd65-77d5-464f-8038-3cfee4d525de"  # 請替換成您的 api_token

    # Step 2: 載入要預測的資料
    # 從表單中提取數值
    
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

    # Step 3: 發送 POST 請求
    # 設定您的 API 網址 (例如內網服務或域名)
    post_api_path = "http://10.16.32.97:8098/tukey/tukey/api/"
    request_json = {"api_token": api_token, "data": predict_info}

    print("開始發送 POST 請求...")
    print(predict_info)
    post_result = requests.post(post_api_path, json=request_json, headers={"Content-Type": "application/json"})
    post_result.raise_for_status()  # 若請求出現 HTTP 錯誤則拋出例外
    post_result_json = post_result.json()

    # 取得返回的查詢連結 (假設 API 返回的 JSON 格式中有 "link" 項)
    get_api_path = post_result_json.get("link")
    if not get_api_path:
        raise Exception("POST 請求未返回查詢連結！請檢查 API 回應格式。")

    print("POST 請求成功，查詢連結：", get_api_path)

    # Step 4: 輪詢獲取結果，等待預測完成，超過 30 分鐘則拋出例外
    time_limit = 60 * 30  # 30 分鐘
    time_start = time.time()

    while True:
        current_time = time.time()
        if current_time - time_start >= time_limit:
            raise Exception("預測失敗：請求超過時間限制")

        response = requests.get(get_api_path)
        response.raise_for_status()
        result_json = response.json()

        predicted_data = result_json.get("data")
        status = predicted_data.get("status") if predicted_data else None

        if status == "success":
            print("預測成功：")
            print(predicted_data)
            result = predicted_data['indv'][0]['value']
            print(result)  # 642.8
            result = round(result, 2)
            print(result)
            break
        elif status == "fail":
            raise Exception("預測失敗")
        else:
            print("預測中，等待中...")
            time.sleep(3)  # 每 3 秒輪詢一次
    return render_template("tukey_result.html",
                result_val=result,
                j=japan,k=korea,h=hongkong,
                s=singapore,sh=shanghai,zh=zhoushan)
# def predict_next_day_tukey():
#     """
#     讀取data, 建立lag, 取最後一列-> tukey預測
#     """
#     file_path='./資料集_new.csv'
#     data=pd.read_csv(file_path)
#     data.columns=data.columns.str.strip()
#     data.rename(columns={
#         '日期': 'ds', 'CPC': 'y',
#         '日本': 'japan', '南韓': 'korea', '香港': 'hongkong',
#         '新加坡': 'singapore', '上海': 'shanghai', '舟山': 'zhoushan'
#     }, inplace=True)

#     data['ds'] = pd.to_datetime(data['ds'])
#     data.sort_values(by='ds', inplace=True)
#     data[['y','japan','korea','hongkong','singapore','shanghai','zhoushan']] = \
#         data[['y','japan','korea','hongkong','singapore','shanghai','zhoushan']].ffill().bfill()
    
#     N_LAGS = 3
#     for i in range(1, N_LAGS+1):
#         data[f'y_lag_{i}'] = data['y'].shift(i)
#     data.dropna(inplace=True)

#     last_row = data.iloc[-1]
#     X_future = pd.DataFrame([{
#         'japan':     last_row['japan'],
#         'korea':     last_row['korea'],
#         'hongkong':  last_row['hongkong'],
#         'singapore': last_row['singapore'],
#         'shanghai':  last_row['shanghai'],
#         'zhoushan':  last_row['zhoushan'],
#         'y_lag_1':   last_row['y'],
#         'y_lag_2':   last_row['y_lag_1'],
#         'y_lag_3':   last_row['y_lag_2']
#     }])

    # y_pred = tukey_model.predict(X_future)[0]
    # return y_pred
