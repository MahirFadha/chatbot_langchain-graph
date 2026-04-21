import requests

WAHA_URL = "http://localhost:3000"
WAHA_SESSION = "default"

def waha_sedang_mengetik(chat_id):
    """Memberi tahu WhatsApp agar memunculkan tulisan 'typing...'"""
    try:
        requests.post(f"{WAHA_URL}/api/startTyping", json={"chatId": chat_id, "session": WAHA_SESSION})
    except:
        pass

def waha_kirim_balasan(chat_id, teks_balasan):
    """Mengirim pesan teks dari AI kembali ke WhatsApp pelanggan"""
    try:
        requests.post(f"{WAHA_URL}/api/sendText", json={
            "chatId": chat_id,
            "text": teks_balasan,
            "session": WAHA_SESSION
        })
    except Exception as e:
        print(f"❌ [ERROR WAHA] Gagal mengirim pesan: {e}")