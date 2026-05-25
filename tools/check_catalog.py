from data.vector_manager import bersihkan_html
from data.database import get_db_connection
from langchain_core.tools import tool
from data.vector_manager import get_vector_katalog_db

def jalankan_pencarian_sql(kata_kunci: str, jenis_item: str = ""):
    """Menjalankan pencarian Lexical/Rule-based menggunakan Postgres"""
    
    # -----------------------------------------------------------
    # INJEKSI FILTER BERDASARKAN PARAMETER 'jenis_item'
    # -----------------------------------------------------------
    if jenis_item.lower() == "produk":
        kondisi_filter_tipe = "tipe_item = 'barang'"
    elif jenis_item.lower() == "jasa":
        kondisi_filter_tipe = "tipe_item = 'jasa'"
    else:
        kondisi_filter_tipe = """
        (
            ((SELECT target FROM pk_input) = 'jasa' AND tipe_item = 'jasa')
            OR
            ((SELECT target FROM pk_input) = 'barang' AND tipe_item = 'barang')
            OR
            ((SELECT target FROM pk_input) = 'mixed')
        )
        """

    query_sql = f"""
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
          '\\b(merk|merek|brand|tipe|type|jenis|yang|tolong|pesan|cari|buat|dong|aja|nih|ya|bang|kak|min)\\b',
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
    -- 4) BANGUN KANDIDAT DENGAN JOIN LENGKAP (SEPERTI CHROMA)
    -- ==========================================================
    products_src AS (
      SELECT
        p.kdprod::text AS id,
        p.prod_name::text AS nama_display,
        p.ket_prod::text AS keterangan_item,
        p.price::numeric AS harga,
        'barang'::text AS tipe_item,
        p.service_json->>'srvc_id' AS id_jasa_bundle,
        p.service_json->>'srvc_name' AS nama_jasa_bundle,
        (p.service_json->>'base_price')::numeric AS harga_jasa_bundle,
        b.nmmerk::text AS merek,              -- TAMBAHAN MEREK
        j.nmjens::text AS kategori,           -- TAMBAHAN KATEGORI
        pd.detail_product::text AS spesifikasi -- TAMBAHAN SPESIFIKASI HTML
      FROM catalog.products p
      LEFT JOIN catalog.brands b ON p.kdmerk = b.kdmerk
      LEFT JOIN catalog.jenis_products j ON p.kdjens = j.kdjens
      LEFT JOIN catalog.product_detail pd ON p.kdprod = pd.kdprod
    ),
    services_src AS (
      SELECT
        srvc_id::text AS id,
        srvc_name::text AS nama_display,
        srvc_desc::text AS keterangan_item,
        base_price::numeric AS harga,
        'jasa'::text AS tipe_item,
        NULL::text AS id_jasa_bundle,
        NULL::text AS nama_jasa_bundle,
        NULL::numeric AS harga_jasa_bundle,
        'Aire Optima'::text AS merek,
        'Jasa'::text AS kategori,
        NULL::text AS spesifikasi
      FROM catalog.service_items
    ),
    union_src AS (
      SELECT * FROM products_src
      UNION ALL
      SELECT * FROM services_src
    ),

    -- ==========================================================
    -- 5) EKSTRAK PK DARI NAMA ITEM & GABUNG TEKS UNTUK PENCARIAN
    -- ==========================================================
    enriched AS (
      SELECT
        s.*,
        lower(s.nama_display) AS nama_lc,
        lower(s.nama_display || ' ' || COALESCE(s.keterangan_item, '') || ' ' || COALESCE(s.spesifikasi, '')) AS search_text_lc,
        NULLIF((regexp_match(lower(s.nama_display), '(\\d+(?:\\.\\d+)?)\\s*pk'))[1], '')::numeric AS pk_exact,
        NULLIF((regexp_match(lower(s.nama_display), '(\\d+(?:\\.\\d+)?)\\s*-\\s*(\\d+(?:\\.\\d+)?)\\s*pk'))[1], '')::numeric AS pk_min,
        NULLIF((regexp_match(lower(s.nama_display), '(\\d+(?:\\.\\d+)?)\\s*-\\s*(\\d+(?:\\.\\d+)?)\\s*pk'))[2], '')::numeric AS pk_max
      FROM union_src s
    ),

    -- ==========================================================
    -- 6) SCORING
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

        word_similarity(i.q_no_pk, e.search_text_lc) AS sim_trgm,
        (to_tsvector('indonesian', e.search_text_lc) @@ plainto_tsquery('indonesian', i.q_no_pk)) AS match_fts,
        (length(trim(i.q_no_pk)) > 0 AND e.search_text_lc ILIKE '%%' || trim(i.q_no_pk) || '%%') AS match_ilike,

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
        keterangan_item,
        merek,          -- DITERUSKAN
        kategori,       -- DITERUSKAN
        spesifikasi,    -- DITERUSKAN

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
      keterangan_item,
      merek,
      kategori,
      spesifikasi,
      skor_total
    FROM final_rank
    WHERE
      {kondisi_filter_tipe} 
      AND
      (
        skor_total >= 0.35 
        OR match_ilike = true
        OR (sim_trgm >= 0.25 AND match_fts = true)
      )
      AND
      (
        -- Hard filter: Jika user menyebut PK, hanya tampilkan item dengan PK yang cocok
        (SELECT pk_user FROM pk_input) IS NULL
        OR pk_match = 1
        OR tipe_item = 'jasa'
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
            id_ref = row[0]
            nama = row[1]
            harga = row[2] or 0
            tipe = row[3]
            id_jasa_bundle = row[4]
            jasa_bundle = row[5]
            harga_bundle = row[6] or 0
            keterangan = row[7] or ""
            merek = row[8] or "Tanpa Merek"
            kategori = row[9] or "Umum"
            spesifikasi_html = row[10] or ""
            
            # --- RAKIT STRING IDENTIK DENGAN CHROMA DB ---
            if tipe == 'barang':
                detail_bersih = bersihkan_html(spesifikasi_html)
                
                info_bundling = ""
                if jasa_bundle:
                    info_bundling = f"Jasa Bundling/Pemasangan Wajib: {jasa_bundle} (Biaya Tambahan Jasa: Rp{harga_bundle}). "
                
                teks_gabungan = (
                    f"Nama Produk: {nama}. "
                    f"Kategori: {kategori}. "
                    f"Merek: {merek}. "
                    f"Harga Unit Produk: Rp{harga}. "
                    f"Keterangan Singkat: {keterangan}. "
                    f"{info_bundling}"
                    f"Spesifikasi Detail: {detail_bersih}."
                )
            else:
                # Format untuk Jasa
                teks_gabungan = (
                    f"Nama Layanan: {nama}. "
                    f"Kategori: {kategori}. "
                    f"Harga Dasar: Rp{harga}. "
                    f"Keterangan Layanan: {keterangan}."
                )
                
            hasil_sql.append({
                "id_referensi": id_ref,
                "tipe_item": tipe,
                "sumber": "PostgreSQL (Keyword Exact Match)",
                "teks_gabungan": teks_gabungan
            })
            
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"[SQL ERROR] Gagal menjalankan SQL Search: {e}")
        
    return hasil_sql
@tool
def cari_katalog_produk(kata_kunci: str, jenis_item: str) -> str:
    """
    Gunakan alat ini untuk mencari informasi produk AC, spesifikasi, dan layanan (Jasa Pasang/Cuci AC) di database.
    
    Argumen:
    - kata_kunci: Kata teknis spesifik (misal: "LG Inverter 1 PK", "Daikin", "Cuci AC Split"). Buat PANJANG dan DESKRIPTIF.
    - jenis_item: WAJIB diisi dengan salah satu dari dua kata ini: "produk" atau "jasa". 
      Pilih "produk" jika pelanggan mencari barang fisik (AC, CCTV).
      Pilih "jasa" jika pelanggan mencari layanan teknisi (pasang, bongkar, cuci, perbaikan).
    """
    
    try:
        print(f"\n==================================================")
        print(f"⚙️ [HYBRID SEARCH DIMULAI] Mencari {jenis_item.upper()} | Kata Kunci: '{kata_kunci}'")
        print(f"==================================================")
        
        # 1. TENTUKAN FILTER METADATA UNTUK CHROMA DB
        # Sesuaikan key "tipe_item" dengan skema metadata databasemu
        if jenis_item.lower() == "produk":
            filter_metadata = {"tipe_item": "produk"}
        elif jenis_item.lower() == "jasa":
            filter_metadata = {"tipe_item": "jasa"}
        else:
            filter_metadata = None # Fallback jika AI salah mengisi parameter

        # 2. AMBIL DARI CHROMA DB (Semantic Search)
        db_katalog = get_vector_katalog_db()
        # Model e5 membutuhkan prefix "query: " untuk performa optimal
        query_dengan_prefix = f"query: {kata_kunci}"
        try:
            if filter_metadata:
                hasil_vektor = db_katalog.similarity_search(query_dengan_prefix, k=5, filter=filter_metadata)
            else:
                hasil_vektor = db_katalog.similarity_search(query_dengan_prefix, k=5)
            
            # Post-filter: Jika user menyebut PK spesifik, buang hasil yang PK-nya beda
            # Hanya berlaku untuk PRODUK — jasa punya range PK yang ditangani lexical
            import re as _re
            if jenis_item.lower() == "produk":
                pk_match_input = _re.search(r'(\d+(?:\.\d+)?)\s*pk', kata_kunci.lower())
                if pk_match_input:
                    pk_diminta = pk_match_input.group(1)
                    hasil_vektor_filtered = []
                    for doc in hasil_vektor:
                        pk_in_doc = _re.findall(r'(\d+(?:\.\d+)?)\s*PK', doc.page_content)
                        if pk_in_doc:
                            if pk_diminta in pk_in_doc:
                                hasil_vektor_filtered.append(doc)
                        else:
                            hasil_vektor_filtered.append(doc)
                    hasil_vektor = hasil_vektor_filtered
        except Exception as e:
            print(f"❌ Terjadi Kesalahan pada Chroma DB: {e}")
            hasil_vektor = [] # Kosongkan hasil jika error
        
        print("\n🔍 [DEBUG 1] HASIL SEMANTIC (CHROMA DB) - TOP 5:")
        if not hasil_vektor:
            print("   (Tidak ada hasil dari AI)")
        for i, doc in enumerate(hasil_vektor):
            teks_cuplikan = doc.page_content[:120].replace('\n', ' ')
            print(f"   {i+1}. [{doc.metadata.get('id_referensi')}] {teks_cuplikan}...")
            
        # 3. AMBIL DARI POSTGRESQL (Lexical/Rule-based Search)
        # Parameter jenis_item dilempar ke fungsi SQL untuk memfilter hasilnya
        hasil_sql = jalankan_pencarian_sql(kata_kunci, jenis_item)
        
        print("\n🔍 [DEBUG 2] HASIL LEXICAL (POSTGRESQL) - TOP 5:")
        if not hasil_sql:
            print("   (Tidak ada hasil dari Database)")
        for i, item in enumerate(hasil_sql):
            teks_cuplikan = item['teks_gabungan'][:120].replace('\n', ' ')
            print(f"   {i+1}. [{item['id_referensi']}] {teks_cuplikan}...")
            
        # 4. PENGGABUNGAN (FUSION) MENGGUNAKAN RRF (Reciprocal Rank Fusion)
        # Bobot: Lexical lebih dipercaya karena exact match, Semantic sebagai pelengkap
        K_CONSTANT = 60
        BOBOT_LEXICAL = 1.0
        BOBOT_SEMANTIC = 1.0  # Semantic diberi bobot lebih rendah
        rrf_scores = {}
        katalog_final_dict = {} 
        
        # a) Hitung skor RRF untuk hasil Lexical (SQL) — BOBOT PENUH
        for rank_idx, item in enumerate(hasil_sql):
            id_ref = item["id_referensi"]
            rank = rank_idx + 1
            rrf_scores[id_ref] = rrf_scores.get(id_ref, 0.0) + (BOBOT_LEXICAL * (1.0 / (K_CONSTANT + rank)))
            katalog_final_dict[id_ref] = item
            
        # b) Hitung skor RRF untuk hasil Semantic (Vector Chroma) — BOBOT LEBIH RENDAH
        for rank_idx, doc in enumerate(hasil_vektor):
            id_ref = doc.metadata.get('id_referensi')
            if not id_ref:
                continue

            rank = rank_idx + 1
            rrf_scores[id_ref] = rrf_scores.get(id_ref, 0.0) + (BOBOT_SEMANTIC * (1.0 / (K_CONSTANT + rank)))
            
            if id_ref not in katalog_final_dict:
                # Bersihkan prefix "passage: " dari teks sebelum disimpan
                teks_bersih = doc.page_content
                if teks_bersih.startswith("passage: "):
                    teks_bersih = teks_bersih[9:]  # Hapus "passage: " (9 karakter)
                    
                katalog_final_dict[id_ref] = {
                    "id_referensi": id_ref,
                    "tipe_item": doc.metadata.get('kategori', jenis_item),
                    "sumber": "Chroma DB (Semantic Search)",
                    "teks_gabungan": teks_bersih
                }
            else:
                # Item sudah ada dari SQL — tandai sebagai Hybrid
                katalog_final_dict[id_ref]["sumber"] = "Hybrid (Semantic + Lexical)"
                
        # c) Urutkan ulang berdasarkan nilai RRF tertinggi
        sorted_rrf_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)

        # 5. POTONG HASIL GABUNGAN MENJADI MAKSIMAL 4 SAJA
        katalog_final_list = []
        for id_ref in sorted_rrf_ids[:4]:
            item = katalog_final_dict[id_ref]
            # Update sumber untuk menampilkan skor RRF di debug
            item["sumber"] += f" [RRF Score: {rrf_scores[id_ref]:.4f}]"
            katalog_final_list.append(item)
            
        print("\n🔗 [DEBUG 3] HASIL GABUNGAN FINAL DENGAN RRF (DIPOTONG JADI TOP 4):")
        for i, item in enumerate(katalog_final_list):
            print(f"   {i+1}. [{item['id_referensi']}] (Sumber: {item['sumber']})")
        print(f"==================================================\n")

        # 6. FORMAT OUTPUT UNTUK DIKIRIM KE GEMINI
        if not katalog_final_list:
            return f"Maaf, tidak ditemukan data yang relevan dengan '{kata_kunci}' pada kategori '{jenis_item}'."
            
        hasil_teks = f"Ditemukan {len(katalog_final_list)} hasil (Kombinasi AI dan Database):\n\n"
        for item in katalog_final_list:
            hasil_teks += f"[{str(item['tipe_item']).upper()}] - Ref ID: {item['id_referensi']} | Sumber: {item['sumber']}\n"
            hasil_teks += f"{item['teks_gabungan']}\n"
            hasil_teks += "-" * 20 + "\n"
            
        return hasil_teks
        
    except Exception as e:
        print(f"\n!!!!! ERROR HYBRID SEARCH: {str(e)} !!!!!\n")
        return "Sistem katalog sedang error, tolong beritahu pelanggan."