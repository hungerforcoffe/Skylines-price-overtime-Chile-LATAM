"""
scraper_api_hoteles.py  (v3)
============================
Estrategia: interceptar la RESPONSE de la API (no el request),
así capturamos el JSON directamente sin depender del x-hash.

Playwright visita cada destino, espera la respuesta JSON de la API,
la guarda directo — sin necesitar requests ni headers de sesión.
"""

import asyncio
import re
import json
import sqlite3
import os
from datetime import datetime
from typing import Optional
from playwright.async_api import async_playwright, Page, Response

# ──────────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ──────────────────────────────────────────────────────────────

BRAVE_PATH   = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
URL_HOME     = "https://latamtravel-chile.despegar.cl/?label=cl_web_subhome-deals-packages"
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
DB_PATH      = os.path.join(BASE_DIR, "hoteles.db")
HEADLESS     = False
SCROLL_VECES = 5
MAX_PAGINAS  = 10   # máximo páginas por destino (~21 hoteles c/u)


# ──────────────────────────────────────────────────────────────
# BASE DE DATOS
# ──────────────────────────────────────────────────────────────

def inicializar_bd():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha         TEXT NOT NULL,
            hora          TEXT NOT NULL,
            total_hoteles INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS hoteles (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            hotel_id_despegar   TEXT UNIQUE,
            nombre              TEXT NOT NULL,
            destino             TEXT,
            zona                TEXT,
            direccion           TEXT,
            estrellas           REAL,
            rating              REAL,
            total_resenas       INTEGER,
            descripcion_rating  TEXT
        );

        CREATE TABLE IF NOT EXISTS precios (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id         INTEGER NOT NULL,
            hotel_id            INTEGER NOT NULL,
            precio_persona_clp  INTEGER,
            precio_original_clp INTEGER,
            ahorro_clp          INTEGER,
            descuento_pct       REAL,
            precio_2_personas   INTEGER,
            producto            TEXT,
            regimen             TEXT,
            reserva_flexible    INTEGER DEFAULT 0,
            FOREIGN KEY (snapshot_id) REFERENCES snapshots(id),
            FOREIGN KEY (hotel_id)    REFERENCES hoteles(id)
        );
    """)
    conn.commit()
    conn.close()
    print(f"✅ BD inicializada: {DB_PATH}")


def get_or_create_hotel(conn, acc: dict) -> int:
    hotel_id_desp = acc.get("id", "")
    nombre        = acc.get("name", "Desconocido")
    loc           = acc.get("location", {})
    zona          = loc.get("zone", {}).get("name", "")
    destino       = loc.get("city", {}).get("name", "")
    direccion     = loc.get("address", "")
    estrellas     = acc.get("stars")
    reviews       = acc.get("reviews", {})
    rating        = reviews.get("rating")
    total_res     = reviews.get("total")
    desc_rating   = reviews.get("rating_description", "")

    conn.execute("""
        INSERT INTO hoteles
            (hotel_id_despegar, nombre, destino, zona, direccion,
             estrellas, rating, total_resenas, descripcion_rating)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(hotel_id_despegar) DO UPDATE SET
            rating=excluded.rating,
            total_resenas=excluded.total_resenas
    """, (hotel_id_desp, nombre, destino, zona, direccion,
          estrellas, rating, total_res, desc_rating))

    row = conn.execute(
        "SELECT id FROM hoteles WHERE hotel_id_despegar = ?", (hotel_id_desp,)
    ).fetchone()
    return row[0]


def guardar_precio(conn, snapshot_id: int, hotel_id: int, item: dict):
    prices = item.get("prices", {})

    def parse_clp(texto) -> Optional[int]:
        if not texto:
            return None
        solo = re.sub(r"[^\d]", "", str(texto))
        return int(solo) if solo else None

    precio_persona  = parse_clp(prices.get("main"))
    precio_original = parse_clp(prices.get("secondary"))
    precio_2p       = parse_clp(prices.get("tertiary"))
    producto        = prices.get("product_message", "")

    ahorro = None
    for p_item in prices.get("promotion", {}).get("items", []):
        texto_raw    = p_item.get("value", "")
        texto_limpio = re.sub(r"<[^>]+>", "", texto_raw)
        ahorro = parse_clp(texto_limpio)
        break

    descuento_pct = None
    if precio_original and ahorro and precio_original > 0:
        descuento_pct = round(ahorro / precio_original * 100, 1)

    texto_todo = json.dumps(item).lower()
    if "all inclusive" in texto_todo:
        regimen = "All Inclusive"
    elif "desayuno" in texto_todo or "breakfast" in texto_todo:
        regimen = "Desayuno incluido"
    else:
        regimen = ""

    flexible = 1 if "flexible" in texto_todo else 0

    conn.execute("""
        INSERT INTO precios
            (snapshot_id, hotel_id, precio_persona_clp, precio_original_clp,
             ahorro_clp, descuento_pct, precio_2_personas,
             producto, regimen, reserva_flexible)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (snapshot_id, hotel_id, precio_persona, precio_original,
          ahorro, descuento_pct, precio_2p, producto, regimen, flexible))


# ──────────────────────────────────────────────────────────────
# SCRAPER — intercepta responses directamente
# ──────────────────────────────────────────────────────────────

async def esperar_si_hay_captcha(page: Page):
    """Detecta iframe de DataDome y pausa hasta que el usuario lo resuelva."""
    try:
        captcha = await page.query_selector("iframe[src*='captcha-delivery.com']")
        if captcha:
            print("\n🔴 CAPTCHA DETECTADO — resuélvelo en el navegador y presiona Enter aquí...")
            input()
            await asyncio.sleep(2)  # dar tiempo a que procese la solución
            print("✅ Continuando...")
    except Exception:
        pass

async def scrape_destino(page: Page, href: str, titulo: str, snapshot_id: int, conn) -> int:
    total = 0
    paginas_json = []

    async def capturar_response(response: Response):
        if "/s-accommodations/api/" in response.url and "availability" in response.url:
            try:
                data = await response.json()
                items = data.get("availability", [])
                if items:
                    paginas_json.append((response.url, items))
                    print(f"      📥 API capturada: {len(items)} hoteles")
            except Exception:
                pass

    page.on("response", capturar_response)

    url_base = href if href.startswith("http") else f"https://latamtravel-chile.despegar.cl{href}"

    try:
        # Navegar y esperar redirección a /accommodations/results/
        await page.goto(url_base, wait_until="domcontentloaded", timeout=60000)

        # Esperar hasta que la URL cambie a la página de resultados
        try:
            await page.wait_for_url("**/trip/accommodations/results/**", timeout=20000)
        except Exception:
            print(f"      ⚠️  No redirigió a resultados")

        await esperar_si_hay_captcha(page)

        # Esperar que aparezcan tarjetas de hoteles
        try:
            await page.wait_for_selector("[class*='accommodation'], [class*='hotel-card']", timeout=20000)
        except Exception:
            pass

        await asyncio.sleep(3)

        # Páginas siguientes — usando la URL actual (ya redirigida)
        url_resultados = page.url
        base_sin_page  = re.sub(r"[?&]page=\d+", "", url_resultados)

        for pg in range(2, MAX_PAGINAS + 1):
            sep     = "&" if "?" in base_sin_page else "?"
            url_pag = base_sin_page + f"{sep}page={pg}"

            prev_count = len(paginas_json)
            await page.goto(url_pag, wait_until="domcontentloaded", timeout=40000)
            await esperar_si_hay_captcha(page)
            await asyncio.sleep(7)

            if len(paginas_json) == prev_count:
                print(f"      ⏹  Sin más páginas en página {pg}")
                break

    except Exception as e:
        print(f"      ⚠️  Error: {e}")

    page.remove_listener("response", capturar_response)

    print(f"      📊 Total páginas capturadas en memoria: {len(paginas_json)}")


    # Guardar en BD
    hoteles_vistos = set()
    for _, items in paginas_json:
        for item in items:
            acc = item.get("accommodation", {})
            hid = acc.get("id", "")
            if hid in hoteles_vistos:
                continue
            hoteles_vistos.add(hid)
            try:
                hotel_id = get_or_create_hotel(conn, acc)
                guardar_precio(conn, snapshot_id, hotel_id, item)
                total += 1
            except Exception as e:
                print(f"      ❌ Error guardando hotel {hid}: {e}")
                continue
                
    return total


# ──────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────

async def main():
    inicializar_bd()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=BRAVE_PATH,
            headless=HEADLESS,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/146.0.0.0 Safari/537.36"
            ),
            locale="es-CL",
            timezone_id="America/Santiago",
            viewport={"width": 1440, "height": 900},
        )
        page = await context.new_page()

        # ── Página principal ──────────────────────────────────
        print("🌐 Abriendo página principal...")
        await page.goto(URL_HOME, wait_until="domcontentloaded", timeout=60000)
        try:
            await page.wait_for_selector(".offer-card-pricebox-price-amount", timeout=30000)
        except Exception:
            print("❌ No cargaron tarjetas.")
            await browser.close()
            return

        for i in range(SCROLL_VECES):
            await page.evaluate("window.scrollBy(0, window.innerHeight * 2)")
            await asyncio.sleep(1.5)
        await asyncio.sleep(2)

        # Clic en flechas de carrusel para expandir todos los paquetes
        print("   Expandiendo carruseles...")
        clics_totales = 0
        sin_cambio = 0
        while sin_cambio < 3:
            flechas = await page.query_selector_all(".eva-3-nav-slider.-right")
            hubo_clic = False
            for flecha in flechas:
                try:
                    visible = await flecha.is_visible()
                    enabled = await flecha.is_enabled()
                    if visible and enabled:
                        await flecha.click()
                        await asyncio.sleep(0.8)
                        clics_totales += 1
                        hubo_clic = True
                except Exception:
                    continue
            if not hubo_clic:
                sin_cambio += 1
            else:
                sin_cambio = 0
        print(f"   {clics_totales} clics en flechas realizados.")

        # ── Capturar links únicos ─────────────────────────────

        # ── Capturar links únicos ─────────────────────────────
        tarjetas = await page.query_selector_all(".offer-card-wrapper")
        links = []
        vistos = set()
        for tarjeta in tarjetas:
            link_el = await tarjeta.query_selector("a.offer-card-title")
            if not link_el:
                continue
            href   = await link_el.get_attribute("href")
            titulo = (await link_el.inner_text()).strip()
            if not href:
                continue
            match = re.search(r"typeCodePackage=([A-Z0-9]+)", href)
            key = match.group(1) if match else href[:60]
            if key not in vistos:
                vistos.add(key)
                links.append({"href": href, "titulo": titulo})

        print(f"   {len(links)} destinos únicos encontrados.\n")

        # ── Crear snapshot ────────────────────────────────────
        conn = sqlite3.connect(DB_PATH)
        ahora = datetime.now()
        cur = conn.execute(
            "INSERT INTO snapshots (fecha, hora) VALUES (?, ?)",
            (ahora.strftime("%Y-%m-%d"), ahora.strftime("%H:%M:%S"))
        )
        snapshot_id = cur.lastrowid
        conn.commit()

        # ── Visitar cada destino ──────────────────────────────
        total_global = 0
        for i, link in enumerate(links):
            print(f"[{i+1}/{len(links)}] {link['titulo']}")
            if i == 0:
                print("\n🔴 CAPTCHA DETECTADO — resuélvelo en el navegador y presiona Enter aquí...")
                input()
                print("✅ Continuando...")

            total = await scrape_destino(page, link["href"], link["titulo"], snapshot_id, conn)
            conn.commit()
            print(f"   → {total} hoteles guardados")
            total_global += total
            await asyncio.sleep(2)

        conn.execute(
            "UPDATE snapshots SET total_hoteles = ? WHERE id = ?",
            (total_global, snapshot_id)
        )
        conn.commit()
        conn.close()
        await browser.close()

    print(f"\n{'='*50}")
    print(f"✅ Total hoteles guardados : {total_global}")
    print(f"   Snapshot ID            : {snapshot_id}")
    print(f"{'='*50}")


if __name__ == "__main__":
    asyncio.run(main())
