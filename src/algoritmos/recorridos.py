"""
Algoritmos de recorrido: BFS, DFS, componentes fuertemente conexas
(Tarjan y Kosaraju) y búsqueda acotada de ciclos.

Todos se implementan de forma iterativa (sin recursión) para no depender
del límite de recursión de Python en redes grandes.
"""

from __future__ import annotations

from collections import deque
from typing import Callable, Iterable

from ..graph import Arista, Grafo

FiltroArista = Callable[[Arista], bool]


def bfs(g: Grafo, origen: str, max_nivel: int | None = None,
        no_dirigido: bool = False, filtro: FiltroArista | None = None
        ) -> tuple[dict[str, int], dict[str, Arista | None]]:
    """
    Búsqueda en anchura. Devuelve (nivel, predecesor).
    nivel[v] = número mínimo de saltos desde el origen (distancia en aristas).
    Complejidad: O(V + E) tiempo, O(V) memoria.
    """
    nivel = {origen: 0}
    pred: dict[str, Arista | None] = {origen: None}
    cola = deque([origen])
    while cola:
        u = cola.popleft()
        if max_nivel is not None and nivel[u] >= max_nivel:
            continue
        vecinos = g.vecinos(u)
        if no_dirigido and g.dirigido:
            vecinos = vecinos + g.predecesores(u)
        for v, a in vecinos:
            if v in nivel or (filtro and not filtro(a)):
                continue
            nivel[v] = nivel[u] + 1
            pred[v] = a
            cola.append(v)
    return nivel, pred


def dfs(g: Grafo, origen: str, filtro: FiltroArista | None = None
        ) -> tuple[list[str], dict[str, Arista | None]]:
    """
    Búsqueda en profundidad iterativa. Devuelve (orden de descubrimiento, predecesor).
    Complejidad: O(V + E).
    """
    orden: list[str] = []
    pred: dict[str, Arista | None] = {origen: None}
    visitado = set()
    pila = [origen]
    while pila:
        u = pila.pop()
        if u in visitado:
            continue
        visitado.add(u)
        orden.append(u)
        # se apilan en orden inverso para visitar en el orden natural de la lista
        for v, a in reversed(g.vecinos(u)):
            if v not in visitado and (not filtro or filtro(a)):
                if v not in pred:
                    pred[v] = a
                pila.append(v)
    return orden, pred


def camino_desde_pred(pred: dict[str, Arista | None], origen: str, destino: str) -> list[Arista]:
    """Reconstruye la secuencia de aristas origen -> destino a partir de un árbol de predecesores."""
    if destino not in pred:
        return []
    camino: list[Arista] = []
    actual = destino
    while actual != origen:
        a = pred[actual]
        if a is None:
            return []
        camino.append(a)
        actual = a.otro_extremo(actual)
    camino.reverse()
    return camino


def tarjan_scc(g: Grafo, nodos: Iterable[str] | None = None) -> list[list[str]]:
    """
    Componentes fuertemente conexas (Tarjan, versión iterativa).
    Un grupo de cuentas donde todas pueden enviarse dinero entre sí (directa
    o indirectamente) es una SCC: condición necesaria para que exista
    circulación de fondos.  Complejidad: O(V + E).
    """
    indice: dict[str, int] = {}
    bajo: dict[str, int] = {}
    en_pila: set[str] = set()
    pila: list[str] = []
    componentes: list[list[str]] = []
    contador = 0
    universo = list(nodos) if nodos is not None else g.ids_nodos(solo_activos=True)
    permitidos = set(universo)

    for raiz in universo:
        if raiz in indice:
            continue
        # cada marco: (nodo, iterador de vecinos)
        indice[raiz] = bajo[raiz] = contador
        contador += 1
        pila.append(raiz)
        en_pila.add(raiz)
        marcos = [(raiz, iter(g.vecinos(raiz)))]
        while marcos:
            u, it = marcos[-1]
            avanzo = False
            for v, _ in it:
                if v not in permitidos:
                    continue
                if v not in indice:
                    indice[v] = bajo[v] = contador
                    contador += 1
                    pila.append(v)
                    en_pila.add(v)
                    marcos.append((v, iter(g.vecinos(v))))
                    avanzo = True
                    break
                if v in en_pila:
                    bajo[u] = min(bajo[u], indice[v])
            if avanzo:
                continue
            marcos.pop()
            if marcos:
                padre = marcos[-1][0]
                bajo[padre] = min(bajo[padre], bajo[u])
            if bajo[u] == indice[u]:
                comp = []
                while True:
                    w = pila.pop()
                    en_pila.discard(w)
                    comp.append(w)
                    if w == u:
                        break
                componentes.append(comp)
    return componentes


def kosaraju_scc(g: Grafo) -> list[list[str]]:
    """
    Componentes fuertemente conexas (Kosaraju): dos DFS, una sobre el grafo y
    otra sobre el grafo transpuesto.  Misma complejidad O(V + E) que Tarjan,
    pero recorre las aristas dos veces; se usa en el Módulo 5 como comparación.
    """
    visitado: set[str] = set()
    orden: list[str] = []
    for s in g.ids_nodos(solo_activos=True):
        if s in visitado:
            continue
        visitado.add(s)
        pila = [(s, iter(g.vecinos(s)))]
        while pila:
            u, it = pila[-1]
            for v, _ in it:
                if v not in visitado:
                    visitado.add(v)
                    pila.append((v, iter(g.vecinos(v))))
                    break
            else:
                pila.pop()
                orden.append(u)
    asignado: set[str] = set()
    comps: list[list[str]] = []
    for s in reversed(orden):
        if s in asignado:
            continue
        comp = []
        pila2 = [s]
        asignado.add(s)
        while pila2:
            u = pila2.pop()
            comp.append(u)
            for v, _ in g.predecesores(u):
                if v not in asignado:
                    asignado.add(v)
                    pila2.append(v)
        comps.append(comp)
    return comps


def ciclos_acotados(g: Grafo, nodos: Iterable[str], max_longitud: int = 6,
                    paso_valido: Callable[[Arista | None, Arista], bool] | None = None,
                    max_ciclos: int = 500, min_longitud: int = 3,
                    canonico: bool = True) -> list[list[Arista]]:
    """
    Enumera ciclos simples de longitud <= max_longitud dentro del conjunto
    `nodos` usando DFS con retroceso (backtracking).

    `paso_valido(arista_anterior, arista_siguiente)` permite imponer
    restricciones de dominio (orden cronológico, montos similares) que
    podan el árbol de búsqueda.  Cada ciclo se reporta una sola vez: con
    `canonico=True` empezando en su nodo de menor id; con `canonico=False`
    se prueba cada nodo como inicio (necesario cuando el orden importa, como
    en ciclos cronológicos) y se eliminan duplicados por conjunto de aristas.

    Complejidad en el peor caso: O(V · d^L) con d = grado medio y L = longitud
    máxima; por eso se aplica solo dentro de cada SCC (fuera de una SCC no
    puede haber ciclos) y con L acotado.
    """
    permitidos = set(nodos)
    ciclos: list[list[Arista]] = []
    vistos: set[frozenset[str]] = set()
    for inicio in sorted(permitidos):
        # pila de (nodo actual, camino de aristas, conjunto en camino)
        pila: list[tuple[str, list[Arista], frozenset[str]]] = [(inicio, [], frozenset([inicio]))]
        while pila:
            u, camino, en_camino = pila.pop()
            ultima = camino[-1] if camino else None
            for v, a in g.vecinos(u):
                if v not in permitidos or (canonico and v < inicio):
                    continue
                if paso_valido and not paso_valido(ultima, a):
                    continue
                if v == inicio:
                    clave = frozenset(x.id for x in camino) | {a.id}
                    if len(camino) + 1 >= min_longitud and clave not in vistos:
                        vistos.add(clave)
                        ciclos.append(camino + [a])
                        if len(ciclos) >= max_ciclos:
                            return ciclos
                    continue
                if v in en_camino or len(camino) + 2 > max_longitud:
                    continue
                pila.append((v, camino + [a], en_camino | {v}))
    return ciclos
