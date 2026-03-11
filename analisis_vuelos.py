"""
analisis_vuelos.py
==================
Carga vuelos.json o vuelos.csv y genera un análisis comparativo
de aerolíneas: precio, duración, escalas y conveniencia general.

Uso:
    python analisis_vuelos.py
"""

import json
import csv
from dataclasses import dataclass
from typing import Optional
from pathlib import Path


# ──────────────────────────────────────────────
# Carga de datos
# ──────────────────────────────────────────────

def cargar_vuelos_json(ruta: str = "vuelos.json") -> list[dict]:
    if not Path(ruta).exists():
        print(f"❌ No se encontró {ruta}")
        return []
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def cargar_vuelos_csv(ruta: str = "vuelos.csv") -> list[dict]:
    if not Path(ruta).exists():
        print(f"❌ No se encontró {ruta}")
        return []
    with open(ruta, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ──────────────────────────────────────────────
# Puntuación de conveniencia
# ──────────────────────────────────────────────

def puntaje_conveniencia(vuelo: dict) -> float:
    """
    Calcula un puntaje 0-100 donde mayor = más conveniente.
    Pesos ajustables según tus prioridades.
    """
    score = 100.0

    # ── Precio (penaliza si es caro) ──
    precio = vuelo.get("precio_total_clp")
    if precio:
        try:
            precio = int(precio)
            # Se normaliza después; aquí solo marcamos presencia
            vuelo["_precio_num"] = precio
        except (ValueError, TypeError):
            pass

    # ── Escalas ──
    escalas = vuelo.get("escalas", 0)
    try:
        escalas = int(escalas)
    except (ValueError, TypeError):
        escalas = 0
    score -= escalas * 15  # -15 pts por escala

    # ── Equipaje bodega ──
    bodega = vuelo.get("equipaje_bodega", False)
    if str(bodega).lower() in ("true", "1", "yes"):
        score += 10

    # ── Equipaje cabina ──
    cabina = vuelo.get("equipaje_cabina", False)
    if str(cabina).lower() in ("true", "1", "yes"):
        score += 5

    # ── Permite cambios ──
    cambios = vuelo.get("permite_cambios", False)
    if str(cambios).lower() in ("true", "1", "yes"):
        score += 8

    # ── Reembolso ──
    reembolso = vuelo.get("permite_reembolso", False)
    if str(reembolso).lower() in ("true", "1", "yes"):
        score += 7

    return max(0.0, min(100.0, score))


def normalizar_precios(vuelos: list[dict]) -> list[dict]:
    """Agrega penalización/bonificación relativa de precio al score."""
    precios = [v.get("_precio_num", 0) for v in vuelos if v.get("_precio_num")]
    if not precios:
        return vuelos

    precio_min = min(precios)
    precio_max = max(precios)
    rango = precio_max - precio_min or 1

    for v in vuelos:
        p = v.get("_precio_num", 0)
        if p:
            # -20 pts si es el más caro, 0 si es el más barato
            penalizacion = ((p - precio_min) / rango) * 20
            v["score_conveniencia"] = round(v.get("score_conveniencia", 100) - penalizacion, 1)

    return vuelos


# ──────────────────────────────────────────────
# Reporte
# ──────────────────────────────────────────────

def imprimir_tabla(vuelos: list[dict]):
    if not vuelos:
        print("No hay vuelos para mostrar.")
        return

    ancho = 110
    print("\n" + "=" * ancho)
    print(f"{'RANKING':^6} {'AEROLÍNEA':^12} {'SALIDA':^7} {'LLEGADA':^7} "
          f"{'DURACIÓN':^10} {'ESCALAS':^8} {'PRECIO CLP':^12} "
          f"{'BODEGA':^8} {'CAMBIOS':^8} {'SCORE':^7}")
    print("=" * ancho)

    for i, v in enumerate(vuelos, 1):
        precio_str = f"${int(v.get('_precio_num', 0)):,}" if v.get('_precio_num') else "N/D"
        bodega = "✓" if str(v.get("equipaje_bodega", "")).lower() in ("true","1","yes") else "✗"
        cambios = "✓" if str(v.get("permite_cambios", "")).lower() in ("true","1","yes") else "✗"
        score = v.get("score_conveniencia", "?")

        print(
            f"  {i:>3}.  "
            f"{v.get('aerolinea','?'):^12} "
            f"{v.get('hora_salida','?'):^7} "
            f"{v.get('hora_llegada','?'):^7} "
            f"{v.get('duracion_total','?'):^10} "
            f"{v.get('escalas','?'):^8} "
            f"{precio_str:^12} "
            f"{bodega:^8} "
            f"{cambios:^8} "
            f"{str(score):^7}"
        )

    print("=" * ancho)
    print("Score: 0=peor, 100=mejor  |  Bodega/Cambios: ✓=incluido, ✗=no incluido\n")


def resumen_por_aerolinea(vuelos: list[dict]):
    desde_por_aerolinea: dict[str, list[int]] = {}
    scores_por_aerolinea: dict[str, list[float]] = {}

    for v in vuelos:
        al = v.get("aerolinea", "Desconocida")
        precio = v.get("_precio_num")
        score = v.get("score_conveniencia")

        if precio:
            desde_por_aerolinea.setdefault(al, []).append(int(precio))
        if score:
            scores_por_aerolinea.setdefault(al, []).append(float(score))

    print("📊 RESUMEN POR AEROLÍNEA")
    print("-" * 55)
    for al in sorted(desde_por_aerolinea):
        precios = desde_por_aerolinea[al]
        scores = scores_por_aerolinea.get(al, [0])
        print(
            f"  {al:15}  "
            f"Desde: ${min(precios):>10,} CLP  |  "
            f"Score prom: {sum(scores)/len(scores):.1f}"
        )
    print()


def guardar_reporte_csv(vuelos: list[dict], ruta: str = "reporte_comparativo.csv"):
    if not vuelos:
        return
    campos = [
        "score_conveniencia", "aerolinea", "hora_salida", "hora_llegada",
        "duracion_total", "escalas", "precio_total_clp", "_precio_num",
        "equipaje_bodega", "equipaje_cabina", "permite_cambios",
        "permite_reembolso", "tarifa_tipo", "fecha_salida", "url_fuente"
    ]
    campos_disponibles = [c for c in campos if c in vuelos[0]]

    with open(ruta, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=campos_disponibles, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(vuelos)
    print(f"💾 Reporte guardado en: {ruta}")


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def main():
    # Intentar cargar desde JSON primero, luego CSV
    vuelos = cargar_vuelos_json("vuelos.json")
    if not vuelos:
        vuelos = cargar_vuelos_csv("vuelos.csv")
    if not vuelos:
        print("⚠️  No hay datos. Ejecuta primero scraper_vuelos.py")
        return

    print(f"✅ {len(vuelos)} vuelos cargados.")

    # Calcular scores
    for v in vuelos:
        v["score_conveniencia"] = puntaje_conveniencia(v)

    # Normalizar por precio relativo
    vuelos = normalizar_precios(vuelos)

    # Ordenar por score descendente
    vuelos.sort(key=lambda v: v.get("score_conveniencia", 0), reverse=True)

    # Mostrar resultados
    imprimir_tabla(vuelos)
    resumen_por_aerolinea(vuelos)
    guardar_reporte_csv(vuelos)


if __name__ == "__main__":
    main()
