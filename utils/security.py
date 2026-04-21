import psycopg2
from config.settings import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS

def cek_izin_dan_update_interaksi(chat_id):
    """Mengecek apakah user boleh dilayani bot (bot_active & blacklist)."""
    diizinkan = True
    try:
        conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS)
        cursor = conn.cursor()
        
        cursor.execute("SELECT bot_active, blacklist FROM public.customers WHERE id_customer = %s", (chat_id,))
        row = cursor.fetchone()
        
        if row:
            bot_active = row[0]
            blacklist = row[1]
            
            if blacklist == True:
                print(f"[SATPAM] 🚫 User {chat_id} ada di daftar Blacklist. Diabaikan.")
                diizinkan = False
            elif bot_active == False:
                print(f"[SATPAM] 👨‍💻 User {chat_id} sedang ditangani Admin Manusia (Handoff). Diabaikan.")
                diizinkan = False
            else:
                cursor.execute("UPDATE public.customers SET last_interaction = NOW() WHERE id_customer = %s", (chat_id,))
        else:
            print(f"[SATPAM] ✨ Mendaftarkan pelanggan baru: {chat_id}")
            cursor.execute("""
                INSERT INTO public.customers (id_customer, bot_active, blacklist, total_orders, last_interaction)
                VALUES (%s, true, false, 0, NOW())
            """, (chat_id,))
            
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"❌ [ERROR DB] Gagal mengecek izin: {e}")
        
    return diizinkan