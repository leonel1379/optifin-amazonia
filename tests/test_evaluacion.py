"""Módulo 5: casos de prueba integrales, benchmarks y validación cruzada."""
from src.evaluacion_resultados import (benchmark_caminos, benchmark_flujo, casos_de_prueba,
                                       pendientes_loglog, validar_con_networkx)


def test_casos_de_prueba_superados():
    casos = casos_de_prueba()
    fallidos = [c for c in casos if c["estado"] != "✔"]
    assert not fallidos, fallidos


def test_benchmarks_pequenos():
    f = benchmark_caminos((50, 100), repeticiones=1, memoria=False)
    assert {x["algoritmo"] for x in f} == {"Dijkstra", "Bellman-Ford", "Floyd-Warshall"}
    assert pendientes_loglog(f)
    fl = benchmark_flujo((50, 100), repeticiones=1, memoria=False)
    por_n = {}
    for x in fl:
        por_n.setdefault(x["n"], set()).add(x["flujo"])
    assert all(len(v) == 1 for v in por_n.values())         # los 3 algoritmos dan el mismo flujo


def test_validacion_networkx():
    assert all(v["estado"] == "✔" for v in validar_con_networkx(5) if "estado" in v)
