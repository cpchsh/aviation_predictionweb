import re, os, requests, pandas as pd, pymssql
from io import StringIO
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime

# ------------------ 0. 參數設定 ------------------ #
OUTER_URL   = "https://www.cpc.com.tw/cp.aspx?n=44"
UA          = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

DB_SERVER   = os.getenv("DB_SERVER")
DB_USER     = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME     = os.getenv("DB_NAME")

TABLE_NAME  = "oooiiilll_new"      # ← 依實際表名修改
DATE_COL    = "日期"               # ← date / datetime 欄位
CPC_COL     = "CPC"                # ← 價格欄位

# ------------------ 1. 抓取油價 ------------------ #
sess = requests.Session()
sess.headers["User-Agent"] = UA

outer_html = sess.get(OUTER_URL, timeout=10).text
iframe_src = BeautifulSoup(outer_html, "lxml").find("iframe")["src"]
inner_url  = urljoin(OUTER_URL, iframe_src)

inner_html = sess.get(inner_url, timeout=10).text
df = pd.read_html(StringIO(inner_html), flavor="lxml")[0]

# 1-1 擷取日期
match = re.search(r"Effective\s*Date\s*:\s*(\d{4}/\d{2}/\d{2})", inner_html)
if not match:
    raise RuntimeError("抓不到 Effective Date")
effective_date_str = match.group(1)              # "2025/04/29"
effective_date     = datetime.strptime(effective_date_str, "%Y/%m/%d").date()

# 1-2 擷取 6118100 價格（Code No = 6118100）
row = df[df["Code No"].astype(str).str.strip() == "113F 6118100"]
if row.empty:
    raise RuntimeError("今天沒有 113F 6118100 牌價")
spot_price = float(row.iloc[0]["Spot (USD/MT)"])

print(f"抓到日期 {effective_date}，113F 6118100 價格 = {spot_price}")

# ------------------ 2. 連線 MSSQL ------------------ #
conn = pymssql.connect(server=DB_SERVER,
                       user=DB_USER,
                       password=DB_PASSWORD,
                       database=DB_NAME,
                       autocommit=False)          # 用交易確保一致性
cursor = conn.cursor(as_dict=True)

try:
    # 2-1 檢查是否已有該日 CPC 價格
    select_sql = f"""
        SELECT {CPC_COL} FROM {TABLE_NAME}
        WHERE {DATE_COL} = %s
    """
    cursor.execute(select_sql, (effective_date,))
    row_in_db = cursor.fetchone()

    if row_in_db and row_in_db[CPC_COL] is not None:
        print(f"資料表已有 {effective_date} 的 CPC 價格（{row_in_db[CPC_COL]}），不更新。")
    elif row_in_db:
        # 該日已有紀錄但 CPC 是 NULL，執行 UPDATE
        update_sql = f"""
            UPDATE {TABLE_NAME}
            SET {CPC_COL} = %s
            WHERE {DATE_COL} = %s
        """
        cursor.execute(update_sql, (spot_price, effective_date))
        conn.commit()
        print(f"已更新 {effective_date} 的 CPC 價格為 {spot_price}")
    else:
        # 該日不存在任何紀錄，INSERT 一筆（其餘欄位自行補 NULL 或預設）
        insert_sql = f"""
            INSERT INTO {TABLE_NAME} ({DATE_COL}, {CPC_COL})
            VALUES (%s, %s)
        """
        cursor.execute(insert_sql, (effective_date, spot_price))
        conn.commit()
        print(f"已新增 {effective_date}，CPC = {spot_price}")

except Exception as e:
    conn.rollback()
    raise
finally:
    cursor.close()
    conn.close()
