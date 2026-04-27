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

def ambil_data_pelanggan_lama(chat_id: str):
    """Mengecek apakah pelanggan sudah pernah order dan punya data lengkap"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Ambil data. Jika belum pernah order, biasanya real_name masih NULL
        cursor.execute("""
            SELECT real_name, telepon, address, total_orders 
            FROM public.customers 
            WHERE id_customer = %s
        """, (chat_id,))
        row = cursor.fetchone()
        
        # Jika baris ada, DAN real_name tidak kosong (sudah pernah isi form)
        if row and row[0]: 
            return {
                "nama": row[0],
                "telepon": row[1],
                "alamat": row[2] if row[2] else "Belum terdata",
                "total_orders": row[3]
            }
        return None
    except Exception as e:
        print(f"❌ [ERROR DB] Gagal mengambil data pelanggan lama: {e}")
        return None
    finally:
        cursor.close()
        conn.close()