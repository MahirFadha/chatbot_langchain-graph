import requests

WAHA_URL = "http://localhost:3000"
WAHA_SESSION = "default"

# 1. MASUKKAN API KEY WAHA KAMU DI SINI
# Jika di n8n kamu pakai API Key, copy-paste ke sini.
# Jika kamu merasa tidak pernah membuat API Key, coba ubah jadi "123" atau biarkan kosong ""
WAHA_API_KEY = "chatbot-aire" 

def get_headers():
    """Fungsi pembantu untuk merakit Kepala Surat (Headers)"""
    headers = {"Content-Type": "application/json"}
    if WAHA_API_KEY:
        headers["X-Api-Key"] = WAHA_API_KEY
    return headers

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

def dapatkan_lid_dari_waha(nomor_hp: str):
    """Mencari @lid dari nomor HP pelanggan via WAHA"""
    nomor_bersih = "".join(filter(str.isdigit, nomor_hp))
    try:
        url = f"{WAHA_URL}/api/{WAHA_SESSION}/lids/pn/{nomor_bersih}@c.us"
        response = requests.get(url, headers=get_headers())
        if response.status_code == 200:
            return response.json().get("lid")
    except Exception as e:
        print(f"⚠️ [WARNING] Gagal mencari LID ke WAHA: {e}")
    return None

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