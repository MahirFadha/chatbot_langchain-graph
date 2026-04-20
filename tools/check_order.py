import psycopg2
from langchain_core.tools import tool
from config.settings import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS

@tool
def cek_status_pesanan(order_id: str) -> str:
    """Gunakan tool ini untuk mengecek status pesanan, harga total, dan item apa saja yang dibeli pelanggan. 
    Input harus berupa ID Pesanan (misal: ORD-123)."""
    
    try:
        conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS
        )
        cursor = conn.cursor()
        
        # Ambil header order
        cursor.execute("SELECT order_status, total_price FROM orders WHERE order_id = %s", (order_id,))
        order_data = cursor.fetchone()
        
        if not order_data:
            return f"ID Pesanan '{order_id}' tidak ditemukan di sistem."
            
        status_pesanan = order_data[0]
        total_harga = order_data[1]
        
        # Ambil detail order
        cursor.execute("SELECT item_name, qty, price FROM order_detail WHERE order_id = %s", (order_id,))
        detail_data = cursor.fetchall()
        
        laporan = f"Status Pesanan {order_id}: {status_pesanan.upper()}.\n"
        laporan += f"Total Harga: Rp{total_harga}\n"
        laporan += "Detail Barang:\n"
        
        for item in detail_data:
            laporan += f"- {item[0]} (Jumlah: {item[1]}, Harga Satuan: Rp{item[2]})\n"
            
        cursor.close()
        conn.close()
        return laporan
        
    except Exception as e:
        return f"Terjadi kesalahan saat mengecek database pesanan: {str(e)}"