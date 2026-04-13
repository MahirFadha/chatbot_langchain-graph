from langchain_google_genai import ChatGoogleGenerativeAI
from config.settings import GOOGLE_API_KEY

def get_llm():
    # Menggunakan Gemini 2.5 Flash karena cepat dan sangat baik untuk Agentic Tools
    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash", 
        temperature=0.2, # Dibuat rendah agar AI tidak berhalusinasi saat membaca data
        api_key=GOOGLE_API_KEY
    )