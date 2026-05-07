from utils.security import bersihkan_memori_langgraph
import asyncio
import time
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request

# =================================================================
# 📥 IMPOR FUNGSI & SERVICES
# =================================================================
from utils.security import (
    cek_izin_dan_update_interaksi, 
    ubah_status_bot_manual, 
    tambah_kata_blacklist, 
    hapus_kata_blacklist,
    lihat_daftar_blacklist,
    lihat_pelanggan_bot_nonaktif,
    normalisasi_id_waha
)
from services.waha_services import waha_sedang_mengetik, waha_kirim_balasan, waha_tandai_dibaca
from graph.builder import rakit_pabrik_cs, tutup_pabrik_cs
from data.vector_manager import inisialisasi_vektor_awal

# ✨ BARU: Impor modul sinkronisasi dan scheduler
from apscheduler.schedulers.background import BackgroundScheduler
from services.sync_catalog import run_all_sync 

agen = None

# =================================================================
# ⚙️ SETUP BACKGROUND SCHEDULER
# =================================================================
scheduler = BackgroundScheduler()

# Atur jadwal sinkronisasi (Contoh: Berjalan setiap 3 hari sekali)
scheduler.add_job(run_all_sync, 'interval', days=3)

# Opsi lain jika ingin jalan setiap jam 02:00 pagi setiap hari:
# scheduler.add_job(run_all_sync, 'cron', hour=2, minute=0)

# =================================================================
# 📥 KOTAK SURAT SEMENTARA (MESSAGE BUFFERING)
# =================================================================
CHAT_BUFFER = {}
WAKTU_TUNGGU_DETIK = 10 

async def proses_chat_dari_buffer(chat_id: str):
    data_buffer = CHAT_BUFFER.pop(chat_id, None)
    if not data_buffer or not data_buffer["messages"]:
        return

    pesan_gabungan = ". ".join(data_buffer["messages"])
    print(f"\n[BUFFER SELESAI] 📦 Menggabungkan pesan {chat_id}: '{pesan_gabungan}'")
    
    waha_tandai_dibaca(chat_id)

    jumlah_kata = len(pesan_gabungan.split())
    waktu_baca_kalkulasi = jumlah_kata / 4.0
    waktu_jeda = max(1.5, min(waktu_baca_kalkulasi, 6.0))

    print(f"⏱️ [UX] Simulasi membaca {jumlah_kata} kata selama {waktu_jeda:.1f} detik...")
    time.sleep(waktu_jeda)

    waha_sedang_mengetik(chat_id)

    config = {"configurable": {"thread_id": chat_id}}
    
    try:
        print("[LANGGRAPH] 🧠 Sedang memikirkan jawaban...")
        hasil_ai = agen.invoke({"messages": [("user", pesan_gabungan)]}, config)
        
        raw_content = hasil_ai["messages"][-1].content
        
        if isinstance(raw_content, list):
            teks_balasan = "".join([item["text"] for item in raw_content if "text" in item])
        else:
            teks_balasan = str(raw_content)
        
        waha_kirim_balasan(chat_id, teks_balasan)
        print(f"📤 [BALASAN AI] : {teks_balasan}\n")
    except Exception as e:
        print(f"❌ [ERROR AI]: {str(e)}")

def tambah_ke_buffer(chat_id: str, teks_pesan: str):
    if chat_id not in CHAT_BUFFER:
        CHAT_BUFFER[chat_id] = {
            "messages": [teks_pesan],
            "timer": None
        }
    else:
        CHAT_BUFFER[chat_id]["messages"].append(teks_pesan)
        if CHAT_BUFFER[chat_id]["timer"]:
            CHAT_BUFFER[chat_id]["timer"].cancel()
            print(f"[BUFFER] ⏱️ Chat baru masuk dari {chat_id}. Timer di-reset!")

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
    
    print("[SYSTEM] ⏰ Menjalankan tugas Garbage Collector (Jam 03:00 pagi)...")
    scheduler.add_job(
        bersihkan_memori_langgraph, 
        'cron', 
        hour=3, 
        minute=0,
        id='hapus_memori_langgraph',  # Sabuk pengaman agar tidak ganda
        replace_existing=True         # Timpa jadwal lama jika server direstart
    )
    
    print("[SYSTEM] ⏰ Menyalakan Background Scheduler (Katalog Sync)...")
    scheduler.start()
    
    print("[SYSTEM] ✅ Otak AI & Scheduler Siap Melayani!\n")
    
    yield  # Server berjalan di titik ini...
    
    print("\n[SYSTEM] 🛑 Mematikan Server...\n")
    
    # ✨ BARU: Mematikan Scheduler dengan aman
    print("[SYSTEM] ⏰ Mematikan Background Scheduler...")
    scheduler.shutdown()
    
    for chat_id, data in CHAT_BUFFER.items():
        if data.get("timer"):
            data["timer"].cancel()
            
    print("[SYSTEM] 🧹 Membersihkan sisa antrean tugas...")
    await asyncio.sleep(0.5)

    tutup_pabrik_cs()
    print("[SYSTEM] ✅ Koneksi Database LangGraph (Pool) ditutup dengan aman.\n")

app = FastAPI(title="Aire Optima AI API", lifespan=lifespan)

@app.post("/webhook")
async def terima_pesan_waha(request: Request):
    try:
        data = await request.json()
        
        if data.get("event") in ["message", "message.any"]:
            payload = data.get("payload", {})
            
            from_me = payload.get("fromMe")
            id_pengirim_mentah = payload.get("from")
            id_penerima_mentah = payload.get("to")
            teks_pesan = payload.get("body", "").strip()

            # =======================================================
            # 🛡️ NORMALISASI ID DI PINTU GERBANG UTAMA!
            # =======================================================
            id_pengirim = normalisasi_id_waha(id_pengirim_mentah)
            id_penerima = normalisasi_id_waha(id_penerima_mentah)

            # =======================================================
            # 🎛️ PUSAT KENDALI (Admin chat ke dirinya sendiri)
            # =======================================================
            if from_me and id_pengirim == id_penerima:
                menu_bantuan = (
                    "🛠️ *PUSAT KENDALI ADMIN* 🛠️\n\n"
                    "Daftar perintah yang tersedia:\n"
                    "🔹 */bot off [nomor]* - Mematikan AI untuk pelanggan.\n"
                    "🔹 */bot on [nomor]* - Menyalakan AI untuk pelanggan.\n"
                    "🔹 */cek bot nonaktif* - Lihat daftar pelanggan yg ditangani Admin.\n"
                    "🔹 */blacklist [kata] [kategori]* - Tambah kata terlarang.\n"
                    "🔹 */unblacklist [kata]* - Hapus kata terlarang.\n"
                    "🔹 */list blacklist* - Lihat semua kata terlarang.\n"
                    "🔹 */list command* - Menampilkan pesan bantuan ini.\n"
                )

                if teks_pesan.startswith("/bot off "):
                    nomor_input = teks_pesan.replace("/bot off ", "").strip()
                    nomor_target = normalisasi_id_waha(nomor_input)
                    hasil = ubah_status_bot_manual(nomor_target, False)
                    waha_kirim_balasan(id_pengirim, hasil)
                    return {"status": "Command /bot off dieksekusi"}
                    
                elif teks_pesan.startswith("/bot on "):
                    nomor_input = teks_pesan.replace("/bot on ", "").strip()
                    nomor_target = normalisasi_id_waha(nomor_input)
                    hasil = ubah_status_bot_manual(nomor_target, True)
                    waha_kirim_balasan(id_pengirim, hasil)
                    return {"status": "Command /bot on dieksekusi"}

                elif teks_pesan.startswith("/blacklist "):
                    isi_perintah = teks_pesan.replace("/blacklist ", "").strip()
                    parts = isi_perintah.split(" ", 1)
                    kata_input = parts[0]
                    kategori_input = parts[1] if len(parts) > 1 else "umum"
                    
                    hasil = tambah_kata_blacklist(kata_input, kategori_input)
                    waha_kirim_balasan(id_pengirim, hasil)
                    return {"status": "Command /blacklist dieksekusi"}

                elif teks_pesan.startswith("/unblacklist "):
                    kata_input = teks_pesan.replace("/unblacklist ", "").strip()
                    hasil = hapus_kata_blacklist(kata_input)
                    waha_kirim_balasan(id_pengirim, hasil)
                    return {"status": "Command /unblacklist dieksekusi"}

                elif teks_pesan == "/cek bot nonaktif":
                    hasil = lihat_pelanggan_bot_nonaktif()
                    waha_kirim_balasan(id_pengirim, hasil)
                    return {"status": "Command /cek_bot_nonaktif dieksekusi"}

                elif teks_pesan == "/list blacklist":
                    hasil = lihat_daftar_blacklist()
                    waha_kirim_balasan(id_pengirim, hasil)
                    return {"status": "Command /list_blacklist dieksekusi"}

                elif teks_pesan == "/list command":
                    waha_kirim_balasan(id_pengirim, menu_bantuan)
                    return {"status": "Command /list_command dieksekusi"}

                elif teks_pesan.startswith("/"):
                    pesan_typo = f"⚠️ *Perintah '{teks_pesan}' tidak dikenali atau salah ketik!*\n\n{menu_bantuan}"
                    waha_kirim_balasan(id_pengirim, pesan_typo)
                    return {"status": "Command tidak dikenali (Fallback)"}
                    
            # =======================================================
            # MENCEGAH LOOPING (Abaikan semua pesan dari kita sendiri)
            # =======================================================
            if from_me:
                return {"status": "Diabaikan, ini pesan keluar"}

            # =======================================================
            # PROSES PESAN MASUK DARI PELANGGAN 
            # =======================================================
            if not teks_pesan:
                return {"status": "Pesan bukan teks"}

            # 1. Panggil Satpam
            if not cek_izin_dan_update_interaksi(id_pengirim, teks_pesan):
                return {"status": "Ditolak Satpam"}

            # 2. Masukkan ke Buffer
            tambah_ke_buffer(id_pengirim, teks_pesan)

            return {"status": "Sukses dimasukkan buffer"}
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)