from langchain_chroma import Chroma
from llm.embedding_client import get_embedding_model # Sesuaikan path import jika berbeda

def inspeksi_chroma():
    print("Membaca Vector Database Katalog...\n")
    
    # 1. Load Model Embedding yang sama persis
    embedding_model = get_embedding_model()
    
    # 2. Buka koneksi ke folder Chroma lokal
    direktori_db = "./database/chroma/db_katalog"
    db_katalog = Chroma(
        persist_directory=direktori_db, 
        embedding_function=embedding_model
    )
    
    # 3. Tarik seluruh data (tanpa angka vektornya agar terminal tidak penuh)
    data_isi = db_katalog.get()
    
    # data_isi akan berbentuk Dictionary dengan key: 'ids', 'metadatas', 'documents'
    total_data = len(data_isi['ids'])
    print(f"✅ TOTAL ITEM DI DATABASE: {total_data} data\n")
    
    if total_data == 0:
        print("Database kosong! Sepertinya proses vektorisasi gagal atau belum dijalankan.")
        return

    # 4. Tampilkan sampel 3 data pertama
    batas_tampil = min(3, total_data)
    print(f"--- MENAMPILKAN SAMPEL {batas_tampil} DATA PERTAMA ---\n")
    
    for i in range(batas_tampil):
        print(f"🔑 Vektor ID : {data_isi['ids'][i]}")
        print(f"🏷️  Metadata  : {data_isi['metadatas'][i]}")
        
        # Tampilkan teks asli (dibatasi 200 karakter agar rapi di terminal)
        teks_lengkap = data_isi['documents'][i]
        teks_potong = teks_lengkap[:200] + "..." if len(teks_lengkap) > 200 else teks_lengkap
        print(f"📄 Teks Asli : {teks_potong}")
        print("-" * 50)

    # (Opsional) Tampilkan 1 data yang memiliki tipe_item = 'layanan'
    print("\n--- MENCARI 1 CONTOH DATA 'LAYANAN' ---")
    for i in range(total_data):
        if data_isi['metadatas'][i].get('tipe_item') == 'layanan':
            print(f"🏷️  Metadata  : {data_isi['metadatas'][i]}")
            print(f"📄 Teks Asli : {data_isi['documents'][i][:200]}...")
            break

if __name__ == "__main__":
    inspeksi_chroma()