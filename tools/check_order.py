from langchain_core.tools import tool
from supabase import create_client, Client
from config.settings import SUPABASE_URL, SUPABASE_KEY

# Tabel orders ada di schema 'public' (default), jadi tidak perlu ClientOptions
supabase_public: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

@tool
def cek_status_pesanan(order_id: str) -> str:
    """Gunakan tool ini untuk mengecek status pesanan, harga total, dan item apa saja yang dibeli pelanggan. 
    Input harus berupa ID Pesanan (misal: ORD-123)."""
    try:
        # Ambil header order
        order_resp = supabase_public.table("orders").select("order_status, total_price").eq("order_id", order_id).execute()
        if not order_resp.data:
            return f"ID Pesanan '{order_id}' tidak ditemukan di sistem."
            
        pesanan = order_resp.data[0]
        
        # Ambil detail order
        detail_resp = supabase_public.table("order_detail").select("item_name, qty, price").eq("order_id", order_id).execute()
        
        # Rangkai informasi untuk AI
        laporan = f"Status Pesanan {order_id}: {pesanan['order_status'].upper()}.\n"
        laporan += f"Total Harga: Rp{pesanan['total_price']}\n"
        laporan += "Detail Barang:\n"
        
        for item in detail_resp.data:
            laporan += f"- {item['item_name']} (Jumlah: {item['qty']}, Harga Satuan: Rp{item['price']})\n"
            
        return laporan
    except Exception as e:
        return f"Terjadi kesalahan saat mengecek data orders: {str(e)}"