# app/routes/main_routes.py
from flask import Blueprint, render_template, request
import pandas as pd

from app.routes.xgb_routes import predict_next_day_xgb_db
from app.routes.tukey_routes import predict_next_day_tukey
from app.services.db_service import get_recent_7_records, get_error_metrics
# 建立 Blueprint 物件
main_bp = Blueprint('main_bp', __name__)


@main_bp.route("/", methods=["GET"])
def index():
  
    # Tukey 預測
    next_day_tukey = predict_next_day_tukey()
    # 1) 用 XGB 預測下一天
    latest_date, next_day_pred = predict_next_day_xgb_db()
    next_day_pred_str = f"{next_day_pred:.2f}"


    # 4) 取得使用者篩選日期 (GET 參數)
    filter_date = request.args.get("filter_date")  # /?filter_date=YYYY-MM-DD

    # 5) 呼叫獨立 service 查詢最近7筆紀錄
    rows = get_recent_7_records(filter_date=filter_date)
    #print("if_final_cpc", rows[0]['is_final_cpc'])

    # 將 rows 轉成 pandas DataFrame, 產生 HTML
    if rows:
        df = pd.DataFrame(rows)
        # 調整欄位順序 (可選)
        #df = df[["日期","日本","南韓","香港","新加坡","上海","舟山","CPC","PredictedCPC","is_final_cpc"]]
        df = df[["日期","日本","南韓","香港","新加坡","上海","舟山","CPC","predictCPC"]]
        df_html = df.to_html(classes="table table-bordered table-striped", index=False)
        #final_cpc = rows[0]['is_final_cpc']
    else:
        df_html = "<p>查無資料</p>"

    # 計算 MAE, MAPE
    mae, mape, rmse = get_error_metrics()
    # 若都計不到就給None
    if mae is None or mape is None or rmse is None:
        mae_display = "N/A"
        mape_display = "N/A"
        rmse_display = "N/A"
    else:
        mae_display = round(mae, 4)
        mape_display = round(mape, 2)
        rmse_display = round(rmse, 4)

    
    return render_template(
        "index.html",
        next_day=latest_date,
        next_day2=next_day_tukey[0],
        tukey_pred=next_day_tukey[1],
        xgb_pred=next_day_pred_str,
        # prophet_fvalue=f_value,
        # future_table_html=future_table_html,
        table_html=df_html,
        #final_cpc = final_cpc,
        filter_date=filter_date,  # 讓前端可回填
        mae=mae_display,
        mape=mape_display,
        rmse=rmse_display
        # plot_full_url=plot_full_url,
        # plot_recent_url=plot_recent_url
    )
