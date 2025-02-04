#!/usr/bin/env python3
# train_prophet.py

import pandas as pd
from prophet import Prophet
import matplotlib
matplotlib.use('Agg')  # 防止在非GUI環境報錯
import matplotlib.pyplot as plt

def main():
    # 1) 讀取原始資料
    file_path = '資料集_new.csv'
    data = pd.read_csv(file_path)

    # 必要的資料清洗、欄位改名
    data.columns = data.columns.str.strip()
    data.rename(columns={
        '日期': 'ds',
        'CPC': 'y',
    }, inplace=True)
    data['ds'] = pd.to_datetime(data['ds'])
    data.sort_values('ds', inplace=True)

    # 2) 建立 Prophet 模型，並訓練
    model = Prophet(
        changepoint_prior_scale=0.5,
        yearly_seasonality=False,
        weekly_seasonality=True,
        daily_seasonality=False,
        seasonality_mode='additive'
    )
    model.fit(data[['ds','y']])

    # 3) 產生未來 7 天 (或更多) 預測
    future = model.make_future_dataframe(periods=7)
    forecast = model.predict(future)

    # 4) 輸出預測結果到 CSV
    forecast.to_csv('latest_forecast.csv', index=False)

    # 5) 繪圖 - (A) 全部歷史 + 未來
    fig1 = model.plot(forecast)
    plt.title("Prophet Forecast (All history + Future)")
    plt.savefig("app/static/plot_full.png")  # 儲存圖檔
    plt.close(fig1)

    print("Prophet training done. Output => latest_forecast.csv, plot_full.png")

if __name__ == "__main__":
    main()
