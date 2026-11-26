"""Utilidades compartidas: rutas, medición de tiempo/memoria, formato y exportación de reportes."""

from __future__ import annotations

import csv
import json
import time
import tracemalloc
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

RAIZ = Path(__file__).resolve().parents[1]
DATA_DIR = RAIZ / "data"
REPORTS_DIR = RAIZ / "reports"


def medir(funcion: Callable[[], Any], repeticiones: int = 1, memoria: bool = False) -> tuple[Any, float, float]:
    """
    Ejecuta `funcion` y devuelve (resultado, tiempo_ms, memoria_pico_kb).
    Con varias repeticiones se informa el menor tiempo (menos ruido del SO).
    """
    mejor = float("inf")
    resultado = None
    for _ in range(max(1, repeticiones)):
        t0 = time.perf_counter()
        resultado = funcion()
        mejor = min(mejor, (time.perf_counter() - t0) * 1000)
    pico_kb = 0.0
    if memoria:
        tracemalloc.start()
        funcion()
        _, pico = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        pico_kb = pico / 1024
    return resultado, mejor, pico_kb


def soles(valor: float, decimales: int = 2) -> str:
    s = f"{valor:,.{decimales}f}"
    return "S/ " + s.replace(",", "X").replace(".", ",").replace("X", " ")


def miles_soles(valor: float) -> str:
    """Formato para montos expresados en miles de soles (Módulo 4)."""
    return soles(valor * 1000, 0)


def tabla_texto(filas: list[dict[str, Any]], columnas: list[str] | None = None, max_filas: int = 40) -> str:
    """Tabla en texto plano con bordes, para el modo terminal."""
    if not filas:
        return "(sin resultados)"
    columnas = columnas or list(filas[0].keys())
    datos = [[_fmt(f.get(c, "")) for c in columnas] for f in filas[:max_filas]]
    anchos = [max(len(str(c)), *(len(r[i]) for r in datos)) for i, c in enumerate(columnas)]
    linea = "+" + "+".join("-" * (w + 2) for w in anchos) + "+"
    def fila(valores): return "| " + " | ".join(v.ljust(w) for v, w in zip(valores, anchos)) + " |"
    salida = [linea, fila([str(c) for c in columnas]), linea, *[fila(r) for r in datos], linea]
    if len(filas) > max_filas:
        salida.append(f"... {len(filas) - max_filas} filas más")
    return "\n".join(salida)


def _fmt(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:,.4f}".rstrip("0").rstrip(".") if abs(v) < 1000 else f"{v:,.2f}"
    if isinstance(v, (list, tuple)):
        return " → ".join(map(str, v)) if len(v) < 12 else f"[{len(v)} elementos]"
    return str(v)


def exportar_csv(filas: list[dict[str, Any]], nombre: str, carpeta: Path | None = None) -> Path:
    carpeta = carpeta or REPORTS_DIR
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / nombre
    columnas: list[str] = []
    for f in filas:
        for k in f:
            if k not in columnas:
                columnas.append(k)
    with open(ruta, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=columnas)
        w.writeheader()
        for f in filas:
            w.writerow({k: _fmt(v) if isinstance(v, (list, tuple)) else v for k, v in f.items()})
    return ruta


def exportar_json(datos: Any, nombre: str, carpeta: Path | None = None) -> Path:
    carpeta = carpeta or REPORTS_DIR
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / nombre
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return ruta


def markdown_tabla(filas: list[dict[str, Any]], columnas: list[str] | None = None) -> str:
    if not filas:
        return "_Sin resultados._\n"
    columnas = columnas or list(filas[0].keys())
    cab = "| " + " | ".join(columnas) + " |\n|" + "|".join("---" for _ in columnas) + "|\n"
    cuerpo = "".join("| " + " | ".join(_fmt(f.get(c, "")) for c in columnas) + " |\n" for f in filas)
    return cab + cuerpo


def marca_tiempo() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def ruta_texto(nodos: Iterable[str]) -> str:
    return " → ".join(nodos)
