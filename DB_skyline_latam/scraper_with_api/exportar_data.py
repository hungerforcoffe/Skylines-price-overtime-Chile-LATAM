"""
exportar_data.py
================
Exporta datos de hoteles.db a dashboard_data.json
para que el dashboard HTML pueda leerlos.

Uso:
    python exportar_data.py

Genera: dashboard_data.json en la misma carpeta.
"""

import sqlite3
import json
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "hoteles.db")
OUT_PATH = os.path.join(BASE_DIR, "dashboard_data.json")


def exportar():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # ── Snapshots ────────────────────────────────────────────
    snapshots = conn.execute(
        "SELECT id, fecha, hora, total_hoteles FROM snapshots ORDER BY id"
    ).fetchall()

    # ── Destinos únicos ───────────────────────────────────────
    destinos = conn.execute(
        "SELECT DISTINCT destino FROM hoteles WHERE destino != '' ORDER BY destino"
    ).fetchall()
    destinos = [d["destino"] for d in destinos]

    # ── Evolución de precio promedio por destino ──────────────
    evolucion = conn.execute("""
        SELECT
            s.fecha,
            h.destino,
            ROUND(AVG(p.precio_persona_clp)) AS precio_promedio,
            ROUND(MIN(p.precio_persona_clp)) AS precio_minimo,
            ROUND(MAX(p.precio_persona_clp)) AS precio_maximo,
            COUNT(DISTINCT h.id)             AS total_hoteles
        FROM precios p
        JOIN hoteles   h ON h.id = p.hotel_id
        JOIN snapshots s ON s.id = p.snapshot_id
        WHERE p.precio_persona_clp IS NOT NULL
          AND h.destino != ''
        GROUP BY s.fecha, h.destino
        ORDER BY s.fecha, h.destino
    """).fetchall()

    # ── Top hoteles con mayor bajada de precio ────────────────
    mejores_bajas = conn.execute("""
        SELECT
            h.nombre,
            h.destino,
            h.estrellas,
            h.rating,
            MIN(p.precio_persona_clp)  AS precio_min,
            MAX(p.precio_persona_clp)  AS precio_max,
            MAX(p.precio_persona_clp) - MIN(p.precio_persona_clp) AS variacion,
            ROUND(
                (MAX(p.precio_persona_clp) - MIN(p.precio_persona_clp)) * 100.0
                / MAX(p.precio_persona_clp), 1
            ) AS variacion_pct
        FROM precios p
        JOIN hoteles h ON h.id = p.hotel_id
        WHERE p.precio_persona_clp IS NOT NULL
        GROUP BY h.id
        HAVING COUNT(DISTINCT p.snapshot_id) >= 3
        ORDER BY variacion_pct DESC
        LIMIT 20
    """).fetchall()

    # ── Precio promedio por destino (resumen general) ─────────
    resumen_destinos = conn.execute("""
        SELECT
            h.destino,
            ROUND(AVG(p.precio_persona_clp))  AS precio_promedio,
            ROUND(MIN(p.precio_persona_clp))  AS precio_minimo,
            ROUND(MAX(p.precio_persona_clp))  AS precio_maximo,
            ROUND(AVG(p.descuento_pct), 1)    AS descuento_promedio,
            COUNT(DISTINCT h.id)              AS total_hoteles
        FROM precios p
        JOIN hoteles h ON h.id = p.hotel_id
        WHERE p.precio_persona_clp IS NOT NULL
          AND h.destino != ''
        GROUP BY h.destino
        ORDER BY precio_promedio ASC
    """).fetchall()

    # ── Evolución por hotel específico (top 10 más tracked) ───
    hoteles_top = conn.execute("""
        SELECT
            h.id,
            h.nombre,
            h.destino,
            h.estrellas,
            h.rating,
            COUNT(p.id) AS apariciones
        FROM precios p
        JOIN hoteles h ON h.id = p.hotel_id
        WHERE p.precio_persona_clp IS NOT NULL
        AND h.destino != ''
        GROUP BY h.id
        HAVING COUNT(p.id) >= 3
        ORDER BY h.destino, apariciones DESC
        LIMIT 100
    """).fetchall()

    precios_por_hotel = {}
    for hotel in hoteles_top:
        hid = hotel["id"]
        filas = conn.execute("""
            SELECT s.fecha, p.precio_persona_clp, p.precio_original_clp, p.ahorro_clp
            FROM precios p
            JOIN snapshots s ON s.id = p.snapshot_id
            WHERE p.hotel_id = ? AND p.precio_persona_clp IS NOT NULL
            ORDER BY s.fecha
        """, (hid,)).fetchall()
        precios_por_hotel[hid] = {
            "nombre":    hotel["nombre"],
            "destino":   hotel["destino"],
            "estrellas": hotel["estrellas"],
            "rating":    hotel["rating"],
            "precios":   [dict(f) for f in filas]
        }

    conn.close()

    # ── Armar JSON ────────────────────────────────────────────
    data = {
        "generado_en": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "snapshots":        [dict(s) for s in snapshots],
        "destinos":         destinos,
        "evolucion":        [dict(e) for e in evolucion],
        "mejores_bajas":    [dict(b) for b in mejores_bajas],
        "resumen_destinos": [dict(r) for r in resumen_destinos],
        "hoteles_top":      precios_por_hotel,
    }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Exportado: {OUT_PATH}")
    print(f"  Snapshots      : {len(data['snapshots'])}")
    print(f"  Destinos       : {len(data['destinos'])}")
    print(f"  Registros evol.: {len(data['evolucion'])}")
    print(f"  Hoteles top    : {len(data['hoteles_top'])}")


if __name__ == "__main__":
    exportar()
