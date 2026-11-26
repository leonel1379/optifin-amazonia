"""
Módulo 3 — Optimización del enrutamiento de operaciones financieras y
cálculo de comisiones.

Modelo: multigrafo DIRIGIDO.  Nodos = agencias, cámara de compensación,
billeteras, procesador de tarjetas, red de cajeros, entidades y agentes
corresponsales.  Aristas = canales de operación (interplaza, interbancaria
diferida o inmediata, billetera, tarjeta, ATM...) con atributos:
    comision_fija (S/), comision_pct (% del monto), tiempo_min, riesgo
    (probabilidad de falla), limite (monto máximo por operación) y
    bonificacion (cashback promocional, opcional).

Peso de una arista para un monto M:
    comisión = comision_fija + comision_pct/100 · M  (− bonificación si hay promoción)
    tiempo   = tiempo_min
    riesgo   = −ln(1 − riesgo)  → al sumar se minimiza la probabilidad de falla
               total 1 − ∏(1 − r_i) (transformación logarítmica que mantiene pesos ≥ 0)
Si M supera el límite del canal, la arista no se puede usar (restricción de servicio).

Algoritmo principal: DIJKSTRA (pesos ≥ 0, consulta origen-destino).
Bellman-Ford solo si hay pesos negativos (promociones); Floyd-Warshall solo
para la matriz completa de costos entre agencias.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from .algoritmos.caminos_minimos import (INF, bellman_ford, costo_camino, dijkstra,
                                         floyd_warshall, nodos_de_camino,
                                         rutas_backtracking, yen_k_rutas)
from .graph import Arista, Grafo
from .utils import medir

CRITERIOS = {
    "comision": "Comisión total (S/)",
    "tiempo": "Tiempo de procesamiento (min)",
    "riesgo": "Riesgo operativo (probabilidad de falla)",
    "combinado": "Combinado (comisión + tiempo + riesgo normalizados)",
}

PROMOCIONES = {
    "ninguna": set(),
    "cashback_recarga": {"recarga"},
    "promo_interoperabilidad": {"recarga", "interoperabilidad"},
}
DESCRIPCION_PROMOCIONES = {
    "ninguna": "Tarifario normal: todas las comisiones son ≥ 0.",
    "cashback_recarga": "Bonificación de S/ 3 por recargar la billetera A: aparece un peso negativo.",
    "promo_interoperabilidad": "Además, S/ 1.50 por cada envío entre billeteras A↔B: se forma un "
                               "ciclo negativo (la promoción se puede explotar indefinidamente).",
}


@dataclass
class ResultadoRuta:
    origen: str
    destino: str
    monto: float
    criterio: str
    algoritmo: str
    nodos: list[str]
    aristas: list[Arista]
    valor_criterio: float
    comision: float
    tiempo_min: float
    riesgo: float
    tiempo_ejecucion_ms: float
    justificacion: str = ""
    estadisticas: dict[str, Any] = field(default_factory=dict)
    ciclo_negativo: list[str] | None = None
    motivo_sin_ruta: str = ""

    @property
    def existe(self) -> bool:
        return bool(self.aristas)

    def a_dict(self) -> dict[str, Any]:
        return {"algoritmo": self.algoritmo, "ruta": self.nodos, "saltos": len(self.aristas),
                "canales": [f"{a.get('tipo_operacion')}/{a.get('canal')}" for a in self.aristas],
                "comision_S/": round(self.comision, 2), "tiempo_min": round(self.tiempo_min, 1),
                "prob_falla_%": round(100 * self.riesgo, 3),
                "valor_criterio": round(self.valor_criterio, 4),
                "tiempo_ejecucion_ms": round(self.tiempo_ejecucion_ms, 4)}


class Enrutador:
    def __init__(self, g: Grafo) -> None:
        self.g = g

    # ---------------------------------------------------------- pesos
    def comision_arista(self, a: Arista, monto: float, promocion: str = "ninguna") -> float:
        c = float(a.get("comision_fija", 0) or 0) + float(a.get("comision_pct", 0) or 0) / 100 * monto
        if a.get("canal") in PROMOCIONES.get(promocion, set()):
            c -= float(a.get("bonificacion", 0) or 0)
        return c

    def disponible(self, a: Arista, monto: float) -> bool:
        limite = a.get("limite")
        return limite is None or monto <= float(limite)

    def peso_fn(self, criterio: str, monto: float, promocion: str = "ninguna",
                pesos: tuple[float, float, float] = (0.5, 0.3, 0.2)) -> Callable[[Arista], float | None]:
        if criterio not in CRITERIOS:
            raise ValueError(f"Criterio desconocido '{criterio}'. Opciones: {list(CRITERIOS)}")

        def log_riesgo(a: Arista) -> float:
            r = min(float(a.get("riesgo", 0) or 0), 0.999999)
            return -math.log1p(-r)

        if criterio == "comision":
            return lambda a: self.comision_arista(a, monto, promocion) if self.disponible(a, monto) else None
        if criterio == "tiempo":
            return lambda a: float(a.get("tiempo_min", 0) or 0) if self.disponible(a, monto) else None
        if criterio == "riesgo":
            return lambda a: log_riesgo(a) if self.disponible(a, monto) else None

        usables = [a for a in self.g.aristas(incluir_inactivas=False) if self.disponible(a, monto)] or [None]
        cmax = max((abs(self.comision_arista(a, monto)) for a in usables if a), default=1) or 1
        tmax = max((float(a.get("tiempo_min", 0) or 0) for a in usables if a), default=1) or 1
        rmax = max((log_riesgo(a) for a in usables if a), default=1) or 1
        wc, wt, wr = pesos

        def combinado(a: Arista) -> float | None:
            if not self.disponible(a, monto):
                return None
            return (wc * self.comision_arista(a, monto, promocion) / cmax
                    + wt * float(a.get("tiempo_min", 0) or 0) / tmax + wr * log_riesgo(a) / rmax)
        return combinado

    def tiene_pesos_negativos(self, peso: Callable[[Arista], float | None]) -> list[Arista]:
        return [a for a in self.g.aristas(incluir_inactivas=False) if (w := peso(a)) is not None and w < 0]

    # ----------------------------------------------- métricas de una ruta
    def metricas(self, aristas: list[Arista], monto: float, promocion: str = "ninguna") -> dict[str, float]:
        com = sum(self.comision_arista(a, monto, promocion) for a in aristas)
        tiempo = sum(float(a.get("tiempo_min", 0) or 0) for a in aristas)
        exito = 1.0
        for a in aristas:
            exito *= 1 - float(a.get("riesgo", 0) or 0)
        return {"comision": com, "tiempo_min": tiempo, "riesgo": 1 - exito}

    # ------------------------------------------- selección justificada
    def seleccionar_algoritmo(self, peso: Callable[[Arista], float | None],
                              todos_los_pares: bool = False) -> tuple[str, str]:
        V = len(self.g.ids_nodos(solo_activos=True))
        E = len(self.g.aristas(incluir_inactivas=False))
        negativos = self.tiene_pesos_negativos(peso)
        if negativos:
            ej = negativos[0]
            return "bellman_ford", (
                f"Se detectaron {len(negativos)} arista(s) con peso negativo por bonificaciones "
                f"(p. ej. {ej.origen}→{ej.destino}). Dijkstra asume que la distancia de un nodo extraído "
                f"de la cola es definitiva, lo cual deja de ser cierto con pesos negativos. Bellman-Ford "
                f"los admite y además detecta ciclos negativos. Costo: O(V·E) = {V}·{E} = {V * E} relajaciones "
                f"en el peor caso.")
        if todos_los_pares:
            return "floyd_warshall", (
                f"Se piden los costos entre todos los pares: Floyd-Warshall resuelve la matriz completa en "
                f"O(V³) = {V}³ = {V ** 3} operaciones con un código simple. Ejecutar Dijkstra V veces "
                f"(O(V·(V+E)·log V)) también es válido; para V = {V} la diferencia es despreciable.")
        cota = (V + E) * max(1, math.ceil(math.log2(max(V, 2))))
        return "dijkstra", (
            f"Todos los pesos son ≥ 0 (comisiones, tiempos y −ln(1−riesgo) nunca son negativos) y la "
            f"consulta es de un origen a un destino. Dijkstra con montículo binario cuesta "
            f"O((V+E)·log V) ≈ {cota} operaciones (V = {V}, E = {E}) y puede detenerse al extraer el "
            f"destino. Bellman-Ford necesitaría hasta V·E = {V * E} relajaciones sin aportar nada "
            f"(no hay pesos negativos) y Floyd-Warshall O(V³) = {V ** 3} calcularía todos los pares "
            f"innecesariamente.")

    # ----------------------------------------------------- consultas
    def _red(self, cerrar_nodos: Iterable[str] = (), cerrar_aristas: Iterable[str] = ()) -> Grafo:
        cerrar_nodos, cerrar_aristas = list(cerrar_nodos), list(cerrar_aristas)
        if not cerrar_nodos and not cerrar_aristas:
            return self.g
        g = self.g.copia()
        for n in cerrar_nodos:
            g.cerrar_nodo(n)
        for a in cerrar_aristas:
            g.cerrar_arista(a)
        return g

    def ruta_optima(self, origen: str, destino: str, monto: float, criterio: str = "comision",
                    algoritmo: str = "auto", promocion: str = "ninguna",
                    cerrar_nodos: Iterable[str] = (), cerrar_aristas: Iterable[str] = (),
                    pesos: tuple[float, float, float] = (0.5, 0.3, 0.2)) -> ResultadoRuta:
        g = self._red(cerrar_nodos, cerrar_aristas)
        sub = Enrutador(g)
        peso = sub.peso_fn(criterio, monto, promocion, pesos)
        justificacion = ""
        if algoritmo == "auto":
            algoritmo, justificacion = sub.seleccionar_algoritmo(peso)
        ciclo = None
        if algoritmo == "dijkstra":
            res, ms, _ = medir(lambda: dijkstra(g, origen, peso, destino,
                                                verificar_negativos=False))
            camino, stats = res.camino(destino), res.estadisticas
        elif algoritmo == "bellman_ford":
            res, ms, _ = medir(lambda: bellman_ford(g, origen, peso))
            stats = res.estadisticas
            if res.ciclo_negativo:
                ciclo = nodos_de_camino(res.ciclo_negativo[0].origen, res.ciclo_negativo)
                camino = []
            else:
                camino = res.camino(destino)
        elif algoritmo == "floyd_warshall":
            res, ms, _ = medir(lambda: floyd_warshall(g, peso))
            camino = [] if res.ciclo_negativo else res.camino(origen, destino)
            stats = {"operaciones": len(res.nodos) ** 3}
        elif algoritmo == "backtracking":
            (rutas, stats), ms, _ = medir(lambda: rutas_backtracking(g, origen, destino, peso, max_saltos=10,
                                                                     solo_mejor=True, max_rutas=10 ** 6))
            camino = rutas[0][1] if rutas else []
        else:
            raise ValueError(f"Algoritmo desconocido '{algoritmo}'.")
        m = sub.metricas(camino, monto, promocion)
        valor = costo_camino(camino, peso) if camino else INF
        if criterio == "riesgo" and camino:
            valor = m["riesgo"]
        motivo = ""
        if not camino:
            if ciclo:
                motivo = ("Existe un ciclo de costo negativo: la promoción permite ganar dinero dando "
                          "vueltas, por lo que el 'costo mínimo' no está definido.")
            else:
                alcanzable = dijkstra(g, origen, lambda a: 1.0, destino)
                if destino in alcanzable.dist:
                    limites = sorted({float(a.get('limite')) for _, a in g.predecesores(destino)
                                      if a.get('limite') is not None}, reverse=True)
                    motivo = (f"Hay conexión física, pero el monto S/ {monto:,.2f} supera el límite "
                              f"transaccional de los canales disponibles (máximo de llegada al destino: "
                              f"S/ {limites[0]:,.0f})." if limites else "El monto excede los límites de los canales.")
                else:
                    motivo = "No existe conexión entre origen y destino con los nodos y rutas abiertos."
        return ResultadoRuta(origen, destino, monto, criterio, algoritmo,
                             nodos_de_camino(origen, camino) if camino else [], camino, valor,
                             m["comision"], m["tiempo_min"], m["riesgo"], ms, justificacion, stats, ciclo, motivo)

    def comparar_algoritmos(self, origen: str, destino: str, monto: float, criterio: str = "comision",
                            promocion: str = "ninguna", cerrar_nodos: Iterable[str] = (),
                            cerrar_aristas: Iterable[str] = ()) -> list[dict[str, Any]]:
        """Ejecuta los 4 enfoques sobre la misma consulta para el análisis comparativo (Módulo 5)."""
        filas = []
        referencia = None
        negativos = bool(Enrutador(self._red(cerrar_nodos, cerrar_aristas)).tiene_pesos_negativos(
            self.peso_fn(criterio, monto, promocion)))
        for alg in ("dijkstra", "bellman_ford", "floyd_warshall", "backtracking"):
            r = self.ruta_optima(origen, destino, monto, criterio, alg, promocion, cerrar_nodos, cerrar_aristas)
            if alg == "bellman_ford":
                referencia = r.valor_criterio
            d = r.a_dict()
            d["operaciones"] = sum(v for v in r.estadisticas.values() if isinstance(v, (int, float)))
            if r.ciclo_negativo:
                d["observacion"] = "ciclo negativo: " + " → ".join(r.ciclo_negativo)
            elif alg == "floyd_warshall" and negativos and not r.existe:
                d["observacion"] = "ciclo negativo (diagonal de la matriz < 0)"
            elif alg == "dijkstra" and negativos:
                d["observacion"] = "sin garantía de optimalidad (hay pesos negativos)"
            elif alg == "backtracking":
                d["observacion"] = "exhaustivo con poda; exponencial en el peor caso"
            else:
                d["observacion"] = ""
            filas.append(d)
        for d in filas:
            d["coincide_con_optimo"] = (referencia is not None and referencia != INF and
                                        abs(d["valor_criterio"] - round(referencia, 4)) < 1e-3)
        return filas

    def rutas_alternativas(self, origen: str, destino: str, monto: float, criterio: str = "comision",
                           k: int = 5, promocion: str = "ninguna", cerrar_nodos: Iterable[str] = (),
                           cerrar_aristas: Iterable[str] = ()) -> list[dict[str, Any]]:
        """Top-k rutas simples (Yen). Si hubiera pesos negativos se usa el backtracking exhaustivo."""
        g = self._red(cerrar_nodos, cerrar_aristas)
        sub = Enrutador(g)
        peso = sub.peso_fn(criterio, monto, promocion)
        if sub.tiene_pesos_negativos(peso):
            rutas, _ = rutas_backtracking(g, origen, destino, peso, max_saltos=10)
            rutas = rutas[:k]
        else:
            rutas = yen_k_rutas(g, origen, destino, k, peso)
        filas = []
        for i, (costo, camino) in enumerate(rutas, start=1):
            m = sub.metricas(camino, monto, promocion)
            filas.append({"opcion": i, "ruta": nodos_de_camino(origen, camino), "saltos": len(camino),
                          "canales": [f"{a.get('tipo_operacion')}/{a.get('canal')}" for a in camino],
                          "comision_S/": round(m["comision"], 2), "tiempo_min": round(m["tiempo_min"], 1),
                          "prob_falla_%": round(100 * m["riesgo"], 3),
                          "valor_criterio": round(costo, 4), "aristas": [a.id for a in camino]})
        return filas

    def enumerar_alternativas(self, origen: str, destino: str, monto: float, max_saltos: int = 6,
                              cerrar_nodos: Iterable[str] = (), cerrar_aristas: Iterable[str] = ()
                              ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        """Todas las rutas disponibles (backtracking), ordenadas por comisión."""
        g = self._red(cerrar_nodos, cerrar_aristas)
        sub = Enrutador(g)
        peso = sub.peso_fn("comision", monto)
        rutas, stats = rutas_backtracking(g, origen, destino, peso, max_saltos=max_saltos)
        filas = []
        for costo, camino in rutas:
            m = sub.metricas(camino, monto)
            filas.append({"ruta": nodos_de_camino(origen, camino), "saltos": len(camino),
                          "comision_S/": round(m["comision"], 2), "tiempo_min": round(m["tiempo_min"], 1),
                          "prob_falla_%": round(100 * m["riesgo"], 3)})
        return filas, stats

    def matriz_costos(self, nodos: list[str], monto: float, criterio: str = "comision") -> dict[str, Any]:
        """Tarifario completo entre los nodos indicados (Floyd-Warshall sobre toda la red)."""
        peso = self.peso_fn(criterio, monto)
        res, ms, _ = medir(lambda: floyd_warshall(self.g, peso))
        idx = res.indice
        matriz = {u: {v: (None if res.dist[idx[u]][idx[v]] == INF else round(res.dist[idx[u]][idx[v]], 2))
                      for v in nodos if v in idx} for u in nodos if u in idx}
        return {"matriz": matriz, "tiempo_ms": ms, "nodos_red": len(res.nodos)}

    def impacto_cierre(self, origen: str, destino: str, monto: float, criterio: str,
                       cerrar_nodos: Iterable[str] = (), cerrar_aristas: Iterable[str] = ()) -> dict[str, Any]:
        antes = self.ruta_optima(origen, destino, monto, criterio)
        despues = self.ruta_optima(origen, destino, monto, criterio, cerrar_nodos=cerrar_nodos,
                                   cerrar_aristas=cerrar_aristas)
        return {"antes": antes, "despues": despues,
                "incremento_comision": (despues.comision - antes.comision) if despues.existe else None,
                "incremento_tiempo": (despues.tiempo_min - antes.tiempo_min) if despues.existe else None,
                "sin_ruta": not despues.existe}


def nodos_criticos(g: Grafo, origen: str) -> list[dict[str, Any]]:
    """
    Simula el cierre de cada nodo (mantenimiento, sucursal cerrada) y mide cuántos
    puntos de la red quedan inalcanzables desde `origen`.  Un BFS por nodo:
    O(V · (V + E)).  Identifica los puntos únicos de falla de la red.
    """
    from .algoritmos.recorridos import bfs
    base, _ = bfs(g, origen)
    filas = []
    for n in g.ids_nodos(solo_activos=True):
        if n == origen:
            continue
        nivel, _ = bfs(g, origen, filtro=lambda a, n=n: a.destino != n and a.origen != n)
        perdidos = sorted(set(base) - set(nivel) - {n})
        if perdidos:
            filas.append({"nodo_cerrado": n, "nombre": g.nodos[n].nombre, "tipo": g.nodos[n].tipo,
                          "puntos_aislados": len(perdidos), "aislados": ", ".join(perdidos)})
    filas.sort(key=lambda f: -f["puntos_aislados"])
    return filas
