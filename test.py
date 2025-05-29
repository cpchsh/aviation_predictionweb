import os
import json
holidays_file = os.path.join(
    os.path.dirname(__file__),       # 目前檔案所在資料夾
    "data", "holidays.sg.json"       # 相對於專案的路徑
)
with open(holidays_file, encoding="utf-8") as fp:
    SG_HOLIDAYS = {h["date"] for h in json.load(fp)}
print(SG_HOLIDAYS)