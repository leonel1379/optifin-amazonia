"""
Módulo 5 — Evaluación, comparación y validación de resultados.

* Casos de prueba por módulo con resultado esperado vs. obtenido.
* Comparación empírica de algoritmos alternativos sobre redes sintéticas de
  tamaño creciente (tiempo con perf_counter y memoria pico con tracemalloc).
* Estimación del exponente empírico (pendiente log-log) para contrastarlo con
  la complejidad teórica.
* Validación cruzada contra NetworkX (biblioteca de referencia), si está instalada.
"""

from __future__ import annotations

import json
import math
import random
from typing import Any, Callable

from .algoritmos import (bellman_ford, bfs, dfs, dijkstra, dinic, edmonds_karp, floyd_warshall,
                         flujo_costo_minimo, kosaraju_scc, kruskal, prim, red_desde_grafo, tarjan_scc)
from .graph import Grafo
from .utils import DATA_DIR, medir

# --------------------------------------------------------------------------
# Tabla de decisiones algorítmicas (se muestra en la interfaz y en el informe)
# --------------------------------------------------------------------------
TABLA_COMPLEJIDAD = [
    {"escenario": "Fraude y lavado", "algoritmo": "BFS", "tiempo": "O(V + E)", "espacio": "O(V)",
     "uso": "Niveles de proximidad y relaciones indirectas", "decision": "ELEGIDO",
     "motivo": "Da el número mínimo de saltos entre cuentas; DFS no garantiza distancias mínimas."},
    {"escenario": "Fraude y lavado", "algoritmo": "DFS acotada (backtracking)", "tiempo": "O(V · d^L)",
     "espacio": "O(L)", "uso": "Ciclos cronológicos de fondos", "decision": "ELEGIDO",
     "motivo": "Enumera ciclos con restricciones de fecha y monto; se acota a L ≤ 6 y se aplica solo dentro de SCC."},
    {"escenario": "Fraude y lavado", "algoritmo": "Tarjan (SCC)", "tiempo": "O(V + E)", "espacio": "O(V)",
     "uso": "Grupos cerrados y poda de la búsqueda de ciclos", "decision": "ELEGIDO",
     "motivo": "Una pasada; Kosaraju tiene la misma cota pero recorre el grafo dos veces y necesita el transpuesto."},
    {"escenario": "Fraude y lavado", "algoritmo": "Dijkstra / MST / flujo", "tiempo": "—", "espacio": "—",
     "uso": "—", "decision": "DESCARTADO",
     "motivo": "El problema es de conectividad y patrones, no de costo mínimo, árbol barato ni capacidad."},
    {"escenario": "Enrutamiento y comisiones", "algoritmo": "Dijkstra (heap binario)", "tiempo": "O((V + E) log V)",
     "espacio": "O(V)", "uso": "Ruta de menor comisión / tiempo / riesgo", "decision": "ELEGIDO",
     "motivo": "Pesos ≥ 0, consulta origen-destino y parada temprana al extraer el destino."},
    {"escenario": "Enrutamiento y comisiones", "algoritmo": "Bellman-Ford", "tiempo": "O(V · E)", "espacio": "O(V)",
     "uso": "Solo con bonificaciones (pesos negativos)", "decision": "CONDICIONAL",
     "motivo": "Más lento; necesario únicamente si existen pesos negativos y para detectar ciclos negativos."},
    {"escenario": "Enrutamiento y comisiones", "algoritmo": "Floyd-Warshall", "tiempo": "O(V³)", "espacio": "O(V²)",
     "uso": "Matriz completa de costos entre agencias", "decision": "COMPLEMENTARIO",
     "motivo": "Calcula todos los pares aunque se pida uno; útil solo para el tarifario completo en redes pequeñas."},
    {"escenario": "Enrutamiento y comisiones", "algoritmo": "Yen (k rutas) / backtracking", "tiempo": "O(k·V·(V+E)log V) / O(d^L)",
     "espacio": "O(k·V) / O(L)", "uso": "Rutas alternativas y cierre de sucursales", "decision": "COMPLEMENTARIO",
     "motivo": "Yen reutiliza Dijkstra; el backtracking lista todas las rutas, pero es exponencial."},
    {"escenario": "Liquidez a bóvedas", "algoritmo": "Dinic", "tiempo": "O(V² · E)", "espacio": "O(V + E)",
     "uso": "Máximo efectivo distribuible y corte mínimo", "decision": "ELEGIDO",
     "motivo": "Mejor cota y menos fases que Edmonds-Karp; el problema es de capacidades, no de rutas cortas."},
    {"escenario": "Liquidez a bóvedas", "algoritmo": "Edmonds-Karp", "tiempo": "O(V · E²)", "espacio": "O(V + E)",
     "uso": "Comparación y validación del flujo", "decision": "COMPARACIÓN",
     "motivo": "Correcto pero con peor cota; sirve para verificar que ambos obtienen el mismo flujo."},
    {"escenario": "Liquidez a bóvedas", "algoritmo": "Flujo máximo de costo mínimo (SPFA)", "tiempo": "O(F · V · E)",
     "espacio": "O(V + E)", "uso": "Asignación más barata del flujo máximo", "decision": "ELEGIDO",
     "motivo": "Decide por qué rutas enviar cada sol minimizando el costo de traslado."},
    {"escenario": "Liquidez a bóvedas", "algoritmo": "Kruskal / Prim (MST)", "tiempo": "O(E log E) / O(E log V)",
     "espacio": "O(V + E)", "uso": "Red troncal mínima de rutas custodiadas", "decision": "COMPLEMENTARIO",
     "motivo": "Conecta todo al menor costo pero ignora capacidad y demanda: no sirve para distribuir."},
]


# --------------------------------------------------------------------------
# Redes sintéticas
# --------------------------------------------------------------------------
def red_aleatoria(n: int, grado_medio: float = 4.0, semilla: int = 7, dirigido: bool = True,
                  peso_min: float = 0.5, peso_max: float = 20.0) -> Grafo:
    """Red conexa: un camino base 0→1→…→n−1 garantiza alcanzabilidad; el resto de aristas es aleatorio."""
    rnd = random.Random(semilla + n)
    g = Grafo(f"sintetica_{n}", dirigido=dirigido, multiple=True)
    for i in range(n):
        g.agregar_nodo(f"N{i}")
    m = int(n * grado_medio)
    for i in range(n - 1):
        g.agregar_arista(f"N{i}", f"N{i + 1}", peso=round(rnd.uniform(peso_min, peso_max), 3),
                         capacidad=rnd.randint(5, 50), costo=round(rnd.uniform(0.5, 5), 2))
    for _ in range(m - (n - 1)):
        u, v = rnd.sample(range(n), 2)
        g.agregar_arista(f"N{u}", f"N{v}", canal=str(rnd.random()),
                         peso=round(rnd.uniform(peso_min, peso_max), 3),
                         capacidad=rnd.randint(5, 50), costo=round(rnd.uniform(0.5, 5), 2))
    return g


def _peso(a):
    return a.atributos["peso"]


# --------------------------------------------------------------------------
# Benchmarks
# --------------------------------------------------------------------------
def benchmark_caminos(tamanos=(100, 200, 400, 800, 1600), fw_max: int = 200, bf_max: int = 800,
                      repeticiones: int = 3, memoria: bool = True) -> list[dict[str, Any]]:
    filas = []
    for n in tamanos:
        g = red_aleatoria(n)
        casos: list[tuple[str, Callable[[], Any]]] = [("Dijkstra", lambda: dijkstra(g, "N0", _peso))]
        if n <= bf_max:
            casos.append(("Bellman-Ford", lambda: bellman_ford(g, "N0", _peso)))
        if n <= fw_max:
            casos.append(("Floyd-Warshall", lambda: floyd_warshall(g, _peso)))
        for nombre, f in casos:
            res, ms, kb = medir(f, repeticiones, memoria)
            ops = (sum(res.estadisticas.values()) if hasattr(res, "estadisticas") else n ** 3)
            filas.append({"familia": "rutas más cortas", "algoritmo": nombre, "n": n, "m": g.num_aristas,
                          "tiempo_ms": round(ms, 3), "memoria_kb": round(kb, 1), "operaciones": ops})
    return filas


def red_flujo_aleatoria(n: int, semilla: int = 11):
    """Red por capas (bóveda → … → agencias) para comparar algoritmos de flujo."""
    rnd = random.Random(semilla + n)
    g = Grafo(f"flujo_{n}", dirigido=True, multiple=True)
    capas = max(3, int(math.sqrt(n) / 2))
    por_capa = max(1, n // capas)
    ids = [[f"C{c}_{i}" for i in range(por_capa)] for c in range(capas)]
    for capa in ids:
        for x in capa:
            g.agregar_nodo(x)
    for c in range(capas - 1):
        for u in ids[c]:
            for v in rnd.sample(ids[c + 1], min(3, por_capa)):
                g.agregar_arista(u, v, canal=str(rnd.random()), capacidad=rnd.randint(5, 60),
                                 costo=round(rnd.uniform(0.5, 6), 2))
    ofe = {u: 1000.0 for u in ids[0]}
    dem = {v: float(rnd.randint(20, 80)) for v in ids[-1]}
    return g, ofe, dem


def benchmark_flujo(tamanos=(100, 200, 400, 800, 1600), repeticiones: int = 3,
                    memoria: bool = True, costo_min_max: int = 400) -> list[dict[str, Any]]:
    filas = []
    for n in tamanos:
        g, ofe, dem = red_flujo_aleatoria(n)
        algoritmos = [("Edmonds-Karp", edmonds_karp), ("Dinic", dinic)]
        if n <= costo_min_max:
            algoritmos.append(("Costo mínimo (SPFA)", flujo_costo_minimo))
        for nombre, alg in algoritmos:
            def correr(alg=alg):
                red = red_desde_grafo(g, "capacidad", "costo", ofe, dem)
                return alg(red, "__FUENTE__", "__SUMIDERO__")
            res, ms, kb = medir(correr, repeticiones, memoria)
            filas.append({"familia": "flujo máximo", "algoritmo": nombre, "n": g.num_nodos, "m": g.num_aristas,
                          "tiempo_ms": round(ms, 3), "memoria_kb": round(kb, 1),
                          "operaciones": sum(res.estadisticas.values()), "flujo": round(res.valor, 2)})
    return filas


def benchmark_recorridos(tamanos=(500, 1000, 2000, 4000, 8000), repeticiones: int = 3,
                         memoria: bool = True) -> list[dict[str, Any]]:
    filas = []
    for n in tamanos:
        g = red_aleatoria(n, grado_medio=3)
        for nombre, f in (("BFS", lambda: bfs(g, "N0")), ("DFS", lambda: dfs(g, "N0")),
                          ("Tarjan (SCC)", lambda: tarjan_scc(g)), ("Kosaraju (SCC)", lambda: kosaraju_scc(g))):
            _, ms, kb = medir(f, repeticiones, memoria)
            filas.append({"familia": "recorridos", "algoritmo": nombre, "n": n, "m": g.num_aristas,
                          "tiempo_ms": round(ms, 3), "memoria_kb": round(kb, 1)})
    return filas


def benchmark_mst(tamanos=(500, 1000, 2000, 4000, 8000), repeticiones: int = 3,
                  memoria: bool = True) -> list[dict[str, Any]]:
    filas = []
    for n in tamanos:
        g = red_aleatoria(n, grado_medio=4, dirigido=False)
        for nombre, f in (("Kruskal", lambda: kruskal(g, _peso)), ("Prim", lambda: prim(g, _peso))):
            (arbol, costo), ms, kb = medir(f, repeticiones, memoria)
            filas.append({"familia": "árbol de expansión mínima", "algoritmo": nombre, "n": n,
                          "m": g.num_aristas, "tiempo_ms": round(ms, 3), "memoria_kb": round(kb, 1),
                          "costo_arbol": round(costo, 3)})
    return filas


def pendientes_loglog(filas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Exponente empírico k en t ≈ c·n^k (regresión lineal de log t sobre log n)."""
    por_alg: dict[str, list[tuple[float, float]]] = {}
    for f in filas:
        if f["tiempo_ms"] > 0:
            por_alg.setdefault(f["algoritmo"], []).append((math.log(f["n"]), math.log(f["tiempo_ms"])))
    teoria = {"Dijkstra": "≈1.1 (n log n, E∝n)", "Bellman-Ford": "≤2 (V·E, E∝n; menor con parada temprana)",
              "Floyd-Warshall": "3", "Edmonds-Karp": "≤3 (V·E²)", "Dinic": "≤3 (V²·E)",
              "Costo mínimo (SPFA)": "variable", "BFS": "1", "DFS": "1", "Tarjan (SCC)": "1",
              "Kosaraju (SCC)": "1", "Kruskal": "≈1.1 (E log E)", "Prim": "≈1.1 (E log V)"}
    res = []
    for alg, pts in por_alg.items():
        if len(pts) < 2:
            continue
        mx = sum(x for x, _ in pts) / len(pts)
        my = sum(y for _, y in pts) / len(pts)
        sxx = sum((x - mx) ** 2 for x, _ in pts)
        k = sum((x - mx) * (y - my) for x, y in pts) / sxx if sxx else float("nan")
        res.append({"algoritmo": alg, "exponente_empirico": round(k, 2), "exponente_teorico": teoria.get(alg, "—"),
                    "puntos": len(pts)})
    return res


# --------------------------------------------------------------------------
# Validación cruzada con NetworkX
# --------------------------------------------------------------------------
def validar_con_networkx(pruebas: int = 15, semilla: int = 3) -> list[dict[str, Any]]:
    try:
        import networkx as nx
    except ImportError:
        return [{"prueba": "NetworkX no instalado", "coinciden": None, "detalle": "pip install networkx"}]
    rnd = random.Random(semilla)
    ok = {"Dijkstra": 0, "Bellman-Ford": 0, "Floyd-Warshall": 0, "Edmonds-Karp": 0, "Dinic": 0,
          "Tarjan": 0, "Kruskal": 0, "Prim": 0, "BFS": 0}
    for t in range(pruebas):
        n = rnd.randint(8, 60)
        g = red_aleatoria(n, grado_medio=rnd.uniform(2, 5), semilla=t)
        G = nx.DiGraph()
        for a in g.aristas():
            u, v, w, c = a.origen, a.destino, a["peso"], a["capacidad"]
            if G.has_edge(u, v):
                G[u][v]["weight"] = min(G[u][v]["weight"], w)
                G[u][v]["capacity"] += c
            else:
                G.add_edge(u, v, weight=w, capacity=c)
        ref = nx.single_source_dijkstra_path_length(G, "N0")
        d = dijkstra(g, "N0", _peso).dist
        b = bellman_ford(g, "N0", _peso).dist
        fw = floyd_warshall(g, _peso)
        ok["Dijkstra"] += all(abs(d[k] - v) < 1e-9 for k, v in ref.items())
        ok["Bellman-Ford"] += all(abs(b[k] - v) < 1e-9 for k, v in ref.items())
        ok["Floyd-Warshall"] += all(abs(fw.distancia("N0", k) - v) < 1e-9 for k, v in ref.items())
        t_ = f"N{n - 1}"
        fv = nx.maximum_flow_value(G, "N0", t_)
        ok["Edmonds-Karp"] += abs(edmonds_karp(red_desde_grafo(g), "N0", t_).valor - fv) < 1e-6
        ok["Dinic"] += abs(dinic(red_desde_grafo(g), "N0", t_).valor - fv) < 1e-6
        ok["Tarjan"] += (sorted(sorted(c) for c in tarjan_scc(g))
                         == sorted(sorted(c) for c in nx.strongly_connected_components(G)))
        ok["BFS"] += bfs(g, "N0")[0] == nx.single_source_shortest_path_length(G, "N0")
        U = nx.Graph()
        gu = Grafo(dirigido=False, multiple=True)
        for x in g.nodos:
            gu.agregar_nodo(x)
        for a in g.aristas():
            gu.agregar_arista(a.origen, a.destino, canal=a.id, peso=a["peso"])
            if not U.has_edge(a.origen, a.destino) or U[a.origen][a.destino]["weight"] > a["peso"]:
                U.add_edge(a.origen, a.destino, weight=a["peso"])
        mst_ref = sum(dd["weight"] for *_, dd in nx.minimum_spanning_edges(U, data=True))
        ok["Kruskal"] += abs(kruskal(gu, _peso)[1] - mst_ref) < 1e-6
        ok["Prim"] += abs(prim(gu, _peso)[1] - mst_ref) < 1e-6
    return [{"algoritmo": k, "pruebas": pruebas, "coinciden": v, "estado": "✔" if v == pruebas else "✘"}
            for k, v in ok.items()]


# --------------------------------------------------------------------------
# Casos de prueba de los escenarios (esperado vs obtenido)
# --------------------------------------------------------------------------
def casos_de_prueba() -> list[dict[str, Any]]:
    from .analisis_transacciones import AnalizadorTransacciones, evaluar_contra_patrones
    from .distribucion_liquidez import PlanificadorLiquidez, cargar_escenarios
    from .enrutamiento_financiero import Enrutador
    from .gestion_red import GestorRedes, cargar_red, importar

    filas: list[dict[str, Any]] = []

    def caso(modulo, nombre, entrada, condicion, esperado, obtenido, ok=None):
        filas.append({"modulo": modulo, "caso": nombre, "entrada": entrada, "condicion_inicial": condicion,
                      "esperado": str(esperado), "obtenido": str(obtenido),
                      "estado": "✔" if (ok if ok is not None else str(esperado) == str(obtenido)) else "✘"})

    # ---------------- Módulo 1
    g, err = importar((DATA_DIR / "ejemplo_minimo.csv").read_text(encoding="utf-8"), "csv")
    caso("M1", "Carga CSV mínimo (formato de la guía)", "ejemplo_minimo.csv", "archivo válido",
         "5 nodos, 5 aristas, 0 errores", f"{g.num_nodos} nodos, {g.num_aristas} aristas, {len(err)} errores")
    _, err = importar((DATA_DIR / "ejemplo_con_errores.csv").read_text(encoding="utf-8"), "csv")
    caso("M1", "Validación de datos inválidos", "ejemplo_con_errores.csv",
         "duplicada, bucle, negativa, riesgo>1, destino vacío", "5 errores detectados", f"{len(err)} errores detectados")
    gest = GestorRedes().cargar_todas()
    r1 = gest.agregar_nodo("ejemplo", "ATM_02", "atm", nombre="Cajero nuevo")
    r2 = gest.agregar_arista("ejemplo", "AG_IQT", "ATM_02", comision_fija=0.0)
    r3 = gest.agregar_arista("ejemplo", "AG_IQT", "NO_EXISTE")
    r4 = gest.eliminar_nodo("ejemplo", "ATM_02")
    caso("M1", "Alta/baja de nodos y aristas", "ATM_02 + AG_IQT→ATM_02 + arista a nodo inexistente",
         "red_ejemplo.json", "ok, ok, rechazada, ok", ", ".join(["ok" if r.ok else "rechazada" for r in (r1, r2, r3, r4)]))
    caso("M1", "Consistencia de redes del proyecto", "4 redes de data/", "carga inicial", "0 errores",
         f"{sum(1 for g in gest.redes.values() for h in g.validar() if h['nivel'] == 'error')} errores")

    # ---------------- Módulo 2
    gt = cargar_red("transacciones")
    patrones = json.loads((DATA_DIR / "patrones_plantados.json").read_text(encoding="utf-8"))
    semilla = next(p["cuenta_reportada"] for p in patrones["patrones"] if p["id"] == "P2")
    res = AnalizadorTransacciones(gt).analisis_completo(semilla)
    for fila in evaluar_contra_patrones(res, patrones):
        if fila["patron"] == "—":
            caso("M2", "Falsos positivos (riesgo alto/medio fuera de patrones)", "transacciones.csv",
                 "404 cuentas, 2711 transferencias", "0", fila["detectadas_por_su_regla"])
        else:
            caso("M2", f"Patrón {fila['patron']} ({fila['tipo']})", "transacciones.csv",
                 f"{fila['cuentas_plantadas']} cuentas plantadas", "DETECTADO", fila["resultado"])
    rastreo = AnalizadorTransacciones(gt).rastrear_fondos(patrones["patrones"][3]["origen"], max_saltos=8,
                                                         monto_minimo=20000)
    mulas = patrones["patrones"][3]["cuentas"]
    caso("M2", "Rastreo cronológico de fondos", f"origen {patrones['patrones'][3]['origen']}, monto ≥ 20 000",
         "cadena de 6 mulas", f"alcanza a {mulas[-1]}", f"alcanza a {mulas[-1]}" if mulas[-1] in
         [f['cuenta'] for f in rastreo['filas']] else "no alcanza")

    # ---------------- Módulo 3
    E = Enrutador(cargar_red("enrutamiento"))
    r = E.ruta_optima("AG_LIM", "CORR_CAB", 1500)
    caso("M3", "Comisión mínima Lima→Caballococha", "S/ 1 500, criterio comisión", "red completa",
         "S/ 5.75 vía billeteras", f"S/ {r.comision:.2f} vía {'billeteras' if 'BILL_A' in r.nodos else '/'.join(r.nodos)}")
    r = E.ruta_optima("AG_LIM", "CORR_CAB", 5000)
    caso("M3", "Límite de billetera excedido", "S/ 5 000", "billeteras limitadas a S/ 2 000",
         "S/ 18.50 vía CCE diferida", f"S/ {r.comision:.2f} vía {'CCE ' + r.aristas[0].get('canal') if r.existe else '—'}")
    r = E.ruta_optima("AG_LIM", "CORR_CAB", 25000)
    caso("M3", "Monto mayor a todos los límites", "S/ 25 000", "corresponsal admite S/ 5 000",
         "sin ruta", "sin ruta" if not r.existe else "con ruta")
    r = E.ruta_optima("AG_LIM", "CORR_CAB", 800, cerrar_nodos=["CMS_IQT"])
    caso("M3", "Sucursal cerrada (Caja Selva en mantenimiento)", "S/ 800, CMS_IQT cerrado", "nodo cerrado",
         "S/ 13.00 vía BILL_A", f"S/ {r.comision:.2f} vía {r.nodos[1] if r.existe else '—'}")
    r = E.ruta_optima("AG_LIM", "CORR_CAB", 1500, promocion="promo_interoperabilidad")
    caso("M3", "Promoción mal diseñada", "S/ 1 500, bonificaciones A↔B", "pesos negativos",
         "Bellman-Ford detecta ciclo negativo", f"{r.algoritmo} " + ("detecta ciclo negativo" if r.ciclo_negativo else "sin ciclo"),
         ok=r.algoritmo == "bellman_ford" and bool(r.ciclo_negativo))
    gm, _ = importar((DATA_DIR / "ejemplo_minimo.csv").read_text(encoding="utf-8"), "csv")
    d = dijkstra(gm, "CuentaA", lambda a: a["comision"])
    caso("M3", "Ejemplo de la guía CuentaA→CuentaE", "ejemplo_minimo.csv", "comisiones fijas",
         "6.0 (A→C→D→E)", f"{d.dist['CuentaE']} ({'→'.join(x[-1] for x in ['CuentaA'] + [a.destino for a in d.camino('CuentaE')])})")

    # ---------------- Módulo 4
    P = PlanificadorLiquidez(cargar_red("liquidez"))
    esc = cargar_escenarios()
    rn = P.calcular(esc["normal"])
    caso("M4", "Flujo máximo escenario normal", "distribucion_liquidez.csv", "ríos en nivel medio",
         "S/ 120 000 mil (EK = Dinic = costo mín.)",
         f"S/ {rn.flujo_maximo:,.0f} mil ({'EK = Dinic = costo mín.' if rn.verificacion['mismo_flujo_EK_Dinic_CostoMin'] else 'difieren'})".replace(",", " "))
    caso("M4", "Restricciones de la distribución", "escenario normal", "capacidades y demandas",
         "todas se cumplen", "todas se cumplen" if all(rn.verificacion.values()) else str(rn.verificacion))
    rv = P.calcular(esc["vuelo_cancelado"])
    caso("M4", "Vuelo Lima–Iquitos cancelado", "arista L024 cerrada", "escenario normal",
         "flujo baja en S/ 8 000 mil", f"flujo baja en S/ {rn.flujo_maximo - rv.flujo_maximo:,.0f} mil".replace(",", " "))
    criticos = [c["id"] for c in rn.cuellos_botella if c.get("ganancia_si_amplia_20pct", 0) > 0]
    caso("M4", "Cuello de botella hacia Loreto", "corte mínimo", "escenario normal",
         "incluye L024 (aéreo Lima–Iquitos)", "incluye L024 (aéreo Lima–Iquitos)" if "L024" in criticos else str(criticos))
    caso("M4", "Política equitativa", "escenario normal", "demanda > capacidad hacia Loreto",
         "toda agencia ≥ 80 % de su demanda",
         f"mínimo {min(a['cobertura_pct'] for a in rn.agencias)} %",
         ok=min(a["cobertura_pct"] for a in rn.agencias) >= 80)

    # ---------------- Módulo 5
    gneg = Grafo("neg", multiple=False)
    for x in "SAB":
        gneg.agregar_nodo(x)
    gneg.agregar_arista("S", "A", w=2.0)
    gneg.agregar_arista("S", "B", w=3.0)
    gneg.agregar_arista("B", "A", w=-2.0)
    pd = dijkstra(gneg, "S", lambda a: a["w"], verificar_negativos=False).dist["A"]
    pb = bellman_ford(gneg, "S", lambda a: a["w"]).dist["A"]
    caso("M5", "Dijkstra con peso negativo (contraejemplo)", "S→A 2, S→B 3, B→A −2", "peso negativo",
         "Dijkstra 2 ≠ Bellman-Ford 1", f"Dijkstra {pd:g} ≠ Bellman-Ford {pb:g}", ok=(pd == 2 and pb == 1))
    val = validar_con_networkx(pruebas=8)
    caso("M5", "Validación cruzada con NetworkX", "8 redes aleatorias", "9 algoritmos",
         "todos coinciden", "todos coinciden" if all(v.get("estado") == "✔" for v in val) else "hay diferencias")
    return filas
