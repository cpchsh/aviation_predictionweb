# app/routes/main_routes.py
from flask import Blueprint, render_template, request, redirect, url_for
import os, pandas as pd
import joblib

# 建立 Blueprint 物件
main_bp = Blueprint('main_bp', __name__)

# 可能還需要載入你的 XGB 函式
# from app import predict_next_day_xgb

#======================#
#   1) 載入 XGB 模型   #
#======================#
# 假設你已在其他地方用 joblib.dump(xgb_model, "xgb_model.pkl")
# 並把檔案放在專案根目錄
xgb_model_path = "./xgb_model_new.pkl"
xgb_model = joblib.load(xgb_model_path)

#======================#
#   2) 預測下一天CPC (XGB) #
#======================#
def predict_next_day_xgb(xgb_model):
    """
    用XGB預測下一天
    具體做法:
     - 從資料庫/檔案中抓最新特徵(含lag等)
     - xgb_model.predict([features]) -> y_pred
    """
    # 假設 features = [ .. ]，維度要跟訓練時一致
    file_path = './資料集_new.csv'
    data = pd.read_csv(file_path)

    # 去除列名空白
    data.columns = data.columns.str.strip()

    # 假設欄位為這些，若有需要請自行 rename
    data.rename(columns={
        '日期': 'ds',
        'CPC': 'y',
        '日本': 'japan',
        '南韓': 'korea',
        '香港': 'hongkong',
        '新加坡': 'singapore',
        '上海': 'shanghai',
        '舟山': 'zhoushan'
    }, inplace=True)

    data['ds'] = pd.to_datetime(data['ds'])
    data.sort_values(by='ds', inplace=True)  # 依日期排序
    # 如果有缺失值，先補一下
    data[['y','japan','korea','hongkong','singapore','shanghai','zhoushan']] = \
        data[['y','japan','korea','hongkong','singapore','shanghai','zhoushan']].ffill().bfill()

    N_LAGS = 3

    for i in range(1, N_LAGS+1):
        data[f'y_lag_{i}'] = data['y'].shift(i)
    # 去掉有 NaN（因為 shift 後前幾筆沒值）
    data.dropna(inplace=True)

    #print(data.tail(10))
    # 測試預測
    # predictions = loaded_model.predict(X[:5])
    # print("Predictions:", predictions)
    last_row = data.iloc[-1]  # 取最後一天記錄
    X_future = pd.DataFrame([{
        'japan': last_row['japan'],  # 當天 or 預估的外生變數
        'korea': last_row['korea'],
        'hongkong': last_row['hongkong'],
        'singapore': last_row['singapore'],
        'shanghai': last_row['shanghai'],
        'zhoushan': last_row['zhoushan'],
        # 其他外生欄位...
        'y_lag_1': last_row['y'],       # 最後一天本身的 y 當 lag_1
        'y_lag_2': last_row['y_lag_1'], # 以此類推
        'y_lag_3': last_row['y_lag_2']
    }])

    # 用模型預測未來一天 (下一天) 的 CPC
    y_pred = xgb_model.predict(X_future)[0]
    return y_pred

@main_bp.route("/", methods=["GET"])
def index():
    # 1) 用 XGB 預測下一天
    next_day_pred = predict_next_day_xgb(xgb_model)
    next_day_pred_str = f"{next_day_pred:.2f}"  # 格式化
    
    # 1) 讀取預測結果 CSV (latest_forecast.csv)
    if os.path.exists("./latest_forecast.csv"):
        forecast = pd.read_csv("latest_forecast.csv",encoding="utf-8-sig")
        forecast.columns = forecast.columns.str.strip()  # 去除欄位名稱前後的空白
        # 取最後 7 天的預測
        future_part = forecast.tail(7)[['ds', 'yhat', 'yhat_lower', 'yhat_upper']]
        # 重新命名欄位名稱
        future_part = future_part.rename(columns={
            'ds': '日期',
            'yhat': '預測值',
            'yhat_lower': '預測信賴區間下界',
            'yhat_upper': '預測信賴區間上界'
        })
        print("Renamed columns:", future_part.columns.tolist(), flush=True)
        print("future_part",future_part)
        value = future_part.iloc[0,1]
        f_value = f"{value:.2f}"
        f_day = future_part.iloc[0,0]
        future_table_html = future_part.to_html(classes="table custom-table text-center", index=False)
    else:
        f_day = "N/A"
        f_value="N/A"
        future_table_html = "<p>No forecast data found. Please check if the offline script has run.</p>"
    
    # 2)圖檔檢查
    plot_full_url = "/static/plot_full.png" if os.path.exists("app/static/plot_full.png") else ""
    plot_recent_url = "/static/plot_recent_future.png" if os.path.exists("app/static/plot_recent_future.png") else ""
    
    return render_template("index.html",
                           next_day=f_day,
                           xgb_pred=next_day_pred_str,
                           prophet_fvalue=f_value,
                           future_table_html=future_table_html,
                           plot_full_url=plot_full_url,
                           plot_recent_url=plot_recent_url)
