import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
NOMOR_WA = os.getenv("NOMOR_WA")
WAHA_URL = os.getenv("WAHA_URL")
WAHA_SESSION = os.getenv("WAHA_SESSION")
WAHA_API_KEY = os.getenv("WAHA_API_KEY")
BASE_URL_API_AIRE = os.getenv("BASE_URL_API_AIRE")
GOOGLE_API_KEY_RAGAS_1 = os.getenv("GOOGLE_API_KEY_RAGAS_1")
GOOGLE_API_KEY_RAGAS_2 = os.getenv("GOOGLE_API_KEY_RAGAS_2")
GOOGLE_API_KEY_RAGAS_3 = os.getenv("GOOGLE_API_KEY_RAGAS_3")
GOOGLE_API_KEY_RAGAS_4 = os.getenv("GOOGLE_API_KEY_RAGAS_4")
GOOGLE_API_KEY_RAGAS_5 = os.getenv("GOOGLE_API_KEY_RAGAS_5")
