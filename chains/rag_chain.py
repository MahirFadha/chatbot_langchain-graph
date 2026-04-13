import os
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_core.tools import create_retriever_tool

def setup_rag_tool():
    embedding_model = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    persist_dir_sop = "./chroma_db_sop"
    
    if not os.path.exists(persist_dir_sop):
        loader = TextLoader("./data/sop.txt")
        docs = loader.load()
        splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
        splits = splitter.split_documents(docs)
        db_sop = Chroma.from_documents(documents=splits, embedding=embedding_model, persist_directory=persist_dir_sop)
    else:
        db_sop = Chroma(persist_directory=persist_dir_sop, embedding_function=embedding_model)

    retriever_sop = db_sop.as_retriever(search_kwargs={"k": 2})
    tool_sop = create_retriever_tool(
        retriever_sop,
        name="cari_sop_toko",
        description="Gunakan tool ini HANYA untuk mencari informasi jam buka, retur, atau prosedur toko."
    )
    return tool_sop