from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

from llm.gemini_client import get_llm
from tools.check_order import cek_status_pesanan
from tools.check_catalog import cari_katalog_produk  # <--- Import tool SQL manual kita
from chains.rag_chain import setup_rag_tool

def build_agent():
    llm = get_llm()
    tool_sop = setup_rag_tool()
    
    # Gabungkan semua tool
    tools = [cari_katalog_produk, cek_status_pesanan, tool_sop]
    
    instruksi_sistem = """Kamu adalah asisten layanan pelanggan handal dari Kampung Ilmu.
    Tugasmu meliputi:
    1. Menjawab tentang produk dan layanan menggunakan tool cari_katalog_produk.
    2. Mengecek status pesanan pelanggan menggunakan tool cek_status_pesanan.
    3. Menjawab pertanyaan SOP toko (jam buka, retur) menggunakan tool cari_sop_toko.
    Jawablah dengan format yang rapi (gunakan bullet points jika perlu) dan sangat ramah. 
    Jika tidak tahu, jangan mengarang jawaban."""
    
    memori = MemorySaver()
    
    agent = create_react_agent(
        llm, 
        tools=tools, 
        prompt=instruksi_sistem, 
        checkpointer=memori 
    )
    
    return agent