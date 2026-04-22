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