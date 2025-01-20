# app/routes/main_routes.py
from flask import Blueprint, render_template, request, redirect, url_for
import os, pandas as pd

# 建立 Blueprint 物件
main_bp = Blueprint('main_bp', __name__)

# 可能還需要載入你的 XGB 函式
from app.routes.xgb_routes import predict_next_day_xgb

@main_bp.route("/", methods=["GET"])
def index():
    """
    首頁: 
     1) 呼叫 predict_next_day_xgb() 預測下一天
     2) 若有 latest_forecast.csv，讀取 Prophet結果並顯示
     3) 顯示圖檔等
    """
    # XGB 預測
    next_day_pred = predict_next_day_xgb()
    next_day_pred_str = f"{next_day_pred:.2f}"

    # 讀取 Prophet 預測結果 (若檔案存在)
    f_day, f_value, future_table_html = "N/A","N/A","<p>No forecast data found.</p>"
    if os.path.exists("./latest_forecast.csv"):
        forecast = pd.read_csv("./latest_forecast.csv")
        future_part = forecast.tail(7)[['ds','yhat','yhat_lower','yhat_upper']]

        value = future_part.iloc[0,1]
        f_value = f"{value:.2f}"
        f_day = future_part.iloc[0,0]
        future_table_html = future_part.to_html(index=False)

    # 檢查圖檔
    plot_full_url = "static/plot_full.png" if os.path.exists("app/static/plot_full.png") else ""
    plot_recent_url = "static/plot_recent_future.png" if os.path.exists("app/static/plot_recent_future.png") else ""

    return render_template("index.html",
                           next_day=f_day,
                           xgb_pred=next_day_pred_str,
                           prophet_fvalue=f_value,
                           future_table_html=future_table_html,
                           plot_full_url=plot_full_url,
                           plot_recent_url=plot_recent_url)
