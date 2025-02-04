# import pyodbc

# # 資料庫連線字串
# conn = pyodbc.connect(
#     server='hqsbdsql22tv@cpc.com.tw', user='db_owner', password='P@ssW0rd#cpc', database='BDC_TEST'
# )
# cursor = conn.cursor()
# cursor.execute("SELECT * FROM [BDC_TEST].[dbo].[aviation_prediction]")
# rows = cursor.fetchall()

# for row in rows:
#     print(row)

# conn.close()

import pymssql
from requests_ntlm import HttpNtlmAuth
# user = 'cpc\\REMOVED_NUM'
# userpass = ''
# auth = HttpNtlmAuth(user ,userpass )

# 資料庫連線字串
conn = pymssql.connect(
   server='REMOVED_INFORMATION', user=r'cpc\REMOVED_NUM', password=r'REMOVED_INFO',  database='BDC_TEST'
)
# 10.168.244.93

# conn = pymssql.connect(server='10.168.230.92', user='cpcbdc', password='P@ssW0rd#cpc', database='A00_BDT_MDM')
# cpcbdc
# P@ssW0rd#cpc
cursor = conn.cursor()
cursor.execute("SELECT * FROM [BDC_TEST].[dbo].[aviation_prediction]")

# cursor.execute("SELECT * FROM [A00_BDT_MDM].[dbo].[CTRL_LOG]")
rows = cursor.fetchall()

for row in rows:
    print(row)

conn.close()
