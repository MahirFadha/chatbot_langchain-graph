from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
import uvicorn
import asyncio # <-- IMPORT BARU UNTUK TIMER

from services.waha_services import waha_sedang_mengetik, waha_kirim_balasan
from utils.security import cek_izin_dan_update_interaksi
from graph.builder import rakit_pabrik_cs, pool
from database.vector_manager import inisialisasi_vektor_awal

agen = None

# =================================================================
# 📥 KOTAK SURAT SEMENTARA (MESSAGE BUFFERING)
# =================================================================
# Struktur: { "62812xxx@c.us": {"messages": ["p", "mau nanya"], "timer": <Task_Object>} }
CHAT_BUFFER = {}
WAKTU_TUNGGU_DETIK = 10 # Tunggu 10 detik sebelum membalas

async def proses_chat_dari_buffer(chat_id: str):
    """
    Fungsi ini dipanggil oleh Alarm/Timer saat waktunya habis.
    Ia akan menggabungkan chat, melempar ke AI, dan mengirim balasan.
    """
    # 1. Ambil semua pesan yang sudah terkumpul
    data_buffer = CHAT_BUFFER.pop(chat_id, None)
    if not data_buffer or not data_buffer["messages"]:
        return

    # Gabungkan dengan spasi/titik koma
    pesan_gabungan = ". ".join(data_buffer["messages"])
    
    print(f"\n[BUFFER SELESAI] 📦 Menggabungkan pesan {chat_id}: '{pesan_gabungan}'")
    # Animasi mengetik
    waha_sedang_mengetik(chat_id)

    # 2. Lempar ke LangGraph (Otak AI)
    config = {"configurable": {"thread_id": chat_id}}
    
    try:
        print("[LANGGRAPH] 🧠 Sedang memikirkan jawaban...")
        hasil_ai = agen.invoke({"messages": [("user", pesan_gabungan)]}, config)
        
        # --- PERBAIKAN: EKSTRAK TEKS (KARDUS VS KERTAS) ---
        raw_content = hasil_ai["messages"][-1].content
        
        if isinstance(raw_content, list):
            teks_balasan = "".join([item["text"] for item in raw_content if "text" in item])
        else:
            teks_balasan = str(raw_content)
        # ---------------------------------------------------
        
        # 3. Kirim balasan
        waha_kirim_balasan(chat_id, teks_balasan)
        print(f"📤 [BALASAN AI] : {teks_balasan}\n")
    except Exception as e:
        print(f"❌ [ERROR AI]: {str(e)}")


def tambah_ke_buffer(chat_id: str, teks_pesan: str):
    """
    Memasukkan pesan baru ke kotak surat dan me-reset Alarm/Timer.
    """
        
    if chat_id not in CHAT_BUFFER:
        # Jika belum ada di buffer, buat baru
        CHAT_BUFFER[chat_id] = {
            "messages": [teks_pesan],
            "timer": None # Akan diisi di bawah
        }
    else:
        # Jika sudah ada, tambahkan ke ujung list
        CHAT_BUFFER[chat_id]["messages"].append(teks_pesan)
        
        # Jika ada timer lama yang sedang berjalan, BATALKAN (Reset)
        if CHAT_BUFFER[chat_id]["timer"]:
            CHAT_BUFFER[chat_id]["timer"].cancel()
            print(f"[BUFFER] ⏱️ Chat baru masuk dari {chat_id}. Timer di-reset!")

    # Setel/Buat Timer Baru (Alarm)
    # create_task akan menjalankan fungsi sleep & proses_chat_dari_buffer di background
    async def jalankan_timer():
        await asyncio.sleep(WAKTU_TUNGGU_DETIK)
        await proses_chat_dari_buffer(chat_id)
        
    CHAT_BUFFER[chat_id]["timer"] = asyncio.create_task(jalankan_timer())


# =================================================================
# SIKLUS SERVER & ENDPOINT WEBHOOK
# =================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    global agen
    print("\n[SYSTEM] ⚙️ Menginisialisasi Vector DB dan Agen AI...")
    inisialisasi_vektor_awal()
    agen = rakit_pabrik_cs()
    print("[SYSTEM] ✅ Otak AI Siap Melayani!\n")
    yield
    print("\n[SYSTEM] 🛑 Mematikan Server...\n")
    pool.close()
    print("[SYSTEM] ✅ Koneksi Database LangGraph (Pool) ditutup dengan aman.\n")

app = FastAPI(title="Aire Optima AI API", lifespan=lifespan)

@app.post("/webhook")
async def terima_pesan_waha(request: Request):
    try:
        data = await request.json()
        
        if data.get("event") == "message":
            payload = data.get("payload", {})
            if payload.get("fromMe") == True:
                return {"status": "Diabaikan"}

            id_waha = payload.get("from")
            teks_pelanggan = payload.get("body", "")
            
            if not teks_pelanggan:
                return {"status": "Pesan bukan teks"}
            
            print(f"\n📥 [CHAT MASUK] Dari: {id_waha} | Isi: {teks_pelanggan}")

            # 1. Panggil Satpam dari utils/
            if not cek_izin_dan_update_interaksi(id_waha):
                print(f"🛑 [SISTEM] Pesan dari {id_waha} ditolak oleh Satpam (Handoff/Blacklist).")
                return {"status": "Ditolak Satpam"}

            # 2. MASUKKAN KE BUFFER (Tidak lagi langsung dilempar ke LangGraph)
            tambah_ke_buffer(id_waha, teks_pelanggan)

            return {"status": "Diterima dan dimasukkan ke Buffer"}
            
        return {"status": "Bukan pesan masuk"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)