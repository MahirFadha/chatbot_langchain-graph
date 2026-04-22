# Isi dari file: utils/database.py
import psycopg2
from psycopg2.extras import RealDictCursor
from config.settings import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS

def get_db_connection():
    """
    Fungsi sentral untuk mendapatkan koneksi ke PostgreSQL.
    Nantinya, jika kita mau upgrade ke Connection Pool, 
    kita cukup ubah di satu file ini saja!
    """
    try:
        conn = psycopg2.connect(
            host=DB_HOST, 
            port=DB_PORT, 
            dbname=DB_NAME, 
            user=DB_USER, 
            password=DB_PASS
        )
        return conn
    except Exception as e:
        print(f"❌ [DATABASE ERROR] Gagal terhubung ke PostgreSQL: {e}")
        raise e