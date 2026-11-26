"""
Árbol (bosque) de expansión mínima: Kruskal con Union-Find y Prim con heap.
Se aplican sobre la versión no dirigida de la red.
"""

from __future__ import annotations

import heapq
import itertools

from ..graph import Arista, Grafo
from .caminos_minimos import PesoFn


class UnionFind:
    """Conjuntos disjuntos con compresión de caminos y unión por rango: ~O(α(n)) por operación."""

    def __init__(self, elementos) -> None:
        self.padre = {x: x for x in elementos}
        self.rango = {x: 0 for x in elementos}

    def buscar(self, x):
        raiz = x
        while self.padre[raiz] != raiz:
            raiz = self.padre[raiz]
        while self.padre[x] != raiz:
            self.padre[x], x = raiz, self.padre[x]
        return raiz

    def unir(self, a, b) -> bool:
        ra, rb = self.buscar(a), self.buscar(b)
        if ra == rb:
            return False
        if self.rango[ra] < self.rango[rb]:
            ra, rb = rb, ra
        self.padre[rb] = ra
        if self.rango[ra] == self.rango[rb]:
            self.rango[ra] += 1
        return True


def kruskal(g: Grafo, peso: PesoFn) -> tuple[list[Arista], float]:
    """Ordena las aristas y agrega la más barata que no forme ciclo. O(E log E)."""
    nodos = g.ids_nodos(solo_activos=True)
    uf = UnionFind(nodos)
    candidatas = []
    for a in g.aristas(incluir_inactivas=False):
        w = peso(a)
        if w is not None:
            candidatas.append((w, a.id, a))
    candidatas.sort(key=lambda x: (x[0], x[1]))
    arbol: list[Arista] = []
    total = 0.0
    for w, _, a in candidatas:
        if uf.unir(a.origen, a.destino):
            arbol.append(a)
            total += w
            if len(arbol) == len(nodos) - 1:
                break
    return arbol, total


def prim(g: Grafo, peso: PesoFn, inicio: str | None = None) -> tuple[list[Arista], float]:
    """Crece el árbol desde un nodo tomando la arista más barata de la frontera. O(E log V)."""
    nodos = g.ids_nodos(solo_activos=True)
    if not nodos:
        return [], 0.0
    en_arbol: set[str] = set()
    arbol: list[Arista] = []
    total = 0.0
    contador = itertools.count()
    raices = ([inicio] if inicio else []) + nodos   # reinicia en cada componente (bosque)
    for raiz in raices:
        if raiz in en_arbol:
            continue
        en_arbol.add(raiz)
        heap: list = []

        def empujar(u: str) -> None:
            vecinos = g.vecinos(u) + (g.predecesores(u) if g.dirigido else [])
            for v, a in vecinos:
                if v not in en_arbol:
                    w = peso(a)
                    if w is not None:
                        heapq.heappush(heap, (w, next(contador), v, a))

        empujar(raiz)
        while heap:
            w, _, v, a = heapq.heappop(heap)
            if v in en_arbol:
                continue
            en_arbol.add(v)
            arbol.append(a)
            total += w
            empujar(v)
    return arbol, total
