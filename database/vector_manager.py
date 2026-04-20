import os
import psycopg2
import re
from langchain_core.documents import Document
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_core.tools import create_retriever_tool
from llm.embedding_client import get_embedding_model
from config.settings import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS

# Tambahkan ini di bagian atas file bersama global _embedding_model
vector_katalog_db = None
vector_sop_tool = None

def inisialisasi_vektor_awal():
    """Saklar Utama: Dipanggil di nodes.py saat server/bot pertama kali dinyalakan"""
    global vector_katalog_db, vector_sop_tool
    print("\n[SYSTEM] Memulai Inisialisasi Vector Database...")
    
    vector_katalog_db = setup_katalog_chroma()
    vector_sop_tool = setup_sop_chroma()
    
    print("[SYSTEM] Vector Database Siap!\n")

def setup_sop_chroma():
    """Membaca file txt, memotong teks, dan menjadikannya Vector DB SOP"""
    embedding_model = get_embedding_model()
    persist_dir = "./chroma/db_sop"
    
    if not os.path.exists(persist_dir):
        print("Membangun Vector DB SOP...")
        loader = TextLoader("./data/sop.txt")
        docs = loader.load()
        splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
        splits = splitter.split_documents(docs)
        db_sop = Chroma.from_documents(documents=splits, embedding=embedding_model, persist_directory=persist_dir)
    else:
        db_sop = Chroma(persist_directory=persist_dir, embedding_function=embedding_model)

    # Karena SOP murni untuk dibaca LLM, kita langsung ubah jadi LangChain Tool
    retriever_sop = db_sop.as_retriever(search_kwargs={"k": 2})
    tool_sop = create_retriever_tool(
        retriever_sop,
        name="cari_sop_toko",
        description="Gunakan tool ini HANYA untuk mencari informasi jam buka, retur, atau prosedur toko."
    )
    return tool_sop


def bersihkan_html(teks_html):
    """Fungsi pembantu untuk menghilangkan tag HTML dari detail produk/servis"""
    if not teks_html:
        return ""
    # Hapus tag HTML
    teks_bersih = re.sub(r'<[^>]+>', ' ', teks_html)
    # Hapus spasi berlebih
    return " ".join(teks_bersih.split())

def setup_katalog_chroma():
    embedding_model = get_embedding_model()
    persist_dir_katalog = "./database/chroma/db_katalog"

    # Jika folder Vector DB belum ada, kita bangun dari Postgres
    if not os.path.exists(persist_dir_katalog):
        print("Membangun Vector DB untuk Katalog dari PostgreSQL...")
        
        dokumen_katalog = []
        
        try:
            # Buka koneksi ke Postgres lokal
            conn = psycopg2.connect(
                host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS
            )
            cursor = conn.cursor()
            
            # ==========================================
            # 1. AMBIL DAN RAKIT DATA PRODUK (AC, CCTV)
            # ==========================================
            query_produk = """
                SELECT 
                    p.kdprod, p.prod_name, p.price, p.ket_prod,
                    b.nmmerk, j.nmjens,
                    pd.detail_product,
                    s.srvc_name, s.base_price -- TAMBAHAN: Ambil data service bundling
                FROM catalog.products p
                LEFT JOIN catalog.brands b ON p.kdmerk = b.kdmerk
                LEFT JOIN catalog.jenis_products j ON p.kdjens = j.kdjens
                LEFT JOIN catalog.product_detail pd ON p.kdprod = pd.kdprod
                LEFT JOIN catalog.service_items s ON p.srvc_id = s.srvc_id; -- TAMBAHAN: Relasi service
            """
            cursor.execute(query_produk)
            produk_rows = cursor.fetchall()
            
            for row in produk_rows:
                kdprod = row[0] or ""
                prod_name = row[1] or "Tanpa Nama"
                price = row[2] or 0
                ket_prod = row[3] or ""
                nmmerk = row[4] or "Tanpa Merek"
                nmjens = row[5] or "Umum"
                detail_html = row[6] or ""
                srvc_name = row[7] # Nama jasa bundling (bisa None)
                srvc_price = row[8] # Harga jasa bundling (bisa None)
                
                detail_bersih = bersihkan_html(detail_html)
                
                # RAKIT LOGIKA BUNDLING SERVICE
                info_bundling = ""
                if srvc_name:
                    harga_jasa = srvc_price or 0
                    info_bundling = f"Jasa Bundling/Pemasangan Wajib: {srvc_name} (Biaya Tambahan Jasa: Rp{harga_jasa}). "
                
                # Merakit TEKS GABUNGAN
                teks_gabungan = (
                    f"Nama Produk: {prod_name}. "
                    f"Kategori: {nmjens}. "
                    f"Merek: {nmmerk}. "
                    f"Harga Unit Produk: Rp{price}. "
                    f"Keterangan Singkat: {ket_prod}. "
                    f"{info_bundling}" # <--- AI AKAN MEMBACA BIAYA WAJIB INI
                    f"Spesifikasi Detail: {detail_bersih}."
                )
                
                doc = Document(
                    page_content=teks_gabungan,
                    metadata={"id_referensi": kdprod, "tipe_item": "produk", "merek": nmmerk}
                )
                dokumen_katalog.append(doc)

            # ==========================================
            # 2. AMBIL DAN RAKIT DATA LAYANAN (Jasa Servis/Cuci)
            # ==========================================
            query_layanan = """
                SELECT 
                    s.srvc_id, s.srvc_name, s.base_price, s.srvc_desc,
                    sp.srv_package_name,
                    sd.prob_detail
                FROM catalog.service_items s
                LEFT JOIN catalog.service_packages sp ON s.srvprodid = sp.srv_prodid
                LEFT JOIN catalog.service_detail sd ON s.srvc_id = sd.srvc_id;
            """
            cursor.execute(query_layanan)
            layanan_rows = cursor.fetchall()
            
            for row in layanan_rows:
                srvc_id = row[0] or ""
                srvc_name = row[1] or "Layanan Tanpa Nama"
                base_price = row[2] or 0
                srvc_desc = row[3] or ""
                paket = row[4] or "Paket Standar"
                prob_html = row[5] or ""
                
                prob_bersih = bersihkan_html(prob_html)
                
                # Merakit TEKS GABUNGAN
                teks_gabungan = (
                    f"Nama Layanan: {srvc_name}. "
                    f"Kategori Paket: {paket}. "
                    f"Harga Dasar: Rp{base_price}. "
                    f"Keterangan Layanan: {srvc_desc}. "
                    f"Detail Pengerjaan/Masalah: {prob_bersih}."
                )
                
                doc = Document(
                    page_content=teks_gabungan,
                    metadata={"id_referensi": srvc_id, "tipe_item": "layanan", "kategori": paket}
                )
                dokumen_katalog.append(doc)

            # ==========================================
            # 3. PROSES VEKTORISASI KE CHROMA DB
            # ==========================================
            db_katalog = Chroma.from_documents(
                documents=dokumen_katalog, 
                embedding=embedding_model, 
                persist_directory=persist_dir_katalog
            )
            
            cursor.close()
            conn.close()
            print(f"Berhasil memvektorisasi {len(dokumen_katalog)} item katalog ke Chroma DB!")
            
        except Exception as e:
            print(f"GAGAL MEMBANGUN VEKTOR KATALOG: {e}")
            raise e
            
    else:
        # Jika folder sudah ada, cukup load modelnya
        db_katalog = Chroma(
            persist_directory=persist_dir_katalog, 
            embedding_function=embedding_model
        )
        
    return db_katalog

def get_vector_katalog_db():
    """Fungsi ini dipanggil oleh Tool. Sangat cepat karena mengambil dari RAM/Memory."""
    global vector_katalog_db
    if vector_katalog_db is None:
        # Fallback jaga-jaga kalau lupa inisialisasi di awal
        vector_katalog_db = setup_katalog_chroma()
    return vector_katalog_db

def get_sop_tool():
    """Pustakawan: Dipanggil oleh graph/nodes.py untuk dimasukkan ke daftar alat LLM"""
    global vector_sop_tool
    if vector_sop_tool is None:
        vector_sop_tool = setup_sop_chroma()
    return vector_sop_tool