import os
import pymssql
from dotenv import load_dotenv; load_dotenv()
import pandas as pd

DB_SERVER = os.getenv("DB_SERVER")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
EIS_SERVER = os.getenv("EIS_SERVER")
EIS_NAME = os.getenv("EIS_NAME")

def debug_eis(date_str: str):
    sql = """
        SELECT [DATE], [NAME], [CLOSE]
        FROM dbo.MARKET_DATA
        WHERE [DATE] = %s
    """
    with pymssql.connect(server=EIS_SERVER,
                         user=DB_USER, password=DB_PASSWORD,
                         database=EIS_NAME) as conn:
        df = pd.read_sql(sql, conn, params=(date_str,))
    print("=== 原始資料 ===")
    print(df)

    if df.empty:
        print("⚠️  這天本來就沒有任何列 (原因 A)")
        return

    print("\n=== DISTINCT NAME ===")
    print(df["NAME"].unique())          # 檢查原因 B / C

    # 測看看你的 LIKE 條件
    df_like = df[df["NAME"].str.contains("MarineFuel", case=False, na=False)]
    print(f"\nLIKE %%MarineFuel%% 命中 {len(df_like)} 列")
    print(df_like)

print(debug_eis("2025-05-19"))