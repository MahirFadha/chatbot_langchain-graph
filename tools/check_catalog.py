from database.koneksi import get_db_connection
from langchain_core.tools import tool
from database.vector_manager import get_vector_katalog_db

def jalankan_pencarian_sql(kata_kunci: str):
    """Menjalankan pencarian Lexical/Rule-based menggunakan Postgres"""
    
    # KITA GUNAKAN QUERY ASLIMU SECARA UTUH (Hanya ganti $1 jadi %s)
    query_sql = """
    WITH
    -- ==========================================================
    -- 0) INPUT USER
    -- ==========================================================
    raw AS (
      SELECT lower(%s)::text AS q
    ),

    -- ==========================================================
    -- 1) NORMALISASI + HAPUS NOISE WORDS
    -- ==========================================================
    normalized AS (
      SELECT
        q,
        trim(regexp_replace(q, '[^a-z0-9\.\-\s]', ' ', 'g')) AS q_clean0
      FROM raw
    ),
    cleaned AS (
      SELECT
        q,
        trim(regexp_replace(
          q_clean0,
          '\\b(ac|merk|merek|brand|tipe|type|jenis|yang|tolong|pesan|cari|buat|dong|aja|nih|ya|bang|kak|min)\\b',
          '',
          'g'
        )) AS q_clean1
      FROM normalized
    ),
    collapsed AS (
      SELECT
        q,
        trim(regexp_replace(q_clean1, '\\s+', ' ', 'g')) AS q_clean
      FROM cleaned
    ),

    -- ==========================================================
    -- 2) DETEKSI INTENT (JASA vs BARANG)
    -- ==========================================================
    intent AS (
      SELECT
        q_clean,
        (q_clean ~ '\\b(cuci|cleaning|service|servis|perbaiki|benerin|maintenance|isi freon|freon|bongkar|pasang|instal|pemasangan|cek|pengecekan|repair)\\b') AS want_service,
        (q_clean ~ '\\b(beli|order|pesan|harga|jual|stok|ready|promo|diskon|cicil|barang|unit)\\b') AS want_product
      FROM collapsed
    ),
    decision AS (
      SELECT
        q_clean,
        want_service,
        want_product,
        CASE
          WHEN want_service AND NOT want_product THEN 'jasa'
          WHEN want_product AND NOT want_service THEN 'barang'
          ELSE 'mixed' 
        END AS target
      FROM intent
    ),

    -- ==========================================================
    -- 3) EKSTRAK PK DARI INPUT (mis: "1 pk", "0.5 pk", "2 pk")
    -- ==========================================================
    pk_input AS (
      SELECT
        q_clean,
        target,
        want_service,
        want_product,
        NULLIF((regexp_match(q_clean, '(\\d+(?:\\.\\d+)?)\\s*pk'))[1], '')::numeric AS pk_user,
        trim(regexp_replace(q_clean, '\\d+(?:\\.\\d+)?\\s*pk', '', 'g')) AS q_no_pk
      FROM decision
    ),

    -- ==========================================================
    -- 4) BANGUN KANDIDAT: PRODUCTS + SERVICE_ITEMS
    -- ==========================================================
    products_src AS (
      SELECT
        kdprod::text AS id,
        prod_name::text AS nama_display,
        price::numeric AS harga,
        'barang'::text AS tipe_item,
        service_json->>'srvc_id' AS id_jasa_bundle,
        service_json->>'srvc_name' AS nama_jasa_bundle,
        (service_json->>'base_price')::numeric AS harga_jasa_bundle
      FROM catalog.products
    ),
    services_src AS (
      SELECT
        srvc_id::text AS id,
        srvc_name::text AS nama_display,
        base_price::numeric AS harga,
        'jasa'::text AS tipe_item,
        NULL::text AS id_jasa_bundle,
        NULL::text AS nama_jasa_bundle,
        NULL::numeric AS harga_jasa_bundle
      FROM catalog.service_items
    ),
    union_src AS (
      SELECT * FROM products_src
      UNION ALL
      SELECT * FROM services_src
    ),

    -- ==========================================================
    -- 5) EKSTRAK PK DARI NAMA ITEM
    -- ==========================================================
    enriched AS (
      SELECT
        s.*,
        lower(s.nama_display) AS nama_lc,
        NULLIF((regexp_match(lower(s.nama_display), '(\\d+(?:\\.\\d+)?)\\s*pk'))[1], '')::numeric AS pk_exact,
        NULLIF((regexp_match(lower(s.nama_display), '(\\d+(?:\\.\\d+)?)\\s*-\\s*(\\d+(?:\\.\\d+)?)\\s*pk'))[1], '')::numeric AS pk_min,
        NULLIF((regexp_match(lower(s.nama_display), '(\\d+(?:\\.\\d+)?)\\s*-\\s*(\\d+(?:\\.\\d+)?)\\s*pk'))[2], '')::numeric AS pk_max
      FROM union_src s
    ),

    -- ==========================================================
    -- 6) SCORING: FTS + TRIGRAM + ILIKE + RULE BOOST
    -- ==========================================================
    scored AS (
      SELECT
        e.*,
        i.q_clean,
        i.q_no_pk,
        i.pk_user,
        i.target,
        i.want_service,
        i.want_product,

        word_similarity(i.q_no_pk, e.nama_lc) AS sim_trgm,
        (to_tsvector('indonesian', e.nama_lc) @@ plainto_tsquery('indonesian', i.q_no_pk)) AS match_fts,
        (e.nama_lc ILIKE '%%' || i.q_no_pk || '%%') AS match_ilike,

        CASE
          WHEN i.pk_user IS NULL THEN 0
          WHEN e.tipe_item = 'barang' AND e.pk_exact IS NOT NULL AND e.pk_exact = i.pk_user THEN 1
          WHEN e.tipe_item = 'jasa' AND e.pk_min IS NOT NULL AND e.pk_max IS NOT NULL AND i.pk_user BETWEEN e.pk_min AND e.pk_max THEN 1
          WHEN e.tipe_item = 'jasa' AND e.pk_exact IS NOT NULL AND e.pk_exact = i.pk_user THEN 1
          ELSE 0
        END AS pk_match,

        CASE
          WHEN i.target = 'jasa' AND e.tipe_item = 'jasa' THEN 1
          WHEN i.target = 'barang' AND e.tipe_item = 'barang' THEN 1
          WHEN i.target = 'mixed' AND i.want_service AND e.tipe_item = 'jasa' THEN 1
          ELSE 0
        END AS intent_match
      FROM enriched e
      CROSS JOIN pk_input i
    ),

    final_rank AS (
      SELECT
        id,
        nama_display AS pesanan,
        harga,
        tipe_item,
        id_jasa_bundle,
        nama_jasa_bundle,
        harga_jasa_bundle,

        sim_trgm,
        match_fts,
        match_ilike,
        pk_match,
        intent_match,

        (
          (sim_trgm * 1.0)
          + (CASE WHEN match_fts THEN 0.35 ELSE 0 END)
          + (CASE WHEN match_ilike THEN 0.50 ELSE 0 END)
          + (pk_match * 0.25)
          + (intent_match * 0.20)
        ) AS skor_total
      FROM scored
    )

    -- ==========================================================
    -- 7) FILTER & OUTPUT
    -- ==========================================================
    SELECT
      id,
      pesanan,
      harga,
      tipe_item,
      id_jasa_bundle,
      nama_jasa_bundle,
      harga_jasa_bundle,
      skor_total
    FROM final_rank
    WHERE
      (
        ((SELECT target FROM pk_input) = 'jasa' AND tipe_item = 'jasa')
        OR
        ((SELECT target FROM pk_input) = 'barang' AND tipe_item = 'barang')
        OR
        ((SELECT target FROM pk_input) = 'mixed')
      )
      AND
      (
        skor_total >= 0.35 
        OR match_ilike = true
        OR (sim_trgm >= 0.25 AND match_fts = true)
      )
    ORDER BY
      CASE
        WHEN (SELECT target FROM pk_input) = 'mixed'
             AND (SELECT want_service FROM pk_input) = true
             AND tipe_item = 'jasa' THEN 0
        ELSE 1
      END,
      skor_total DESC
    LIMIT 5;
    """
    
    hasil_sql = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(query_sql, (kata_kunci,))
        rows = cursor.fetchall()
        
        for row in rows:
            # PENTING: Menyesuaikan index dengan SELECT akhir di query!
            # id (0), pesanan (1), harga (2), tipe_item (3), 
            # id_jasa_bundle (4), nama_jasa_bundle (5), harga_jasa_bundle (6), skor_total (7)
            id_ref = row[0]
            nama = row[1]
            harga = row[2]
            tipe = row[3]
            id_jasa_bundle = row[4]
            # row[4] adalah id_jasa_bundle, kita lewati karena tidak perlu ditampilkan ke LLM
            jasa_bundle = row[5]
            harga_bundle = row[6]
            # row[7] adalah skor_total
            
            teks = f"Nama {str(tipe).capitalize()}: {nama}. Harga: Rp{harga}. "
            if jasa_bundle:
                teks += f"Jasa Bundling Wajib: [{id_jasa_bundle}] {jasa_bundle} (Biaya: Rp{harga_bundle})."
                
            hasil_sql.append({
                "id_referensi": id_ref,
                "tipe_item": tipe,
                "sumber": "PostgreSQL (Keyword Exact Match)",
                "teks_gabungan": teks
            })
            
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"[SQL ERROR] Gagal menjalankan SQL Search: {e}")
        
    return hasil_sql

@tool
def cari_katalog_produk(kata_kunci: str) -> str:
    """Gunakan tool ini untuk mencari informasi produk AC, spesifikasi, dan layanan (Jasa Pasang/Cuci AC).
    PENTING: Buatlah 'kata_kunci' yang PANJANG dan DESKRIPTIF."""
    
    try:
        print(f"\n==================================================")
        print(f"⚙️ [HYBRID SEARCH DIMULAI] Kata Kunci: '{kata_kunci}'")
        print(f"==================================================")
        
        # 1. AMBIL DARI CHROMA DB (Semantic Search)
        db_katalog = get_vector_katalog_db()
        hasil_vektor = db_katalog.similarity_search(kata_kunci, k=5) # Ambil 2 teratas
        
        print("\n🔍 [DEBUG 1] HASIL SEMANTIC (CHROMA DB) - TOP 5:")
        if not hasil_vektor:
            print("   (Tidak ada hasil dari AI)")
        for i, doc in enumerate(hasil_vektor):
            # Potong teks agar tidak terlalu panjang di layar
            teks_cuplikan = doc.page_content[:120].replace('\n', ' ')
            print(f"   {i+1}. [{doc.metadata.get('id_referensi')}] {teks_cuplikan}...")
            
        # 2. AMBIL DARI POSTGRESQL (Lexical/Rule-based Search)
        hasil_sql = jalankan_pencarian_sql(kata_kunci)
        
        print("\n🔍 [DEBUG 2] HASIL LEXICAL (POSTGRESQL) - TOP 5:")
        if not hasil_sql:
            print("   (Tidak ada hasil dari Database)")
        for i, item in enumerate(hasil_sql):
            teks_cuplikan = item['teks_gabungan'][:120].replace('\n', ' ')
            print(f"   {i+1}. [{item['id_referensi']}] {teks_cuplikan}...")
            
        # 3. PENGGABUNGAN (FUSION) & MENGHAPUS DUPLIKASI
        katalog_final_dict = {} 
        
        # Masukkan hasil SQL terlebih dahulu
        for item in hasil_sql:
            katalog_final_dict[item["id_referensi"]] = item
            
        # Masukkan hasil Vektor (Jika ID sudah ada, akan otomatis di-skip)
        for doc in hasil_vektor:
            id_ref = doc.metadata.get('id_referensi')
            if id_ref not in katalog_final_dict:
                katalog_final_dict[id_ref] = {
                    "id_referensi": id_ref,
                    "tipe_item": doc.metadata.get('tipe_item', 'umum'),
                    "sumber": "Chroma DB (Semantic Search)",
                    "teks_gabungan": doc.page_content
                }
                
        # 4. POTONG HASIL GABUNGAN MENJADI MAKSIMAL 4 SAJA
        # (Agar hasil Vektor tidak terbuang jika SQL mendominasi urutan awal)
        katalog_final_list = list(katalog_final_dict.values())[:4]
        
        print("\n🔗 [DEBUG 3] HASIL GABUNGAN FINAL (DIPOTONG JADI TOP 4):")
        for i, item in enumerate(katalog_final_list):
            print(f"   {i+1}. [{item['id_referensi']}] (Sumber: {item['sumber']})")
        print(f"==================================================\n")

        # 5. FORMAT OUTPUT UNTUK DIKIRIM KE GEMINI
        if not katalog_final_list:
            return f"Maaf, tidak ditemukan data yang relevan dengan '{kata_kunci}'."
            
        hasil_teks = f"Ditemukan {len(katalog_final_list)} hasil (Kombinasi AI dan Database):\n\n"
        for item in katalog_final_list:
            hasil_teks += f"[{str(item['tipe_item']).upper()}] - Ref ID: {item['id_referensi']} | Sumber: {item['sumber']}\n"
            hasil_teks += f"{item['teks_gabungan']}\n"
            hasil_teks += "-" * 20 + "\n"
            
        return hasil_teks
        
    except Exception as e:
        print(f"\n!!!!! ERROR HYBRID SEARCH: {str(e)} !!!!!\n")
        return "Sistem katalog sedang error, tolong beritahu pelanggan."