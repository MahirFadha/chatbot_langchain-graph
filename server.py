from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
import uvicorn

# Pastikan file-file ini benar-benar ada di folder yang sesuai!
from services.waha_services import waha_sedang_mengetik, waha_kirim_balasan
from utils.security import cek_izin_dan_update_interaksi
from graph.builder import rakit_pabrik_cs
from database.vector_manager import inisialisasi_vektor_awal # JANGAN LUPA INI

agen = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global agen
    print("\n[SYSTEM] ⚙️ Menginisialisasi Vector DB dan Agen AI...")
    inisialisasi_vektor_awal() # Wajib dipanggil agar Hybrid Search jalan
    agen = rakit_pabrik_cs()
    print("[SYSTEM] ✅ Otak AI Siap Melayani!\n")
    yield
    print("\n[SYSTEM] 🛑 Mematikan Server dan membersihkan memori...\n")

# Cukup 1 kali saja mendeklarasikan 'app'
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
                return {"status": "Pesan bukan teks, diabaikan."}
            
            print(f"\n📥 [CHAT MASUK] Dari: {id_waha} | Isi: {teks_pelanggan}")

            # 1. Panggil Satpam dari utils/
            if not cek_izin_dan_update_interaksi(id_waha):
                return {"status": "Ditolak Satpam"}

            # 2. Panggil WAHA dari services/
            waha_sedang_mengetik(id_waha)

            # 3. Lempar ke LangGraph
            config = {"configurable": {"thread_id": id_waha}}
            hasil_ai = agen.invoke({"messages": [("user", teks_pelanggan)]}, config)
            teks_balasan = hasil_ai["messages"][-1].content
            
            # 4. Kirim balasan via services/
            waha_kirim_balasan(id_waha, teks_balasan)
            print(f"📤 [BALASAN AI] : {teks_balasan}\n")

            return {"status": "Sukses"}
            
        return {"status": "Bukan pesan masuk"}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)