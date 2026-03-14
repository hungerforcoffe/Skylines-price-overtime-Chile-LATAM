"""
scraper_despegar_v2.py
======================
Scraper para paquetes en latamtravel-chile.despegar.cl
Campos: nombre, precio, precio original, ahorro, días/noches,
        rating, estrellas, hotel+vuelo, millas, oferta imbatible.

Uso:
    python scraper_despegar_v2.py
"""

import asyncio
import json
import re
import csv
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Optional
from playwright.async_api import async_playwright, Page

# ──────────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ──────────────────────────────────────────────────────────────

BRAVE_PATH = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
URL        = "https://latamtravel-chile.despegar.cl/?label=cl_web_subhome-deals-packages"
HEADLESS   = False
SCROLL_VECES = 6
SALIDA_JSON  = "paquetes.json"
SALIDA_CSV   = "paquetes.csv"


# ──────────────────────────────────────────────────────────────
# Modelo de datos — solo lo que importa
# ──────────────────────────────────────────────────────────────

@dataclass
class Paquete:
    fecha_scraping:       str            = ""
    nombre_paquete:       str            = ""
    precio_clp:           Optional[int]  = None
    precio_original_clp:  Optional[int]  = None   # tachado (puede ser None)
    ahorro_clp:           Optional[int]  = None   # puede ser None
    descuento_pct:        Optional[float]= None   # calculado: ahorro/precio_original
    dias_noches:          str            = ""      # "8 DÍAS / 7 NOCHES"
    rating:               Optional[float]= None   # 7.9
    estrellas:            Optional[int]  = None   # 1-5
    hotel_y_vuelo:        int            = 0      # 1 = sí, 0 = no
    millas:               Optional[int]  = None
    oferta_imbatible:     int            = 0      # 1 = sí, 0 = no


def limpiar_precio(texto: str) -> Optional[int]:
    if not texto:
        return None
    solo_nums = re.sub(r"[^\d]", "", texto)
    return int(solo_nums) if solo_nums else None

def limpiar_float(texto: str) -> Optional[float]:
    if not texto:
        return None
    texto = texto.strip().replace(",", ".")
    nums = re.findall(r"[\d.]+", texto)
    try:
        return float(nums[0]) if nums else None
    except ValueError:
        return None


# ──────────────────────────────────────────────────────────────
# Scraper
# ──────────────────────────────────────────────────────────────

async def scrape() -> list[Paquete]:
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

        print(f"🌐 Abriendo {URL}")
        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)

        # Esperar tarjetas
        print("⏳ Esperando tarjetas de paquetes...")
        try:
            await page.wait_for_selector(".offer-card-pricebox-price-amount", timeout=30000)
            print("✅ Tarjetas detectadas.")
        except Exception:
            print("❌ No se detectaron tarjetas. Guardando HTML...")
            with open("debug.html", "w", encoding="utf-8") as f:
                f.write(await page.content())
            await browser.close()
            return []

        # Scroll para activar lazy-load de secciones
        for i in range(SCROLL_VECES):
            await page.evaluate("window.scrollBy(0, window.innerHeight * 2)")
            await asyncio.sleep(1.5)
            print(f"   scroll {i+1}/{SCROLL_VECES}")

        await asyncio.sleep(2)

        # Clic en todas las flechas de carrusel hasta agotarlas
        print("🔄 Expandiendo carruseles...")
        clics_totales = 0
        while True:
            flechas = await page.query_selector_all(".eva-3-nav-slider.-right")
            if not flechas:
                break
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
                break

        print(f"   {clics_totales} clics en flechas realizados.")

        paquetes = await parsear(page)
        await browser.close()
        return paquetes


async def parsear(page: Page) -> list[Paquete]:
    paquetes = []
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Cada tarjeta tiene esta clase raíz
    tarjetas = await page.query_selector_all(".offer-card-wrapper")

    if not tarjetas:
        # Fallback
        tarjetas = await page.query_selector_all("[class*='offer-card-wrapper']")

    print(f"🃏 {len(tarjetas)} tarjetas encontradas.")

    for i, t in enumerate(tarjetas):
        try:
            pkg = Paquete(fecha_scraping=ahora)

            # ── Nombre del paquete ────────────────────────────
            title = await t.get_attribute("title")
            if title:
                pkg.nombre_paquete = title.strip()
            else:
                h_el = await t.query_selector("h2, h3, [class*='title']")
                if h_el:
                    pkg.nombre_paquete = (await h_el.inner_text()).strip()

            # ── Precio final ──────────────────────────────────
            precio_el = await t.query_selector(".offer-card-pricebox-price-amount")
            if precio_el:
                pkg.precio_clp = limpiar_precio(await precio_el.inner_text())

            # ── Precio original tachado (opcional) ───────────
            precio_old_el = await t.query_selector(".offer-card-pricebox-price-old")
            if precio_old_el:
                pkg.precio_original_clp = limpiar_precio(await precio_old_el.inner_text())

            # ── Ahorro ────────────────────────────────────────
            # El ahorro está como: <span>Ahorras </span>"$150.718"
            # Buscamos el contenedor padre que tenga "Ahorras"
            # ── Ahorro ────────────────────────────────────────
            ahorro_container = await t.query_selector(".-eva-3-tc-gray-0")
            if ahorro_container:
                texto_completo = await ahorro_container.evaluate(
                    "(el) => el.parentElement ? el.parentElement.innerText : el.innerText"
                )
                pkg.ahorro_clp = limpiar_precio(texto_completo)

            # ── Descuento % (calculado) ───────────────────────
            if pkg.precio_original_clp and pkg.ahorro_clp:
                pkg.descuento_pct = round(
                    pkg.ahorro_clp / pkg.precio_original_clp * 100, 1
                )

            # ── Días / Noches ─────────────────────────────────
            driver_el = await t.query_selector(".offer-card-main-driver")
            if driver_el:
                texto_driver = (await driver_el.inner_text()).strip()
                # Limpiar espacios y saltos raros
                pkg.dias_noches = " ".join(texto_driver.split())

            # ── Rating ────────────────────────────────────────
            rating_el = await t.query_selector(".rating-text")
            if rating_el:
                pkg.rating = limpiar_float(await rating_el.inner_text())

            # ── Estrellas ─────────────────────────────────────
            estrellas_els = await t.query_selector_all(
                ".offer-card-rating-stars .eva-3-icon-star-filled, "
                ".offer-card-rating-stars [class*='star-filled']"
            )
            pkg.estrellas = len(estrellas_els) if estrellas_els else None

            # ── Hotel + Vuelo ─────────────────────────────────
            desc_el = await t.query_selector(".offer-card-description")
            if desc_el:
                desc_texto = (await desc_el.inner_text()).lower()
                pkg.hotel_y_vuelo = 1 if ("hotel" in desc_texto and "vuelo" in desc_texto) else 0

            # ── Millas ────────────────────────────────────────
            # Por esto:
            millas_el = await t.query_selector(".capitalized-message .-eva-3-bold")
            if millas_el:
                texto_m = await millas_el.inner_text()
                if "milla" in texto_m.lower():
                    pkg["millas"] = limpiar_precio(texto_m)

            # ── Oferta Imbatible ──────────────────────────────
            texto_tarjeta = (await t.inner_text()).lower()
            pkg.oferta_imbatible = 1 if "imbatible" in texto_tarjeta else 0

            paquetes.append(pkg)
            print(
                f"   [{i+1:>2}] {pkg.nombre_paquete:<35} "
                f"${pkg.precio_clp:>12,}" if pkg.precio_clp else
                f"   [{i+1:>2}] {pkg.nombre_paquete} — sin precio"
            )

        except Exception as e:
            print(f"   ⚠️  Error tarjeta {i+1}: {e}")

    return paquetes


# ──────────────────────────────────────────────────────────────
# Guardar
# ──────────────────────────────────────────────────────────────

CAMPOS_CSV = [
    "fecha_scraping", "nombre_paquete",
    "precio_clp", "precio_original_clp", "ahorro_clp", "descuento_pct",
    "dias_noches", "rating", "estrellas",
    "hotel_y_vuelo", "millas", "oferta_imbatible",
]

def guardar_json(paquetes: list[Paquete]):
    with open(SALIDA_JSON, "w", encoding="utf-8") as f:
        json.dump([asdict(p) for p in paquetes], f, ensure_ascii=False, indent=2)
    print(f"\n💾 JSON → {SALIDA_JSON}")

def guardar_csv(paquetes: list[Paquete]):
    if not paquetes:
        return
    with open(SALIDA_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS_CSV, extrasaction="ignore")
        writer.writeheader()
        for p in paquetes:
            writer.writerow(asdict(p))
    print(f"💾 CSV  → {SALIDA_CSV}")


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────

async def main():
    paquetes = await scrape()

    if not paquetes:
        print("\n❌ Sin resultados.")
        return

    con_precio = [p for p in paquetes if p.precio_clp]
    print(f"\n{'='*50}")
    print(f"✅ Paquetes capturados : {len(paquetes)}")
    print(f"   Con precio         : {len(con_precio)}")
    if con_precio:
        precios = [p.precio_clp for p in con_precio]
        print(f"   Precio mínimo      : ${min(precios):,} CLP")
        print(f"   Precio máximo      : ${max(precios):,} CLP")
        con_descuento = [p for p in con_precio if p.descuento_pct]
        if con_descuento:
            prom_desc = sum(p.descuento_pct for p in con_descuento) / len(con_descuento)
            print(f"   Descuento promedio : {prom_desc:.1f}%")
    print(f"{'='*50}")

    guardar_json(paquetes)
    guardar_csv(paquetes)

if __name__ == "__main__":
    asyncio.run(main())
