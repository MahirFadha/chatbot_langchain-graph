from utils.security import ubah_status_bot_manual
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
import uvicorn
import asyncio 
from utils.security import (
    cek_izin_dan_update_interaksi, 
    ubah_status_bot_manual, 
    tambah_kata_blacklist, 
    hapus_kata_blacklist,
    lihat_daftar_blacklist,
    lihat_pelanggan_bot_nonaktif
)
from services.waha_services import waha_sedang_mengetik, waha_kirim_balasan
from graph.builder import rakit_pabrik_cs, tutup_pabrik_cs
from data.vector_manager import inisialisasi_vektor_awal

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
    
    # 1. Batalkan semua antrean timer
    for chat_id, data in CHAT_BUFFER.items():
        if data.get("timer"):
            data["timer"].cancel()
            
    print("[SYSTEM] 🧹 Membersihkan sisa antrean tugas...")
    await asyncio.sleep(0.5) # Beri waktu sejenak agar asnycio membatalkan tugas

    # 2. Tutup kolam koneksi
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
            id_pengirim = payload.get("from")
            id_penerima = payload.get("to")
            teks_pesan = payload.get("body", "").strip()

            # =======================================================
            # 🎛️ PUSAT KENDALI (Admin chat ke dirinya sendiri)
            # =======================================================
            if from_me and id_pengirim == id_penerima:
                
                # --- MENU BANTUAN (TEMPLATE) ---
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

                # --- PENGECEKAN COMMAND ---
                if teks_pesan.startswith("/bot off "):
                    nomor_target = teks_pesan.replace("/bot off ", "")
                    hasil = ubah_status_bot_manual(nomor_target, False)
                    waha_kirim_balasan(id_pengirim, hasil)
                    return {"status": "Command /bot off dieksekusi"}
                    
                elif teks_pesan.startswith("/bot on "):
                    nomor_target = teks_pesan.replace("/bot on ", "")
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

                # --- FALLBACK (JIKA ADMIN TYPO / COMMAND TIDAK DIKENAL) ---
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