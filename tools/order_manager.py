from langchain_core.tools import tool
from langchain_core.runnables.config import RunnableConfig
from data.database import get_db_connection
from services.waha_services import kirim_notifikasi_admin
import datetime

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
    id_jasa_tambahan: str = "",     
    nama_jasa_tambahan: str = "",   
    harga_jasa_tambahan: int = 0,
    # --- PARAMETER BIAYA TAMBAHAN ---
    keterangan_biaya_tambahan: str = "",
    nominal_biaya_tambahan: int = 0
) -> str:
    """
    WAJIB DIPANGGIL SAAT PELANGGAN SUDAH MEMBERIKAN 5 DATA LENGKAP.
    Jika pesanan memiliki Jasa Bundling/Tambahan, WAJIB masukkan ke parameter *_jasa_tambahan.
    Jika ada biaya tambahan (Apartemen/Jam Malam), WAJIB masukkan ke parameter biaya_tambahan.
    """
    id_customer_aktif = config.get("configurable", {}).get("thread_id")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. UPDATE DATA CUSTOMER
        cursor.execute("""
            UPDATE public.customers 
            SET real_name = %s, telepon = %s, address = %s, total_orders = total_orders + 1
            WHERE id_customer = %s
        """, (nama_asli, no_wa, alamat_lengkap, id_customer_aktif))

        # 2. BUAT HEADER ORDER (SEKARANG MEMASUKKAN SURCHARGE KE SINI)
        timestamp_sekarang = datetime.datetime.now()
        order_id = f"ORD-{timestamp_sekarang.strftime('%y%m%d%H%M%S')}"
        
        total_semua = harga_item_utama + harga_jasa_tambahan + nominal_biaya_tambahan
        
        cursor.execute("""
            INSERT INTO public.orders (
                order_id, id_customer, total_price, order_status, 
                request_service_time, created_at, surcharge_reason, surcharge_fee
            )
            VALUES (%s, %s, %s, 'pending', %s, %s, %s, %s)
        """, (order_id, id_customer_aktif, total_semua, jadwal, timestamp_sekarang, 
              keterangan_biaya_tambahan, nominal_biaya_tambahan))

        # 3. BUAT DETAIL ORDER (Hanya untuk produk dan jasa riil)
        # -- Insert Item Utama --
        cursor.execute("""
            INSERT INTO public.order_detail (order_id, product_service_id, item_name, qty, price)
            VALUES (%s, %s, %s, 1, %s)
        """, (order_id, id_item_utama, nama_item_utama, harga_item_utama))

        # -- Insert Item Tambahan JIKA ADA --
        if id_jasa_tambahan and nama_jasa_tambahan:
            cursor.execute("""
                INSERT INTO public.order_detail (order_id, product_service_id, item_name, qty, price)
                VALUES (%s, %s, %s, 1, %s)
            """, (order_id, id_jasa_tambahan, nama_jasa_tambahan, harga_jasa_tambahan))

        # 4. SIMPAN PERUBAHAN
        conn.commit()
        
        # ======================================================
        # 5. SIAPKAN DAN KIRIM NOTIFIKASI KE ADMIN
        # ======================================================
        rincian_item = f"- 1x {nama_item_utama} (Rp {harga_item_utama:,})"
        if id_jasa_tambahan and nama_jasa_tambahan:
            rincian_item += f"\n- 1x {nama_jasa_tambahan} (Rp {harga_jasa_tambahan:,})"
            
        # Jika ada surcharge, tambahkan informasinya di WhatsApp Admin
        if nominal_biaya_tambahan > 0:
            rincian_item += f"\n\n⚠️ *BIAYA TAMBAHAN*\n- {keterangan_biaya_tambahan} (Rp {nominal_biaya_tambahan:,})"
            
        data_order = {
            "id_order": order_id,
            "nama": nama_asli,
            "nomor_hp": id_customer_aktif,
            "alamat": alamat_lengkap,
            "jadwal": jadwal,
            "rincian_item": rincian_item,
            "total_tagihan": total_semua
        }
        
        kirim_notifikasi_admin(data_order)
        # ======================================================

        cursor.close()
        conn.close()
        
        return f"SUKSES. Pesanan berhasil dicatat. Beritahu pelanggan Nomor Order mereka: {order_id} dan sampaikan Admin akan segera menghubungi."

    except Exception as e:
        # Jika ada error, batalkan semua perubahan di database
        conn.rollback()
        print(f"\n!!!!! ERROR PENYIMPANAN DATABASE: {str(e)} !!!!!\n")
        return "Sistem penyimpanan gagal. Minta pelanggan menunggu."