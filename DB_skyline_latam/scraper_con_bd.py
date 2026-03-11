"""
scraper_con_bd.py
=================
Scraper de paquetes Despegar + SQLite para seguimiento de precios.

Tablas:
  - destinos  : catálogo de destinos únicos
  - snapshots : cada ejecución del scraper (fecha/hora)
  - precios   : precio capturado por destino y snapshot

Uso:
    python scraper_con_bd.py          → scraper + guardar en BD
    python scraper_con_bd.py reporte  → ver cambios de precio
"""

import asyncio
import re
import sys
import sqlite3
from datetime import datetime
from dataclasses import dataclass
from typing import Optional
from playwright.async_api import async_playwright, Page

# ──────────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ──────────────────────────────────────────────────────────────

BRAVE_PATH   = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
URL          = "https://latamtravel-chile.despegar.cl/?label=cl_web_subhome-deals-packages"
HEADLESS     = False
SCROLL_VECES = 6
DB_PATH      = "precios.db"


# ──────────────────────────────────────────────────────────────
# BASE DE DATOS
# ──────────────────────────────────────────────────────────────

def conectar() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def inicializar_bd():
    """Crea las tablas si no existen."""
    conn = conectar()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS destinos (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre          TEXT UNIQUE NOT NULL,
            creado_en       TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS snapshots (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha           TEXT NOT NULL,   -- 'YYYY-MM-DD'
            hora            TEXT NOT NULL,   -- 'HH:MM:SS'
            total_paquetes  INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS precios (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id           INTEGER NOT NULL,
            destino_id            INTEGER NOT NULL,
            precio_clp            INTEGER,
            precio_original_clp   INTEGER,
            ahorro_clp            INTEGER,
            descuento_pct         REAL,
            dias_noches           TEXT,
            rating                REAL,
            estrellas             INTEGER,
            hotel_y_vuelo         INTEGER DEFAULT 0,
            millas                INTEGER,
            oferta_imbatible      INTEGER DEFAULT 0,
            FOREIGN KEY (snapshot_id) REFERENCES snapshots(id),
            FOREIGN KEY (destino_id)  REFERENCES destinos(id)
        );

        CREATE INDEX IF NOT EXISTS idx_precios_destino
            ON precios(destino_id);
        CREATE INDEX IF NOT EXISTS idx_precios_snapshot
            ON precios(snapshot_id);
    """)
    conn.commit()
    conn.close()
    print(f"✅ BD inicializada: {DB_PATH}")


def upsert_destino(conn: sqlite3.Connection, nombre: str) -> int:
    """Inserta destino si no existe y retorna su id."""
    conn.execute(
        "INSERT OR IGNORE INTO destinos (nombre) VALUES (?)", (nombre,)
    )
    row = conn.execute(
        "SELECT id FROM destinos WHERE nombre = ?", (nombre,)
    ).fetchone()
    return row["id"]


def crear_snapshot(conn: sqlite3.Connection) -> int:
    ahora = datetime.now()
    cur = conn.execute(
        "INSERT INTO snapshots (fecha, hora) VALUES (?, ?)",
        (ahora.strftime("%Y-%m-%d"), ahora.strftime("%H:%M:%S"))
    )
    return cur.lastrowid


def actualizar_total_snapshot(conn: sqlite3.Connection, snapshot_id: int, total: int):
    conn.execute(
        "UPDATE snapshots SET total_paquetes = ? WHERE id = ?",
        (total, snapshot_id)
    )


def guardar_precio(conn: sqlite3.Connection, snapshot_id: int, destino_id: int, p: dict):
    conn.execute("""
        INSERT INTO precios (
            snapshot_id, destino_id,
            precio_clp, precio_original_clp, ahorro_clp, descuento_pct,
            dias_noches, rating, estrellas,
            hotel_y_vuelo, millas, oferta_imbatible
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        snapshot_id, destino_id,
        p.get("precio_clp"),
        p.get("precio_original_clp"),
        p.get("ahorro_clp"),
        p.get("descuento_pct"),
        p.get("dias_noches"),
        p.get("rating"),
        p.get("estrellas"),
        p.get("hotel_y_vuelo", 0),
        p.get("millas"),
        p.get("oferta_imbatible", 0),
    ))


# ──────────────────────────────────────────────────────────────
# SCRAPER
# ──────────────────────────────────────────────────────────────

def limpiar_precio(texto: str) -> Optional[int]:
    if not texto:
        return None
    solo_nums = re.sub(r"[^\d]", "", texto)
    return int(solo_nums) if solo_nums else None


def limpiar_float(texto: str) -> Optional[float]:
    if not texto:
        return None
    nums = re.findall(r"[\d]+[.,]?[\d]*", texto.strip())
    try:
        return float(nums[0].replace(",", ".")) if nums else None
    except ValueError:
        return None


async def parsear_tarjeta(t, page: Page) -> Optional[dict]:
    """Extrae datos de una tarjeta. Retorna dict o None si falla."""
    try:
        pkg = {}

        # Nombre
        title = await t.get_attribute("title")
        if title:
            pkg["nombre"] = title.strip()
        else:
            h_el = await t.query_selector("h2, h3, [class*='title']")
            pkg["nombre"] = (await h_el.inner_text()).strip() if h_el else "Desconocido"

        # Precio final
        precio_el = await t.query_selector(".offer-card-pricebox-price-amount")
        if precio_el:
            pkg["precio_clp"] = limpiar_precio(await precio_el.inner_text())

        # Precio original tachado
        precio_old_el = await t.query_selector(".offer-card-pricebox-price-old")
        if precio_old_el:
            pkg["precio_original_clp"] = limpiar_precio(await precio_old_el.inner_text())

        # Ahorro
        ahorro_el = await t.query_selector(".-eva-3-tc-gray-0")
        if ahorro_el:
            texto_ahorro = await ahorro_el.evaluate(
                "(el) => el.parentElement ? el.parentElement.innerText : el.innerText"
            )
            pkg["ahorro_clp"] = limpiar_precio(texto_ahorro)

        # Descuento % calculado
        if pkg.get("precio_original_clp") and pkg.get("ahorro_clp"):
            pkg["descuento_pct"] = round(
                pkg["ahorro_clp"] / pkg["precio_original_clp"] * 100, 1
            )

        # Días / Noches
        driver_el = await t.query_selector(".offer-card-main-driver")
        if driver_el:
            pkg["dias_noches"] = " ".join((await driver_el.inner_text()).split())

        # Rating
        rating_el = await t.query_selector(".rating-text")
        if rating_el:
            pkg["rating"] = limpiar_float(await rating_el.inner_text())

        # Estrellas
        estrellas_els = await t.query_selector_all(
            ".offer-card-rating-stars [class*='star-filled']"
        )
        pkg["estrellas"] = len(estrellas_els) if estrellas_els else None

        # Hotel + Vuelo
        desc_el = await t.query_selector(".offer-card-description")
        if desc_el:
            desc = (await desc_el.inner_text()).lower()
            pkg["hotel_y_vuelo"] = 1 if ("hotel" in desc and "vuelo" in desc) else 0

        # Millas
        millas_els = await t.query_selector_all(".-eva-3-bold")
        for mel in millas_els:
            texto_m = await mel.inner_text()
            if "milla" in texto_m.lower():
                pkg["millas"] = limpiar_precio(texto_m)
                break

        # Oferta Imbatible
        texto_tarjeta = (await t.inner_text()).lower()
        pkg["oferta_imbatible"] = 1 if "imbatible" in texto_tarjeta else 0

        return pkg

    except Exception as e:
        return None


async def scrape() -> list[dict]:
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
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="es-CL",
            timezone_id="America/Santiago",
            viewport={"width": 1440, "height": 900},
        )
        page = await context.new_page()

        print(f"🌐 {datetime.now().strftime('%Y-%m-%d %H:%M')} — Abriendo página...")
        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)

        try:
            await page.wait_for_selector(".offer-card-pricebox-price-amount", timeout=30000)
        except Exception:
            print("❌ No se cargaron tarjetas.")
            await browser.close()
            return []

        for i in range(SCROLL_VECES):
            await page.evaluate("window.scrollBy(0, window.innerHeight * 2)")
            await asyncio.sleep(1.5)

        await asyncio.sleep(2)

        tarjetas = await page.query_selector_all(".offer-card-wrapper")
        print(f"🃏 {len(tarjetas)} tarjetas encontradas.")

        resultados = []
        for t in tarjetas:
            datos = await parsear_tarjeta(t, page)
            if datos and datos.get("precio_clp"):
                resultados.append(datos)

        await browser.close()
        return resultados


# ──────────────────────────────────────────────────────────────
# GUARDAR EN BD
# ──────────────────────────────────────────────────────────────

def guardar_en_bd(paquetes: list[dict]):
    conn = conectar()
    snapshot_id = crear_snapshot(conn)

    guardados = 0
    for p in paquetes:
        nombre = p.get("nombre", "").strip()
        if not nombre:
            continue
        destino_id = upsert_destino(conn, nombre)
        guardar_precio(conn, snapshot_id, destino_id, p)
        guardados += 1
        print(f"   ✓ {nombre:<40} ${p.get('precio_clp', 0):>12,} CLP")

    actualizar_total_snapshot(conn, snapshot_id, guardados)
    conn.commit()
    conn.close()
    print(f"\n💾 {guardados} paquetes guardados en '{DB_PATH}' (snapshot #{snapshot_id})")


# ──────────────────────────────────────────────────────────────
# REPORTE DE CAMBIOS
# ──────────────────────────────────────────────────────────────

def reporte_cambios():
    """Compara el último snapshot con el anterior y muestra cambios."""
    conn = conectar()

    snapshots = conn.execute(
        "SELECT id, fecha, hora, total_paquetes FROM snapshots ORDER BY id DESC LIMIT 2"
    ).fetchall()

    if len(snapshots) < 2:
        print("⚠️  Necesitas al menos 2 ejecuciones para ver cambios.")
        conn.close()
        return

    nuevo_id  = snapshots[0]["id"]
    viejo_id  = snapshots[1]["id"]
    fecha_new = f"{snapshots[0]['fecha']} {snapshots[0]['hora']}"
    fecha_old = f"{snapshots[1]['fecha']} {snapshots[1]['hora']}"

    print(f"\n📊 REPORTE DE CAMBIOS DE PRECIO")
    print(f"   Comparando: {fecha_old}  →  {fecha_new}")
    print("=" * 75)

    query = """
        SELECT
            d.nombre,
            p_new.precio_clp      AS precio_nuevo,
            p_old.precio_clp      AS precio_viejo,
            p_new.oferta_imbatible AS imbatible,
            p_new.dias_noches
        FROM destinos d
        JOIN precios p_new ON p_new.destino_id = d.id AND p_new.snapshot_id = ?
        JOIN precios p_old ON p_old.destino_id = d.id AND p_old.snapshot_id = ?
        ORDER BY (p_new.precio_clp - p_old.precio_clp) ASC
    """
    filas = conn.execute(query, (nuevo_id, viejo_id)).fetchall()

    subio, bajo, igual = [], [], []
    for f in filas:
        if f["precio_nuevo"] and f["precio_viejo"]:
            diff = f["precio_nuevo"] - f["precio_viejo"]
            pct  = diff / f["precio_viejo"] * 100
            entry = (f["nombre"], f["precio_viejo"], f["precio_nuevo"], diff, pct)
            if diff > 0:   subio.append(entry)
            elif diff < 0: bajo.append(entry)
            else:          igual.append(entry)

    if bajo:
        print("\n🟢 BAJARON DE PRECIO:")
        for nombre, viejo, nuevo, diff, pct in bajo:
            print(f"   {nombre:<40} ${viejo:>10,} → ${nuevo:>10,}  ({pct:+.1f}%)")

    if subio:
        print("\n🔴 SUBIERON DE PRECIO:")
        for nombre, viejo, nuevo, diff, pct in subio:
            print(f"   {nombre:<40} ${viejo:>10,} → ${nuevo:>10,}  ({pct:+.1f}%)")

    if igual:
        print(f"\n⚪ Sin cambio: {len(igual)} destinos")

    # Nuevos destinos (aparecieron hoy)
    nuevos = conn.execute("""
        SELECT d.nombre, p.precio_clp
        FROM destinos d
        JOIN precios p ON p.destino_id = d.id AND p.snapshot_id = ?
        WHERE d.id NOT IN (
            SELECT destino_id FROM precios WHERE snapshot_id = ?
        )
    """, (nuevo_id, viejo_id)).fetchall()

    if nuevos:
        print(f"\n🆕 NUEVOS DESTINOS HOY:")
        for n in nuevos:
            print(f"   {n['nombre']:<40} ${n['precio_clp']:>10,}")

    print("=" * 75)
    conn.close()


def historial_destino(nombre: str):
    """Muestra el historial completo de precios de un destino específico."""
    conn = conectar()
    filas = conn.execute("""
        SELECT s.fecha, s.hora, p.precio_clp, p.ahorro_clp, p.oferta_imbatible
        FROM precios p
        JOIN snapshots s ON s.id = p.snapshot_id
        JOIN destinos  d ON d.id = p.destino_id
        WHERE LOWER(d.nombre) LIKE LOWER(?)
        ORDER BY s.id ASC
    """, (f"%{nombre}%",)).fetchall()

    if not filas:
        print(f"❌ No se encontró '{nombre}' en la BD.")
        conn.close()
        return

    print(f"\n📈 HISTORIAL: {nombre.upper()}")
    print(f"{'Fecha':<12} {'Hora':<10} {'Precio CLP':>12} {'Ahorro':>10} {'Imbatible'}")
    print("-" * 60)
    for f in filas:
        ahorro_str = f"${f['ahorro_clp']:,}" if f["ahorro_clp"] else "-"
        imb = "⭐" if f["oferta_imbatible"] else ""
        print(f"{f['fecha']:<12} {f['hora']:<10} ${f['precio_clp']:>10,} {ahorro_str:>10} {imb}")

    conn.close()


# ──────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────

async def main():
    inicializar_bd()

    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "reporte":
            reporte_cambios()
            return
        elif cmd == "historial" and len(sys.argv) > 2:
            historial_destino(sys.argv[2])
            return

    # Scraping normal
    paquetes = await scrape()

    if not paquetes:
        print("❌ Sin resultados.")
        return

    print(f"\n✅ {len(paquetes)} paquetes capturados.")
    guardar_en_bd(paquetes)

    # Mostrar reporte si hay datos previos
    conn = conectar()
    total_snapshots = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
    conn.close()
    if total_snapshots >= 2:
        reporte_cambios()


if __name__ == "__main__":
    asyncio.run(main())
