from graph.builder import rakit_pabrik_cs
import uuid

def jalankan_bot():
    agen = rakit_pabrik_cs()
    
    # ID Sesi KTP Pelanggan untuk memori
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    
    print("\n--- Sesi Chat CS Dimulai ---")
    print("Ketik 'keluar' untuk menghentikan aplikasi.\n")
    
    while True:
        teks_user = input("Pelanggan: ")
        if teks_user.lower() in ['keluar', 'exit']:
            print("Mematikan sistem...")
            break
            
        try:
            # Masukkan pesan user ke State awal
            input_state = {"messages": [("user", teks_user)]}
            
            # invoke() akan menjalankan graf dari START sampai END
            hasil_akhir = agen.invoke(input_state, config=config)
            
            # Ambil konten pesan paling terakhir dari State
            isi_pesan = hasil_akhir["messages"][-1].content
            
            # Saringan khusus untuk Gemini: Jika bentuknya list, ambil 'text'-nya saja
            if isinstance(isi_pesan, list):
                jawaban_ai = "".join(item.get("text", "") for item in isi_pesan if isinstance(item, dict))
            else:
                jawaban_ai = isi_pesan
                
            print(f"AI CS: {jawaban_ai}\n")
            
        except Exception as e:
            print(f"Terjadi error fatal: {e}")

if __name__ == "__main__":
    jalankan_bot()