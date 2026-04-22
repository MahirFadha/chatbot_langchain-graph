from database.koneksi import get_db_connection
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

@tool
def catat_pesanan_baru(
    nama_asli: str, 
    no_wa: str, 
    alamat_lengkap: str, 
    id_item_utama: str, 
    nama_item_utama: str, 
    harga_item_utama: int, 
    jadwal: str,
    config: RunnableConfig,
    id_jasa_tambahan: str = "",     # Parameter baru (Opsional)
    nama_jasa_tambahan: str = "",   # Parameter baru (Opsional)
    harga_jasa_tambahan: int = 0    # Parameter baru (Opsional)
) -> str:
    """
    WAJIB DIPANGGIL SAAT PELANGGAN SUDAH MEMBERIKAN 5 DATA LENGKAP.
    Jika pesanan memiliki Jasa Bundling/Tambahan, WAJIB masukkan ke parameter *_jasa_tambahan.
    Jika tidak ada jasa tambahan, kosongkan parameter tambahannya.
    """
    id_customer_aktif = config.get("configurable", {}).get("thread_id")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. UPDATE DATA CUSTOMER & TAMBAH TOTAL ORDERS (Selesaikan Poin 3)
        cursor.execute("""
            UPDATE public.customers 
            SET real_name = %s, telepon = %s, address = %s, total_orders = total_orders + 1
            WHERE id_customer = %s
        """, (nama_asli, no_wa, alamat_lengkap, id_customer_aktif))

        # 2. BUAT HEADER ORDER
        import datetime
        timestamp_sekarang = datetime.datetime.now()
        order_id = f"ORD-{timestamp_sekarang.strftime('%y%m%d%H%M%S')}"
        
        total_semua = harga_item_utama + harga_jasa_tambahan
        
        cursor.execute("""
            INSERT INTO public.orders (order_id, id_customer, total_price, order_status, request_service_time, created_at)
            VALUES (%s, %s, %s, 'pending', %s, %s)
        """, (order_id, id_customer_aktif, total_semua, jadwal, timestamp_sekarang))

        # 3. BUAT DETAIL ORDER (Selesaikan Poin 5)
        # -- Insert Item Utama (AC atau Jasa Tunggal) --
        cursor.execute("""
            INSERT INTO public.order_detail (order_id, product_service_id, item_name, qty, price)
            VALUES (%s, %s, %s, 1, %s)
        """, (order_id, id_item_utama, nama_item_utama, harga_item_utama))

        # -- Insert Item Tambahan JIKA ADA (Jasa Pasang Bundling) --
        if id_jasa_tambahan and nama_jasa_tambahan:
            cursor.execute("""
                INSERT INTO public.order_detail (order_id, product_service_id, item_name, qty, price)
                VALUES (%s, %s, %s, 1, %s)
            """, (order_id, id_jasa_tambahan, nama_jasa_tambahan, harga_jasa_tambahan))

        # 4. SIMPAN PERUBAHAN
        conn.commit()
        cursor.close()
        conn.close()
        
        return f"SUKSES. Pesanan berhasil dicatat. Beritahu pelanggan Nomor Order mereka: {order_id}"

    except Exception as e:
        print(f"\n!!!!! ERROR PENYIMPANAN DATABASE: {str(e)} !!!!!\n")
        return "Sistem penyimpanan gagal. Minta pelanggan menunggu."