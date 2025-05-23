import pymssql, os
conn = pymssql.connect(server=os.getenv("DB_SERVER"),
                       user=os.getenv("DB_USER"),
                       password=os.getenv("DB_PASSWORD"),
                       database=os.getenv("DB_NAME"))
cur = conn.cursor()
cur.execute("SELECT MAX(日期) FROM LSMF_Prediction")
print(cur.fetchone())
