from agents.cs_agent import build_agent
import uuid

def run_cli_mode():
    print("Memuat Agen AI LangGraph...")
    agen = build_agent()
    
    # Generate ID Unik untuk memori percakapan (Thread ID di LangGraph)
    thread_id = str(uuid.uuid4())
    print(f"--- Sesi Chat Dimulai (Thread ID: {thread_id}) ---")
    print("Ketik 'keluar' untuk menghentikan aplikasi.\n")
    
    # Konfigurasi LangGraph
    config = {"configurable": {"thread_id": thread_id}}
    
    while True:
        user_input = input("Pelanggan: ")
        if user_input.lower() in ['keluar', 'exit', 'quit','q']:
            print("Mematikan agen...")
            break
            
        try:
            # LangGraph mengharapkan input berupa struktur pesan
            input_state = {"messages": [("user", user_input)]}
            
            # Eksekusi agen (stream mode agar kita bisa melihat jika dia memanggil tool)
            print("AI sedang berpikir...")
            
            # Kita gunakan invoke untuk mendapatkan state akhir
            hasil = agen.invoke(input_state, config=config)
            
            # Hasil dari LangGraph adalah seluruh state memori. 
            # Kita ambil pesan paling terakhir (indeks -1) yang merupakan jawaban AI.
            jawaban_ai = hasil["messages"][-1].content
            
            print(f"AI CS: {jawaban_ai}\n")
            
        except Exception as e:
            print(f"Terjadi error: {e}")

if __name__ == "__main__":
    run_cli_mode()