"""
inspector_html.py
=================
Herramienta de diagnóstico: abre una URL de aerolínea, guarda el HTML
y muestra los selectores CSS más relevantes automáticamente.

Úsalo ANTES de ajustar los selectores en scraper_vuelos.py.

Uso:
    python inspector_html.py
"""

import asyncio
import re
from pathlib import Path
from playwright.async_api import async_playwright

# ── Configura la URL a inspeccionar ──
URL_OBJETIVO = (
    "https://www.latamairlines.com/cl/es/vuelos?"
    "q=SCLPMC&inFlow=false&from=SCL&adult=1&child=0&infant=0"
    "&trip=OW&date=2025-08-15&cabin=Economy"
)
ARCHIVO_SALIDA = "inspeccion.html"
SCREENSHOT_SALIDA = "screenshot.png"


# Palabras clave para detectar selectores relevantes
PALABRAS_CLAVE = [
    "price", "precio", "fare", "monto", "cost",
    "flight", "vuelo", "result", "card", "tarjeta",
    "duration", "duracion", "time", "hora", "hour",
    "stop", "escala", "baggage", "equipaje",
    "airline", "aerolinea", "operator",
]


async def inspeccionar(url: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe", headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="es-CL",
            timezone_id="America/Santiago",
            viewport={"width": 1280, "height": 900},
        )
        page = await context.new_page()

        print(f"🌐 Cargando: {url}")
        await page.goto(url, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(5)  # Dar tiempo al JS para renderizar

        # Guardar HTML
        html = await page.content()
        Path(ARCHIVO_SALIDA).write_text(html, encoding="utf-8")
        print(f"📄 HTML guardado en: {ARCHIVO_SALIDA} ({len(html):,} caracteres)")

        # Guardar screenshot
        await page.screenshot(path=SCREENSHOT_SALIDA, full_page=True)
        print(f"📸 Screenshot guardado en: {SCREENSHOT_SALIDA}")

        # Buscar clases CSS que parezcan relevantes
        clases_encontradas = re.findall(r'class="([^"]+)"', html)
        clases_unicas = set()
        for grupo in clases_encontradas:
            for clase in grupo.split():
                clases_unicas.add(clase)

        print("\n🔍 Clases CSS posiblemente relevantes:")
        relevantes = sorted([
            c for c in clases_unicas
            if any(kw in c.lower() for kw in PALABRAS_CLAVE)
        ])
        for clase in relevantes[:50]:
            print(f"   .{clase}")

        # Buscar data-testid
        testids = re.findall(r'data-testid="([^"]+)"', html)
        if testids:
            print("\n🏷️  data-testid encontrados:")
            for tid in sorted(set(testids))[:30]:
                print(f"   [data-testid='{tid}']")

        await browser.close()
        print("\n✅ Inspección completa. Revisa los archivos generados.")
        print("   Abre 'inspeccion.html' en tu navegador para explorar el DOM.")


if __name__ == "__main__":
    asyncio.run(inspeccionar(URL_OBJETIVO))
