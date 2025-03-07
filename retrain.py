import os
import datetime
import pandas as pd
import numpy as np
from xgboost import XGBRegressor
from joblib import dump
import pymssql
from dotenv import load_dotenv

def train_model():
    # 載入 .env 檔案中的環境變數
    load_dotenv()
    DB_SERVER = os.getenv("DB_SERVER")
    DB_USER = os.getenv("DB_USER")
    DB_PASSWORD = os.getenv("DB_PASSWORD")
    DB_NAME = os.getenv("DB_NAME")

    # 與資料庫建立連線
    conn = pymssql.connect(server=DB_SERVER, user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
    cursor = conn.cursor(as_dict=True)

    try:
        # 撈取資料，範例中只撈 is_final_cpc=1 的資料
        query = """
            SELECT
                [日期] as dt,
                [日本],
                [南韓],
                [香港],
                [新加坡],
                [上海],
                [舟山],
                [CPC],
                [PredictedCPC],
                [y_lag_1],
                [y_lag_2],
                [y_lag_3],
                [is_final_cpc]
            FROM [BDC_TEST].[dbo].[oooiiilll]
            WHERE [is_final_cpc] = 1
            ORDER BY [日期]
        """
        cursor.execute(query)
        rows = cursor.fetchall()  # list of dict

        # 將查詢結果轉為 DataFrame
        data = pd.DataFrame(rows)

        # 重新命名欄位
        data.rename(columns={
            'dt': 'ds',
            'CPC': 'y',
            '日本': 'japan',
            '南韓': 'korea',
            '香港': 'hongkong',
            '新加坡': 'singapore',
            '上海': 'shanghai',
            '舟山': 'zhoushan'
        }, inplace=True)

        # 轉換日期格式、排序、移除全空列
        data['ds'] = pd.to_datetime(data['ds'])
        data.sort_values(by='ds', inplace=True)
        data.dropna(how='all', inplace=True)

        # 選擇特徵欄位與目標欄位
        feature_cols = [
            'japan', 'korea', 'hongkong', 'singapore', 'shanghai', 'zhoushan',
            'y_lag_1', 'y_lag_2', 'y_lag_3'
        ]
        X = data[feature_cols]
        y = data['y']

        # 手動切分訓練集與測試集 (8:2)，因為 shuffle=False，直接依照 index 分割
        split_index = int(0.8 * len(data))
        X_train = X.iloc[:split_index]
        X_test = X.iloc[split_index:]
        y_train = y.iloc[:split_index]
        y_test = y.iloc[split_index:]

        # 建立並訓練 XGBoost 迴歸模型
        model = XGBRegressor(n_estimators=100, learning_rate=0.1, random_state=42)
        model.fit(X_train, y_train)

        # 預測結果
        y_pred_train = model.predict(X_train)
        y_pred_test = model.predict(X_test)

        # 計算誤差指標：RMSE 與 MAE (利用 numpy)
        rmse_train = np.sqrt(np.mean((y_train - y_pred_train) ** 2))
        rmse_test = np.sqrt(np.mean((y_test - y_pred_test) ** 2))
        mae_test = np.mean(np.abs(y_test - y_pred_test))

        # 使用固定檔名來覆蓋原有模型檔
        model_filename = "/shared_volume/xgb_model.pkl"
        dump(model, model_filename)
        print(f"新模型已儲存：{model_filename}")

        # 產生一段文字紀錄 (包含指標與訓練時間)
        now_str = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        log_text = (
            f"[{now_str}] Model Retrained\n"
            f"  Train RMSE: {rmse_train:.2f}\n"
            f"  Test RMSE:  {rmse_test:.2f}\n"
            f"  Test MAE:   {mae_test:.2f}\n"
            "----------------------------------------\n"
        )

        # 寫入或追加到 log 檔案
        log_filename = "/shared_volume/training_log.txt"
        with open(log_filename, "a", encoding="utf-8") as f:
            f.write(log_text)
        
        print("訓練紀錄已寫入：training_log.txt")

    except Exception as e:
        print(f"訓練過程發生錯誤: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    train_model()
