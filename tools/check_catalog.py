from langchain_core.tools import tool
from langchain_huggingface import HuggingFaceEmbeddings
from supabase import create_client, Client
from config.settings import SUPABASE_URL, SUPABASE_KEY

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# KITA GUNAKAN MODEL YANG SAMA PERSIS DENGAN SAAT KAMU MEMBUAT DATABASE!
embedding_model = HuggingFaceEmbeddings(model_name="paraphrase-multilingual-mpnet-base-v2")

@tool
def cari_katalog_produk(kata_kunci: str) -> str:
    """Gunakan tool ini untuk mencari spesifikasi, fitur, detail harga AC, dan layanan Jasa Pasang AC."""
    try:
        # Ubah teks menjadi vektor (Otomatis akan menjadi 768 dimensi yang benar)
        vektor_query = embedding_model.embed_query(kata_kunci)
        vektor_string = f"[{','.join(map(str, vektor_query))}]"
        
        response = supabase.rpc(
            "match_documents", # Pastikan pakai 's' atau tidak, sesuai database kamu
            {"query_embedding": vektor_string, "match_count": 3}
        ).execute()
        a
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