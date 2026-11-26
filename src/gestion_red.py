"""
Módulo 1 — Gestión y modelamiento de redes financieras.

Carga las redes del proyecto desde data/, importa archivos externos
(CSV, JSON o TXT), ofrece operaciones de alta/baja/modificación con
mensajes claros y reporta la consistencia de los datos.
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .graph import Grafo, GrafoError
from .utils import DATA_DIR

# nombre -> (archivo de nodos, archivo de aristas, opciones del grafo, descripción)
REDES_PROYECTO: dict[str, tuple[str, str, dict[str, bool], str]] = {
    "enrutamiento": ("nodos_enrutamiento.csv", "red_enrutamiento.csv",
                     {"dirigido": True, "ponderado": True, "multiple": True},
                     "Agencias, entidades, billeteras, tarjetas y cajeros con comisiones, tiempos, riesgos y límites."),
    "liquidez": ("nodos_liquidez.csv", "distribucion_liquidez.csv",
                 {"dirigido": True, "ponderado": True, "multiple": True},
                 "Bóvedas y agencias con oferta/demanda de efectivo y rutas terrestres, aéreas y fluviales."),
    "transacciones": ("cuentas.csv", "transacciones.csv",
                      {"dirigido": True, "ponderado": True, "multiple": True},
                      "Cuentas y transferencias (sep–oct 2026) con patrones sospechosos plantados."),
}


def cargar_red(nombre: str, carpeta: Path | None = None) -> Grafo:
    """Carga una de las redes del proyecto (ver REDES_PROYECTO)."""
    if nombre == "ejemplo":
        return Grafo.cargar_json((carpeta or DATA_DIR) / "red_ejemplo.json")
    try:
        nodos, aristas, opciones, _ = REDES_PROYECTO[nombre]
    except KeyError:
        raise GrafoError(f"Red desconocida '{nombre}'. Opciones: {list(REDES_PROYECTO) + ['ejemplo']}") from None
    carpeta = carpeta or DATA_DIR
    g, _ = Grafo.desde_csv(carpeta / aristas, carpeta / nodos, nombre=nombre, estricto=True, **opciones)
    return g


def _txt_a_csv(texto: str, atributo_peso: str) -> str:
    """TXT: una conexión por línea `origen destino [peso]`; '#' inicia comentario."""
    filas = ["origen,destino," + atributo_peso]
    for linea in texto.splitlines():
        linea = linea.split("#", 1)[0].strip()
        if not linea:
            continue
        partes = linea.replace(",", " ").replace(";", " ").split()
        if len(partes) < 2:
            filas.append(f"{partes[0] if partes else ''},,")
            continue
        peso = partes[2] if len(partes) > 2 else ""
        filas.append(f"{partes[0]},{partes[1]},{peso}")
    return "\n".join(filas)


def importar(contenido: str | bytes, formato: str, contenido_nodos: str | bytes | None = None,
             nombre: str = "importada", dirigido: bool = True, ponderado: bool = True,
             multiple: bool = False, atributo_peso: str = "comision") -> tuple[Grafo | None, list[str]]:
    """
    Importa una red desde texto CSV / JSON / TXT.  No lanza excepciones:
    devuelve (grafo o None, lista de errores encontrados).
    """
    def texto(x):
        return x.decode("utf-8-sig") if isinstance(x, bytes) else x
    formato = formato.lower().lstrip(".")
    try:
        if formato == "json":
            datos = json.loads(texto(contenido))
            datos.setdefault("nombre", nombre)
            return Grafo.desde_dict(datos), []
        if formato == "txt":
            contenido = _txt_a_csv(texto(contenido), atributo_peso)
            formato = "csv"
        if formato == "csv":
            nodos_io = io.StringIO(texto(contenido_nodos)) if contenido_nodos else None
            g, errores = Grafo.desde_csv(io.StringIO(texto(contenido)), nodos_io, nombre=nombre,
                                         dirigido=dirigido, ponderado=ponderado,
                                         multiple=multiple, estricto=False)
            return g, errores
        return None, [f"Formato no soportado: {formato}. Use CSV, JSON o TXT."]
    except (GrafoError, ValueError, KeyError, TypeError) as e:
        return None, [f"No se pudo importar: {e}"]


@dataclass
class Resultado:
    ok: bool
    mensaje: str
    datos: Any = None


@dataclass
class GestorRedes:
    """Administra las redes cargadas en la sesión y encapsula las operaciones del Módulo 1."""
    redes: dict[str, Grafo] = field(default_factory=dict)

    def cargar_todas(self) -> "GestorRedes":
        for nombre in list(REDES_PROYECTO) + ["ejemplo"]:
            self.redes[nombre] = cargar_red(nombre)
        return self

    def __getitem__(self, nombre: str) -> Grafo:
        return self.redes[nombre]

    def registrar(self, g: Grafo, nombre: str | None = None) -> None:
        self.redes[nombre or g.nombre] = g

    def restaurar(self, nombre: str) -> Resultado:
        try:
            self.redes[nombre] = cargar_red(nombre)
            return Resultado(True, f"Red '{nombre}' restaurada desde data/.")
        except GrafoError as e:
            return Resultado(False, str(e))

    # ---- operaciones con mensajes amigables (las usa la interfaz) -------
    def _op(self, funcion, exito: str) -> Resultado:
        try:
            r = funcion()
            return Resultado(True, exito, r)
        except (GrafoError, ValueError, TypeError) as e:
            return Resultado(False, str(e))

    def agregar_nodo(self, red: str, id: str, tipo: str, **kw) -> Resultado:
        return self._op(lambda: self.redes[red].agregar_nodo(id, tipo, **kw), f"Nodo '{id}' creado.")

    def modificar_nodo(self, red: str, id: str, **cambios) -> Resultado:
        return self._op(lambda: self.redes[red].modificar_nodo(id, **cambios), f"Nodo '{id}' actualizado.")

    def eliminar_nodo(self, red: str, id: str) -> Resultado:
        return self._op(lambda: self.redes[red].eliminar_nodo(id),
                        f"Nodo '{id}' eliminado junto con sus conexiones.")

    def agregar_arista(self, red: str, origen: str, destino: str, **kw) -> Resultado:
        return self._op(lambda: self.redes[red].agregar_arista(origen, destino, **kw),
                        f"Conexión {origen} → {destino} creada.")

    def modificar_arista(self, red: str, id: str, **cambios) -> Resultado:
        return self._op(lambda: self.redes[red].modificar_arista(id, **cambios), f"Conexión '{id}' actualizada.")

    def eliminar_arista(self, red: str, id: str) -> Resultado:
        return self._op(lambda: self.redes[red].eliminar_arista(id), f"Conexión '{id}' eliminada.")

    def resumen(self) -> list[dict[str, Any]]:
        filas = []
        for nombre, g in self.redes.items():
            e = g.estadisticas()
            filas.append({"red": nombre, "nodos": e["nodos"], "aristas": e["aristas"],
                          "dirigida": e["dirigido"], "ponderada": e["ponderado"],
                          "multigrafo": e["multigrafo"], "densidad": e["densidad"],
                          "cerrados": e["nodos_cerrados"] + e["aristas_cerradas"]})
        return filas


def tabla_nodos(g: Grafo) -> list[dict[str, Any]]:
    return [n.a_dict() for n in g.nodos.values()]


def tabla_aristas(g: Grafo) -> list[dict[str, Any]]:
    return [a.a_dict() for a in g.aristas()]
