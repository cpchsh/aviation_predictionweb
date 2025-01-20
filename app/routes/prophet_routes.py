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