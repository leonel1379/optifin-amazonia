"""Algoritmos implementados desde cero, verificados contra casos pequeños conocidos."""
from src.algoritmos import (bellman_ford, bfs, ciclos_acotados, corte_minimo, dijkstra, dinic,
                            edmonds_karp, floyd_warshall, flujo_costo_minimo, kosaraju_scc, kruskal,
                            prim, red_desde_grafo, rutas_backtracking, tarjan_scc, yen_k_rutas)
from src.graph import Grafo


def red(aristas, dirigido=True):
    g = Grafo(dirigido=dirigido, multiple=True)
    for u, v, *_ in aristas:
        for x in (u, v):
            if x not in g.nodos:
                g.agregar_nodo(x)
    for u, v, w in aristas:
        g.agregar_arista(u, v, w=w, capacidad=abs(w), costo=1.0, canal=f"{u}{v}{w}")
    return g


W = lambda a: a["w"]  # noqa: E731
G1 = [("A", "B", 4), ("A", "C", 2), ("C", "B", 1), ("B", "D", 5), ("C", "D", 8), ("D", "E", 3)]


def test_caminos_minimos_coinciden():
    g = red(G1)
    d, b, f = dijkstra(g, "A", W), bellman_ford(g, "A", W), floyd_warshall(g, W)
    assert d.dist["E"] == b.dist["E"] == f.distancia("A", "E") == 11
    assert [a.destino for a in d.camino("E")] == ["C", "B", "D", "E"]


def test_bellman_ford_detecta_ciclo_negativo():
    g = red([("A", "B", 1), ("B", "C", -2), ("C", "B", 1)])
    assert bellman_ford(g, "A", W).ciclo_negativo


def test_dijkstra_falla_con_negativos():
    g = red([("S", "A", 2), ("S", "B", 3), ("B", "A", -2)])
    assert dijkstra(g, "S", W, verificar_negativos=False).dist["A"] == 2
    assert bellman_ford(g, "S", W).dist["A"] == 1


def test_yen_y_backtracking():
    g = red(G1)
    k = yen_k_rutas(g, "A", "E", 3, W)
    assert [c for c, _ in k] == [11, 12, 13]
    todas, _ = rutas_backtracking(g, "A", "E", W)
    assert len(todas) == 3 and todas[0][0] == 11


def test_flujo_maximo_y_corte():
    g = red([("s", "a", 10), ("s", "b", 5), ("a", "b", 15), ("a", "t", 10), ("b", "t", 10)])
    for alg in (edmonds_karp, dinic, flujo_costo_minimo):
        r = red_desde_grafo(g)
        assert alg(r, "s", "t").valor == 15
    r = red_desde_grafo(g)
    dinic(r, "s", "t")
    lado, corte = corte_minimo(r, "s")
    assert sum(r.cap[e] for e in corte) == 15 and lado == {"s"}


def test_scc_y_ciclos():
    g = red([("A", "B", 1), ("B", "C", 1), ("C", "A", 1), ("C", "D", 1)])
    assert sorted(map(sorted, tarjan_scc(g))) == sorted(map(sorted, kosaraju_scc(g))) == [["A", "B", "C"], ["D"]]
    assert len(ciclos_acotados(g, ["A", "B", "C"], 5)) == 1


def test_mst():
    g = red([("A", "B", 1), ("B", "C", 2), ("A", "C", 3), ("C", "D", 1)], dirigido=False)
    assert kruskal(g, W)[1] == prim(g, W)[1] == 4


def test_bfs_niveles():
    nivel, _ = bfs(red(G1), "A")
    assert nivel == {"A": 0, "B": 1, "C": 1, "D": 2, "E": 3}
