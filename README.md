# Skylines — Análisis de Precios de Paquetes Turísticos Chile

Herramienta de scraping y seguimiento histórico de precios de paquetes de viaje en LATAM Travel Chile (Despegar), con base de datos SQLite para detectar cambios de precio a lo largo del tiempo.

---

## Estructura del proyecto

```
Skylines_project_Chile/
│
├── scraper_despegar_v2.py        # Scraper de página principal (guarda JSON y CSV)
├── analisis_vuelos.py            # Análisis y ranking de conveniencia
├── inspector_html.py             # Diagnóstico de selectores CSS
│
├── paquetes.json                 # Último resultado del scraper (JSON)
├── paquetes.csv                  # Último resultado del scraper (CSV)
│
└── DB_skyline_latam/
    ├── scraper_con_bd.py         # Scraper de página principal con historial SQLite
    ├── precios.db                # Base de datos de paquetes principales
    ├── crear_tarea_diaria.bat    # (Opcional) Automatización con Windows Task Scheduler
    │
    └── scraper_with_api/
        ├── scraper_api_hoteles.py  # Scraper de sub-paquetes via API interna
        └── hoteles.db              # Base de datos de hoteles con historial de precios
```

---

## Instalación

```bash
pip install playwright requests
playwright install chromium
```

Este proyecto usa Brave Browser como motor de automatización. Verifica que la ruta en cada script apunte a tu instalación:

```python
BRAVE_PATH = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
```

---

## Flujo de trabajo

### Nivel 1 — Scraping de página principal

Captura los paquetes destacados que aparecen en la home de LATAM Travel Chile.

```bash
# Scrapear y guardar en JSON + CSV
python scraper_despegar_v2.py

# Correr con historial diario en SQLite
python DB_skyline_latam/scraper_con_bd.py

# Ver cambios de precio respecto al día anterior
python DB_skyline_latam/scraper_con_bd.py reporte

# Ver historial de un destino específico
python DB_skyline_latam/scraper_con_bd.py historial "Punta Cana"
```

### Nivel 2 — Scraping de sub-paquetes (hoteles detallados)

Entra a cada destino de la página principal, intercepta la API interna de Despegar y captura todos los hoteles disponibles con sus precios completos.

```bash
python DB_skyline_latam/scraper_with_api/scraper_api_hoteles.py
```

Este script abre el navegador, navega por cada destino automáticamente y guarda los resultados en `hoteles.db`. Si aparece un captcha, el script pausa y espera que lo resuelvas manualmente antes de continuar.

---

## Datos capturados

### Página principal — `precios.db`

| Campo | Descripción |
|---|---|
| `nombre_paquete` | Destino del paquete |
| `precio_clp` | Precio final por persona (CLP) |
| `precio_original_clp` | Precio antes del descuento (si aplica) |
| `ahorro_clp` | Monto ahorrado (si aplica) |
| `descuento_pct` | Porcentaje de descuento (calculado) |
| `dias_noches` | Duración del paquete (ej: "8 DIAS / 7 NOCHES") |
| `rating` | Puntuación del paquete (ej: 7.9) |
| `estrellas` | Categoría del hotel (1-5) |
| `hotel_y_vuelo` | 1 si incluye hotel + vuelo, 0 si no |
| `millas` | Millas LATAM Pass acumulables |
| `oferta_imbatible` | 1 si tiene etiqueta "Oferta Imbatible" |
| `fecha_scraping` | Fecha y hora de la captura |

### Sub-paquetes — `hoteles.db`

| Campo | Descripción |
|---|---|
| `nombre` | Nombre exacto del hotel |
| `destino` | Ciudad de destino |
| `zona` | Zona o sector (ej: "Bávaro") |
| `direccion` | Dirección del hotel |
| `estrellas` | Categoría del hotel (1-5) |
| `rating` | Puntuación (ej: 7.4) |
| `total_resenas` | Número de reseñas |
| `precio_persona_clp` | Precio final por persona (CLP) |
| `precio_original_clp` | Precio antes del descuento (si aplica) |
| `ahorro_clp` | Monto ahorrado (si aplica) |
| `descuento_pct` | Porcentaje de descuento (calculado) |
| `precio_2_personas` | Precio total para 2 personas |
| `producto` | Descripción (ej: "Vuelo + Alojamiento") |
| `regimen` | Régimen de comidas (ej: "All Inclusive") |
| `reserva_flexible` | 1 si permite cambios, 0 si no |

---

## Estructura de las bases de datos

**precios.db**
```
destinos   ->  id, nombre
snapshots  ->  id, fecha, hora, total_paquetes
precios    ->  snapshot_id, destino_id, precio_clp, ahorro_clp, rating ...
```

**hoteles.db**
```
snapshots  ->  id, fecha, hora, total_hoteles
hoteles    ->  id, hotel_id_despegar, nombre, destino, zona, estrellas, rating ...
precios    ->  snapshot_id, hotel_id, precio_persona_clp, ahorro_clp, regimen ...
```

Cada ejecución crea un nuevo snapshot, permitiendo comparar la evolución de precios en el tiempo.

---

## Diagnostico

Si el scraper no captura datos, usa el inspector para identificar los selectores CSS actuales de la página:

```bash
python inspector_html.py
```

Genera `inspeccion.html` y `screenshot.png` para inspección manual con DevTools.

---

## Automatizacion diaria (opcional)

Para correr el scraper automáticamente todos los días a las 9 AM, ejecuta `crear_tarea_diaria.bat` como Administrador. Edita las rutas dentro del archivo antes de ejecutarlo.

---

## Consideraciones

⚠️ El scraping de sitios web puede ir en contra de los términos de uso de cada plataforma. Este proyecto es de uso personal para análisis de precios y no redistribuye datos de ningún tipo. Usalo de forma responsable, respetando los tiempos de espera entre requests y sin sobrecargar los servidores.

- El scraper requiere `HEADLESS = False` ya que Despegar usa DataDome como sistema anti-bot, que bloquea navegadores headless.
- Cuando aparece un captcha, el script lo detecta automáticamente y pausa hasta que lo resuelves manualmente.
- No ejecutar más de una vez al día por destino.

---

## Roadmap

- [ ] Dashboard de visualización con gráficos de evolución de precios
- [ ] Alertas por email cuando un precio baje un porcentaje definido
- [ ] Comparación entre múltiples agencias (Sky, Cocha, Viajes Falabella)
- [ ] Análisis de mejor época para viajar por destino
