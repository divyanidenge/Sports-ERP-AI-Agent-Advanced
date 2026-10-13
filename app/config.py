import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from the backend root directory
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

SECRET_KEY = os.getenv("SECRET_KEY", "super_secret_sports_erp_key_2026_change_in_production")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

# Always resolve DB_PATH to an absolute, stable backend path regardless of CWD
raw_db = os.getenv("DB_PATH", "sports_erp.db")
if os.path.isabs(raw_db):
    DB_PATH = raw_db
else:
    DB_PATH = str((BASE_DIR / raw_db).resolve())

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
