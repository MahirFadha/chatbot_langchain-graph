import datetime
import uuid
from database.koneksi import get_db_connection
from graph.builder import rakit_pabrik_cs

def simpan_customer_baru(id_waha):
    """Fungsi sistem untuk memastikan ID WAHA terdaftar di database sebelum chat dimulai"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Cek apakah ID sudah ada
        cursor.execute("SELECT id_customer FROM public.customers WHERE id_customer = %s", (id_waha,))
        if not cursor.fetchone():
            waktuSekarang = datetime.datetime.now()
            # Jika belum ada, Insert data dasar
            cursor.execute("""
                INSERT INTO public.customers (id_customer, bot_active, blacklist, total_orders,last_interaction)
                VALUES (%s, true, false, 0, %s)
            """, (id_waha,waktuSekarang))
            conn.commit()
            print(f"[SYSTEM DB] User baru {id_waha} berhasil didaftarkan di sistem!")
            
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"[SYSTEM DB ERROR] Gagal inisialisasi customer: {e}")

def jalankan_bot():
    agen = rakit_pabrik_cs()
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. GENERATE ID (Simulasi WAHA ID)
    # Nanti kalau sudah pakai WAHA, ini diganti dengan ID dari JSON Webhook (misal: 62812xxx@s.whatsapp.net)
    id_waha_simulasi = f"WAHA-{str(uuid.uuid4())[:8]}" 
    
    # 2. DAFTARKAN KE DATABASE SEBELUM MULAI
    simpan_customer_baru(id_waha_simulasi)
    
    # 3. SET CONFIG THREAD ID LANGGRAPH SAMA DENGAN ID WAHA
    config = {"configurable": {"thread_id": id_waha_simulasi}}
    
    print("\n" + "="*50)
    print("--- Sesi Chat CS Dimulai ---")
    print(f"ID Customer Aktif : {id_waha_simulasi}")
    print("Ketik 'keluar' untuk menghentikan aplikasi.")
    print("="*50 + "\n")
    
    while True:
        teks_user = input("Pelanggan: ")
        cursor.execute("UPDATE public.customers SET last_interaction = NOW() WHERE id_customer = %s", (id_waha_simulasi,))
        conn.commit()
        if teks_user.lower() in ['keluar', 'exit','q']:
            print("Mematikan sistem...")
            break
            
        try:
            # Masukkan pesan user ke State awal
            input_state = {"messages": [("user", teks_user)]}
            
            # invoke() akan menjalankan graf dari START sampai END
            hasil_akhir = agen.invoke(input_state, config=config)
            
            # Ambil konten pesan paling terakhir dari State
            isi_pesan = hasil_akhir["messages"][-1].content
            
            # Saringan khusus untuk Gemini: Jika bentuknya list, ambil 'text'-nya saja
            if isinstance(isi_pesan, list):
                jawaban_ai = "".join(item.get("text", "") for item in isi_pesan if isinstance(item, dict))
            else:
                jawaban_ai = isi_pesan
                
            print(f"AI CS: {jawaban_ai}\n")
            
        except Exception as e:
            print(f"Terjadi error fatal: {e}")

if __name__ == "__main__":
    jalankan_bot()