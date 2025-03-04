# app/routes/main_routes.py
from flask import Blueprint, render_template, request
import pandas as pd

from app.routes.xgb_routes import predict_next_day_xgb_db
from app.routes.tukey_routes import predict_next_day_tukey
from app.services.db_service import get_recent_7_records
# 建立 Blueprint 物件
main_bp = Blueprint('main_bp', __name__)


@main_bp.route("/", methods=["GET"])
def index():
  
    # Tukey 預測
    next_day_tukey = predict_next_day_tukey()
    # 1) 用 XGB 預測下一天
    latest_date, next_day_pred = predict_next_day_xgb_db()
    next_day_pred_str = f"{next_day_pred:.2f}"
    
    # # 2) 讀取預測結果 CSV (latest_forecast.csv)
    # if os.path.exists("./latest_forecast.csv"):

    #     forecast = pd.read_csv("latest_forecast.csv",encoding="utf-8-sig")
    #     forecast.columns = forecast.columns.str.strip()  # 去除欄位名稱前後的空白
    #     # 取最後 7 天的預測
    #     future_part = forecast.tail(7)[['ds', 'yhat', 'yhat_lower', 'yhat_upper']]
    #     # 重新命名欄位名稱
    #     future_part = future_part.rename(columns={
    #         'ds': '日期',
    #         'yhat': '預測值',
    #         'yhat_lower': '預測信賴區間下界',
    #         'yhat_upper': '預測信賴區間上界'
    #     })
    #     if not future_part.empty:
    #         value = future_part.iloc[0, 1]
    #         f_value = f"{value:.2f}"
    #         f_day = future_part.iloc[0, 0]
    #     else:
    #         f_value = "N/A"
    #         f_day = "N/A"
    #     future_table_html = future_part.to_html(classes="table custom-table text-center", index=False)
    # else:
    #     f_day = "N/A"
    #     f_value = "N/A"
    #     future_table_html = "<p>No forecast data found.</p>"
    
    # 3)圖檔檢查, 改用 chart.js故先忽略
    # plot_full_url = "/static/plot_full.png" if os.path.exists("app/static/plot_full.png") else ""
    # plot_recent_url = "/static/plot_recent_future.png" if os.path.exists("app/static/plot_recent_future.png") else ""

    # 4) 取得使用者篩選日期 (GET 參數)
    filter_date = request.args.get("filter_date")  # /?filter_date=YYYY-MM-DD

    # 5) 呼叫獨立 service 查詢最近7筆紀錄
    rows = get_recent_7_records(filter_date=filter_date)
    print("if_final_cpc", rows[0]['is_final_cpc'])

    # 將 rows 轉成 pandas DataFrame, 產生 HTML
    if rows:
        df = pd.DataFrame(rows)
        # 調整欄位順序 (可選)
        df = df[["日期","日本","南韓","香港","新加坡","上海","舟山","CPC","PredictedCPC","is_final_cpc"]]
        df_html = df.to_html(classes="table table-bordered table-striped", index=False)
        final_cpc = rows[0]['is_final_cpc']
    else:
        df_html = "<p>查無資料</p>"
    
    return render_template(
        "index.html",
        next_day=latest_date,
        next_day2=next_day_tukey[0],
        tukey_pred=next_day_tukey[1],
        xgb_pred=next_day_pred_str,
        # prophet_fvalue=f_value,
        # future_table_html=future_table_html,
        table_html=df_html,
        final_cpc = final_cpc,
        filter_date=filter_date  # 讓前端可回填
        # plot_full_url=plot_full_url,
        # plot_recent_url=plot_recent_url
    )
