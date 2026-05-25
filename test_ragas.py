"""
Script Evaluasi RAGAS untuk Chatbot Aire Optima
Dengan rotasi API key otomatis untuk mengatasi rate limit Gemini free tier
Jalankan: python test_ragas.py
"""
import os
import time
from dotenv import load_dotenv
load_dotenv()
from config.settings import GOOGLE_API_KEY, GOOGLE_API_KEY_RAGAS_1, GOOGLE_API_KEY_RAGAS_2, GOOGLE_API_KEY_RAGAS_3, GOOGLE_API_KEY_RAGAS_4, GOOGLE_API_KEY_RAGAS_5

from datasets import Dataset
from ragas import evaluate
from ragas.metrics import (
    Faithfulness,
    AnswerRelevancy,
    ContextPrecision,
    ContextRecall,
)
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_huggingface import HuggingFaceEmbeddings

# ============================================================
# 1. SETUP ROTASI API KEY
# ============================================================

# Simpan semua API key di .env seperti ini:
# GOOGLE_API_KEY_1=AIza...
# GOOGLE_API_KEY_2=AIza...
# GOOGLE_API_KEY_3=AIza...

api_keys = [
    k for k in [
        GOOGLE_API_KEY_RAGAS_1,
        GOOGLE_API_KEY_RAGAS_2,
        GOOGLE_API_KEY_RAGAS_3,
        GOOGLE_API_KEY_RAGAS_4,
        GOOGLE_API_KEY_RAGAS_5
    ]
    if k is not None  # abaikan key yang tidak diset
]

# Fallback ke single key jika hanya punya 1 akun
if not api_keys:
    single_key = GOOGLE_API_KEY
    if single_key:
        api_keys = [single_key]
    else:
        raise ValueError("Tidak ada API key ditemukan di .env")

print(f"✅ {len(api_keys)} API key ditemukan")

# Index key yang sedang aktif
current_key_index = 0

def get_llm(key_index: int = 0):
    """Buat instance LLM dengan key tertentu"""
    return ChatGoogleGenerativeAI(
        model="gemini-3.1-flash-lite",  # perbaikan nama model
        temperature=0.0,
        api_key=api_keys[key_index]
    )

def get_llm_with_fallback():
    """
    Coba buat LLM, kalau kena rate limit otomatis
    pindah ke key berikutnya
    """
    global current_key_index

    for attempt in range(len(api_keys)):
        try:
            idx = (current_key_index + attempt) % len(api_keys)
            llm = get_llm(idx)

            # Test ringan untuk cek apakah key aktif
            llm.invoke("hi")

            current_key_index = idx
            print(f"✅ Menggunakan API key ke-{idx + 1}")
            return llm

        except Exception as e:
            error_msg = str(e).lower()
            if "quota" in error_msg or "limit" in error_msg or "429" in error_msg:
                print(f"⚠️  Key ke-{idx + 1} kena rate limit, coba key berikutnya...")
                time.sleep(2)
                continue
            else:
                # Error bukan rate limit, langsung raise
                raise e

    # Semua key habis quota — tunggu lalu coba lagi
    print("⏳ Semua key kena rate limit, tunggu 60 detik...")
    time.sleep(60)
    return get_llm(0)

# ============================================================
# 2. SETUP LLM & EMBEDDING
# ============================================================

langchain_llm = get_llm_with_fallback()

# Embedding tetap pakai HuggingFace lokal — tidak perlu API
# karena sudah ada di project Anda dan tidak ada limit
langchain_embeddings = HuggingFaceEmbeddings(
    model_name="intfloat/multilingual-e5-base",
    model_kwargs={"device": "cuda"},  # ganti ke "cuda" jika ada GPU
    encode_kwargs={"normalize_embeddings": True}
)

llm_judge  = LangchainLLMWrapper(langchain_llm)
emb_judge  = LangchainEmbeddingsWrapper(langchain_embeddings)

metrics = [
    Faithfulness(llm=llm_judge),
    AnswerRelevancy(llm=llm_judge, embeddings=emb_judge),
    ContextPrecision(llm=llm_judge),
    ContextRecall(llm=llm_judge),
]

# ============================================================
# 3. DATASET EVALUASI
# ============================================================

eval_data = {
    "question": [
        # 1-5: Pertanyaan asli
        "Berapa harga pasang ac split 2 pk",
        "Berapa harga refill freon r22 2 pk",
        "Berapa harga daikin thailand 1 pk",
        "Bagaimana spesifikasi dari AC Daikin 1.5 pk",
        "AC Honshu 2 pk cocok untuk ruangan berapa m",
        # 6-10: Pertanyaan tentang jasa
        "Berapa biaya cuci AC split 1 pk",
        "Berapa harga bongkar AC split 2 pk",
        "Ada biaya tambahan kalau pasang AC malam hari",
        "Berapa biaya pasang AC di apartemen",
        "Berapa lama garansi jasa pasang AC",
        # 11-15: Pertanyaan tentang produk
        "Berapa harga AC LG 1 pk",
        "Ada AC yang cocok untuk ruangan 12 m persegi",
        "Merek AC apa saja yang tersedia",
        "Berapa harga AC Daikin 2 pk",
        "AC apa yang paling hemat listrik 1.5 pk",
        # 16-20: Pertanyaan umum tentang layanan
        "Aire Optima buka jam berapa",
        "Area layanan Aire Optima meliputi mana saja",
        "Bagaimana cara pesan jasa pasang AC",
        "Metode pembayaran apa saja yang tersedia",
        "Apakah bisa reschedule jadwal teknisi",
    ],
    "answer": [
        # 1-5: Jawaban asli
        "Untuk jasa pasang AC Split ukuran 1.5 sampai 2 PK harganya Rp350.000 yaa kak.",
        "Untuk refill atau isi full freon R-22 ukuran 1.5 sampai 2 PK harganya Rp410.000 yaa kak.",
        "Untuk AC Daikin Thailand 1 PK harganya Rp4.307.000 yaa kak. Harga tersebut belum termasuk jasa pasang yaa kak. Untuk jasa pasang AC Split 0.5 - 1 PK ada tambahan biaya Rp250.000.",
        "Siap kak, untuk AC Daikin 1.5 PK model Daikin Inverter (FTKQ35UVM4) spesifikasinya: Kapasitas Pendinginan 11.900 BTU/h, Daya Listrik 990 Watt (Mode Inverter), Tipe Freon R32, EER Bintang 5. Fitur unggulannya ada Super PCB tahan lonjakan listrik hingga 440V, Gin-Ion Blue Filter, dan Mode Low Watt. Cocok untuk ruangan ukuran 18 - 24 m².",
        "AC Honshu 2 PK cocok untuk ruangan ukuran 24 - 36 m² yaa kak.",
        # 6-10: Jawaban jasa
        "Untuk jasa cuci AC Split ukuran 0.5 sampai 1 PK harganya Rp80.000 yaa kak.",
        "Untuk jasa bongkar AC Split ukuran 1.5 sampai 2 PK harganya Rp200.000 yaa kak.",
        "Iya kak, ada biaya tambahan Rp50.000 untuk pengerjaan di jam malam yaitu jam 18.00 - 00.00 WIB.",
        "Untuk pasang AC di apartemen ada biaya tambahan Rp25.000 karena tingkat kesulitan akses dan perizinan gedung yaa kak. Jadi total biaya pasang AC Split 0.5-1 PK di apartemen adalah Rp275.000.",
        "Garansi jasa pasang AC berlaku selama 30 hari yaa kak. Sedangkan untuk jasa servis dan cuci AC garansinya 7 hari.",
        # 11-15: Jawaban produk
        "Untuk AC LG 1 PK harganya Rp3.850.000 yaa kak. Harga tersebut belum termasuk jasa pasang. Untuk jasa pasang AC Split 0.5-1 PK ada tambahan biaya Rp250.000.",
        "Untuk ruangan 12 m² cocoknya pakai AC 0.5 sampai 1 PK kak. Kami punya beberapa pilihan seperti Daikin Thailand 1 PK Rp4.307.000 atau LG 1 PK Rp3.850.000.",
        "Kami menyediakan beberapa merek AC kak, antara lain Daikin, Daikin Thailand, LG, Honshu, dan beberapa merek lainnya.",
        "Untuk AC Daikin 2 PK harganya Rp7.200.000 yaa kak. Harga tersebut belum termasuk jasa pasang. Untuk jasa pasang AC Split 1.5-2 PK ada tambahan biaya Rp350.000.",
        "Untuk AC 1.5 PK yang hemat listrik, kami rekomendasikan Daikin Inverter 1.5 PK kak. Dengan mode inverter daya listriknya hanya 990 Watt dan sudah EER Bintang 5. Harganya Rp5.345.000.",
        # 16-20: Jawaban umum
        "Aire Optima buka setiap hari Senin sampai Minggu selama 24 jam kak.",
        "Area layanan kami meliputi wilayah Surabaya, Gresik, dan Sidoarjo kak.",
        "Untuk pesan jasa pasang AC, kakak bisa langsung konsultasi di sini. Nanti saya bantu kumpulkan data pesanan, lalu admin kami akan menghubungi kakak via WhatsApp untuk konfirmasi jadwal teknisi.",
        "Kami menyediakan beberapa metode pembayaran kak: Transfer Manual, QRIS, Multi Payment Online, atau bisa juga bayar di akhir setelah teknisi selesai bekerja (Postpaid).",
        "Bisa kak, reschedule dan pembatalan bisa dilakukan selama teknisi belum dalam perjalanan ke lokasi.",
    ],
    "contexts": [
        # 1-5: Konteks asli
        ["Nama Layanan: Jasa Pasang AC Split - 1.5 - 2 PK. Kategori: Jasa. Harga Dasar: Rp350000.00. Keterangan Layanan: Layanan pemasangan unit AC Split untuk kapasitas 1.5 sampai 2 PK."],
        ["Nama Layanan: Refill / Isi Full Freon R-22 - 1.5 - 2 PK. Kategori: Jasa. Harga Dasar: Rp410000.00. Keterangan Layanan: Layanan pengisian ulang freon R-22 untuk AC kapasitas 1.5 sampai 2 PK."],
        ["Nama Produk: DAIKIN THAILAND - 1 PK. Kategori: AC. Merek: DAIKIN THAILAND. Harga Unit Produk: Rp4307000.00. Keterangan Singkat: AC Daikin Thailand 1 PK. Jasa Bundling/Pemasangan Wajib: Jasa Pasang AC Split - 0.5 - 1 PK (Biaya Tambahan Jasa: Rp250000)."],
        ["Nama Produk: DAIKIN - 1.5 PK. Kategori: AC. Merek: DAIKIN. Harga Unit Produk: Rp5345000.00. Keterangan Singkat: AC Daikin Inverter 1.5 PK. Spesifikasi Detail: Model Representatif: Daikin Inverter (FTKQ35UVM4). Kapasitas Pendinginan: 11.900 BTU/h. Daya Listrik: 990 Watt (Mode Inverter). Tipe Freon: R32. EER: Bintang 5. Fitur Unggulan: Super PCB tahan lonjakan listrik hingga 440V, Gin-Ion Blue Filter, Mode Low Watt. Cocok Untuk Ruangan: Ukuran 18 - 24 m²."],
        ["Nama Produk: HONSHU - 2 PK. Kategori: AC. Merek: HONSHU. Harga Unit Produk: Rp5300000.00. Keterangan Singkat: AC Honshu 2 PK. Spesifikasi Detail: Cocok Untuk Ruangan: Ukuran 24 - 36 m²."],
        # 6-10: Konteks jasa
        ["Nama Layanan: Jasa Cuci AC Split - 0.5 - 1 PK. Kategori: Jasa. Harga Dasar: Rp80000.00. Keterangan Layanan: Layanan pembersihan/cuci unit AC Split untuk kapasitas 0.5 sampai 1 PK."],
        ["Nama Layanan: Jasa Bongkar AC Split - 1.5 - 2 PK. Kategori: Jasa. Harga Dasar: Rp200000.00. Keterangan Layanan: Layanan pembongkaran unit AC Split untuk kapasitas 1.5 sampai 2 PK."],
        ["Surcharge Jam Malam: Terdapat biaya tambahan sebesar Rp50.000 untuk pengerjaan di luar jam kerja (jam 18.00 WIB - 00.00 WIB)."],
        ["Surcharge Apartemen: Terdapat biaya tambahan sebesar Rp25.000 untuk pengerjaan di lokasi Apartemen karena tingkat kesulitan akses dan perizinan gedung. Nama Layanan: Jasa Pasang AC Split - 0.5 - 1 PK. Kategori: Jasa. Harga Dasar: Rp250000.00."],
        ["Garansi Jasa (Servis/Cuci/Pasang): Garansi servis, cuci AC berlaku selama 7 hari, sedangkan garansi pasang AC berlaku selama 30 hari."],
        # 11-15: Konteks produk
        ["Nama Produk: LG - 1 PK. Kategori: AC. Merek: LG. Harga Unit Produk: Rp3850000.00. Keterangan Singkat: AC LG 1 PK. Jasa Bundling/Pemasangan Wajib: Jasa Pasang AC Split - 0.5 - 1 PK (Biaya Tambahan Jasa: Rp250000)."],
        ["Nama Produk: DAIKIN THAILAND - 1 PK. Kategori: AC. Merek: DAIKIN THAILAND. Harga Unit Produk: Rp4307000.00. Keterangan Singkat: AC Daikin Thailand 1 PK. Nama Produk: LG - 1 PK. Kategori: AC. Merek: LG. Harga Unit Produk: Rp3850000.00. Keterangan Singkat: AC LG 1 PK."],
        ["Nama Produk: DAIKIN - 1.5 PK. Merek: DAIKIN. Nama Produk: DAIKIN THAILAND - 1 PK. Merek: DAIKIN THAILAND. Nama Produk: LG - 1 PK. Merek: LG. Nama Produk: HONSHU - 2 PK. Merek: HONSHU."],
        ["Nama Produk: DAIKIN - 2 PK. Kategori: AC. Merek: DAIKIN. Harga Unit Produk: Rp7200000.00. Keterangan Singkat: AC Daikin 2 PK. Jasa Bundling/Pemasangan Wajib: Jasa Pasang AC Split - 1.5 - 2 PK (Biaya Tambahan Jasa: Rp350000)."],
        ["Nama Produk: DAIKIN - 1.5 PK. Kategori: AC. Merek: DAIKIN. Harga Unit Produk: Rp5345000.00. Keterangan Singkat: AC Daikin Inverter 1.5 PK. Spesifikasi Detail: Model Representatif: Daikin Inverter (FTKQ35UVM4). Daya Listrik: 990 Watt (Mode Inverter). EER: Bintang 5."],
        # 16-20: Konteks umum
        ["Jam Operasional: Buka setiap hari (Senin - Minggu) selama 24 Jam."],
        ["Cakupan Area Layanan: Meliputi wilayah Surabaya, Gresik, dan Sidoarjo."],
        ["Alur Pemesanan: Pelanggan melakukan konsultasi atau langsung mengajukan permintaan pesanan kepada Bot. Bot akan mengumpulkan data detail pesanan. Setelah seluruh data pesanan dan data diri lengkap, sistem akan mengirimkan notifikasi kepada Admin. Admin akan menghubungi pelanggan melalui WhatsApp untuk konfirmasi akhir dan penentuan jadwal kedatangan teknisi."],
        ["Metode Pembayaran: Aire mendukung dua sistem pembayaran: Pembayaran di Awal (Transfer Manual, QRIS, Multi Payment Online) dan Pembayaran di Akhir setelah jasa selesai (Postpaid)."],
        ["Kebijakan Reschedule & Pembatalan: Reschedule dan pembatalan bisa dilakukan selama teknisi belum perjalanan ke lokasi."],
    ],
    "ground_truth": [
        # 1-5: Ground truth asli
        "Harga jasa pasang AC Split 1.5-2 PK adalah Rp350.000",
        "Harga refill freon R-22 untuk AC 1.5-2 PK adalah Rp410.000",
        "Harga AC Daikin Thailand 1 PK adalah Rp4.307.000 dengan jasa pasang wajib Rp250.000",
        "AC Daikin 1.5 PK model FTKQ35UVM4 memiliki kapasitas 11.900 BTU/h, daya 990 Watt, freon R32, EER Bintang 5, fitur Super PCB, Gin-Ion Blue Filter, Mode Low Watt, cocok untuk ruangan 18-24 m²",
        "AC Honshu 2 PK cocok untuk ruangan ukuran 24-36 m²",
        # 6-10: Ground truth jasa
        "Harga jasa cuci AC Split 0.5-1 PK adalah Rp80.000",
        "Harga jasa bongkar AC Split 1.5-2 PK adalah Rp200.000",
        "Ada biaya tambahan Rp50.000 untuk pengerjaan di jam malam (18.00-00.00 WIB)",
        "Ada biaya tambahan Rp25.000 untuk pengerjaan di apartemen. Harga pasang AC Split 0.5-1 PK adalah Rp250.000",
        "Garansi jasa pasang AC berlaku 30 hari, garansi servis dan cuci AC berlaku 7 hari",
        # 11-15: Ground truth produk
        "Harga AC LG 1 PK adalah Rp3.850.000 dengan jasa pasang wajib Rp250.000",
        "Untuk ruangan 12 m² cocok menggunakan AC 0.5-1 PK seperti Daikin Thailand 1 PK Rp4.307.000 atau LG 1 PK Rp3.850.000",
        "Merek AC yang tersedia antara lain Daikin, Daikin Thailand, LG, dan Honshu",
        "Harga AC Daikin 2 PK adalah Rp7.200.000 dengan jasa pasang wajib Rp350.000",
        "AC Daikin Inverter 1.5 PK memiliki daya 990 Watt dengan EER Bintang 5, harga Rp5.345.000",
        # 16-20: Ground truth umum
        "Aire Optima buka setiap hari Senin-Minggu selama 24 jam",
        "Area layanan Aire Optima meliputi Surabaya, Gresik, dan Sidoarjo",
        "Alur pemesanan: konsultasi dengan bot, bot kumpulkan data pesanan, admin konfirmasi via WhatsApp dan tentukan jadwal teknisi",
        "Metode pembayaran: Transfer Manual, QRIS, Multi Payment Online, atau bayar di akhir (Postpaid)",
        "Reschedule dan pembatalan bisa dilakukan selama teknisi belum dalam perjalanan ke lokasi",
    ],
}

# ============================================================
# 4. EVALUASI PER BATCH DENGAN ROTASI KEY OTOMATIS
# ============================================================

dataset    = Dataset.from_dict(eval_data)
total      = len(eval_data["question"])
batch_size = 2  # 2 pertanyaan per batch agar hemat quota
all_results = []

print("\n" + "="*50)
print("🚀 MEMULAI EVALUASI RAGAS...")
print(f"   Total pertanyaan : {total}")
print(f"   Ukuran batch     : {batch_size}")
print(f"   Total batch      : {(total + batch_size - 1) // batch_size}")
print("="*50)

for i in range(0, total, batch_size):
    batch_num = (i // batch_size) + 1
    end_idx   = min(i + batch_size, total)

    print(f"\n📦 Batch {batch_num} — pertanyaan {i+1} s/d {end_idx}")

    # Ambil slice dataset untuk batch ini
    batch_data = {k: v[i:end_idx] for k, v in eval_data.items()}
    batch_dataset = Dataset.from_dict(batch_data)

    try:
        batch_result = evaluate(
            dataset=batch_dataset,
            metrics=metrics,
            llm=llm_judge,
            embeddings=emb_judge,
        )
        all_results.append(batch_result.to_pandas())
        print(f"   ✅ Batch {batch_num} selesai")

    except Exception as e:
        error_msg = str(e).lower()
        if "quota" in error_msg or "429" in error_msg or "limit" in error_msg:
            print(f"   ⚠️  Rate limit! Coba ganti API key...")

            # Coba key berikutnya
            langchain_llm  = get_llm_with_fallback()
            llm_judge      = LangchainLLMWrapper(langchain_llm)

            # Update semua metrik dengan LLM baru
            metrics = [
                Faithfulness(llm=llm_judge),
                AnswerRelevancy(llm=llm_judge, embeddings=emb_judge),
                ContextPrecision(llm=llm_judge),
                ContextRecall(llm=llm_judge),
            ]

            # Coba ulang batch yang sama
            print(f"   🔄 Mencoba ulang batch {batch_num}...")
            try:
                batch_result = evaluate(
                    dataset=batch_dataset,
                    metrics=metrics,
                    llm=llm_judge,
                    embeddings=emb_judge,
                )
                all_results.append(batch_result.to_pandas())
                print(f"   ✅ Batch {batch_num} berhasil setelah ganti key")
            except Exception as e2:
                print(f"   ❌ Batch {batch_num} gagal: {e2}")
                print(f"   ⏭️  Melewati batch ini...")
        else:
            print(f"   ❌ Error tidak dikenal: {e}")
            raise e

    # Jeda antar batch untuk menghindari rate limit
    if end_idx < total:
        jeda = 30  # detik
        print(f"   ⏳ Jeda {jeda} detik sebelum batch berikutnya...")
        time.sleep(jeda)

# ============================================================
# 5. GABUNGKAN DAN TAMPILKAN HASIL
# ============================================================

if not all_results:
    print("\n❌ Tidak ada hasil yang berhasil dikumpulkan.")
else:
    import pandas as pd

    df_final = pd.concat(all_results, ignore_index=True)
    df_final.to_csv("hasil_ragas.csv", index=False)

    faith     = df_final["faithfulness"].dropna().mean()
    relevancy = df_final["answer_relevancy"].dropna().mean()
    precision = df_final["context_precision"].dropna().mean()
    recall    = df_final["context_recall"].dropna().mean()

    print("\n" + "="*50)
    print("📊 HASIL RATA-RATA EVALUASI RAGAS")
    print("="*50)
    print(f"  Faithfulness      : {faith:.4f}")
    print(f"  Answer Relevancy  : {relevancy:.4f}")
    print(f"  Context Precision : {precision:.4f}")
    print(f"  Context Recall    : {recall:.4f}")
    print("="*50)
    print(f"\n  Berhasil mengevaluasi : {len(df_final)} dari {total} pertanyaan")
    print("  ✅ Detail disimpan ke  : hasil_ragas.csv\n")