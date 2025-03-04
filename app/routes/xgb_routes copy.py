# xgb_routes.py
from flask import Blueprint, render_template, request
import pandas as pd
import os
import pymssql
import joblib
from datetime import date
from dotenv import load_dotenv

xgb_bp = Blueprint('xgb_bp', __name__)

# 載入 XGB 模型 (可全域 or create_app時載入)
xgb_model_path = "./xgb_model_new.pkl"
xgb_model = joblib.load(xgb_model_path)

@xgb_bp.route("/xgb_form", methods=["GET"])
def xgb_input_form():
    """
    顯示自訂 XGB 預測的表單
    """
    return render_template("xgb_form.html")

@xgb_bp.route("/xgb_predict", methods=["POST"])
def xgb_predict_custom():
    """
    以表單輸入作為特徵, y_lag_1 = japan + 5...預測 XGB
    回傳 xgb_result.html
    """
    japan     = float(request.form.get("japan", 0))
    korea     = float(request.form.get("korea", 0))
    hongkong  = float(request.form.get("hongkong",0))
    singapore = float(request.form.get("singapore", 0))
    shanghai  = float(request.form.get("shanghai", 0))
    zhoushan  = float(request.form.get("zhoushan", 0))

    y_lag_1 = japan + 5
    y_lag_2 = japan
    y_lag_3 = japan - 5

    X_custom = pd.DataFrame([{
        'japan': japan,
        'korea': korea,
        'hongkong': hongkong,
        'singapore': singapore,
        'shanghai': shanghai,
        'zhoushan': zhoushan,
        'y_lag_1': y_lag_1,
        'y_lag_2': y_lag_2,
        'y_lag_3': y_lag_3
    }])

    pred_val = xgb_model.predict(X_custom)[0]
    result_str = f"{pred_val:.2f}"

    return render_template("xgb_result.html",
                           result_val=result_str,
                           j=japan,k=korea,h=hongkong,
                           s=singapore,sh=shanghai,zh=zhoushan)
