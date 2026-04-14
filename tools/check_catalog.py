from langchain_core.tools import tool
from supabase import create_client, Client
from config.settings import SUPABASE_URL, SUPABASE_KEY
from llm.embedding_client import get_embedding_model # <-- IMPORT BARU

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

@tool
def cari_katalog_produk(kata_kunci: str) -> str:
    # 1. PERBAIKI DESKRIPSI (Ini sangat fatal untuk AI)
    """Gunakan tool ini untuk mencari informasi produk AC, spesifikasi, dan layanan (Jasa Pasang/Cuci AC).
    PENTING: Buatlah 'kata_kunci' yang PANJANG dan DESKRIPTIF. 
    Contoh: Jika pelanggan bertanya tentang cuci AC, JANGAN hanya mencari 'cuci ac', tapi carilah 'layanan jasa pembersihan perawatan cuci ac'."""
    
    try:
        # 2. PASANG CCTV KATA KUNCI
        print(f"\n[DEBUG TOOL] Kata Kunci yang diketik Gemini: '{kata_kunci}'")
        
        embedding_model = get_embedding_model()
        vektor_query = embedding_model.embed_query(kata_kunci)
        vektor_string = f"[{','.join(map(str, vektor_query))}]"
        
        response = supabase.rpc(
            "match_documents", 
            {"query_embedding": vektor_string, "match_count": 5}
        ).execute()
        
        data = response.data
        if not data:
            return f"Maaf, tidak ditemukan data yang relevan dengan '{kata_kunci}'."
            
        hasil_teks = f"Ditemukan {len(data)} hasil di database:\n\n"
        for item in data:
            meta = item.get("metadata", {})
            hasil_teks += f"[{str(meta.get('tipe_item')).upper()}] - Ref ID: {meta.get('id_referensi')}\n"
            hasil_teks += f"{item.get('content')}\n"
            hasil_teks += "-" * 20 + "\n"
            
        # (CCTV hasil teks yang sebelumnya kita buat boleh tetap ada)
        print(f"\n[DEBUG TOOL] Data dari Supabase:\n{hasil_teks}")
        
        return hasil_teks
        
    except Exception as e:
        error_msg = f"ERROR ASLI SUPABASE: {str(e)}"
        print(f"\n!!!!! {error_msg} !!!!!\n")
        return "Sistem sedang error, tolong beritahu pelanggan."