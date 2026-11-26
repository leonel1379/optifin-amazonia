"""
Flujo en redes: Edmonds-Karp, Dinic, corte mínimo y flujo máximo de costo
mínimo (caminos sucesivos más baratos).

Se usa una representación de red residual con arreglos paralelos: cada
arista e tiene su reversa en e ^ 1, lo que permite actualizar el flujo
residual en O(1).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from ..graph import Grafo

EPS = 1e-9
SUPER_FUENTE = "__FUENTE__"
SUPER_SUMIDERO = "__SUMIDERO__"


class RedFlujo:
    def __init__(self, nombres: list[str] | None = None) -> None:
        self.nombres: list[str] = []
        self.idx: dict[str, int] = {}
        self.ady: list[list[int]] = []
        self.hacia: list[int] = []
        self.cap: list[float] = []
        self.flujo: list[float] = []
        self.costo: list[float] = []
        self.ref: list[str | None] = []
        for n in nombres or []:
            self.nodo(n)

    def nodo(self, nombre: str) -> int:
        if nombre not in self.idx:
            self.idx[nombre] = len(self.nombres)
            self.nombres.append(nombre)
            self.ady.append([])
        return self.idx[nombre]

    def agregar(self, u: str, v: str, capacidad: float, costo: float = 0.0,
                ref: str | None = None) -> int:
        a, b = self.nodo(u), self.nodo(v)
        e = len(self.hacia)
        for desde, hasta, c, k, r in ((a, b, capacidad, costo, ref), (b, a, 0.0, -costo, None)):
            self.ady[desde].append(len(self.hacia))
            self.hacia.append(hasta)
            self.cap.append(float(c))
            self.flujo.append(0.0)
            self.costo.append(float(k))
            self.ref.append(r)
        return e

    def residual(self, e: int) -> float:
        return self.cap[e] - self.flujo[e]

    def reiniciar(self) -> None:
        self.flujo = [0.0] * len(self.flujo)

    def origen_de(self, e: int) -> int:
        return self.hacia[e ^ 1]

    @property
    def n(self) -> int:
        return len(self.nombres)

    @property
    def m(self) -> int:
        return len(self.hacia) // 2

    def flujo_por_referencia(self) -> dict[str, float]:
        return {self.ref[e]: self.flujo[e] for e in range(0, len(self.hacia), 2) if self.ref[e]}


@dataclass
class ResultadoFlujo:
    valor: float
    costo: float = 0.0
    estadisticas: dict[str, int] = field(default_factory=dict)


# ------------------------------------------------------------ Edmonds-Karp
def edmonds_karp(red: RedFlujo, s: str, t: str) -> ResultadoFlujo:
    """
    Ford-Fulkerson con caminos de aumento por BFS (el de menos aristas).
    Complejidad: O(V · E^2).  Garantiza terminación también con capacidades reales.
    """
    S, T = red.idx[s], red.idx[t]
    total = 0.0
    aumentos = 0
    while True:
        padre = [-1] * red.n
        padre[S] = -2
        cola = deque([S])
        while cola and padre[T] == -1:
            u = cola.popleft()
            for e in red.ady[u]:
                v = red.hacia[e]
                if padre[v] == -1 and red.cap[e] - red.flujo[e] > EPS:
                    padre[v] = e
                    cola.append(v)
        if padre[T] == -1:
            break
        f = float("inf")
        v = T
        while v != S:
            e = padre[v]
            f = min(f, red.cap[e] - red.flujo[e])
            v = red.hacia[e ^ 1]
        v = T
        while v != S:
            e = padre[v]
            red.flujo[e] += f
            red.flujo[e ^ 1] -= f
            v = red.hacia[e ^ 1]
        total += f
        aumentos += 1
    return ResultadoFlujo(total, 0.0, {"caminos_aumento": aumentos})


# ------------------------------------------------------------------- Dinic
def dinic(red: RedFlujo, s: str, t: str) -> ResultadoFlujo:
    """
    Dinic: grafo de niveles por BFS + flujo bloqueante por DFS (iterativa).
    Complejidad: O(V^2 · E); en la práctica mucho más rápido que Edmonds-Karp.
    """
    S, T = red.idx[s], red.idx[t]
    total = 0.0
    fases = aumentos = 0
    while True:
        nivel = [-1] * red.n
        nivel[S] = 0
        cola = deque([S])
        while cola:
            u = cola.popleft()
            for e in red.ady[u]:
                v = red.hacia[e]
                if nivel[v] < 0 and red.cap[e] - red.flujo[e] > EPS:
                    nivel[v] = nivel[u] + 1
                    cola.append(v)
        if nivel[T] < 0:
            break
        fases += 1
        it = [0] * red.n
        while True:
            camino: list[int] = []
            u = S
            while u != T:
                avanzo = False
                lista = red.ady[u]
                while it[u] < len(lista):
                    e = lista[it[u]]
                    v = red.hacia[e]
                    if red.cap[e] - red.flujo[e] > EPS and nivel[v] == nivel[u] + 1:
                        camino.append(e)
                        u = v
                        avanzo = True
                        break
                    it[u] += 1
                if not avanzo:
                    if u == S:
                        break
                    nivel[u] = -1           # callejón sin salida en esta fase
                    e = camino.pop()
                    u = red.hacia[e ^ 1]
                    it[u] += 1
            if u != T:
                break
            f = min(red.cap[e] - red.flujo[e] for e in camino)
            for e in camino:
                red.flujo[e] += f
                red.flujo[e ^ 1] -= f
            total += f
            aumentos += 1
    return ResultadoFlujo(total, 0.0, {"fases": fases, "caminos_aumento": aumentos})


# ------------------------------------------------------------ corte mínimo
def corte_minimo(red: RedFlujo, s: str) -> tuple[set[str], list[int]]:
    """
    Tras calcular el flujo máximo, los nodos alcanzables desde s en la red
    residual forman el lado S del corte mínimo (teorema flujo máximo - corte
    mínimo).  Las aristas originales S -> T saturadas son los cuellos de botella.
    """
    S = red.idx[s]
    vis = {S}
    cola = deque([S])
    while cola:
        u = cola.popleft()
        for e in red.ady[u]:
            v = red.hacia[e]
            if v not in vis and red.cap[e] - red.flujo[e] > EPS:
                vis.add(v)
                cola.append(v)
    aristas = [e for e in range(0, len(red.hacia), 2)
               if red.hacia[e ^ 1] in vis and red.hacia[e] not in vis and red.cap[e] > EPS]
    return {red.nombres[i] for i in vis}, aristas


# ----------------------------------------- flujo máximo de costo mínimo
def flujo_costo_minimo(red: RedFlujo, s: str, t: str,
                       limite_flujo: float | None = None) -> ResultadoFlujo:
    """
    Caminos sucesivos más baratos: en cada iteración se busca, con
    Bellman-Ford en cola (SPFA), el camino de aumento de menor costo en la
    red residual (las aristas reversas tienen costo negativo) y se satura.
    Resultado: el flujo máximo posible con el menor costo operativo total.
    Complejidad: O(F · V · E) en el peor caso, con F = número de aumentos.
    """
    S, T = red.idx[s], red.idx[t]
    total = costo_total = 0.0
    aumentos = 0
    while limite_flujo is None or total < limite_flujo - EPS:
        dist = [float("inf")] * red.n
        en_cola = [False] * red.n
        padre = [-1] * red.n
        veces = [0] * red.n
        dist[S] = 0.0
        cola = deque([S])
        en_cola[S] = True
        while cola:
            u = cola.popleft()
            en_cola[u] = False
            veces[u] += 1
            if veces[u] > red.n + 1:
                raise RuntimeError("Ciclo de costo negativo en la red residual: el flujo de costo mínimo no está definido.")
            for e in red.ady[u]:
                if red.cap[e] - red.flujo[e] > EPS:
                    v = red.hacia[e]
                    nd = dist[u] + red.costo[e]
                    if nd < dist[v] - EPS:
                        dist[v] = nd
                        padre[v] = e
                        if not en_cola[v]:
                            en_cola[v] = True
                            cola.append(v)
        if dist[T] == float("inf"):
            break
        f = float("inf") if limite_flujo is None else limite_flujo - total
        v = T
        while v != S:
            e = padre[v]
            f = min(f, red.cap[e] - red.flujo[e])
            v = red.hacia[e ^ 1]
        v = T
        while v != S:
            e = padre[v]
            red.flujo[e] += f
            red.flujo[e ^ 1] -= f
            v = red.hacia[e ^ 1]
        total += f
        costo_total += f * dist[T]
        aumentos += 1
    return ResultadoFlujo(total, costo_total, {"caminos_aumento": aumentos})


# ------------------------------------------------------- desde un Grafo
def red_desde_grafo(g: Grafo, atributo_capacidad: str = "capacidad",
                    atributo_costo: str | None = "costo",
                    ofertas: dict[str, float] | None = None,
                    demandas: dict[str, float] | None = None) -> RedFlujo:
    """
    Construye la red residual a partir de un Grafo.  Con varias fuentes y
    sumideros se agrega una superfuente (capacidad = oferta de cada bóveda)
    y un supersumidero (capacidad = demanda de cada agencia), reduciendo el
    problema multi-origen/multi-destino a un flujo s-t clásico.
    """
    red = RedFlujo(g.ids_nodos(solo_activos=True))
    for a in g.aristas(incluir_inactivas=False):
        cap = float(a.get(atributo_capacidad, 0) or 0)
        costo = float(a.get(atributo_costo, 0) or 0) if atributo_costo else 0.0
        red.agregar(a.origen, a.destino, cap, costo, a.id)
        if not g.dirigido:
            red.agregar(a.destino, a.origen, cap, costo, a.id + "~")
    if ofertas is not None:
        for nodo, oferta in ofertas.items():
            if nodo in red.idx and oferta > 0:
                red.agregar(SUPER_FUENTE, nodo, oferta, 0.0, f"OFERTA:{nodo}")
        red.nodo(SUPER_FUENTE)
    if demandas is not None:
        for nodo, demanda in demandas.items():
            if nodo in red.idx and demanda > 0:
                red.agregar(nodo, SUPER_SUMIDERO, demanda, 0.0, f"DEMANDA:{nodo}")
        red.nodo(SUPER_SUMIDERO)
    return red
