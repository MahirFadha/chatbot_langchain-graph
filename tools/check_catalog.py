from langchain_core.tools import tool
from supabase import create_client, Client
from config.settings import SUPABASE_URL, SUPABASE_KEY
from llm.embedding_client import get_embedding_model # <-- IMPORT BARU

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

@tool
def cari_katalog_produk(kata_kunci: str) -> str:
    """Gunakan tool ini untuk mencari spesifikasi, fitur, detail harga AC, dan layanan Jasa Pasang AC."""
    try:
        # PANGGIL MODEL DARI PUSAT
        embedding_model = get_embedding_model()
        
        vektor_query = embedding_model.embed_query(kata_kunci)
        vektor_string = f"[{','.join(map(str, vektor_query))}]"
        
        response = supabase.rpc(
            "match_documents", 
            {"query_embedding": vektor_string, "match_count": 3}
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
            
        return hasil_teks
        
    except Exception as e:
        error_msg = f"ERROR ASLI SUPABASE: {str(e)}"
        print(f"\n!!!!! {error_msg} !!!!!\n")
        return "Sistem sedang error, tolong beritahu pelanggan."