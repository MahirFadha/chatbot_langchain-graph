from langchain_core.messages import SystemMessage
from langgraph.prebuilt import ToolNode

from graph.state import AgentState
from llm.gemini_client import get_llm
from tools.check_catalog import cari_katalog_produk
from tools.check_order import cek_status_pesanan
from database.vector_manager import inisialisasi_vektor_awal, get_sop_tool

# 1. Kumpulkan semua alat LangChain
inisialisasi_vektor_awal()
tool_sop = get_sop_tool()
daftar_tools = [cari_katalog_produk, cek_status_pesanan, tool_sop]

# 2. PEKERJA 1: EKSEKUTOR ALAT
# LangGraph sudah punya pekerja bawaan yang pintar mengeksekusi daftar alat di atas
node_eksekutor_alat = ToolNode(daftar_tools)

# 3. PEKERJA 2: PEMIKIR (LLM)
def node_pemikir(state: AgentState):
    llm = get_llm()
    # Beri tahu LLM bahwa ia punya alat-alat ini
    llm_dengan_tools = llm.bind_tools(daftar_tools)
    
    instruksi_sistem = SystemMessage(
        content="""Kamu adalah asisten CS handal dari Aire Optima.
        Tugasmu menjawab seputar produk, mengecek pesanan, dan SOP toko.
        Jangan pernah mengarang jawaban jika tidak ada di database."""
    )
    
    # Gabungkan instruksi sistem dengan riwayat chat pelanggan saat ini
    pesan_lengkap = [instruksi_sistem] + state["messages"]
    
    # Suruh LLM berpikir dan membaca seluruh pesan
    response = llm_dengan_tools.invoke(pesan_lengkap)
    
    # Kembalikan response untuk ditambahkan (append) ke State
    return {"messages": [response]}