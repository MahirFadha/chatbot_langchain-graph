import requests
import json
from data.database import get_db_connection

BASE_URL = "https://aire.co.id/iris/api"

def execute_query(query, params=None):
    """Fungsi pembantu agar tidak mengulang try-except terus menerus"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(query, params)
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"❌ [DB ERROR]: {e}")
    finally:
        cursor.close()
        conn.close()

def fetch_data(endpoint):
    """Fungsi pembantu untuk hit API Aire Optima"""
    try:
        response = requests.get(f"{BASE_URL}{endpoint}", timeout=30)
        response.raise_for_status()
        return response.json().get("data", [])
    except Exception as e:
        print(f"⚠️ [API ERROR] Gagal mengambil {endpoint}: {e}")
        return []

# =====================================================================
# 1. SYNC CORE, JENIS & PACKAGES
# =====================================================================
def sync_core_jenis_packages():
    print("🔄 [SYNC] 1/5: Sinkronisasi Core, Jenis, & Packages...")
    data_core = fetch_data("/core-products")
    seen_packages = set()

    for core in data_core:
        cdcore = core.get("cdcore")
        crjens = core.get("crjens")
        
        execute_query("""
            INSERT INTO catalog.core_products (cdcore, crjens, synced_at, is_active) VALUES (%s, %s, now(), true)
            ON CONFLICT (cdcore) DO UPDATE SET crjens = EXCLUDED.crjens, synced_at = now(), is_active = true;
        """, (cdcore, crjens))
        
        for jenis in core.get("data_jenis_prod") or []:
            kdjens = jenis.get("kdjens")
            execute_query("""
                INSERT INTO catalog.jenis_products (kdjens, cdcore, nmjens, title, "desc", icon_name, synced_at, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, now(), true)
                ON CONFLICT (kdjens) DO UPDATE SET cdcore = EXCLUDED.cdcore, nmjens = EXCLUDED.nmjens, title = EXCLUDED.title,
                "desc" = EXCLUDED."desc", icon_name = EXCLUDED.icon_name, synced_at = now(), is_active = true;
            """, (kdjens, cdcore, jenis.get("nmjens"), jenis.get("title"), jenis.get("desc"), jenis.get("icon_name")))
            
            for pkg in jenis.get("m_service_product") or []:
                srv_prodid = pkg.get("srv_prodid")
                if srv_prodid and srv_prodid not in seen_packages:
                    seen_packages.add(srv_prodid)
                    execute_query("""
                        INSERT INTO catalog.service_packages (srv_prodid, kdjens, cdcore, srv_package_name, srv_icon, srv_short_desc, synced_at, is_active)
                        VALUES (%s, %s, %s, %s, %s, %s, now(), true)
                        ON CONFLICT (srv_prodid) DO UPDATE SET kdjens = EXCLUDED.kdjens, cdcore = EXCLUDED.cdcore, 
                        srv_package_name = EXCLUDED.srv_package_name, srv_icon = EXCLUDED.srv_icon, srv_short_desc = EXCLUDED.srv_short_desc, synced_at = now(), is_active = true;
                    """, (srv_prodid, kdjens, cdcore, pkg.get("srv_package_name"), pkg.get("srv_icon"), pkg.get("srv_short_desc")))

# =====================================================================
# 2. SYNC BRANDS & PRODUCTS
# =====================================================================
def sync_brands_products():
    print("🔄 [SYNC] 2/5: Sinkronisasi Brands & Products...")
    data_core = fetch_data("/products")
    seen_merk = set()

    for core in data_core:
        cdcore = core.get("cdcore")
        for jenis in core.get("data_jenis_prod") or []:
            kdjens = jenis.get("kdjens")
            for merk in jenis.get("merks") or []:
                kdmerk = merk.get("kdmerk")
                nmmerk = merk.get("nmmerk").strip() if merk.get("nmmerk") else kdmerk
                
                if kdmerk and kdmerk not in seen_merk:
                    seen_merk.add(kdmerk)
                    execute_query("""
                        INSERT INTO catalog.brands (kdmerk, nmmerk, synced_at, is_active) VALUES (%s, %s, now(), true)
                        ON CONFLICT (kdmerk) DO UPDATE SET nmmerk = EXCLUDED.nmmerk, synced_at = now(), is_active = true;
                    """, (kdmerk, nmmerk))
                
                for prod in merk.get("products") or []:
                    service_data = prod.get("service")
                    srvc_id = service_data.get("srvc_id") if service_data else None
                    service_json = json.dumps(service_data) if service_data else None
                    
                    execute_query("""
                        INSERT INTO catalog.products (kdprod, prod_name, price, slug, ket_prod, cdcore, kdjens, kdmerk, srvc_id, service_json, synced_at, is_active)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, now(), true)
                        ON CONFLICT (kdprod) DO UPDATE SET prod_name = EXCLUDED.prod_name, price = EXCLUDED.price, slug = EXCLUDED.slug,
                        ket_prod = EXCLUDED.ket_prod, cdcore = EXCLUDED.cdcore, kdjens = EXCLUDED.kdjens, kdmerk = EXCLUDED.kdmerk, 
                        srvc_id = EXCLUDED.srvc_id, service_json = EXCLUDED.service_json, synced_at = now(), is_active = true;
                    """, (prod.get("kdprod"), prod.get("prod_name"), prod.get("price"), prod.get("slug"), prod.get("ket_prod"), cdcore, kdjens, kdmerk, srvc_id, service_json))

# =====================================================================
# 3. SYNC SERVICE ITEMS PER PACKAGE
# =====================================================================
def sync_service_items():
    print("🔄 [SYNC] 3/5: Sinkronisasi Service Items...")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT srv_prodid FROM catalog.service_packages WHERE is_active = true;")
    packages = cursor.fetchall()
    cursor.close()
    conn.close()

    for pkg in packages:
        srv_prodid = pkg[0]
        data_services = fetch_data(f"/services?id={srv_prodid}")
        
        for srv in data_services:
            execute_query("""
                INSERT INTO catalog.service_items (srvc_id, srvprodid, cdcore, slug, srvc_name, srvc_desc, base_price, date_log, synced_at, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now(), true)
                ON CONFLICT (srvc_id) DO UPDATE SET srvprodid = EXCLUDED.srvprodid, cdcore = EXCLUDED.cdcore, slug = EXCLUDED.slug,
                srvc_name = EXCLUDED.srvc_name, srvc_desc = EXCLUDED.srvc_desc, base_price = EXCLUDED.base_price, date_log = EXCLUDED.date_log,
                synced_at = now(), is_active = true;
            """, (srv.get("srvc_id"), srv.get("srvprodid"), srv.get("cdcore"), srv.get("slug"), srv.get("srvc_name"), srv.get("srvc_desc"), srv.get("base_price"), srv.get("date_log")))

# =====================================================================
# 4. SYNC SERVICE DETAILS & IMAGES
# =====================================================================
def sync_service_details():
    print("🔄 [SYNC] 4/5: Sinkronisasi Service Details & Images...")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT srvc_id, slug FROM catalog.service_items WHERE is_active = true AND slug IS NOT NULL;")
    services = cursor.fetchall()
    cursor.close()
    conn.close()

    for srv in services:
        slug = srv[1]
        detail_data = fetch_data(f"/detail-service/{slug}")
        if not detail_data: continue
        
        # Data dari API
        if isinstance(detail_data, list) and len(detail_data) > 0:
            detail_data = detail_data[0] # Kalau API balikin array
            
        m_service = detail_data.get("m_service", {})
        problem_json = detail_data.get("m_service_det_problem", [])
        
        if m_service.get("srvc_id"):
            srvc_id = m_service.get("srvc_id")
            
            # Upsert Detail
            execute_query("""
                INSERT INTO catalog.service_detail (srvc_id, slug, prob_detail, service_json, problem_json, date_log, synced_at, is_active)
                VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, now(), true)
                ON CONFLICT (srvc_id) DO UPDATE SET slug = EXCLUDED.slug, prob_detail = EXCLUDED.prob_detail,
                service_json = EXCLUDED.service_json, problem_json = EXCLUDED.problem_json, date_log = EXCLUDED.date_log, synced_at = now(), is_active = true;
            """, (srvc_id, detail_data.get("slug", m_service.get("slug")), detail_data.get("prob_detail", ""), json.dumps(m_service), json.dumps(problem_json), m_service.get("date_log")))
            
            # Upsert Images
            for img in m_service.get("service_images", []):
                execute_query("""
                    INSERT INTO catalog.service_images (id, srvc_id, image_url, created_at, synced_at)
                    SELECT %s, %s, %s, %s, now() WHERE EXISTS (SELECT 1 FROM catalog.service_items WHERE srvc_id = %s)
                    ON CONFLICT (id) DO UPDATE SET srvc_id = EXCLUDED.srvc_id, image_url = EXCLUDED.image_url, created_at = EXCLUDED.created_at, synced_at = now();
                """, (img.get("id"), srvc_id, img.get("image_url"), img.get("created_at"), srvc_id))

# =====================================================================
# 5. SYNC PRODUCT DETAILS & IMAGES
# =====================================================================
def sync_product_details():
    print("🔄 [SYNC] 5/5: Sinkronisasi Product Details & Images...")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT kdprod, slug FROM catalog.products WHERE is_active = true AND slug IS NOT NULL;")
    products = cursor.fetchall()
    cursor.close()
    conn.close()

    for prod in products:
        slug = prod[1]
        detail_data = fetch_data(f"/detail-product/{slug}")
        if not detail_data: continue
        
        if isinstance(detail_data, list) and len(detail_data) > 0:
            detail_data = detail_data[0]

        kdprod = detail_data.get("KDPROD")
        if kdprod:
            srvc_id = detail_data.get("srvc_id")
            service_json = json.dumps(detail_data.get("service")) if detail_data.get("service") else None
            
            # Upsert Detail
            execute_query("""
                INSERT INTO catalog.product_detail (kdprod, slug, detail_product, product_json, srvc_id, service_json, synced_at, is_active)
                VALUES (%s, %s, %s, %s::jsonb, %s, %s::jsonb, now(), true)
                ON CONFLICT (kdprod) DO UPDATE SET slug = EXCLUDED.slug, detail_product = EXCLUDED.detail_product,
                product_json = EXCLUDED.product_json, srvc_id = EXCLUDED.srvc_id, service_json = EXCLUDED.service_json, synced_at = now(), is_active = true;
            """, (kdprod, detail_data.get("slug"), detail_data.get("detail_product", ""), json.dumps(detail_data), srvc_id, service_json))
            
            # Upsert Images
            for img in detail_data.get("product_images", []):
                execute_query("""
                    INSERT INTO catalog.product_images (id, kdprod, image_url, created_at, synced_at)
                    SELECT %s, %s, %s, %s, now() WHERE EXISTS (SELECT 1 FROM catalog.products WHERE kdprod = %s)
                    ON CONFLICT (id) DO UPDATE SET kdprod = EXCLUDED.kdprod, image_url = EXCLUDED.image_url, created_at = EXCLUDED.created_at, synced_at = now();
                """, (img.get("id"), kdprod, img.get("image_url"), img.get("created_at"), kdprod))

def run_all_sync():
    """Master Eksekutor untuk menjalankan semua fungsi secara berurutan"""
    print("\n=======================================================")
    print("🚀 MEMULAI BACKGROUND TASK: SINKRONISASI KATALOG API...")
    sync_core_jenis_packages()
    sync_brands_products()
    sync_service_items()
    sync_service_details()
    sync_product_details()
    print("✨ SELURUH PROSES SINKRONISASI SELESAI!")
    print("=======================================================\n")