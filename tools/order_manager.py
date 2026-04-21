import psycopg2
import uuid
from langchain_core.tools import tool
from config.settings import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS

@tool
def catat_pesanan_baru(nama_asli: str, no_wa: str, alamat_lengkap: str, pesanan_spesifik: str, jadwal: str) -> str:
    """
    WAJIB DIPANGGIL SAAT PELANGGAN SUDAH MEMBERIKAN 5 DATA LENGKAP (Nama, WA, Alamat, Pesanan, Jadwal).
    Gunakan tool ini untuk mencatat pesanan resmi ke dalam sistem database Aire Optima.
    """
    try:
        # Buka koneksi database
        conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS)
        cursor = conn.cursor()
        
        print(f"\n[SYSTEM] Menyimpan Pesanan Baru dari {nama_asli}...")

        # 1. CEK ATAU BUAT CUSTOMER BARU
        # (Logika: Cari berdasarkan no_wa. Jika tidak ada, insert ke tabel customers)
        cursor.execute("SELECT id_customer FROM public.customers WHERE telepon = %s", (no_wa,))
        cust_row = cursor.fetchone()
        
        if cust_row:
            id_customer = cust_row[0]
            # Opsional: Update alamat terakhir pelanggan jika ada perubahan
            cursor.execute("UPDATE public.customers SET address = %s, real_name = %s WHERE id_customer = %s", (alamat_lengkap, nama_asli, id_customer))
        else:
            id_customer = str(uuid.uuid4()) # Generate ID baru
            cursor.execute("""
                INSERT INTO public.customers (id_customer, real_name, telepon, address, total_orders, bot_status)
                VALUES (%s, %s, %s, %s, 0, true)
            """, (id_customer, nama_asli, no_wa, alamat_lengkap))

        # 2. BUAT HEADER ORDER
        # (Generate order_id misal: ORD-2026xxxx)
        import datetime
        timestamp_sekarang = datetime.datetime.now()
        order_id = f"ORD-{timestamp_sekarang.strftime('%y%m%d%H%M%S')}"
        
        cursor.execute("""
            INSERT INTO public.orders (order_id, id_customer, total_price, order_status, request_service_time, created_at)
            VALUES (%s, %s, %s, 'pending', %s, %s)
        """, (order_id, id_customer, 0, jadwal, timestamp_sekarang)) # Total price bisa di-update nanti atau dikirim via parameter

        # 3. BUAT DETAIL ORDER
        # (Masukkan pesanan_spesifik ke order_detail)
        cursor.execute("""
            INSERT INTO public.order_detail (order_id, item_name, qty, price)
            VALUES (%s, %s, 1, 0) -- Untuk sementara price 0, atau tambahkan parameter harga di fungsi tool ini
        """, (order_id, pesanan_spesifik))

        # 4. SIMPAN PERUBAHAN & TUTUP KONEKSI
        conn.commit()
        cursor.close()
        conn.close()
        
        print(f"[SYSTEM] Pesanan {order_id} berhasil disimpan ke database!")
        
        # Pesan ini akan dibaca oleh LLM agar ia tahu ID transaksinya
        return f"SUKSES. Pesanan berhasil dicatat. Beritahu pelanggan bahwa pesanan berhasil dan berikan Nomor Resi / Order ID mereka: {order_id}"

    except Exception as e:
        print(f"\n!!!!! ERROR PENYIMPANAN DATABASE: {str(e)} !!!!!\n")
        return "Sistem penyimpanan gagal. Minta pelanggan menunggu sebentar sementara admin dipanggil."