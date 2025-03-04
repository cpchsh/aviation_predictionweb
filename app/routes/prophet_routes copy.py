from flask import Blueprint, jsonify
import pandas as pd
import os
import subprocess
import sys

prophet_bp = Blueprint('prophet_bp', __name__)

@prophet_bp.route("/append_and_train", methods = ["POST"])
def append_and_train():
    """
    1)讀取 collectedata/temdata.csv & 資料集_new.csv
      - 若tempdata日期比現有最新日期更新 => append
      - 否則不動
    2) 執行 train_prophet.py (subprocess)
    3) 回傳 json
    """
    temp_path = "./collectedata/tempdata.csv"
    data_path = "./資料集_new.csv"

    if not os.path.exists(temp_path):
        return jsonify({"message": "Tempdata CSV not found!"}), 400
    if not os.path.exists(data_path):
        return jsonify({"message": "資料集 CSV not found!"}), 400
    
    temp_df = pd.read_csv(temp_path, header=None)
    temp_df.columns = ['日期', '日本', '南韓', '香港', '新加坡', '上海', '舟山', 'CPC']
    data_df = pd.read_csv(data_path)
    data_df.columns = data_df.columns.str.strip()

    temp_df['日期'] = pd.to_datetime(temp_df['日期'])
    data_df['日期'] = pd.to_datetime(data_df['日期'])

    temp_df.sort_values('日期', inplace=True)
    data_df.sort_values('日期', inplace=True)

    last_date = data_df['日期'].max()
    first_temp_date = temp_df.iloc[0]['日期']

    if first_temp_date > last_date:
        appended_df = pd.concat([data_df, temp_df], ignore_index=True)
        appended_df.sort_values('日期', inplace=True)
        appended_df.to_csv(data_path, index=False)
        msg = f"New data appended successfully! (First day={first_temp_date.date()})"
    else:
        msg = f"No update. (tempdata first day={first_temp_date.date()} not > last data day={last_date.date()})"

    # 執行 train_prophet.py
    try:
        subprocess.run([sys.executable, "train_prophet.py"], check=True)
        msg += " - Train completed!"
        return jsonify({"message": msg}), 200
    except subprocess.CalledProcessError as e:
        msg += f" - Train script failed: {e}"
        return jsonify({"message": msg}), 500
    
@prophet_bp.route("/api/prophet_forecast", methods=["GET"])
def get_forecast_json():
    """
    回傳 Prophet 預測的 (全部) 資料
    以 JSON 格式給前端 Chart.js使用
    """
    if not os.path.exists("latest_forecast.csv"):
        return jsonify({"error": "No forecast data found"}), 404
    
    df = pd.read_csv("latest_forecast.csv")
    # 先轉成 datetime，再以 YYYY-MM-DD 格式輸出
    df["ds"] = pd.to_datetime(df["ds"])
    df["ds"] = df["ds"].dt.strftime("%Y-%m-%d")

    needed_cols = ["ds","yhat","yhat_lower","yhat_upper"]
    if not all(col in df.columns for col in needed_cols):
        return jsonify({"error":"Required columns not found"}), 400
    
    records = df[needed_cols].to_dict(orient="records")
    return jsonify(records)

@prophet_bp.route("/api/historical_data", methods=["GET"])
def get_historical_data():
    """
    回傳歷史實際值 y
    """
    if not os.path.exists("資料集_new.csv"):
        return jsonify({"error": "No historical data"}), 404
    
    df = pd.read_csv("資料集_new.csv")
    df.columns = df.columns.str.strip()
    df.rename(columns={"日期":"ds", "CPC":"y"}, inplace=True)
    df["ds"] = pd.to_datetime(df["ds"]).dt.strftime("%Y-%m-%d")
    # 選擇想回傳的欄位
    records = df[["ds","y"]].to_dict(orient="records")
    return jsonify(records)

@prophet_bp.route("/api/prophet_recent_future", methods = ["GET"])
def get_prophet_recent_future():
    """
    回傳「最近15天 + 未來7天」的資料:
      - recent15: [{ds, y}, ...]
      - future7: [{ds, yhat, yhat_lower, yhat_upper}, ...]
    """
    if not os.path.exists("latest_forecast.csv"):
        return jsonify({"error": "No forecast data found"}), 404
    
    df_forecast = pd.read_csv("latest_forecast.csv")
    # 確保ds都為同一格式
    df_forecast["ds"] = pd.to_datetime(df_forecast["ds"]).dt.strftime("%Y-%m-%d")

    # 讀取原始 data (含真實y)
    if not os.path.exists("資料集_new.csv"):
        return jsonify({"error":"no base data"}), 404
    df_base = pd.read_csv("資料集_new.csv")
    df_base.columns = df_base.columns.str.strip()
    df_base.rename(columns={"日期": "ds", "CPC": "y"}, inplace=True)
    df_base["ds"] = pd.to_datetime(df_base["ds"]).dt.strftime("%Y-%m-%d")

    # 找最後日期(資料集裡 or forecast裡)
    last_date_str = df_base["ds"].max()
    last_date = pd.to_datetime(last_date_str)

    start_15days_ago = last_date - pd.Timedelta(days=14)
    # recent15 => df_base 中 ds 在 [start_15days_ago, last_date]
    df_recent15 = df_base[
        (pd.to_datetime(df_base["ds"]) >= start_15days_ago) &
        (pd.to_datetime(df_base["ds"]) <= last_date)
    ].copy()

    # future7 => df_forecast 中 ds > last_date
    df_future7 = df_forecast[
        pd.to_datetime(df_forecast["ds"]) > last_date
    ].copy()

    # 轉成 list of dict
    recent_part = df_recent15[["ds", "y"]].to_dict(orient="records")
    future_part = df_future7[["ds", "yhat", "yhat_lower", "yhat_upper"]].to_dict(orient="records")

    return jsonify({
        "recent15": recent_part,
        "future7": future_part
    })
