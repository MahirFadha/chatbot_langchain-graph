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
                    
                    # Balasan disesuaikan kategori, TAPI eksekusinya SAMA (Matikan Bot)
                    if kategori_kata == "kasar":
                        pesan_balasan = "Mohon maaf, tolong gunakan bahasa yang sopan. Apakah ada yang bisa saya bantu?"
                    else:
                        pesan_balasan = "Mohon maaf, kami tidak melayani pertanyaan mengenai hal tersebut. Apakah ada yang bisa saya bantu mengenai AC dan CCTV?"

                    # Kirim peringatan ke user
                    print(f"⏩ [DEBUG] Mencoba mengirim balasan moderasi ke {chat_id}...")
                    waha_kirim_balasan(chat_id, pesan_balasan)
                    print(f"✅ [DEBUG] Fungsi waha_kirim_balasan selesai dijalankan!")

                    # Matikan bot
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