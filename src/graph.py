"""
graph.py — Estructura de datos común para todas las redes financieras.

Representación: lista de adyacencia (diccionario nodo -> lista de aristas
salientes) más una lista inversa (aristas entrantes) para consultar
predecesores en O(grado). Es la representación sugerida en la guía del
proyecto y la más adecuada para redes dispersas (|E| << |V|^2), que es el
caso de las redes financieras reales: una agencia o cuenta se conecta con
pocas contrapartes en comparación con el total de nodos.

Costo en memoria: O(|V| + |E|).  Recorrer vecinos de u: O(grado(u)).

Soporta:
  * grafos dirigidos y no dirigidos;
  * ponderados y no ponderados (en un grafo no ponderado todo peso vale 1);
  * multigrafos (varias aristas entre el mismo par, p. ej. varias
    transferencias A->B en fechas distintas o dos canales de envío);
  * cierre temporal de nodos y aristas (sucursales en mantenimiento,
    rutas bloqueadas) sin perder la información original.
"""

from __future__ import annotations

import copy
import csv
import io
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# Catálogos y reglas de validación
# ---------------------------------------------------------------------------

TIPOS_NODO = {
    "cuenta", "cliente", "empresa", "agencia", "boveda_central",
    "boveda_regional", "atm", "entidad", "compensacion", "billetera",
    "procesador", "corresponsal", "servidor", "otro",
}

# Atributos numéricos de arista que nunca pueden ser negativos.
NO_NEGATIVOS = {
    "comision_fija", "comision_pct", "bonificacion", "tiempo_min", "tiempo_h",
    "capacidad", "costo", "monto", "limite", "distancia_km",
}
# Atributos que deben estar en [0, 1].
PROBABILIDADES = {"riesgo"}
# Atributos que deben ser estrictamente positivos.
POSITIVOS = {"monto", "limite"}

# Columnas que se leen como texto aunque parezcan números.
COLUMNAS_TEXTO = {"id", "origen", "destino", "fecha", "canal", "modo", "tipo",
                  "nombre", "region", "ciudad", "titular", "actividad"}


class GrafoError(Exception):
    """Error de consistencia en la red (nodo inexistente, valor inválido...)."""


# ---------------------------------------------------------------------------
# Elementos del grafo
# ---------------------------------------------------------------------------

@dataclass
class Nodo:
    id: str
    tipo: str = "otro"
    nombre: str = ""
    lat: float | None = None
    lon: float | None = None
    atributos: dict[str, Any] = field(default_factory=dict)
    activo: bool = True

    def get(self, clave: str, defecto: Any = None) -> Any:
        return self.atributos.get(clave, defecto)

    def a_dict(self) -> dict[str, Any]:
        d = {"id": self.id, "tipo": self.tipo, "nombre": self.nombre,
             "lat": self.lat, "lon": self.lon, "activo": self.activo}
        d.update(self.atributos)
        return d


@dataclass
class Arista:
    id: str
    origen: str
    destino: str
    atributos: dict[str, Any] = field(default_factory=dict)
    activa: bool = True

    def get(self, clave: str, defecto: Any = None) -> Any:
        return self.atributos.get(clave, defecto)

    def __getitem__(self, clave: str) -> Any:
        return self.atributos[clave]

    def otro_extremo(self, nodo: str) -> str:
        return self.destino if nodo == self.origen else self.origen

    def a_dict(self) -> dict[str, Any]:
        d = {"id": self.id, "origen": self.origen, "destino": self.destino,
             "activa": self.activa}
        d.update(self.atributos)
        return d


# ---------------------------------------------------------------------------
# Utilidades de conversión
# ---------------------------------------------------------------------------

def _convertir(valor: Any, columna: str = "") -> Any:
    """Convierte texto de CSV a bool / int / float cuando corresponde."""
    if not isinstance(valor, str):
        return valor
    v = valor.strip()
    if columna in COLUMNAS_TEXTO:
        return v
    if v == "":
        return None
    low = v.lower()
    if low in {"true", "verdadero", "si", "sí"}:
        return True
    if low in {"false", "falso", "no"}:
        return False
    try:
        if v.lstrip("-").isdigit():
            return int(v)
        return float(v)
    except ValueError:
        return v


def _validar_valor(clave: str, valor: Any) -> None:
    if valor is None:
        return
    if clave in NO_NEGATIVOS | PROBABILIDADES | POSITIVOS:
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            raise GrafoError(f"El atributo '{clave}' debe ser numérico (recibido: {valor!r}).")
        if math.isnan(valor) or math.isinf(valor):
            raise GrafoError(f"El atributo '{clave}' no puede ser NaN ni infinito.")
    if clave in NO_NEGATIVOS and valor < 0:
        raise GrafoError(f"El atributo '{clave}' no puede ser negativo ({valor}).")
    if clave in POSITIVOS and valor <= 0:
        raise GrafoError(f"El atributo '{clave}' debe ser mayor que cero ({valor}).")
    if clave in PROBABILIDADES and not 0 <= valor <= 1:
        raise GrafoError(f"El atributo '{clave}' debe estar entre 0 y 1 ({valor}).")


# ---------------------------------------------------------------------------
# Grafo
# ---------------------------------------------------------------------------

class Grafo:
    """Red financiera representada con listas de adyacencia."""

    def __init__(self, nombre: str = "red", dirigido: bool = True,
                 ponderado: bool = True, multiple: bool = False) -> None:
        self.nombre = nombre
        self.dirigido = dirigido
        self.ponderado = ponderado
        self.multiple = multiple
        self.nodos: dict[str, Nodo] = {}
        self._aristas: dict[str, Arista] = {}
        self._ady: dict[str, list[Arista]] = {}   # aristas salientes
        self._inv: dict[str, list[Arista]] = {}   # aristas entrantes
        self._contador = 0

    # ------------------------------------------------------------- nodos
    def agregar_nodo(self, id: str, tipo: str = "otro", nombre: str = "",
                     lat: float | None = None, lon: float | None = None,
                     activo: bool = True, **atributos: Any) -> Nodo:
        id = str(id).strip()
        if not id:
            raise GrafoError("El identificador del nodo no puede estar vacío.")
        if id in self.nodos:
            raise GrafoError(f"El nodo '{id}' ya existe.")
        tipo = (tipo or "otro").strip()
        if tipo not in TIPOS_NODO:
            raise GrafoError(f"Tipo de nodo desconocido '{tipo}'. Válidos: {sorted(TIPOS_NODO)}")
        for coord, nombre_c, lim in ((lat, "lat", 90), (lon, "lon", 180)):
            if coord is not None and not -lim <= float(coord) <= lim:
                raise GrafoError(f"Coordenada {nombre_c}={coord} fuera de rango.")
        for k, v in atributos.items():
            if k in {"oferta", "demanda"} and v is not None and v < 0:
                raise GrafoError(f"'{k}' no puede ser negativa en el nodo '{id}'.")
        nodo = Nodo(id, tipo, nombre or id,
                    None if lat is None else float(lat),
                    None if lon is None else float(lon),
                    dict(atributos), bool(activo))
        self.nodos[id] = nodo
        self._ady[id] = []
        self._inv[id] = []
        return nodo

    def modificar_nodo(self, id: str, **cambios: Any) -> Nodo:
        nodo = self._nodo(id)
        for k, v in cambios.items():
            if k == "tipo":
                if v not in TIPOS_NODO:
                    raise GrafoError(f"Tipo de nodo desconocido '{v}'.")
                nodo.tipo = v
            elif k in {"nombre", "lat", "lon", "activo"}:
                setattr(nodo, k, v)
            else:
                if k in {"oferta", "demanda"} and v is not None and v < 0:
                    raise GrafoError(f"'{k}' no puede ser negativa.")
                nodo.atributos[k] = v
        return nodo

    def eliminar_nodo(self, id: str) -> int:
        """Elimina el nodo y todas sus aristas incidentes. Devuelve cuántas aristas se borraron."""
        self._nodo(id)
        incidentes = {a.id for a in self._ady[id]} | {a.id for a in self._inv[id]}
        for aid in incidentes:
            self.eliminar_arista(aid)
        del self.nodos[id], self._ady[id], self._inv[id]
        return len(incidentes)

    def cerrar_nodo(self, id: str) -> None:
        self._nodo(id).activo = False

    def abrir_nodo(self, id: str) -> None:
        self._nodo(id).activo = True

    def existe_nodo(self, id: str) -> bool:
        return id in self.nodos

    def _nodo(self, id: str) -> Nodo:
        try:
            return self.nodos[id]
        except KeyError:
            raise GrafoError(f"El nodo '{id}' no existe.") from None

    # ----------------------------------------------------------- aristas
    def agregar_arista(self, origen: str, destino: str, id: str | None = None,
                       activa: bool = True, **atributos: Any) -> Arista:
        origen, destino = str(origen).strip(), str(destino).strip()
        if origen not in self.nodos:
            raise GrafoError(f"Nodo de origen inexistente: '{origen}'.")
        if destino not in self.nodos:
            raise GrafoError(f"Nodo de destino inexistente: '{destino}'.")
        if origen == destino:
            raise GrafoError(f"Bucle no permitido en '{origen}' (una entidad no se transfiere a sí misma).")
        for k, v in atributos.items():
            _validar_valor(k, v)

        existentes = self.aristas_entre(origen, destino, incluir_inactivas=True)
        if existentes and not self.multiple:
            raise GrafoError(f"Conexión duplicada {origen}->{destino}: la red no admite aristas paralelas.")
        if existentes and id is None:
            clave = (atributos.get("canal"), atributos.get("fecha"), atributos.get("modo"))
            for a in existentes:
                if (a.get("canal"), a.get("fecha"), a.get("modo")) == clave:
                    raise GrafoError(
                        f"Conexión duplicada no justificada {origen}->{destino}: "
                        "las aristas paralelas deben diferir en id, canal, fecha o modo.")

        if id is None:
            self._contador += 1
            id = f"E{self._contador:05d}"
            while id in self._aristas:
                self._contador += 1
                id = f"E{self._contador:05d}"
        id = str(id)
        if id in self._aristas:
            raise GrafoError(f"Ya existe una arista con id '{id}'.")

        arista = Arista(id, origen, destino, dict(atributos), bool(activa))
        self._aristas[id] = arista
        self._ady[origen].append(arista)
        self._inv[destino].append(arista)
        if not self.dirigido:
            self._ady[destino].append(arista)
            self._inv[origen].append(arista)
        return arista

    def modificar_arista(self, id: str, **cambios: Any) -> Arista:
        a = self.arista(id)
        for k, v in cambios.items():
            if k == "activa":
                a.activa = bool(v)
                continue
            _validar_valor(k, v)
            a.atributos[k] = v
        return a

    def eliminar_arista(self, id: str) -> None:
        a = self.arista(id)
        self._ady[a.origen].remove(a)
        self._inv[a.destino].remove(a)
        if not self.dirigido:
            self._ady[a.destino].remove(a)
            self._inv[a.origen].remove(a)
        del self._aristas[id]

    def cerrar_arista(self, id: str) -> None:
        self.arista(id).activa = False

    def abrir_arista(self, id: str) -> None:
        self.arista(id).activa = True

    def arista(self, id: str) -> Arista:
        try:
            return self._aristas[id]
        except KeyError:
            raise GrafoError(f"La arista '{id}' no existe.") from None

    def aristas_entre(self, u: str, v: str, incluir_inactivas: bool = False) -> list[Arista]:
        if u not in self._ady:
            return []
        res = []
        for a in self._ady[u]:
            if a.otro_extremo(u) == v and (incluir_inactivas or a.activa):
                res.append(a)
        return res

    # --------------------------------------------------------- consultas
    def _usable(self, a: Arista, desde: str, incluir_inactivos: bool) -> bool:
        if incluir_inactivos:
            return True
        return a.activa and self.nodos[a.otro_extremo(desde)].activo and self.nodos[desde].activo

    def vecinos(self, u: str, incluir_inactivos: bool = False) -> list[tuple[str, Arista]]:
        """Sucesores de u como pares (v, arista). Omite elementos cerrados."""
        if not incluir_inactivos and not self.nodos[u].activo:
            return []
        return [(a.otro_extremo(u), a) for a in self._ady[u]
                if self._usable(a, u, incluir_inactivos)]

    def predecesores(self, v: str, incluir_inactivos: bool = False) -> list[tuple[str, Arista]]:
        if not incluir_inactivos and not self.nodos[v].activo:
            return []
        return [(a.otro_extremo(v), a) for a in self._inv[v]
                if self._usable(a, v, incluir_inactivos)]

    def aristas(self, incluir_inactivas: bool = True) -> list[Arista]:
        if incluir_inactivas:
            return list(self._aristas.values())
        return [a for a in self._aristas.values()
                if a.activa and self.nodos[a.origen].activo and self.nodos[a.destino].activo]

    def ids_nodos(self, solo_activos: bool = False, tipo: str | Iterable[str] | None = None) -> list[str]:
        tipos = {tipo} if isinstance(tipo, str) else (set(tipo) if tipo else None)
        return [n.id for n in self.nodos.values()
                if (not solo_activos or n.activo) and (tipos is None or n.tipo in tipos)]

    def grado_salida(self, u: str) -> int:
        return len(self.vecinos(u))

    def grado_entrada(self, v: str) -> int:
        return len(self.predecesores(v))

    def peso(self, arista: Arista, atributo: str, defecto: float = 1.0) -> float:
        """Peso de una arista según un atributo. En grafos no ponderados vale 1."""
        if not self.ponderado:
            return 1.0
        v = arista.atributos.get(atributo, defecto)
        return float(defecto if v is None else v)

    @property
    def num_nodos(self) -> int:
        return len(self.nodos)

    @property
    def num_aristas(self) -> int:
        return len(self._aristas)

    def densidad(self) -> float:
        n = self.num_nodos
        if n < 2:
            return 0.0
        maximo = n * (n - 1) if self.dirigido else n * (n - 1) / 2
        return self.num_aristas / maximo

    def lista_adyacencia(self, atributo: str | None = None) -> dict[str, list[tuple[str, float]]]:
        """Vista simple {nodo: [(vecino, peso), ...]} como en la guía del proyecto."""
        return {u: [(v, self.peso(a, atributo) if atributo else 1.0) for v, a in self.vecinos(u)]
                for u in self.nodos}

    def estadisticas(self) -> dict[str, Any]:
        tipos: dict[str, int] = {}
        for n in self.nodos.values():
            tipos[n.tipo] = tipos.get(n.tipo, 0) + 1
        cerrados_n = sum(not n.activo for n in self.nodos.values())
        cerradas_a = sum(not a.activa for a in self._aristas.values())
        return {
            "nombre": self.nombre, "dirigido": self.dirigido, "ponderado": self.ponderado,
            "multigrafo": self.multiple, "nodos": self.num_nodos, "aristas": self.num_aristas,
            "densidad": round(self.densidad(), 5), "nodos_cerrados": cerrados_n,
            "aristas_cerradas": cerradas_a, "tipos_nodo": tipos,
        }

    def validar(self) -> list[dict[str, str]]:
        """Revisión de consistencia. Devuelve una lista de hallazgos (vacía = red consistente)."""
        hallazgos: list[dict[str, str]] = []
        for a in self._aristas.values():
            for extremo in (a.origen, a.destino):
                if extremo not in self.nodos:
                    hallazgos.append({"nivel": "error", "elemento": a.id,
                                      "detalle": f"Referencia a nodo inexistente '{extremo}'."})
            for k, v in a.atributos.items():
                try:
                    _validar_valor(k, v)
                except GrafoError as e:
                    hallazgos.append({"nivel": "error", "elemento": a.id, "detalle": str(e)})
        if not self.multiple:
            vistos: dict[tuple[str, str], str] = {}
            for a in self._aristas.values():
                par = (a.origen, a.destino) if self.dirigido else tuple(sorted((a.origen, a.destino)))
                if par in vistos:
                    hallazgos.append({"nivel": "error", "elemento": a.id,
                                      "detalle": f"Duplicada con {vistos[par]}."})
                vistos[par] = a.id
        for n in self.nodos.values():
            if not self._ady[n.id] and not self._inv[n.id]:
                hallazgos.append({"nivel": "advertencia", "elemento": n.id,
                                  "detalle": "Nodo aislado (sin conexiones)."})
            if n.lat is None or n.lon is None:
                hallazgos.append({"nivel": "advertencia", "elemento": n.id,
                                  "detalle": "Sin coordenadas: se ubicará automáticamente en el mapa."})
        return hallazgos

    # ------------------------------------------------------------- copia
    def copia(self) -> "Grafo":
        return copy.deepcopy(self)

    # ------------------------------------------------------ persistencia
    def a_dict(self) -> dict[str, Any]:
        return {
            "nombre": self.nombre, "dirigido": self.dirigido,
            "ponderado": self.ponderado, "multiple": self.multiple,
            "nodos": [n.a_dict() for n in self.nodos.values()],
            "aristas": [a.a_dict() for a in self._aristas.values()],
        }

    @classmethod
    def desde_dict(cls, datos: dict[str, Any]) -> "Grafo":
        g = cls(datos.get("nombre", "red"), datos.get("dirigido", True),
                datos.get("ponderado", True), datos.get("multiple", False))
        for n in datos.get("nodos", []):
            n = dict(n)
            g.agregar_nodo(n.pop("id"), n.pop("tipo", "otro"), n.pop("nombre", ""),
                           n.pop("lat", None), n.pop("lon", None), n.pop("activo", True), **n)
        for a in datos.get("aristas", []):
            a = dict(a)
            g.agregar_arista(a.pop("origen"), a.pop("destino"), a.pop("id", None),
                             a.pop("activa", True), **a)
        return g

    def guardar_json(self, ruta: str | Path) -> None:
        Path(ruta).write_text(json.dumps(self.a_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def cargar_json(cls, ruta_o_texto: str | Path) -> "Grafo":
        p = Path(ruta_o_texto) if not str(ruta_o_texto).lstrip().startswith("{") else None
        texto = p.read_text(encoding="utf-8") if p else str(ruta_o_texto)
        return cls.desde_dict(json.loads(texto))

    def guardar_csv(self, ruta_nodos: str | Path, ruta_aristas: str | Path) -> None:
        for ruta, filas in ((ruta_nodos, [n.a_dict() for n in self.nodos.values()]),
                            (ruta_aristas, [a.a_dict() for a in self._aristas.values()])):
            columnas: list[str] = []
            for f in filas:
                for k in f:
                    if k not in columnas:
                        columnas.append(k)
            with open(ruta, "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=columnas)
                w.writeheader()
                w.writerows(filas)

    @classmethod
    def desde_csv(cls, aristas: str | Path | io.StringIO, nodos: str | Path | io.StringIO | None = None,
                  nombre: str = "red", dirigido: bool = True, ponderado: bool = True,
                  multiple: bool = False, estricto: bool = True) -> tuple["Grafo", list[str]]:
        """
        Carga una red desde CSV.  `aristas` necesita las columnas origen,destino
        (el resto se toma como atributos).  Si no se pasa archivo de nodos, los
        nodos se crean automáticamente (formato mínimo de la guía).
        Devuelve (grafo, errores).  Con estricto=True el primer error se lanza.
        """
        g = cls(nombre, dirigido, ponderado, multiple)
        errores: list[str] = []

        def leer(fuente):
            if isinstance(fuente, (str, Path)):
                with open(fuente, newline="", encoding="utf-8-sig") as fh:
                    return list(csv.DictReader(fh))
            return list(csv.DictReader(fuente))

        if nodos is not None:
            for i, fila in enumerate(leer(nodos), start=2):
                f = {k.strip(): _convertir(v, k.strip()) for k, v in fila.items() if k}
                try:
                    g.agregar_nodo(f.pop("id"), f.pop("tipo", "otro") or "otro", f.pop("nombre", "") or "",
                                   f.pop("lat", None), f.pop("lon", None),
                                   f.pop("activo", True) if f.get("activo") is not None else True,
                                   **{k: v for k, v in f.items() if k != "activo"})
                except (GrafoError, KeyError, TypeError, ValueError) as e:
                    msg = f"nodos, fila {i}: {e}"
                    if estricto:
                        raise GrafoError(msg) from e
                    errores.append(msg)

        for i, fila in enumerate(leer(aristas), start=2):
            f = {k.strip(): _convertir(v, k.strip()) for k, v in fila.items() if k}
            try:
                o, d = f.pop("origen"), f.pop("destino")
                if nodos is None:
                    for x in (o, d):
                        if x and x not in g.nodos:
                            g.agregar_nodo(x)
                activa = f.pop("activa", True)
                g.agregar_arista(o, d, f.pop("id", None), True if activa is None else activa,
                                 **{k: v for k, v in f.items() if v is not None})
            except (GrafoError, KeyError, TypeError) as e:
                msg = f"aristas, fila {i}: {e}"
                if estricto:
                    raise GrafoError(msg) from e
                errores.append(msg)
        return g, errores

    def __repr__(self) -> str:
        tipo = "dirigido" if self.dirigido else "no dirigido"
        return f"<Grafo '{self.nombre}' {tipo}: {self.num_nodos} nodos, {self.num_aristas} aristas>"
