from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from config.settings import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS
from psycopg_pool import ConnectionPool
from graph.state import AgentState
from graph.nodes import node_pemikir, node_eksekutor_alat
from graph.edges import polisi_cek_kebutuhan_alat

# String koneksi khusus untuk psycopg v3
DB_URI = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Buat kolam koneksi (Connection Pool)
# Kolam ini akan terus terbuka dan dipakai bergantian oleh agen AI
pool = None

def get_db_pool():
    global pool
    if pool is None:
        pool = ConnectionPool(
            conninfo=DB_URI,
            kwargs={"autocommit": True}  # <--- INI OBATNYA!
        )
    return pool

def rakit_pabrik_cs():
    print("Membangun Cetak Biru (Blueprint) LangGraph...")
    
    # 1. Siapkan Pabrik dengan Papan Jalan kita
    pabrik = StateGraph(AgentState)
    
    # 2. Masukkan Pekerja ke dalam Ruangan
    pabrik.add_node("ruang_pemikir", node_pemikir)
    pabrik.add_node("ruang_tools", node_eksekutor_alat)
    
    # 3. PASANG PIPA (EDGES)
    # Pintu masuk langsung ke ruang pemikir
    pabrik.add_edge(START, "ruang_pemikir")
    
    # Dari ruang pemikir, pasang Polisi Lalu Lintas (Conditional Edge)
    pabrik.add_conditional_edges(
        "ruang_pemikir",            # Titik asal
        polisi_cek_kebutuhan_alat,  # Fungsi penentu arah
        # Kalau fungsi di atas me-return "tools", masuk ke ruang_tools. Kalau "__end__", keluar.
        {"tools": "ruang_tools", "__end__": END} 
    )
    
    # Kalau sudah selesai dari ruang tools, WAJIB kembali ke ruang pemikir untuk evaluasi
    pabrik.add_edge("ruang_tools", "ruang_pemikir")
    
    # 4. Pasang CCTV Memori
    active_pool = get_db_pool()
    memory = PostgresSaver(active_pool)
    memory.setup() # Otomatis membuat tabel jika belum ada
    
    # 5. Resmikan Pabrik!
    agen_beroperasi = pabrik.compile(checkpointer=memory)
    
    return agen_beroperasi

def tutup_pabrik_cs():
    """Fungsi ini dipanggil saat server mati untuk menutup kolam koneksi DB"""
    global pool
    if pool is not None:
        try:
            pool.close()
            print("[SYSTEM] 🔌 Kolam Koneksi PostgreSQL LangGraph berhasil ditutup.")
        except Exception as e:
            print(f"❌ [SYSTEM] Gagal menutup koneksi: {e}")