from dotenv import load_dotenv; load_dotenv()
import os
print("EIS_SERVER =", os.getenv("EIS_SERVER"))