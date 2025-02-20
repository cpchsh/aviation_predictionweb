# README

## 專案簡介

此專案主要用於 **航油價格預測**，包含以下功能：

1. **以 XGBoost 預測下一天的 CPC 價格**  
2. **整合 Prophet** 做更長期的預測，並可自動更新資料後重訓  
3. **自訂輸入**（日本、南韓、香港、新加坡、上海、舟山）以 XGB 模型進行即時預測  
4. **Append Data + Retrain** 工作流程，可快速更新新資料且重訓模型

---

## 專案目錄結構

```bash
my_flask_app/
├─ run.py                          # 主程式入口：執行 Flask
├─ train_prophet.py                # Prophet 重訓程式 (子程式)
├─ 資料集_new.csv                   # 主資料集 CSV
├─ collectedata/
│   └─ tempdata.csv                # 要append的新資料
├─ requirements.txt                # 需要的套件 (可選)
└─ app/
    ├─ __init__.py                 # Flask create_app()，註冊 blueprint
    ├─ xgb_model_new.pkl           # XGB 模型檔
    ├─ static/                     # 放圖片、CSS、JS 等靜態檔
    │   ├─ plot_full.png
    │   ├─ plot_recent_future.png
    │   └─ ...
    ├─ templates/                  # HTML 模板
    │   ├─ index.html              # 首頁: 顯示預測
    │   ├─ xgb_form.html           # 自訂XGB輸入表單
    │   ├─ xgb_result.html         # 顯示XGB預測結果
    │   └─ ...
    └─ routes/
        ├─ main_routes.py          # 首頁 & 常用功能路由
        ├─ xgb_routes.py           # XGB 相關路由: 模型預測、自訂輸入
        └─ prophet_routes.py       # Append & train Prophet 相關路由
```

### 檔案/資料夾說明

- **`run.py`**：整個 Flask 專案的啟動點，內含 `app.run(...)`。  
- **`train_prophet.py`**：Prophet 重訓程式，通常由 `subprocess` 在 `/append_and_train` 路由中被呼叫。  
- **`資料集_new.csv`**：主資料檔案，XGB/Prophet 都會讀取該檔做預測或訓練。  
- **`collectedata/tempdata.csv`**：臨時要追加的新資料，若日期比原檔更新，則會 append 進 `資料集_new.csv`。  
- **`app/__init__.py`**：建立 Flask `create_app()`，並註冊 blueprint (模組化路由)。  
- **`app/routes/*.py`**：分拆路由檔案，對應各功能 (主頁/XGB/Prophet)；每個檔案定義好 blueprint。  
- **`app/templates/`**：所有 HTML 模板 (Jinja2)，如首頁、XGB 輸入、結果頁。  
- **`app/static/`**：存放靜態檔案 (CSS/JS/圖片)，Prophet 圖檔產生後也會寫到這裡 (如 `plot_full.png`)。  
- **`xgb_model_new.pkl`**：XGB 模型檔 (由 joblib.dump(...) 產生)。  

---

## 如何執行

1. **安裝套件**  
   ```bash
   pip install -r requirements.txt
   ```
   （若專案有此檔案；如無，請手動安裝 `Flask`, `pandas`, `matplotlib`, `joblib`, `numpy` 等必要套件。）

2. **準備資料**  
   - 確認 `資料集_new.csv` 以及 `collectedata/tempdata.csv`（若有）已放對位置。  
   - XGB 模型檔 `xgb_model_new.pkl` 亦須存在 `app/` 同層或指定路徑。

3. **啟動 Flask**  
   ```bash
   python run.py
   ```
   - 你可在 `run.py` 或 `app/__init__.py` 的 `create_app()` 中查看 `app.run(debug=True)` 參數。  
   - 啟動後，預設會在 `http://127.0.0.1:5000/` 提供服務。

4. **測試功能**  
   - **首頁**：打開瀏覽器 `http://127.0.0.1:5000/`  
     - 可見 XGB 預測結果與 Prophet 預測表格/圖片（若有生成）。  
   - **Append + ReTrain**：若要測試更新資料 + Prophet 重訓，可透過 POST 到 `/append_and_train`（或在前端有按鈕觸發）。  
   - **自訂輸入 XGB**：`http://127.0.0.1:5000/xgb_form` → 填寫表單送出 → `xgb_result.html` 顯示預測結果。  

5. **檔案與路由對應**  
   - `main_routes.py` → 預設首頁`"/"`  
   - `xgb_routes.py` → `"/xgb_form"`, `"/xgb_predict"`  
   - `prophet_routes.py` → `"/append_and_train"`  


## Docker 建置與執行

1.  **建立 `Dockerfile`**  
    在專案根目錄建立 `Dockerfile` (範例)：
    
    ```dockerfile
    FROM python:3.12
    WORKDIR /app
    
    COPY requirements.txt ./
    RUN pip install --no-cache-dir -r requirements.txt
    
    COPY . .
    
    EXPOSE 5000
    CMD ["python", "run.py"]
    
    ```
    
2.  **Build 映像**
    
    ```bash
    docker build -t python312:latest .
    
    ```
    
3.  **Run 容器**
    
    ```bash
    docker run -d -p 5001:5000 \
        --name python312_container \
        python312:latest
    
    ```
    
    -   這樣 Flask 在容器內的 5000 埠對映到主機的 5001 埠。
    -   瀏覽器訪問 `http://localhost:5001` 測試。
4.  **常見問題**
    
    -   確保程式使用 `app.run(host="0.0.0.0", port=5000)` 監聽，否則容器無法對外提供服務。
    -   若映像太大，可考慮 `python:3.12-slim` 或 `alpine`(在此例中不可行)版本，並清理暫存檔。

---

## GitHub Actions 與 Self-Hosted Runner 

```yaml
name: Deploy locally

on:
  push:
    branches:
      - main         # 每次推送到 main 分支時觸發
      - 'feature/*'  # 每次開發新功能到 feature 分支時觸發
      - 'bugfix/*'   # 每次修復bug到bugfix分支時觸發

jobs:
  deploy:
    runs-on: [self-hosted]
    steps:

    # 1. 取用code
    - name: Checkout repository
      uses: actions/checkout@v3
    
    # 2. 切換到專案目錄
    - name: Build Docker Image
      run: |
        cd ~/1_aviation_fuel_prediction &&
        docker build -t python312:latest .

    # 3. 停止或移除舊容器
    - name: Stop & Remove Old Container
      run: |
        docker stop python312_container || true
        docker rm   python312_container || true

    
    # 4. 執行新容器
    - name: Run Container
      run: |
        docker run -d -p 5001:5000 --name python312_container python312:latest

```

1.  `actions/checkout@v3` 會拉下最新程式碼(針對 push branch)。
2.  `docker build` 重新建置映像
3.  停用舊容器並啟動新容器
4.  之後訪問 `http://<runner機器IP>:5001`
