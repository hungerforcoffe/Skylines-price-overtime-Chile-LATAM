# ✈️ Skylines — Análisis de Precios de Paquetes Turísticos Chile

Herramienta de scraping y seguimiento histórico de precios de paquetes de viaje en **LATAM Travel Chile (Despegar)**, con base de datos SQLite para detectar cambios de precio a lo largo del tiempo.

---

## 📁 Estructura del proyecto

```
Skylines_project_Chile/
│
├── scraper_despegar_v2.py      # Scraper principal (guarda JSON y CSV)
├── analisis_vuelos.py          # Análisis y ranking de conveniencia
├── inspector_html.py           # Diagnóstico de selectores CSS
│
├── paquetes.json               # Último resultado del scraper (JSON)
├── paquetes.csv                # Último resultado del scraper (CSV)
│
└── DB_skyline_latam/
    ├── scraper_con_bd.py       # Scraper con persistencia histórica en SQLite
    ├── precios.db              # Base de datos SQLite con historial de precios
    └── crear_tarea_diaria.bat  # (Opcional) Automatización con Windows Task Scheduler
```

---

## 🚀 Instalación

```bash
pip install playwright
playwright install chromium
```

> ⚠️ Este proyecto usa **Brave Browser** como motor. Verifica que la ruta en cada script apunte a tu instalación:
> ```python
> BRAVE_PATH = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
> ```

---

## 🔄 Flujo de trabajo

### Opción A — Scraping simple (sin historial)

```bash
# 1. Scrapear y guardar en JSON + CSV
python scraper_despegar_v2.py

# 2. Ver ranking de conveniencia
python analisis_vuelos.py
```

### Opción B — Scraping con historial de precios (recomendado)

```bash
# Correr una vez al día — guarda snapshot en precios.db
python DB_skyline_latam/scraper_con_bd.py

# Ver qué precios subieron o bajaron respecto al día anterior
python DB_skyline_latam/scraper_con_bd.py reporte

# Ver historial completo de un destino específico
python DB_skyline_latam/scraper_con_bd.py historial "Punta Cana"
```

---

## 📊 Datos capturados por paquete

| Campo | Descripción |
|---|---|
| `nombre_paquete` | Destino del paquete |
| `precio_clp` | Precio final por persona (CLP) |
| `precio_original_clp` | Precio antes del descuento (si aplica) |
| `ahorro_clp` | Monto ahorrado (si aplica) |
| `descuento_pct` | Porcentaje de descuento (calculado) |
| `dias_noches` | Duración del paquete (ej: "8 DÍAS / 7 NOCHES") |
| `rating` | Puntuación del paquete (ej: 7.9) |
| `estrellas` | Categoría del hotel (1-5) |
| `hotel_y_vuelo` | 1 si incluye hotel + vuelo, 0 si no |
| `millas` | Millas LATAM Pass acumulables |
| `oferta_imbatible` | 1 si tiene etiqueta "Oferta Imbatible" |
| `fecha_scraping` | Fecha y hora de la captura |

---

## 🗄️ Estructura de la base de datos

```sql
destinos   →  id, nombre
snapshots  →  id, fecha, hora, total_paquetes
precios    →  snapshot_id, destino_id, precio_clp, ahorro_clp, rating ...
```

Cada vez que corres `scraper_con_bd.py` se crea un nuevo **snapshot** con todos los precios del día, permitiendo comparar la evolución en el tiempo.

---

## 🛠️ Diagnóstico

Si el scraper no captura datos, usa el inspector para identificar los selectores CSS actuales de la página:

```bash
python inspector_html.py
```

Genera `inspeccion.html` y `screenshot.png` para inspección manual con DevTools.

---

## ⚙️ Automatización diaria (opcional)

Para correr el scraper automáticamente todos los días a las 9 AM, ejecuta `crear_tarea_diaria.bat` como **Administrador**. Edita las rutas dentro del archivo antes de ejecutarlo.

---

## ⚠️ Consideraciones

- Los sitios de viajes usan JavaScript dinámico — el scraper requiere `HEADLESS = False` para evitar detección de bots.
- No ejecutar más de una vez cada 10 minutos para no sobrecargar los servidores.
- Verifica los términos de uso del sitio antes de un uso intensivo.

---

## 📈 Roadmap

- [ ] Visualización de evolución de precios con gráficos
- [ ] Scraping de sub-paquetes al hacer clic en cada destino
- [ ] Alertas por email cuando un precio baje X%
- [ ] Comparación entre múltiples agencias (Sky, Cocha, Viajes Falabella)
Luego agrégala en `OrquestadorVuelos.ejecutar_busqueda()`.
