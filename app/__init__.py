from flask import Flask

def create_app():
    app = Flask(__name__)
    app.secret_key = "anyrandomsecret"

    # 載入/註冊各個Blueprint
    from app.routes.main_routes import main_bp
    from app.routes.xgb_routes import xgb_bp
    from app.routes.prophet_routes import prophet_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(xgb_bp)
    app.register_blueprint(prophet_bp)

    return app