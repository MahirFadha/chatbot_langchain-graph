import urllib.parse
import requests
from config.settings import WAHA_API_KEY, WAHA_SESSION, WAHA_URL

def get_headers():
    """Fungsi pembantu untuk merakit Kepala Surat (Headers)"""
    headers = {"Content-Type": "application/json"}
    if WAHA_API_KEY:
        headers["X-Api-Key"] = WAHA_API_KEY
    return headers

def waha_tandai_dibaca(chat_id: str):
    """Mengirim status 'Centang Biru' (Read/Seen) ke pelanggan"""
    try:
        url = f"{WAHA_URL}/api/sendSeen"
        payload = {
            "session": WAHA_SESSION,
            "chatId": chat_id
        }
        requests.post(url, json=payload, headers=get_headers())
    except Exception as e:
        print(f"⚠️ Gagal mengirim status Read: {e}")

def waha_sedang_mengetik(chat_id):
    """Memberi tahu WhatsApp agar memunculkan tulisan 'typing...'"""
    try:
        requests.post(
            f"{WAHA_URL}/api/startTyping", 
            json={"chatId": chat_id, "session": WAHA_SESSION},
            headers=get_headers() # <-- SISIPKAN KUNCI DI SINI
        )
    except:
        pass

def waha_kirim_balasan(chat_id, teks_balasan):
    """Mengirim pesan teks dari AI kembali ke WhatsApp pelanggan"""
    try:
        response = requests.post(
            f"{WAHA_URL}/api/sendText", 
            json={
                "chatId": chat_id,
                "text": teks_balasan,
                "session": WAHA_SESSION
            },
            headers=get_headers() # <-- SISIPKAN KUNCI DI SINI
        )
        
        # Cek penolakan WAHA
        if response.status_code not in [200, 201]:
            print(f"❌ [WAHA MENOLAK] Kode: {response.status_code} | Alasan: {response.text}")
        else:
            print("✅ [WAHA SUKSES] Pesan terkirim ke WhatsApp pelanggan!")
            
    except Exception as e:
        print(f"❌ [ERROR KONEKSI WAHA] Gagal mengirim pesan: {e}")

def dapatkan_phone_dari_lid(id_lid: str):
    """Menerjemahkan @lid kembali menjadi nomor HP biasa (@c.us)"""
    # Jika sudah @c.us atau tidak ada @lid, langsung kembalikan aslinya
    if "@lid" not in id_lid:
        return id_lid
        
    try:
        url = f"{WAHA_URL}/api/{WAHA_SESSION}/lids/{id_lid}"
        response = requests.get(url, headers=get_headers())
        if response.status_code == 200:
            data = response.json()
            # WAHA biasanya menyimpan nomor HP asli di atribut 'pn' (Phone Number)
            nomor_pn = data.get("pn")
            if nomor_pn:
                return nomor_pn
    except Exception as e:
        print(f"⚠️ [WARNING] Gagal mencari Nomor HP asli ke WAHA: {e}")
        
    return id_lid # Jika gagal, kembalikan aslinya saja

def kirim_notifikasi_admin(data_order: dict):
    """Merakit dan mengirim notifikasi order baru ke Admin"""
    
    # 1. Format ID Pelanggan (KITA YAKIN 100% INI SUDAH @c.us)
    id_pelanggan = data_order.get("nomor_hp", "")
    
    # Langsung bersihkan @c.us untuk keperluan link wa.me
    nomor_bersih = id_pelanggan.replace("@c.us", "")
    
    # 2. Format Harga (Tambahkan titik ribuan ala Indonesia)
    total_harga = data_order.get("total_tagihan", 0)
    total_rp = f"{total_harga:,.0f}".replace(",", ".")
    
    # 3. Format Link Google Maps Ajaib
    import urllib.parse
    alamat_mentah = data_order.get("alamat", "")
    alamat_encoded = urllib.parse.quote(alamat_mentah)
    link_maps = f"https://www.google.com/maps/search/?api=1&query={alamat_encoded}"
    
    # 4. Rakit Template Pesan
    pesan_admin = f"""🚨 *ORDER BARU MASUK (AIRE OPTIMA)* 🚨
ID: {data_order.get('id_order')}
━━━━━━━━━━━━━━━━━━
👤 *DATA PELANGGAN*
Nama   : {data_order.get('nama')}
No HP  : {nomor_bersih}
WA     : https://wa.me/{nomor_bersih}

📍 *LOKASI PENGERJAAN*
Alamat : {alamat_mentah}
🗺️ Maps : {link_maps}

🛠️ *DETAIL PESANAN*
Jadwal : {data_order.get('jadwal')}

🛒 *RINCIAN ITEM:*
{data_order.get('rincian_item')}

💰 *TOTAL TAGIHAN: Rp {total_rp}*
━━━━━━━━━━━━━━━━━━
⚠️ _Mohon segera konfirmasi ketersediaan teknisi ke pelanggan._"""

    # 5. Tembakkan ke nomor Admin!
    try:
        from config.settings import NOMOR_WA # Pastikan nama variabel sesuai di config-mu
        
        # Normalisasi nomor admin jaga-jaga kalau di .env belum ada @c.us
        admin_target = str(NOMOR_WA).strip()
        if admin_target.startswith("0"): admin_target = "62" + admin_target[1:]
        if not admin_target.endswith("@c.us"): admin_target += "@c.us"
        
        waha_kirim_balasan(admin_target, pesan_admin)
        print("✅ [NOTIFIKASI] Form pesanan berhasil dikirim ke Admin!")
    except Exception as e:
        print(f"❌ [NOTIFIKASI ERROR] Gagal mengirim ke Admin: {e}")