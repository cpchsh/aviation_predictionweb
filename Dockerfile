FROM python:3.12-slim

# 設定工作目錄
WORKDIR /app

# 複製 requirements.txt 到容器
COPY requirements.txt ./

#安裝套件
RUN pip install --no-cache-dir -r requirements.txt

# 複製整個專案檔案
COPY . .

# 開放 Flask 預設port, e.g. 5000
EXPOSE  5000

#
CMD ["python", "run.py"]