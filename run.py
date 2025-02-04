from app import create_app

# 開發時用debug=True,上線時關閉
if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5002, debug=True)