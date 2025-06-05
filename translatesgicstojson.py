from pathlib import Path
import json
import re
from datetime import datetime
# 新加坡假日網址
# 台灣假日網址 : https://n.sfs.tw/content/index/16460
ics_path = Path("public-holidays-sg-2023.ics")   # 存放 ICS 的檔名
out_path = Path("holidays.sg2023.json")  # 輸出 JSON

events = []
with ics_path.open(encoding="utf-8") as f:
    block = []
    for line in f:
        line = line.strip()
        if line == "BEGIN:VEVENT":
            block = []
        elif line == "END:VEVENT":
            # 把一個 VEVENT 區塊轉成 dict
            txt = "\n".join(block)
            date_match   = re.search(r"DTSTART;VALUE=DATE:(\d{8})", txt)
            summary_match = re.search(r"SUMMARY:(.+)", txt)
            if date_match and summary_match:
                d8  = date_match.group(1)             # 20250101
                day = datetime.strptime(d8, "%Y%m%d").date().isoformat()
                nm  = summary_match.group(1).strip()
                events.append({"date": day, "name": nm})
        else:
            block.append(line)

# 寫出 JSON
with out_path.open("w", encoding="utf-8") as f:
    json.dump(events, f, ensure_ascii=False, indent=2)

print(f"轉檔完成：{out_path}（共 {len(events)} 筆）")
