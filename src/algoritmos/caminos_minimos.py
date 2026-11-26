"""
Algoritmos de rutas más cortas: Dijkstra, Bellman-Ford, Floyd-Warshall,
k rutas más cortas de Yen y enumeración de rutas por backtracking.

Todos reciben una función de peso `peso(arista) -> float | None`.  Si la
función devuelve None la arista se considera no utilizable (por ejemplo,
porque el monto supera el límite transaccional del canal).
"""

from __future__ import annotations

import heapq
import itertools
import math
from dataclasses import dataclass, field
from typing import Callable, Iterable

from ..graph import Arista, Grafo

PesoFn = Callable[[Arista], "float | None"]
INF = math.inf


@dataclass
class ResultadoSSSP:
    """Resultado de un algoritmo de origen único."""
    origen: str
    dist: dict[str, float]
    pred: dict[str, Arista | None]
    ciclo_negativo: list[Arista] | None = None
    estadisticas: dict[str, int] = field(default_factory=dict)

    def camino(self, destino: str) -> list[Arista]:
        if destino not in self.dist or self.dist[destino] == INF:
            return []
        if destino == self.origen:
            return []
        camino: list[Arista] = []
        actual = destino
        vistos = set()
        while actual != self.origen:
            if actual in vistos:          # protección ante ciclos negativos
                return []
            vistos.add(actual)
            a = self.pred.get(actual)
            if a is None:
                return []
            camino.append(a)
            actual = a.otro_extremo(actual)
        camino.reverse()
        return camino


def _sucesores(g: Grafo, u: str, excluir_nodos: set[str] | None,
               excluir_aristas: set[str] | None):
    for v, a in g.vecinos(u):
        if excluir_nodos and v in excluir_nodos:
            continue
        if excluir_aristas and a.id in excluir_aristas:
            continue
        yield v, a


# ---------------------------------------------------------------- Dijkstra
def dijkstra(g: Grafo, origen: str, peso: PesoFn, destino: str | None = None,
             excluir_nodos: set[str] | None = None, excluir_aristas: set[str] | None = None,
             verificar_negativos: bool = True) -> ResultadoSSSP:
    """
    Dijkstra con cola de prioridad binaria (heapq) y eliminación perezosa.
    Requiere pesos >= 0.  Complejidad: O((V + E) log V) tiempo, O(V) memoria.
    Si se indica `destino`, se detiene al extraerlo (su distancia ya es definitiva).
    """
    dist: dict[str, float] = {origen: 0.0}
    pred: dict[str, Arista | None] = {origen: None}
    finalizados: set[str] = set()
    contador = itertools.count()
    heap = [(0.0, next(contador), origen)]
    relajaciones = extracciones = 0
    while heap:
        d, _, u = heapq.heappop(heap)
        if u in finalizados:
            continue
        finalizados.add(u)
        extracciones += 1
        if u == destino:
            break
        for v, a in _sucesores(g, u, excluir_nodos, excluir_aristas):
            if v in finalizados:
                continue
            w = peso(a)
            if w is None:
                continue
            if w < 0 and verificar_negativos:
                raise ValueError(
                    f"Dijkstra no admite pesos negativos (arista {a.id} {a.origen}->{a.destino}, "
                    f"peso {w:.4f}). Use Bellman-Ford.")
            nd = d + w
            if nd < dist.get(v, INF):
                dist[v] = nd
                pred[v] = a
                relajaciones += 1
                heapq.heappush(heap, (nd, next(contador), v))
    return ResultadoSSSP(origen, dist, pred, None,
                         {"relajaciones": relajaciones, "extracciones": extracciones})


# ------------------------------------------------------------ Bellman-Ford
def bellman_ford(g: Grafo, origen: str, peso: PesoFn,
                 excluir_nodos: set[str] | None = None,
                 excluir_aristas: set[str] | None = None) -> ResultadoSSSP:
    """
    Bellman-Ford con parada temprana.  Admite pesos negativos y detecta
    ciclos negativos alcanzables desde el origen.
    Complejidad: O(V · E) tiempo en el peor caso, O(V) memoria.
    """
    nodos = [n for n in g.ids_nodos(solo_activos=True) if not excluir_nodos or n not in excluir_nodos]
    lista: list[tuple[str, str, float, Arista]] = []
    for u in nodos:
        for v, a in _sucesores(g, u, excluir_nodos, excluir_aristas):
            w = peso(a)
            if w is not None:
                lista.append((u, v, w, a))

    dist: dict[str, float] = {n: INF for n in nodos}
    dist[origen] = 0.0
    pred: dict[str, Arista | None] = {origen: None}
    iteraciones = relajaciones = 0
    for _ in range(max(len(nodos) - 1, 0)):
        iteraciones += 1
        cambio = False
        for u, v, w, a in lista:
            du = dist[u]
            if du != INF and du + w < dist[v] - 1e-12:
                dist[v] = du + w
                pred[v] = a
                relajaciones += 1
                cambio = True
        if not cambio:
            break

    ciclo = None
    for u, v, w, a in lista:
        if dist[u] != INF and dist[u] + w < dist[v] - 1e-9:
            # retroceder |V| veces asegura caer dentro del ciclo
            pred[v] = a
            x = v
            try:
                for _ in range(len(nodos)):
                    x = pred[x].otro_extremo(x)  # type: ignore[union-attr]
                ciclo = []
                y = x
                while True:
                    arista = pred[y]
                    ciclo.append(arista)  # type: ignore[arg-type]
                    y = arista.otro_extremo(y)  # type: ignore[union-attr]
                    if y == x or len(ciclo) > len(nodos):
                        break
                ciclo.reverse()
            except (AttributeError, KeyError):
                ciclo = [a]
            break
    dist = {k: v for k, v in dist.items() if v != INF}
    return ResultadoSSSP(origen, dist, pred, ciclo,
                         {"iteraciones": iteraciones, "relajaciones": relajaciones,
                          "aristas_evaluadas": iteraciones * len(lista)})


# ---------------------------------------------------------- Floyd-Warshall
@dataclass
class ResultadoFW:
    nodos: list[str]
    dist: list[list[float]]
    siguiente: list[list[int]]
    directa: dict[tuple[int, int], Arista]
    ciclo_negativo: bool = False

    @property
    def indice(self) -> dict[str, int]:
        return {n: i for i, n in enumerate(self.nodos)}

    def distancia(self, u: str, v: str) -> float:
        idx = self.indice
        return self.dist[idx[u]][idx[v]]

    def camino(self, u: str, v: str) -> list[Arista]:
        idx = self.indice
        i, j = idx[u], idx[v]
        if self.dist[i][j] == INF or i == j:
            return []
        aristas: list[Arista] = []
        guard = 0
        while i != j:
            k = self.siguiente[i][j]
            if k < 0:
                return []
            aristas.append(self.directa[(i, k)])
            i = k
            guard += 1
            if guard > len(self.nodos):
                return []
        return aristas

    def matriz(self) -> dict[str, dict[str, float]]:
        return {u: {v: self.dist[i][j] for j, v in enumerate(self.nodos)}
                for i, u in enumerate(self.nodos)}


def floyd_warshall(g: Grafo, peso: PesoFn, nodos: Iterable[str] | None = None) -> ResultadoFW:
    """
    Floyd-Warshall: distancias mínimas entre todos los pares.
    Complejidad: O(V^3) tiempo y O(V^2) memoria, independiente de E.
    Conveniente solo para redes pequeñas o cuando se necesita la matriz completa
    (p. ej. el tarifario de comisiones entre todas las agencias).
    """
    orden = list(nodos) if nodos is not None else g.ids_nodos(solo_activos=True)
    idx = {n: i for i, n in enumerate(orden)}
    n = len(orden)
    dist = [[INF] * n for _ in range(n)]
    sig = [[-1] * n for _ in range(n)]
    directa: dict[tuple[int, int], Arista] = {}
    for i in range(n):
        dist[i][i] = 0.0
        sig[i][i] = i
    for u in orden:
        i = idx[u]
        for v, a in g.vecinos(u):
            j = idx.get(v)
            if j is None:
                continue
            w = peso(a)
            if w is None:
                continue
            if w < dist[i][j]:
                dist[i][j] = w
                sig[i][j] = j
                directa[(i, j)] = a
    for k in range(n):
        dk = dist[k]
        for i in range(n):
            dik = dist[i][k]
            if dik == INF:
                continue
            di = dist[i]
            si = sig[i]
            sik = si[k]
            for j in range(n):
                nd = dik + dk[j]
                if nd < di[j]:
                    di[j] = nd
                    si[j] = sik
    negativo = any(dist[i][i] < 0 for i in range(n))
    return ResultadoFW(orden, dist, sig, directa, negativo)


# ---------------------------------------------------- k rutas (Yen, 1971)
def costo_camino(camino: list[Arista], peso: PesoFn) -> float:
    total = 0.0
    for a in camino:
        w = peso(a)
        if w is None:
            return INF
        total += w
    return total


def nodos_de_camino(origen: str, camino: list[Arista]) -> list[str]:
    nodos = [origen]
    for a in camino:
        nodos.append(a.otro_extremo(nodos[-1]))
    return nodos


def yen_k_rutas(g: Grafo, origen: str, destino: str, k: int, peso: PesoFn,
                excluir_nodos: set[str] | None = None) -> list[tuple[float, list[Arista]]]:
    """
    k rutas simples más cortas (algoritmo de Yen) usando Dijkstra como subrutina.
    Complejidad: O(k · V · (V + E) log V).  Requiere pesos >= 0.
    """
    base = dijkstra(g, origen, peso, destino, excluir_nodos=excluir_nodos)
    primero = base.camino(destino)
    if not primero:
        return []
    A: list[tuple[float, list[Arista]]] = [(costo_camino(primero, peso), primero)]
    B: list[tuple[float, int, list[Arista]]] = []
    vistos = {tuple(a.id for a in primero)}
    contador = itertools.count()
    for _ in range(1, k):
        _, ultimo = A[-1]
        nodos_ult = nodos_de_camino(origen, ultimo)
        for i in range(len(ultimo)):
            espuela = nodos_ult[i]
            raiz = ultimo[:i]
            raiz_ids = tuple(a.id for a in raiz)
            excl_aristas = {c[i].id for _, c in A
                            if len(c) > i and tuple(a.id for a in c[:i]) == raiz_ids}
            excl_nodos = set(nodos_ult[:i]) | (excluir_nodos or set())
            r = dijkstra(g, espuela, peso, destino, excluir_nodos=excl_nodos,
                         excluir_aristas=excl_aristas)
            tramo = r.camino(destino)
            if not tramo:
                continue
            total = raiz + tramo
            clave = tuple(a.id for a in total)
            if clave in vistos:
                continue
            vistos.add(clave)
            heapq.heappush(B, (costo_camino(total, peso), next(contador), total))
        if not B:
            break
        c, _, camino = heapq.heappop(B)
        A.append((c, camino))
    return A


# ------------------------------------------------- enumeración (backtracking)
def rutas_backtracking(g: Grafo, origen: str, destino: str, peso: PesoFn,
                       max_saltos: int = 8, cota: float | None = None,
                       max_rutas: int = 5000, solo_mejor: bool = False
                       ) -> tuple[list[tuple[float, list[Arista]]], dict[str, int]]:
    """
    Enumera todas las rutas simples origen -> destino con a lo sumo `max_saltos`
    aristas mediante backtracking (DFS con retroceso).  Con `cota` se poda toda
    rama cuyo costo parcial ya la supera (ramificación y acotamiento; válido
    solo con pesos >= 0).  Con `solo_mejor=True` la cota se actualiza con la
    mejor ruta hallada, lo que convierte la búsqueda en un branch & bound exacto.
    Los nodos y aristas cerrados simplemente no se
    exploran, igual que las calles cerradas en un laberinto.
    Complejidad: exponencial en el peor caso, O(d^L); útil para listar
    alternativas en redes pequeñas, no para optimizar en redes grandes.
    """
    rutas: list[tuple[float, list[Arista]]] = []
    stats = {"nodos_explorados": 0, "podas_por_cota": 0, "podas_por_saltos": 0, "truncado": 0}
    camino: list[Arista] = []
    en_camino = {origen}

    pila: list[tuple[str, float, Iterable]] = [(origen, 0.0, iter(g.vecinos(origen)))]
    while pila:
        u, costo, it = pila[-1]
        siguiente = next(it, None)
        if siguiente is None:
            pila.pop()
            if camino:
                en_camino.discard(u)
                camino.pop()
            continue
        v, a = siguiente
        w = peso(a)
        if w is None or v in en_camino:
            continue
        nuevo = costo + w
        stats["nodos_explorados"] += 1
        if cota is not None and nuevo > cota:
            stats["podas_por_cota"] += 1
            continue
        if v == destino:
            rutas.append((nuevo, camino + [a]))
            if solo_mejor:
                cota = nuevo if cota is None else min(cota, nuevo)
            if len(rutas) >= max_rutas:
                stats["truncado"] = 1
                break
            continue
        if len(camino) + 1 >= max_saltos:
            stats["podas_por_saltos"] += 1
            continue
        camino.append(a)
        en_camino.add(v)
        pila.append((v, nuevo, iter(g.vecinos(v))))
    rutas.sort(key=lambda x: x[0])
    return rutas, stats
