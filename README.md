# ✈️ Comparador de Vuelos Chile

Scraper + análisis de precios para aerolíneas chilenas (LATAM, SKY y extensible a más).

---

## 📁 Archivos del proyecto

| Archivo | Descripción |
|---|---|
| `scraper_vuelos.py` | Scraper principal con Playwright |
| `inspector_html.py` | Herramienta de diagnóstico para encontrar selectores CSS |
| `analisis_vuelos.py` | Análisis y ranking de conveniencia |

---

## 🚀 Instalación

```bash
pip install playwright pandas
playwright install chromium
```

---

## 🔄 Flujo de trabajo recomendado

### Paso 1 — Inspeccionar la página (primera vez)
```bash
python inspector_html.py
```
Esto guarda `inspeccion.html` y `screenshot.png`.  
Abre `inspeccion.html` en tu navegador y usa **DevTools (F12)** para identificar
los selectores CSS exactos de precios, horarios y escalas.

### Paso 2 — Ajustar selectores en `scraper_vuelos.py`
En las clases `ScraperLATAM` y `ScraperSKY`, modifica las líneas con
`query_selector(...)` usando los selectores que encontraste.

Ejemplo:
```python
# Antes (genérico)
precio_el = await tarjeta.query_selector("[class*='price']")

# Después (exacto, tras inspección)
precio_el = await tarjeta.query_selector(".sc-bdXxxt.precio-total span")
```

### Paso 3 — Ejecutar el scraper
```bash
python scraper_vuelos.py
```
Genera: `vuelos.json` y `vuelos.csv`

### Paso 4 — Analizar resultados
```bash
python analisis_vuelos.py
```
Genera: `reporte_comparativo.csv` con ranking de conveniencia.

---

## ⚙️ Configuración del scraper

En `scraper_vuelos.py`, edita estas variables en `main()`:

```python
ORIGEN   = "SCL"         # Código IATA origen
DESTINO  = "PMC"         # Código IATA destino
FECHA    = "2025-08-15"  # Formato YYYY-MM-DD
HEADLESS = True          # False para ver el navegador
```

### Códigos IATA chilenos comunes

| Ciudad | Código |
|---|---|
| Santiago | SCL |
| Puerto Montt | PMC |
| Punta Arenas | PUQ |
| Calama | CJC |
| Antofagasta | ANF |
| Concepción | CCP |
| Arica | ARI |
| Iquique | IQQ |

---

## 📊 Cálculo de Score de Conveniencia (0-100)

| Factor | Puntos |
|---|---|
| Base | +100 |
| Por cada escala | -15 |
| Equipaje bodega incluido | +10 |
| Equipaje cabina incluido | +5 |
| Permite cambios | +8 |
| Permite reembolso | +7 |
| Penalización precio relativo | -0 a -20 |

---

## ⚠️ Consideraciones legales y técnicas

- **Términos de servicio**: Verifica siempre los T&C de cada sitio antes de scrapear.
- **Rate limiting**: El script incluye pausas entre requests (`asyncio.sleep`). No las elimines.
- **Sitios dinámicos**: LATAM y SKY usan React/Angular. Si los selectores fallan, usa el `inspector_html.py` para actualizarlos.
- **CAPTCHAs**: Si el sitio bloquea el scraper, considera usar proxies rotativos o servicios como ScrapingBee.
- **Frecuencia**: No ejecutes el scraper más de 1 vez cada 10 minutos por aerolínea.

---

## 🔧 Extender a más aerolíneas

Para agregar JetSmart u otras, crea una clase nueva siguiendo el mismo patrón:

```python
class ScraperJetSmart:
    def __init__(self, page: Page):
        self.page = page

    async def buscar(self, origen, destino, fecha) -> list[Vuelo]:
        # ... mismo patrón que ScraperLATAM
        pass
```

Luego agrégala en `OrquestadorVuelos.ejecutar_busqueda()`.
