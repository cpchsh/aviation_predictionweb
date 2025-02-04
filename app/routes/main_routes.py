# app/routes/main_routes.py
from flask import Blueprint, render_template
import os
import pandas as pd

from app.services.xgb_service import predict_next_day_xgb
from app.routes.tukey_routes import predict_next_day_tukey
# 建立 Blueprint 物件
main_bp = Blueprint('main_bp', __name__)


@main_bp.route("/", methods=["GET"])
def index():
  
    # Tukey 預測
    next_day_tukey = predict_next_day_tukey()
    # 1) 用 XGB 預測下一天
    next_day_pred = predict_next_day_xgb(
        model_path="./xgb_model_new.pkl",
        csv_path="./資料集_new.csv"
    )

    next_day_pred_str = f"{next_day_pred:.2f}"
    
    # 2) 讀取預測結果 CSV (latest_forecast.csv)
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
        if not future_part.empty:
            value = future_part.iloc[0, 1]
            f_value = f"{value:.2f}"
            f_day = future_part.iloc[0, 0]
        else:
            f_value = "N/A"
            f_day = "N/A"
        future_table_html = future_part.to_html(classes="table custom-table text-center", index=False)
    else:
        f_day = "N/A"
        f_value = "N/A"
        future_table_html = "<p>No forecast data found.</p>"
    
    # 3)圖檔檢查, 改用 chart.js故先忽略
    # plot_full_url = "/static/plot_full.png" if os.path.exists("app/static/plot_full.png") else ""
    # plot_recent_url = "/static/plot_recent_future.png" if os.path.exists("app/static/plot_recent_future.png") else ""
    
    return render_template(
        "index.html",
        next_day=f_day,
       #    next_day2=next_day_tukey[0],
        tukey_pred=next_day_tukey[1],
        xgb_pred=next_day_pred_str,
        prophet_fvalue=f_value,
        future_table_html=future_table_html,
        # plot_full_url=plot_full_url,
        # plot_recent_url=plot_recent_url
    )
