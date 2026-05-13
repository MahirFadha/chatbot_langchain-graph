import re
from data.database import get_db_connection
from services.waha_services import waha_kirim_balasan, dapatkan_phone_dari_lid

def cek_izin_dan_update_interaksi(chat_id: str, teks_pesan: str = ""):
    diizinkan = True
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 1. AMBIL STATUS PELANGGAN (Hanya bot_active)
        cursor.execute("SELECT bot_active FROM public.customers WHERE id_customer = %s", (chat_id,))
        row = cursor.fetchone()
        
        if row:
            if row[0] == False: # Jika bot_active sudah False
                # --- TAMBAHKAN DEBUGGING DI SINI ---
                print(f"🛑 [SATPAM] Pesan dari {chat_id} diabaikan AI (Status: Ditangani Admin Manusia).")
                return False    # Langsung tolak dari AI (biarkan Admin yang urus)
        else:
            # Pendaftar baru
            cursor.execute("""
                INSERT INTO public.customers (id_customer, bot_active, total_orders, last_interaction)
                VALUES (%s, true, 0, NOW())
            """, (chat_id,))
            conn.commit()

        # 2. MODERASI KATA
        print(f"🕵️‍♂️ [DEBUG SATPAM] Memeriksa teks: '{teks_pesan}'") # <-- CCTV KITA

        if teks_pesan:
            pesan_lower = teks_pesan.lower()
            
            cursor.execute("SELECT word, category FROM public.blacklisted_words")
            bad_words_db = cursor.fetchall()
            
            print(f"🕵️‍♂️ [DEBUG SATPAM] Total blacklist words di database: {len(bad_words_db)}") # <-- CCTV KITA
            
            for row_word in bad_words_db:
                # Tambahkan .strip() untuk membuang spasi gaib dari database!
                kata_kotor = row_word[0].lower().strip() 
                kategori_kata = row_word[1].lower() if row_word[1] else "umum" 
                
                pola_regex = r'\b' + re.escape(kata_kotor) + r'\b'
                
                if re.search(pola_regex, pesan_lower):
                    print(f"🚨 [SATPAM] Pelanggaran! Kata '{kata_kotor}' (Kategori: {kategori_kata}).")
                    
                    # Matikan bot (Admin yang akan handle di WA)
                    cursor.execute("UPDATE public.customers SET bot_active = false WHERE id_customer = %s", (chat_id,))
                    conn.commit()
                    
                    return False # Stop AI memproses lebih lanjut

        # 3. JIKA AMAN DARI BLACKLIST
        cursor.execute("UPDATE public.customers SET last_interaction = NOW() WHERE id_customer = %s", (chat_id,))
        conn.commit()
        
    except Exception as e:
        print(f"❌ [ERROR DB] Gagal mengecek izin: {e}")
    finally:
        cursor.close()
        conn.close()
        
    return diizinkan

# =================================================================
# 🛡️ FUNGSI SATPAM KHUSUS WEB (Tanpa kirim via WAHA)
# =================================================================
def cek_izin_dan_update_interaksi_web(session_id: str, teks_pesan: str = "") -> dict:
    """
    Versi web dari cek_izin_dan_update_interaksi.
    Bedanya: tidak mengirim balasan via WAHA, return dict dengan status dan alasan.
    
    Fungsi ini tetap melakukan:
    - Registrasi customer baru ke DB (jika belum ada)
    - Moderasi kata blacklist
    - Update last_interaction
    
    Return: {"allowed": True/False, "reason": "pesan peringatan jika blocked"}
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 1. CEK APAKAH CUSTOMER SUDAH ADA, JIKA BELUM → DAFTARKAN
        cursor.execute("SELECT bot_active FROM public.customers WHERE id_customer = %s", (session_id,))
        row = cursor.fetchone()
        
        if row:
            if row[0] == False:
                print(f"🛑 [SATPAM WEB] Sesi {session_id} diblokir (bot_active = False).")
                return {
                    "allowed": False, 
                    "reason": "Anda telah diblokir karena melanggar aturan penggunaan. Silakan hubungi admin untuk informasi lebih lanjut."
                }
        else:
            # Customer baru dari web — daftarkan ke database
            cursor.execute("""
                INSERT INTO public.customers (id_customer, bot_active, total_orders, last_interaction)
                VALUES (%s, true, 0, NOW())
            """, (session_id,))
            conn.commit()
            print(f"[CHAT API] 🆕 Customer web baru terdaftar: {session_id}")

        # 2. MODERASI KATA BLACKLIST
        if teks_pesan:
            pesan_lower = teks_pesan.lower()
            cursor.execute("SELECT word, category FROM public.blacklisted_words")
            bad_words_db = cursor.fetchall()
            
            for row_word in bad_words_db:
                kata_kotor = row_word[0].lower().strip()
                kategori_kata = row_word[1].lower() if row_word[1] else "umum"
                pola_regex = r'\b' + re.escape(kata_kotor) + r'\b'
                
                if re.search(pola_regex, pesan_lower):
                    print(f"🚨 [SATPAM WEB] Pelanggaran dari {session_id}! Kata: '{kata_kotor}' (Kategori: {kategori_kata})")
                    
                    # Matikan bot untuk session ini
                    cursor.execute("UPDATE public.customers SET bot_active = false WHERE id_customer = %s", (session_id,))
                    conn.commit()
                    
                    # Pesan peringatan sesuai kategori
                    if kategori_kata == "kasar":
                        reason = "Anda diblokir karena menggunakan bahasa kasar. Mohon gunakan bahasa yang sopan saat berkomunikasi."
                    else:
                        reason = "Anda diblokir karena mengirimkan konten yang tidak sesuai. Kami hanya melayani pertanyaan seputar AC dan CCTV."
                    
                    return {"allowed": False, "reason": reason}

        # 3. UPDATE LAST INTERACTION
        cursor.execute("UPDATE public.customers SET last_interaction = NOW() WHERE id_customer = %s", (session_id,))
        conn.commit()
        
    except Exception as e:
        print(f"❌ [SATPAM WEB ERROR] {e}")
    finally:
        cursor.close()
        conn.close()
        
    return {"allowed": True, "reason": ""}

def ubah_status_bot_manual(input_admin: str, status: bool):
    """Dipanggil dari Pusat Kendali (Admin chat '/bot off' ke diri sendiri)"""
    
    # 1. Bersihkan nomor dari spasi/karakter aneh
    nomor_hp = "".join(filter(str.isdigit, input_admin))
    
    # --- UBAH '0' MENJADI '62' (Jaga-jaga jika admin ketik manual 0812...) ---
    if nomor_hp.startswith("0"):
        nomor_hp = "62" + nomor_hp[1:]
    # ------------------------------------------------------------------------
    
    id_cus = f"{nomor_hp}@c.us"
    print(f"\n🔍 [DEBUG PUSAT KENDALI] Target Update Status: {id_cus} menjadi {'ON' if status else 'OFF'}")
    
    # 2. Langsung eksekusi ke Database (Sangat Cepat & Ringan!)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE public.customers SET bot_active = %s WHERE id_customer = %s", (status, id_cus))
        conn.commit()
        
        if cursor.rowcount > 0:
            return f"✅ Berhasil! Bot untuk pelanggan {nomor_hp} sekarang {'MENYALA' if status else 'MATI'}."
        else:
            return f"⚠️ Gagal: Nomor {nomor_hp} tidak ditemukan di database. Pastikan pelanggan tersebut pernah melakukan chat."
    except Exception as e:
        return f"❌ Gagal update database: {e}"
    finally:
        cursor.close()
        conn.close()

def tambah_kata_blacklist(kata: str, kategori: str = "umum"):
    """Fungsi Admin untuk menambahkan kata terlarang ke blacklist"""
    
    # Rapikan kata (huruf kecil semua dan hilangkan spasi berlebih)
    kata_bersih = kata.strip().lower()
    kategori_bersih = kategori.strip().lower()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 1. Cek dulu apakah kata ini sudah ada di database
        cursor.execute("SELECT id FROM public.blacklisted_words WHERE word = %s", (kata_bersih,))
        if cursor.fetchone():
            return f"⚠️ Kata '{kata_bersih}' sudah ada di blacklist!"

        # 2. Jika belum ada, masukkan ke database
        # Asumsi: kolom 'id' menggunakan auto-increment (SERIAL) di Postgres
        cursor.execute(
            """
            INSERT INTO public.blacklisted_words (word, category, created_at) 
            VALUES (%s, %s, NOW())
            """, 
            (kata_bersih, kategori_bersih)
        )
        conn.commit()
        return f"✅ Berhasil! Kata '{kata_bersih}' (Kategori: {kategori_bersih}) telah dimasukkan ke blacklist."
        
    except Exception as e:
        return f"❌ Gagal menambahkan kata ke blacklist: {e}"
    finally:
        cursor.close()
        conn.close()

def hapus_kata_blacklist(kata: str):
    """Fungsi Admin untuk menghapus kata dari blacklist"""
    
    # Rapikan kata agar pencariannya akurat (karena di DB disave huruf kecil)
    kata_bersih = kata.strip().lower()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Jalankan perintah DELETE
        cursor.execute("DELETE FROM public.blacklisted_words WHERE word = %s", (kata_bersih,))
        conn.commit()
        
        # Mengecek apakah ada baris data yang benar-benar terhapus
        if cursor.rowcount > 0:
            return f"✅ Berhasil! Kata '{kata_bersih}' telah dihapus dari blacklist."
        else:
            return f"⚠️ Info: Kata '{kata_bersih}' tidak ada di dalam daftar blacklist."
            
    except Exception as e:
        return f"❌ Gagal menghapus kata dari blacklist: {e}"
    finally:
        cursor.close()
        conn.close()

def lihat_pelanggan_bot_nonaktif():
    """Mengambil pelanggan yang bot_active-nya False"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id_customer FROM public.customers WHERE bot_active = false ORDER BY last_interaction DESC")
        rows = cursor.fetchall()
        
        if not rows:
            return "✅ *DAFTAR KOSONG*\nSaat ini tidak ada pelanggan dengan Bot Nonaktif (Semua dilayani AI)."
            
        pesan = "📋 *DAFTAR PELANGGAN (BOT NONAKTIF)* 📋\nMenunggu balasan manual Admin:\n\n"
        for i, row in enumerate(rows, 1):
            id_asli = row[0]
            
            # Karena database sudah dipastikan isinya @c.us, kita tinggal bersihkan
            id_bersih = id_asli.replace("@c.us", "")
            
            # (Opsional) Jaga-jaga jika ada data sisa masa lalu di database yang belum terhapus
            id_bersih = id_bersih.replace("@lid", "") 
            
            pesan += f"{i}. wa.me/{id_bersih}\n"
            
        pesan += "\n💡 _Ketik /bot on [nomor] untuk mengembalikan pelanggan ke AI._"
        return pesan
    except Exception as e:
        return f"❌ Gagal mengambil daftar pelanggan: {e}"
    finally:
        cursor.close()
        conn.close()


def lihat_daftar_blacklist():
    """Mengambil semua daftar kata terlarang dengan format terkelompok"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # PENTING: Wajib di-ORDER BY category agar kata dengan kategori sama berjejeran
        cursor.execute("SELECT word, category FROM public.blacklisted_words ORDER BY category, word")
        rows = cursor.fetchall()
        
        if not rows:
            return "✅ *DAFTAR KATA TERLARANG KOSONG*"
            
        pesan = "Kata Blacklist\n"
        kategori_sekarang = None # Variabel pengingat kategori
        
        for row in rows:
            kata = row[0]
            # Jika kategori null, kita anggap 'Umum'
            kategori = row[1].strip() if row[1] else "Umum" 
            kategori = kategori.title() # Ubah 'judol' jadi 'Judol'
            
            # Jika ini kategori baru, cetak sebagai Judul (Bold)
            if kategori != kategori_sekarang:
                pesan += f"\n*{kategori}*\n"
                kategori_sekarang = kategori # Update pengingat
                
            # Cetak daftar katanya (tanpa bold)
            pesan += f"- {kata}\n"
            
        pesan += "\n💡 _Ketik /unblacklist [kata] untuk menghapus._"
        return pesan
        
    except Exception as e:
        return f"❌ Gagal mengambil blacklist: {e}"
    finally:
        cursor.close()
        conn.close()

def normalisasi_id_waha(raw_id: str) -> str:
    """
    Satpam Pintu Gerbang: Mengubah SEMUA jenis ID WhatsApp 
    menjadi format standar internasional yang berakhiran @c.us
    """
    # 1. Jika itu @lid, kita bongkar dan cari nomor aslinya
    if "@lid" in raw_id:
        # Gunakan fungsi yang sudah kamu buat sebelumnya di n8n/python
        nomor_asli = dapatkan_phone_dari_lid(raw_id) 
        
        # Bersihkan dari embel-embel lain
        nomor_bersih = str(nomor_asli).replace("@c.us", "").replace("@lid", "").strip()
        return f"{nomor_bersih}@c.us"
        
    # 2. Jika ID masuk belum ada @c.us (misal cuma angka 62813...), kita tambahkan
    if not raw_id.endswith("@c.us") and "@g.us" not in raw_id:
        # Hati-hati jangan tambahkan ke @g.us (Grup WhatsApp)
        nomor_bersih = str(raw_id).strip()
        return f"{nomor_bersih}@c.us"
        
    # 3. Jika sudah @c.us sejak awal, kembalikan apa adanya
    return raw_id

def bersihkan_memori_langgraph():
    """
    Fungsi Garbage Collector: Menghapus checkpoint memori LangGraph
    untuk customer yang tidak aktif lebih dari 3 hari.
    """
    print("🧹 [GARBAGE COLLECTOR] Memulai pembersihan memori LangGraph (Inaktif > 3 Hari)...")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # CATATAN PENTING: 
        # Sesuaikan 'nomor_wa' dengan nama kolom di tabel customers milikmu.
        # Jika thread_id di LangGraph berformat "628123@c.us" sedangkan di tabel customers 
        # hanya "628123", maka kamu harus menggabungkannya di SQL: (nomor_wa || '@c.us')
        
        # 1. Hapus dari checkpoint_writes (Tabel anakan 1)
        query_del_writes = """
            DELETE FROM checkpoint_writes 
            WHERE thread_id IN (
                SELECT nomor_wa 
                FROM customers 
                WHERE last_interaction < NOW() - INTERVAL '3 days'
            );
        """
        cursor.execute(query_del_writes)
        writes_terhapus = cursor.rowcount

        # 2. Hapus dari checkpoint_blobs (Tabel anakan 2)
        query_del_blobs = """
            DELETE FROM checkpoint_blobs 
            WHERE thread_id IN (
                SELECT nomor_wa 
                FROM customers 
                WHERE last_interaction < NOW() - INTERVAL '3 days'
            );
        """
        cursor.execute(query_del_blobs)
        blobs_terhapus = cursor.rowcount

        # 3. Hapus dari checkpoints (Tabel Induk)
        query_del_checkpoints = """
            DELETE FROM checkpoints 
            WHERE thread_id IN (
                SELECT nomor_wa 
                FROM customers 
                WHERE last_interaction < NOW() - INTERVAL '3 days'
            );
        """
        cursor.execute(query_del_checkpoints)
        checkpoints_terhapus = cursor.rowcount

        # Commit semua penghapusan
        conn.commit()
        
        print(f"✅ [GARBAGE COLLECTOR] Selesai!")
        print(f"   - Checkpoints terhapus: {checkpoints_terhapus} baris")
        print(f"   - Writes terhapus: {writes_terhapus} baris")
        print(f"   - Blobs terhapus: {blobs_terhapus} baris")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ [GARBAGE COLLECTOR] Error saat membersihkan memori: {e}")