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
        jadwal_tampil = jadwal # Default jika error
        try:
            import datetime
            dt = datetime.datetime.strptime(jadwal, "%Y-%m-%d %H:%M:%S")
            hari_indo = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
            nama_hari = hari_indo[dt.weekday()]
            jadwal_tampil = f"{nama_hari}, {dt.strftime('%d-%m-%Y %H:%M')} WIB"
        except Exception:
            pass
        # ------------------------------------------------------------
        
        rincian_item = f"- 1x {nama_item_utama} (Rp {harga_item_utama:,})"
        # ... (kode rincian_item sama seperti sebelumnya) ...
            
        data_order = {
            "id_order": order_id,
            "nama": nama_asli,
            "nomor_hp": id_customer_aktif,
            "alamat": alamat_lengkap,
            "jadwal": jadwal_tampil, # <-- UBAH VARIABEL INI DARI 'jadwal' MENJADI 'jadwal_tampil'
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


@tool
def ubah_jadwal_pesanan(order_id: str, jadwal_baru: str, config: RunnableConfig) -> str:
    """
    Gunakan tool ini HANYA JIKA pelanggan ingin mengubah jadwal pesanan (reschedule) 
    DAN kamu sudah memastikan bahwa permintaannya memenuhi syarat maksimal H-1.
    Parameter `jadwal_baru` WAJIB menggunakan format standar PostgreSQL: "YYYY-MM-DD HH:MM:00".
    """
    id_customer_aktif = config.get("configurable", {}).get("thread_id")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. Pastikan order_id benar milik pelanggan ini, DAN ambil Nama Pelanggan (JOIN tabel)
        cursor.execute("""
            SELECT o.request_service_time, c.real_name 
            FROM public.orders o
            JOIN public.customers c ON o.id_customer = c.id_customer
            WHERE o.order_id = %s AND o.id_customer = %s
        """, (order_id, id_customer_aktif))
        row = cursor.fetchone()
        
        if not row:
            return "GAGAL: Nomor Order tidak ditemukan atau pesanan tersebut bukan milik pelanggan ini. Pastikan Nomor Order benar."
            
        jadwal_lama = row[0]
        # Jika nama tidak ditemukan, gunakan "Pelanggan" sebagai default
        nama_pelanggan = row[1] if row[1] else "Pelanggan" 
        
        # 2. Update jadwal di database
        cursor.execute("""
            UPDATE public.orders 
            SET request_service_time = %s 
            WHERE order_id = %s
        """, (jadwal_baru, order_id))
        
        conn.commit()
        
        # 3. Kirim Notif ke Admin dengan Format Manusiawi & Nama Pelanggan
        try:
            from services.waha_services import waha_kirim_balasan
            from config.settings import ADMIN_WA_NUMBER
            
            # --- PENERJEMAH FORMAT JADWAL ---
            hari_indo = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
            
            jadwal_baru_tampil = jadwal_baru
            try:
                dt_baru = datetime.datetime.strptime(jadwal_baru, "%Y-%m-%d %H:%M:%S")
                jadwal_baru_tampil = f"{hari_indo[dt_baru.weekday()]}, {dt_baru.strftime('%d-%m-%Y %H:%M')} WIB"
            except: pass
            
            jadwal_lama_tampil = str(jadwal_lama)
            try:
                if isinstance(jadwal_lama, datetime.datetime):
                    dt_lama = jadwal_lama
                else:
                    dt_lama = datetime.datetime.strptime(str(jadwal_lama), "%Y-%m-%d %H:%M:%S")
                jadwal_lama_tampil = f"{hari_indo[dt_lama.weekday()]}, {dt_lama.strftime('%d-%m-%Y %H:%M')} WIB"
            except: pass
            # --------------------------------
            
            admin_target = str(ADMIN_WA_NUMBER).strip()
            if admin_target.startswith("0"): admin_target = "62" + admin_target[1:]
            if not admin_target.endswith("@c.us"): admin_target += "@c.us"
            
            # --- PESAN ADMIN DENGAN NAMA PELANGGAN ---
            pesan_admin = f"⚠️ *INFO RESCHEDULE PESANAN* ⚠️\n\nID: {order_id}\n👤 *Atas Nama: {nama_pelanggan}*\n\nJadwal Lama: {jadwal_lama_tampil}\n*Jadwal Baru: {jadwal_baru_tampil}*\n\n_Mohon sesuaikan jadwal teknisi!_"
            
            waha_kirim_balasan(admin_target, pesan_admin)
        except Exception as e:
            print(f"⚠️ Gagal kirim notif reschedule ke admin: {e}")
            
        cursor.close()
        conn.close()
        
        return f"SUKSES: Jadwal untuk pesanan {order_id} berhasil diubah menjadi: {jadwal_baru}."
        
    except Exception as e:
        return f"GAGAL: Terjadi kesalahan sistem database: {e}"