from flask import Blueprint, render_template, request
import pandas as pd
from app.routes.xgb_routes import predict_next_day_xgb_db
from app.routes.tukey_routes import predict_next_day_tukey
from app.services.db_service import get_recent_7_records, get_error_metrics

main_bp = Blueprint("main_bp", __name__)

@main_bp.route("/", methods=["GET"])
def index():

    # ───── Tukey 預測（可能回 None） ─────
    try:
        tukey_res = predict_next_day_tukey()          # 期待 [date, value]
    except Exception as e:
        tukey_res = None

    if tukey_res and len(tukey_res) >= 2:
        tukey_date, tukey_pred = tukey_res[0], tukey_res[1]
    else:
        tukey_date, tukey_pred = "N/A", "N/A"

    # ───── XGB 預測 ─────
    latest_date, next_day_pred = predict_next_day_xgb_db()
    xgb_pred_str = f"{next_day_pred:.2f}" if next_day_pred is not None else "N/A"

    # ───── 查詢最近 7 筆 ─────
    filter_date = request.args.get("filter_date")          # /?filter_date=YYYY-MM-DD
    rows = get_recent_7_records(filter_date=filter_date)

    if rows:
        df = pd.DataFrame(rows)[["日期","日本","南韓","香港","新加坡","上海","舟山","CPC","predictCPC"]]
        table_html = df.to_html(classes="table table-bordered table-striped", index=False)
    else:
        table_html = "<p>查無資料</p>"

    # ───── 誤差指標 ─────
    mae, mape, rmse = get_error_metrics()
    mae_disp  = f"{mae:.4f}"  if mae  is not None else "N/A"
    mape_disp = f"{mape:.2f}" if mape is not None else "N/A"
    rmse_disp = f"{rmse:.4f}" if rmse is not None else "N/A"

    return render_template(
        "index.html",
        next_day   = latest_date,
        next_day2  = tukey_date,
        tukey_pred = tukey_pred,
        xgb_pred   = xgb_pred_str,
        table_html = table_html,
        filter_date= filter_date,
        mae  = mae_disp,
        mape = mape_disp,
        rmse = rmse_disp
    )


