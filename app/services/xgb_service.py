import pandas as pd
import os

def predict_next_day_xgb(model_path="./xgb_model_new.pkl", csv_path="./資料集_new.csv"):
    """
    讀取資料集 csv, 建置 lag 特徵
    取最後一列 -> 用 XGB 模型預測下一天CPC
    """
    import joblib

    # 載入模型
    xgb_model = joblib.load(model_path)

    # 讀取資料
    data = pd.read_csv(csv_path)
    data.columns = data.columns.str.strip()
    data.rename(columns={
        '日期': 'ds', 'CPC': 'y',
        '日本': 'japan', '南韓': 'korea', '香港': 'hongkong',
        '新加坡': 'singapore', '上海': 'shanghai', '舟山': 'zhoushan'
    }, inplace=True)

    data['ds'] = pd.to_datetime(data['ds'])
    data.sort_values('ds', inplace=True)
    data[['y','japan','korea','hongkong','singapore','shanghai','zhoushan']] = \
        data[['y','japan','korea','hongkong','singapore','shanghai','zhoushan']].ffill().bfill()
    
    # 建立 lag
    N_LAGS = 3
    for i in range(1, N_LAGS + 1):
        data[f'y_lag_{i}'] = data['y'].shift(i)
    data.dropna(inplace=True)

    # 取最後一筆
    last_row = data.iloc[-1]
    X_future = pd.DataFrame([{
        'japan':     last_row['japan'],
        'korea':     last_row['korea'],
        'hongkong':  last_row['hongkong'],
        'singapore': last_row['singapore'],
        'shanghai':  last_row['shanghai'],
        'zhoushan':  last_row['zhoushan'],
        'y_lag_1':   last_row['y'],
        'y_lag_2':   last_row['y_lag_1'],
        'y_lag_3':   last_row['y_lag_2']
    }])

    # 預測
    y_pred = xgb_model.predict(X_future)[0]
    return y_pred