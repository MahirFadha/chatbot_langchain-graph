from langchain_huggingface import HuggingFaceEmbeddings

# Variabel global untuk menyimpan model agar tidak diload berulang kali
_embedding_model = None

def get_embedding_model():
    global _embedding_model
    # Jika model belum pernah di-load, maka load sekarang
    if _embedding_model is None:
        _embedding_model = HuggingFaceEmbeddings(
            # model_name="paraphrase-multilingual-mpnet-base-v2"
            model_name="intfloat/multilingual-e5-base",
            model_kwargs={"device": "gpu"},
            encode_kwargs={"normalize_embeddings": True}
        )
    return _embedding_model
