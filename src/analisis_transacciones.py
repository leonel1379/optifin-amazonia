"""
Módulo 2 — Análisis de transacciones y detección de operaciones sospechosas
(prevención de fraude y lavado de activos).

Modelo: grafo DIRIGIDO multigrafo.  Nodo = cuenta (persona o empresa).
Arista = transferencia origen -> destino con monto, fecha, canal y concepto.
Se usa multigrafo porque dos cuentas pueden transferirse varias veces y
cada operación es evidencia distinta.

Algoritmos elegidos (todos lineales o casi lineales en |V| + |E|):
  * BFS ............ niveles de proximidad / relaciones indirectas (saltos mínimos).
  * Búsqueda temporal tipo Dijkstra sobre el tiempo de llegada .... rastreo
    cronológico del dinero ("follow the money").
  * Tarjan (SCC) ... grupos donde el dinero puede circular; poda la búsqueda de ciclos.
  * DFS acotada .... ciclos cronológicos de montos similares (round-tripping).
  * Ventanas deslizantes sobre listas de adyacencia (entrantes / salientes) ....
    fragmentación (pitufeo), dispersión y cuentas puente.

IMPORTANTE: los resultados son INDICADORES para revisión del oficial de
cumplimiento; la detección computacional no constituye prueba de delito.
"""

from __future__ import annotations

import heapq
import itertools
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from .algoritmos.recorridos import bfs, camino_desde_pred, ciclos_acotados, tarjan_scc
from .graph import Arista, Grafo

HORA = 3600.0
DIA = 24 * HORA


@dataclass
class ConfigAnalisis:
    umbral_reporte: float = 10000.0          # umbral simulado de reporte de operaciones (S/)
    margen_fragmentacion: float = 0.15       # montos en [umbral·(1-margen), umbral)
    ventana_fragmentacion_dias: float = 7.0
    min_emisores_fragmentacion: int = 5
    max_longitud_ciclo: int = 6
    ventana_ciclo_dias: float = 10.0
    tolerancia_monto_ciclo: float = 0.10     # variación máxima entre montos consecutivos
    monto_minimo_ciclo: float = 5000.0
    ventana_puente_horas: float = 24.0
    ratio_puente: float = 0.85               # % mínimo del monto que se reenvía
    monto_minimo_puente: float = 5000.0
    ventana_dispersion_dias: float = 5.0
    min_receptores_dispersion: int = 10
    conceptos_legitimos: tuple[str, ...] = ("planilla",)
    monto_minimo_grupo: float = 5000.0
    min_tamano_grupo: int = 3


def _fmt_fecha(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


class AnalizadorTransacciones:
    def __init__(self, g: Grafo, config: ConfigAnalisis | None = None) -> None:
        self.g = g
        self.cfg = config or ConfigAnalisis()
        self.ts: dict[str, float] = {}
        for a in g.aristas():
            f = a.get("fecha")
            self.ts[a.id] = datetime.fromisoformat(str(f)).timestamp() if f else 0.0

    # ----------------------------------------------------------- helpers
    def _monto(self, a: Arista) -> float:
        return float(a.get("monto", 0) or 0)

    def _info(self, cid: str) -> dict[str, Any]:
        n = self.g.nodos[cid]
        return {"cuenta": cid, "titular": n.nombre, "ciudad": n.get("ciudad", ""), "tipo": n.tipo}

    def _subgrafo(self, monto_minimo: float) -> Grafo:
        """Subred con transferencias >= monto_minimo (las de bajo monto no aportan a esquemas de capas)."""
        sub = Grafo("sub", dirigido=True, multiple=True)
        for a in self.g.aristas(incluir_inactivas=False):
            if self._monto(a) >= monto_minimo:
                for x in (a.origen, a.destino):
                    if x not in sub.nodos:
                        n = self.g.nodos[x]
                        sub.agregar_nodo(x, n.tipo, n.nombre)
                sub.agregar_arista(a.origen, a.destino, a.id, **a.atributos)
        return sub

    # ---------------------------------------------- relaciones / BFS
    def relaciones(self, cuenta: str, max_nivel: int = 3) -> list[dict[str, Any]]:
        """Relaciones directas (nivel 1) e indirectas (nivel ≥ 2) sin importar el sentido del dinero."""
        nivel, pred = bfs(self.g, cuenta, max_nivel=max_nivel, no_dirigido=True)
        filas = []
        for cid, k in sorted(nivel.items(), key=lambda x: (x[1], x[0])):
            if cid == cuenta:
                continue
            camino = camino_desde_pred(pred, cuenta, cid)
            nodos = [cuenta]
            for a in camino:
                nodos.append(a.otro_extremo(nodos[-1]))
            filas.append({**self._info(cid), "nivel": k,
                          "relacion": "directa" if k == 1 else "indirecta", "via": nodos})
        return filas

    def proximidad(self, a: str, b: str) -> dict[str, Any]:
        """Distancia mínima en saltos entre dos cuentas (BFS no dirigido) y el camino que las une."""
        nivel, pred = bfs(self.g, a, no_dirigido=True)
        if b not in nivel:
            return {"cuenta_a": a, "cuenta_b": b, "saltos": None, "camino": []}
        camino = camino_desde_pred(pred, a, b)
        nodos = [a]
        for x in camino:
            nodos.append(x.otro_extremo(nodos[-1]))
        return {"cuenta_a": a, "cuenta_b": b, "saltos": nivel[b], "camino": nodos,
                "transferencias": [x.id for x in camino]}

    # ------------------------------------------- rastreo cronológico
    def rastrear_fondos(self, origen: str, desde: str | None = None, max_saltos: int = 6,
                        monto_minimo: float = 1000.0) -> dict[str, Any]:
        """
        Árbol de llegada más temprana: el dinero solo puede avanzar por una
        transferencia posterior a la que lo trajo a la cuenta.  Es Dijkstra
        con la "distancia" = instante de llegada.  O(E log V).
        """
        t0 = datetime.fromisoformat(desde).timestamp() if desde else 0.0
        llegada = {origen: t0}
        saltos = {origen: 0}
        pred: dict[str, Arista | None] = {origen: None}
        cont = itertools.count()
        heap = [(t0, next(cont), origen)]
        hecho = set()
        while heap:
            t, _, u = heapq.heappop(heap)
            if u in hecho:
                continue
            hecho.add(u)
            if saltos[u] >= max_saltos:
                continue
            for v, a in self.g.vecinos(u):
                ta = self.ts[a.id]
                if ta < t or self._monto(a) < monto_minimo:
                    continue
                if ta < llegada.get(v, float("inf")):
                    llegada[v] = ta
                    saltos[v] = saltos[u] + 1
                    pred[v] = a
                    heapq.heappush(heap, (ta, next(cont), v))
        hijos: dict[str, int] = defaultdict(int)
        for v, a in pred.items():
            if a is not None:
                hijos[a.origen] += 1
        filas = []
        for v in sorted(llegada, key=lambda x: (saltos[x], llegada[x])):
            if v == origen:
                continue
            a = pred[v]
            camino = camino_desde_pred(pred, origen, v)
            nodos = [origen] + [x.destino for x in camino]
            filas.append({**self._info(v), "saltos": saltos[v], "llegada": _fmt_fecha(llegada[v]),
                          "monto_recibido": round(self._monto(a), 2), "desde": a.origen,
                          "transferencia": a.id,
                          "rol": "intermediario" if hijos.get(v) else "receptor final",
                          "ruta": nodos})
        return {"origen": origen, "alcanzadas": len(filas),
                "intermediarios": [f["cuenta"] for f in filas if f["rol"] == "intermediario"],
                "receptores_finales": [f["cuenta"] for f in filas if f["rol"] == "receptor final"],
                "filas": filas,
                "aristas_arbol": [a.id for a in pred.values() if a is not None]}

    # ------------------------------------------------------- ciclos
    def detectar_ciclos(self) -> list[dict[str, Any]]:
        c = self.cfg
        sub = self._subgrafo(c.monto_minimo_ciclo)
        ventana = c.ventana_ciclo_dias * DIA

        def paso(prev: Arista | None, sig: Arista) -> bool:
            if prev is None:
                return True
            dt = self.ts[sig.id] - self.ts[prev.id]
            if dt < 0 or dt > ventana:
                return False
            r = self._monto(sig) / self._monto(prev)
            return 1 - c.tolerancia_monto_ciclo <= r <= 1 + c.tolerancia_monto_ciclo / 2

        resultados = []
        for comp in tarjan_scc(sub):
            if len(comp) < 3:
                continue
            for ciclo in ciclos_acotados(sub, comp, c.max_longitud_ciclo, paso, canonico=False):
                dur = self.ts[ciclo[-1].id] - self.ts[ciclo[0].id]
                if dur > ventana:
                    continue
                inicial, final = self._monto(ciclo[0]), self._monto(ciclo[-1])
                resultados.append({
                    "cuentas": [a.origen for a in ciclo] + [ciclo[0].origen],
                    "longitud": len(ciclo), "monto_inicial": round(inicial, 2),
                    "monto_final": round(final, 2),
                    "retencion_pct": round(100 * (1 - final / inicial), 2),
                    "inicio": _fmt_fecha(self.ts[ciclo[0].id]),
                    "duracion_h": round(dur / HORA, 1),
                    "transferencias": [a.id for a in ciclo]})
        resultados.sort(key=lambda r: -r["monto_inicial"])
        return resultados

    # ------------------------------------------- fragmentación (pitufeo)
    def detectar_fragmentacion(self) -> list[dict[str, Any]]:
        c = self.cfg
        lo, hi = c.umbral_reporte * (1 - c.margen_fragmentacion), c.umbral_reporte
        ventana = c.ventana_fragmentacion_dias * DIA
        resultados = []
        for v in self.g.ids_nodos(solo_activos=True):
            entr = sorted((a for _, a in self.g.predecesores(v) if lo <= self._monto(a) < hi),
                          key=lambda a: self.ts[a.id])
            if len(entr) < c.min_emisores_fragmentacion:
                continue
            mejor = None
            j = 0
            for i in range(len(entr)):
                while self.ts[entr[i].id] - self.ts[entr[j].id] > ventana:
                    j += 1
                bloque = entr[j:i + 1]
                emisores = {a.origen for a in bloque}
                if len(emisores) >= c.min_emisores_fragmentacion and (
                        mejor is None or len(bloque) > len(mejor)):
                    mejor = bloque
            if not mejor:
                continue
            total = sum(self._monto(a) for a in mejor)
            fin = self.ts[mejor[-1].id]
            salidas = [a for _, a in self.g.vecinos(v) if fin <= self.ts[a.id] <= fin + 7 * DIA]
            resultados.append({
                **self._info(v), "emisores": len({a.origen for a in mejor}), "operaciones": len(mejor),
                "total_recibido": round(total, 2), "monto_promedio": round(total / len(mejor), 2),
                "desde": _fmt_fecha(self.ts[mejor[0].id]), "hasta": _fmt_fecha(fin),
                "salida_posterior_7d": round(sum(self._monto(a) for a in salidas), 2),
                "destinos_posteriores": sorted({a.destino for a in salidas}),
                "lista_emisores": sorted({a.origen for a in mejor}),
                "transferencias": [a.id for a in mejor]})
        resultados.sort(key=lambda r: -r["total_recibido"])
        return resultados

    # ---------------------------------------------- cuentas puente
    def detectar_cuentas_puente(self) -> dict[str, Any]:
        c = self.cfg
        ventana = c.ventana_puente_horas * HORA
        enlaces = []   # (entrada, nodo, [salidas])
        for v in self.g.ids_nodos(solo_activos=True):
            salidas = sorted((a for _, a in self.g.vecinos(v)), key=lambda a: self.ts[a.id])
            if not salidas:
                continue
            for _, e in self.g.predecesores(v):
                m = self._monto(e)
                if m < c.monto_minimo_puente:
                    continue
                t = self.ts[e.id]
                dentro = [s for s in salidas if t < self.ts[s.id] <= t + ventana]
                enviado = sum(self._monto(s) for s in dentro)
                if c.ratio_puente * m <= enviado <= 1.05 * m:
                    enlaces.append((e, v, dentro, enviado))
        filas = []
        for e, v, dentro, enviado in enlaces:
            demora = (self.ts[dentro[-1].id] - self.ts[e.id]) / HORA
            filas.append({**self._info(v), "recibio": round(self._monto(e), 2), "de": e.origen,
                          "reenvio": round(enviado, 2),
                          "reenviado_pct": round(100 * enviado / self._monto(e), 1),
                          "demora_h": round(demora, 1), "hacia": sorted({s.destino for s in dentro}),
                          "fecha_entrada": _fmt_fecha(self.ts[e.id])})
        # encadenar: nodo puente -> siguiente nodo puente
        es_puente = {f["cuenta"] for f in filas}
        siguiente: dict[str, set[str]] = defaultdict(set)
        tiene_prev: set[str] = set()
        for f in filas:
            for h in f["hacia"]:
                if h in es_puente:
                    siguiente[f["cuenta"]].add(h)
                    tiene_prev.add(h)
        cadenas = []
        for inicio in sorted(es_puente - tiene_prev):
            pila = [[inicio]]
            while pila:
                cam = pila.pop()
                sig = [x for x in siguiente.get(cam[-1], ()) if x not in cam]
                if not sig:
                    if len(cam) >= 2:
                        # se agrega el receptor final de la cadena (el último que no reenvía)
                        finales = sorted({h for f in filas if f["cuenta"] == cam[-1]
                                          for h in f["hacia"] if h not in cam})
                        cadenas.append(cam + finales[:1])
                    continue
                for x in sig:
                    pila.append(cam + [x])
        cadenas.sort(key=len, reverse=True)
        return {"filas": sorted(filas, key=lambda f: -f["recibio"]), "cadenas": cadenas}

    # ------------------------------------------------------ dispersión
    def detectar_dispersion(self) -> list[dict[str, Any]]:
        c = self.cfg
        ventana = c.ventana_dispersion_dias * DIA
        resultados = []
        for u in self.g.ids_nodos(solo_activos=True):
            sal = sorted((a for _, a in self.g.vecinos(u) if a.get("concepto") not in c.conceptos_legitimos),
                         key=lambda a: self.ts[a.id])
            if len(sal) < c.min_receptores_dispersion:
                continue
            mejor = None
            j = 0
            for i in range(len(sal)):
                while self.ts[sal[i].id] - self.ts[sal[j].id] > ventana:
                    j += 1
                bloque = sal[j:i + 1]
                if len({a.destino for a in bloque}) >= c.min_receptores_dispersion and (
                        mejor is None or len(bloque) > len(mejor)):
                    mejor = bloque
            if mejor:
                total = sum(self._monto(a) for a in mejor)
                resultados.append({**self._info(u), "receptores": len({a.destino for a in mejor}),
                                   "operaciones": len(mejor), "total_enviado": round(total, 2),
                                   "desde": _fmt_fecha(self.ts[mejor[0].id]),
                                   "hasta": _fmt_fecha(self.ts[mejor[-1].id]),
                                   "lista_receptores": sorted({a.destino for a in mejor})})
        resultados.sort(key=lambda r: -r["total_enviado"])
        return resultados

    # --------------------------------------------------- grupos (SCC)
    def grupos_cerrados(self) -> list[dict[str, Any]]:
        c = self.cfg
        sub = self._subgrafo(c.monto_minimo_grupo)
        resultados = []
        for comp in tarjan_scc(sub):
            if len(comp) < c.min_tamano_grupo:
                continue
            miembros = set(comp)
            internas = [a for u in comp for v, a in sub.vecinos(u) if v in miembros]
            pares = {(a.origen, a.destino) for a in internas}
            k = len(comp)
            resultados.append({"cuentas": sorted(comp), "tamano": k, "transferencias_internas": len(internas),
                               "monto_interno": round(sum(self._monto(a) for a in internas), 2),
                               "densidad": round(len(pares) / (k * (k - 1)), 3),
                               "ciudades": sorted({self.g.nodos[x].get("ciudad", "") for x in comp})})
        resultados.sort(key=lambda r: (-r["densidad"], -r["monto_interno"]))
        return resultados

    # ------------------------------------------------- puntaje de riesgo
    def analisis_completo(self, semilla: str | None = None) -> dict[str, Any]:
        ciclos = self.detectar_ciclos()
        frag = self.detectar_fragmentacion()
        puente = self.detectar_cuentas_puente()
        disp = self.detectar_dispersion()
        grupos = self.grupos_cerrados()

        puntos: dict[str, int] = defaultdict(int)
        motivos: dict[str, set[str]] = defaultdict(set)

        def marcar(cid: str, p: int, motivo: str) -> None:
            if motivo not in motivos[cid]:
                puntos[cid] += p
                motivos[cid].add(motivo)

        for cy in ciclos:
            for cid in cy["cuentas"]:
                marcar(cid, 35, "ciclo de fondos")
        for f in frag:
            marcar(f["cuenta"], 40, "concentradora de pitufeo")
            for e in f["lista_emisores"]:
                marcar(e, 20, "emisor fraccionado bajo umbral")
        for f in puente["filas"]:
            marcar(f["cuenta"], 30, "cuenta puente (reenvío rápido)")
        for d in disp:
            marcar(d["cuenta"], 30, "dispersión masiva")
            for r in d["lista_receptores"]:
                marcar(r, 5, "receptor de dispersión")
        for gr in grupos:
            if gr["densidad"] >= 0.5:
                for cid in gr["cuentas"]:
                    marcar(cid, 30, "grupo cerrado denso")
            elif gr["densidad"] >= 0.2:
                for cid in gr["cuentas"]:
                    marcar(cid, 15, "grupo cerrado")
        # incompatibilidad con el perfil declarado
        for cid in list(puntos):
            n = self.g.nodos[cid]
            ingreso = float(n.get("ingreso_mensual", 0) or 0)
            movido = sum(self._monto(a) for _, a in self.g.predecesores(cid))
            if ingreso and movido > 10 * ingreso * 2:  # > 10 veces el ingreso de los 2 meses analizados
                marcar(cid, 15, "movimiento incompatible con ingreso declarado")
        proximidad = []
        if semilla and semilla in self.g.nodos:
            nivel, _ = bfs(self.g, semilla, max_nivel=2, no_dirigido=True)
            for cid, k in nivel.items():
                if k == 0:
                    marcar(cid, 40, "cuenta reportada")
                elif k == 1:
                    marcar(cid, 15, "vínculo directo con cuenta reportada")
                elif k == 2 and cid in puntos:
                    marcar(cid, 5, "vínculo indirecto con cuenta reportada")
            proximidad = [{"cuenta": c, "nivel": k} for c, k in sorted(nivel.items(), key=lambda x: x[1])]

        ranking = []
        for cid, p in puntos.items():
            p = min(p, 100)
            ranking.append({**self._info(cid), "puntaje": p,
                            "nivel_riesgo": "ALTO" if p >= 60 else "MEDIO" if p >= 30 else "BAJO",
                            "motivos": "; ".join(sorted(motivos[cid]))})
        ranking.sort(key=lambda r: (-r["puntaje"], r["cuenta"]))
        return {"ciclos": ciclos, "fragmentacion": frag, "puente": puente, "dispersion": disp,
                "grupos": grupos, "ranking": ranking, "proximidad_semilla": proximidad,
                "config": asdict(self.cfg)}


def evaluar_contra_patrones(resultado: dict[str, Any], patrones: dict[str, Any]) -> list[dict[str, Any]]:
    """Compara lo detectado con los patrones plantados (verdad de referencia)."""
    alto_medio = {r["cuenta"] for r in resultado["ranking"] if r["nivel_riesgo"] in {"ALTO", "MEDIO"}}
    detectados_tipo = {
        "ciclo": {c for cy in resultado["ciclos"] for c in cy["cuentas"]},
        "fragmentacion": {f["cuenta"] for f in resultado["fragmentacion"]}
                         | {e for f in resultado["fragmentacion"] for e in f["lista_emisores"]},
        "cadena_puente": {f["cuenta"] for f in resultado["puente"]["filas"]},
        "dispersion": {d["cuenta"] for d in resultado["dispersion"]},
        "grupo_cerrado": {c for gr in resultado["grupos"] for c in gr["cuentas"]},
    }
    filas = []
    for p in patrones["patrones"]:
        verdad = set(p["cuentas"])
        if p["tipo"] == "dispersion":
            verdad = {p["emisora"]}
        det = detectados_tipo.get(p["tipo"], set())
        acierto = verdad & det
        filas.append({"patron": p["id"], "tipo": p["tipo"], "cuentas_plantadas": len(verdad),
                      "detectadas_por_su_regla": len(acierto),
                      "recall_pct": round(100 * len(acierto) / len(verdad), 1) if verdad else 0.0,
                      "en_ranking_alto_medio": len(verdad & alto_medio),
                      "resultado": "DETECTADO" if len(acierto) / max(len(verdad), 1) >= 0.8 else
                                   "PARCIAL" if acierto else "NO DETECTADO"})
    plantadas = {c for p in patrones["patrones"] for c in p["cuentas"]}
    falsos = alto_medio - plantadas
    filas.append({"patron": "—", "tipo": "falsos positivos", "cuentas_plantadas": 0,
                  "detectadas_por_su_regla": len(falsos), "recall_pct": None,
                  "en_ranking_alto_medio": len(alto_medio),
                  "resultado": f"precisión {100 * (1 - len(falsos) / max(len(alto_medio), 1)):.1f} %"})
    return filas
