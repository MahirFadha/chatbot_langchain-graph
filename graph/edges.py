from typing import Literal
from graph.state import AgentState

def polisi_cek_kebutuhan_alat(state: AgentState) -> Literal["tools", "__end__"]:
    """Mengecek pesan terakhir dari AI, apakah dia minta izin pakai alat?"""
    
    pesan_terakhir = state["messages"][-1]
    
    # Jika di pesan terakhir AI memanggil alat (tool_calls tidak kosong)
    if pesan_terakhir.tool_calls:
        print("\n[ROUTER] 🚦 LLM butuh alat! Mengalihkan ke ruang Eksekutor...")
        return "tools"
    
    # Jika tidak memanggil alat, berarti AI sudah punya jawaban final untuk user
    print("\n[ROUTER] 🏁 Jawaban final ditemukan! Mengalihkan ke pintu keluar...")
    return "__end__"