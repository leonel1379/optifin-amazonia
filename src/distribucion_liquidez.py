"""
Módulo 4 — Planificación y optimización de la distribución de liquidez
hacia bóvedas y agencias.

Modelo: red de flujo DIRIGIDA (multigrafo).  Nodos = bóveda central,
bóvedas regionales/de custodia y agencias.  Atributos de nodo: oferta
(efectivo disponible) y demanda (requerimiento de la agencia), en miles de
soles por ciclo semanal.  Aristas = rutas de traslado de valores con
capacidad máxima (restricción operativa y de seguridad/seguro), costo por
cada S/ 1 000 trasladados, modo (terrestre, aéreo, fluvial), tiempo y riesgo.

Reducción: superfuente → bóvedas (capacidad = oferta) y agencias →
supersumidero (capacidad = demanda).  Así el problema multi-origen /
multi-destino se convierte en un flujo máximo s–t.

Algoritmos:
  * Dinic (principal) y Edmonds-Karp (comparación) → cantidad máxima distribuible.
  * Corte mínimo → cuellos de botella (teorema max-flow / min-cut).
  * Flujo máximo de costo mínimo → qué ruta usar para cada sol al menor costo.
  * Kruskal / Prim → red troncal mínima que conecta todos los puntos (diseño,
    no distribución: se muestra por qué NO resuelve este problema).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .algoritmos.flujo import (EPS, SUPER_FUENTE, SUPER_SUMIDERO, corte_minimo, dinic,
                               edmonds_karp, flujo_costo_minimo, red_desde_grafo)
from .algoritmos.mst import kruskal, prim
from .graph import Grafo
from .utils import DATA_DIR, medir


@dataclass
class Escenario:
    nombre: str = "normal"
    descripcion: str = "Operación habitual."
    factor_fluvial: float = 1.0
    factor_aereo: float = 1.0
    factor_terrestre: float = 1.0
    factor_demanda: float = 1.0
    cerrar_aristas: list[str] = field(default_factory=list)
    cerrar_nodos: list[str] = field(default_factory=list)


def cargar_escenarios(ruta: Path | None = None) -> dict[str, Escenario]:
    datos = json.loads((ruta or DATA_DIR / "escenarios_liquidez.json").read_text(encoding="utf-8"))
    return {k: Escenario(nombre=k, **v) for k, v in datos.items()}


@dataclass
class ResultadoLiquidez:
    escenario: str
    algoritmo: str
    flujo_maximo: float
    oferta_total: float
    demanda_total: float
    costo_total: float
    rutas: list[dict[str, Any]]
    agencias: list[dict[str, Any]]
    bovedas: list[dict[str, Any]]
    regiones: list[dict[str, Any]]
    cuellos_botella: list[dict[str, Any]]
    bovedas_agotadas: list[str]
    verificacion: dict[str, Any]
    estadisticas: dict[str, Any]
    alertas: list[str]

    @property
    def cobertura_pct(self) -> float:
        return 100 * self.flujo_maximo / self.demanda_total if self.demanda_total else 100.0

    @property
    def deficit(self) -> float:
        return self.demanda_total - self.flujo_maximo


class PlanificadorLiquidez:
    def __init__(self, g: Grafo) -> None:
        self.g = g

    # ------------------------------------------------------- escenario
    def aplicar_escenario(self, esc: Escenario) -> Grafo:
        g = self.g.copia()
        factores = {"fluvial": esc.factor_fluvial, "aereo": esc.factor_aereo, "terrestre": esc.factor_terrestre}
        for a in g.aristas():
            f = factores.get(a.get("modo"), 1.0)
            if f != 1.0:
                a.atributos["capacidad"] = round(float(a.get("capacidad", 0)) * f, 3)
        if esc.factor_demanda != 1.0:
            for n in g.nodos.values():
                if n.get("demanda"):
                    n.atributos["demanda"] = round(float(n.get("demanda")) * esc.factor_demanda, 3)
        for aid in esc.cerrar_aristas:
            if aid in {a.id for a in g.aristas()}:
                g.cerrar_arista(aid)
        for nid in esc.cerrar_nodos:
            if nid in g.nodos:
                g.cerrar_nodo(nid)
        return g

    @staticmethod
    def ofertas(g: Grafo) -> dict[str, float]:
        return {n.id: float(n.get("oferta", 0) or 0) for n in g.nodos.values()
                if n.activo and float(n.get("oferta", 0) or 0) > 0}

    @staticmethod
    def demandas(g: Grafo) -> dict[str, float]:
        return {n.id: float(n.get("demanda", 0) or 0) for n in g.nodos.values()
                if float(n.get("demanda", 0) or 0) > 0}

    # --------------------------------------------------------- cálculo
    @staticmethod
    def cobertura_garantizada(g: Grafo, ofe: dict[str, float], dem: dict[str, float],
                              iteraciones: int = 40) -> tuple[float, int]:
        """
        Mayor fracción λ ∈ [0, 1] tal que TODAS las agencias pueden recibir λ·demanda
        a la vez.  Búsqueda binaria sobre λ: en cada paso se limita cada arista
        agencia→sumidero a λ·d y se verifica con Dinic si el flujo máximo alcanza λ·D.
        Costo: O(log(1/ε) · flujo máximo).  Devuelve (λ, ejecuciones de Dinic).
        """
        total = sum(dem.values())
        if total <= 0:
            return 1.0, 0
        lo, hi, ejec = 0.0, 1.0, 0
        for _ in range(iteraciones):
            mid = (lo + hi) / 2
            red = red_desde_grafo(g, "capacidad", "costo", ofe, {k: v * mid for k, v in dem.items()})
            ejec += 1
            if dinic(red, SUPER_FUENTE, SUPER_SUMIDERO).valor >= mid * total - 1e-6:
                lo = mid
            else:
                hi = mid
            if hi - lo < 1e-6:
                break
        return lo, ejec

    def calcular(self, escenario: Escenario | None = None, algoritmo: str = "dinic",
                 politica: str = "equitativa", evaluar_ampliaciones: bool = True) -> ResultadoLiquidez:
        """
        politica = "costo_minimo": flujo máximo de costo mínimo puro (puede dejar sin
                   efectivo a las agencias más caras de abastecer).
        politica = "equitativa": primero garantiza la misma cobertura mínima λ* a
                   todas las agencias y luego completa al menor costo.
        """
        esc = escenario or Escenario()
        g = self.aplicar_escenario(esc)
        ofe, dem = self.ofertas(g), self.demandas(g)
        dem_activa = {k: v for k, v in dem.items() if g.nodos[k].activo}

        def nueva_red():
            return red_desde_grafo(g, "capacidad", "costo", ofe, dem_activa)

        red_ek, red_dn = nueva_red(), nueva_red()
        r_ek, t_ek, _ = medir(lambda: edmonds_karp(red_ek, SUPER_FUENTE, SUPER_SUMIDERO))
        r_dn, t_dn, _ = medir(lambda: dinic(red_dn, SUPER_FUENTE, SUPER_SUMIDERO))
        red_base, r_base = (red_dn, r_dn) if algoritmo == "dinic" else (red_ek, r_ek)

        lam, ejec = 1.0, 0
        if politica == "equitativa":
            (lam, ejec), t_lam, _ = medir(lambda: self.cobertura_garantizada(g, ofe, dem_activa))
            # Cada agencia recibe dos aristas hacia el sumidero: un tramo "garantizado"
            # λ*·d con premio −M (se llena primero) y el resto (1−λ*)·d con costo 0.
            # Como un camino de aumento nunca reduce el flujo que entra al sumidero,
            # existe un flujo máximo que satura todos los tramos garantizados y el
            # flujo de costo mínimo lo encuentra.
            red_mc = red_desde_grafo(g, "capacidad", "costo", ofe, None)
            premio = 1e6
            for k, d in dem_activa.items():
                if k in red_mc.idx:
                    red_mc.agregar(k, SUPER_SUMIDERO, d * lam, -premio, f"DEMANDA:{k}")
                    red_mc.agregar(k, SUPER_SUMIDERO, d * (1 - lam), 0.0, f"DEMANDA2:{k}")
            red_mc.nodo(SUPER_SUMIDERO)
            r_mc, t_mc, _ = medir(lambda: flujo_costo_minimo(red_mc, SUPER_FUENTE, SUPER_SUMIDERO))
            r_mc.estadisticas["ejecuciones_dinic_busqueda_binaria"] = ejec
            t_mc += t_lam
        else:
            red_mc = nueva_red()
            r_mc, t_mc, _ = medir(lambda: flujo_costo_minimo(red_mc, SUPER_FUENTE, SUPER_SUMIDERO))

        # corte mínimo sobre la red residual del algoritmo elegido
        lado_s, aristas_corte = corte_minimo(red_base, SUPER_FUENTE)
        corte_ids = {red_base.ref[e] for e in aristas_corte}

        flujo: dict[str, float] = {}                   # distribución de costo mínimo
        for e in range(0, len(red_mc.hacia), 2):
            ref = red_mc.ref[e]
            if ref:
                ref = ref.replace("DEMANDA2:", "DEMANDA:")
                flujo[ref] = flujo.get(ref, 0.0) + red_mc.flujo[e]
        rutas = []
        for a in g.aristas():
            cap = float(a.get("capacidad", 0) or 0)
            f = flujo.get(a.id, 0.0) if a.activa and g.nodos[a.origen].activo and g.nodos[a.destino].activo else 0.0
            rutas.append({"id": a.id, "origen": a.origen, "destino": a.destino, "modo": a.get("modo"),
                          "capacidad": round(cap, 2), "flujo": round(f, 2),
                          "utilizacion_pct": round(100 * f / cap, 1) if cap else 0.0,
                          "costo_unitario": a.get("costo"), "costo_ruta": round(f * float(a.get("costo", 0)), 2),
                          "tiempo_h": a.get("tiempo_h"), "riesgo": a.get("riesgo"),
                          "estado": "cerrada" if not a.activa or not g.nodos[a.origen].activo
                          or not g.nodos[a.destino].activo else
                          ("saturada" if cap and f >= cap - 1e-6 else "disponible"),
                          "cuello_botella": a.id in corte_ids})

        agencias = []
        for nid, d in sorted(dem.items(), key=lambda x: -x[1]):
            n = g.nodos[nid]
            recibido = flujo.get(f"DEMANDA:{nid}", 0.0) if n.activo else 0.0
            agencias.append({"id": nid, "nombre": n.nombre, "ciudad": n.get("ciudad"), "region": n.get("region"),
                             "demanda": round(d, 2), "recibido": round(recibido, 2),
                             "pendiente": round(d - recibido, 2),
                             "cobertura_pct": round(100 * recibido / d, 1) if d else 100.0,
                             "estado": "cerrada" if not n.activo else
                             ("atendida" if recibido >= d - 1e-6 else "déficit")})
        bovedas = []
        for nid, o in sorted(ofe.items(), key=lambda x: -x[1]):
            desp = flujo.get(f"OFERTA:{nid}", 0.0)
            bovedas.append({"id": nid, "nombre": g.nodos[nid].nombre, "oferta": round(o, 2),
                            "despachado": round(desp, 2), "remanente": round(o - desp, 2),
                            "uso_pct": round(100 * desp / o, 1) if o else 0.0})
        regiones: dict[str, dict[str, float]] = {}
        for ag in agencias:
            r = regiones.setdefault(ag["region"] or "—", {"demanda": 0.0, "recibido": 0.0})
            r["demanda"] += ag["demanda"]
            r["recibido"] += ag["recibido"]
        filas_reg = [{"region": k, "demanda": round(v["demanda"], 2), "recibido": round(v["recibido"], 2),
                      "pendiente": round(v["demanda"] - v["recibido"], 2),
                      "cobertura_pct": round(100 * v["recibido"] / v["demanda"], 1) if v["demanda"] else 100.0}
                     for k, v in regiones.items()]

        cuellos = [r for r in rutas if r["cuello_botella"]]
        if evaluar_ampliaciones:
            for c in cuellos:
                inc = max(round(0.2 * c["capacidad"], 2), 1.0)
                c["ganancia_si_amplia_20pct"] = self.beneficio_ampliacion(esc, c["id"], inc)["ganancia"]
        agotadas = [ref.split(":", 1)[1] for ref in corte_ids if ref and ref.startswith("OFERTA:")]
        verif = self._verificar(g, red_mc, ofe, dem_activa, r_ek.valor, r_dn.valor, r_mc.valor)
        alertas = self._alertas(agencias, cuellos, filas_reg)
        stats = {"edmonds_karp": {"tiempo_ms": round(t_ek, 4), **r_ek.estadisticas, "flujo": round(r_ek.valor, 3)},
                 "dinic": {"tiempo_ms": round(t_dn, 4), **r_dn.estadisticas, "flujo": round(r_dn.valor, 3)},
                 "costo_minimo": {"tiempo_ms": round(t_mc, 4), **r_mc.estadisticas, "flujo": round(r_mc.valor, 3)},
                 "V": red_base.n, "E": red_base.m}
        stats["politica"] = politica
        stats["cobertura_garantizada_pct"] = round(100 * lam, 2)
        costo_real = sum(r["costo_ruta"] for r in rutas)   # solo rutas físicas (sin premios ficticios)
        return ResultadoLiquidez(esc.nombre, algoritmo, r_base.valor, sum(ofe.values()), sum(dem.values()),
                                 costo_real, rutas, agencias, bovedas, filas_reg, cuellos, agotadas,
                                 verif, stats, alertas)

    @staticmethod
    def _verificar(g, red, ofe, dem, v_ek, v_dn, v_mc) -> dict[str, Any]:
        balance: dict[str, float] = {n: 0.0 for n in red.nombres}
        capacidad_ok = True
        for e in range(0, len(red.hacia), 2):
            f = red.flujo[e]
            if f < -EPS or f > red.cap[e] + 1e-6:
                capacidad_ok = False
            balance[red.nombres[red.hacia[e ^ 1]]] -= f
            balance[red.nombres[red.hacia[e]]] += f
        conservacion = all(abs(b) < 1e-6 for n, b in balance.items() if n not in (SUPER_FUENTE, SUPER_SUMIDERO))
        return {"conservacion_de_flujo": conservacion, "capacidades_respetadas": capacidad_ok,
                "oferta_no_excedida": all(red.flujo[e] <= red.cap[e] + 1e-6 for e in range(0, len(red.hacia), 2)
                                          if (red.ref[e] or "").startswith("OFERTA:")),
                "demanda_no_excedida": all(red.flujo[e] <= red.cap[e] + 1e-6 for e in range(0, len(red.hacia), 2)
                                           if (red.ref[e] or "").startswith("DEMANDA:")),
                "mismo_flujo_EK_Dinic_CostoMin": abs(v_ek - v_dn) < 1e-6 and abs(v_dn - v_mc) < 1e-6}

    @staticmethod
    def _alertas(agencias, cuellos, regiones) -> list[str]:
        al = []
        for r in regiones:
            if r["cobertura_pct"] < 100:
                al.append(f"La región {r['region']} recibe el {r['cobertura_pct']} % de su demanda "
                          f"(faltan S/ {r['pendiente'] * 1000:,.0f}).")
        for ag in agencias:
            if ag["estado"] == "déficit":
                al.append(f"{ag['nombre']}: déficit de S/ {ag['pendiente'] * 1000:,.0f} "
                          f"({ag['cobertura_pct']} % atendido).")
            elif ag["estado"] == "cerrada":
                al.append(f"{ag['nombre']} está cerrada: su demanda no se atiende.")
        criticos = [c for c in cuellos if c.get("ganancia_si_amplia_20pct", 1) > 0]
        if criticos:
            al.append("Cuellos de botella críticos (ampliarlos aumenta el efectivo distribuido): " +
                      ", ".join(f"{c['origen']}→{c['destino']} ({c['modo']}, +{c.get('ganancia_si_amplia_20pct', 0) * 1000:,.0f} S/ si se amplía 20 %)"
                                for c in criticos))
        return al

    # ---------------------------------------- sensibilidad / ampliación
    def beneficio_ampliacion(self, escenario: Escenario, arista_id: str, incremento: float) -> dict[str, Any]:
        """¿Cuánto más efectivo llega si se amplía la capacidad de una ruta?  (re-ejecuta Dinic)"""
        g = self.aplicar_escenario(escenario)
        ofe, dem = self.ofertas(g), {k: v for k, v in self.demandas(g).items() if g.nodos[k].activo}
        red = red_desde_grafo(g, "capacidad", "costo", ofe, dem)
        base = dinic(red, SUPER_FUENTE, SUPER_SUMIDERO).valor
        a = g.arista(arista_id)
        a.atributos["capacidad"] = float(a.get("capacidad", 0)) + incremento
        red2 = red_desde_grafo(g, "capacidad", "costo", ofe, dem)
        nuevo = dinic(red2, SUPER_FUENTE, SUPER_SUMIDERO).valor
        return {"ruta": arista_id, "incremento_capacidad": incremento, "flujo_antes": round(base, 2),
                "flujo_despues": round(nuevo, 2), "ganancia": round(nuevo - base, 2)}

    # ------------------------------------------------- red troncal (MST)
    def red_troncal(self, algoritmo: str = "kruskal", criterio: str = "costo") -> dict[str, Any]:
        """
        Árbol de expansión mínima sobre la versión no dirigida de la red: el
        conjunto más barato de rutas que mantiene conectados todos los puntos.
        Útil para decidir qué rutas custodiar o contratar en exclusiva; NO
        considera capacidades, ofertas ni demandas, por lo que no reemplaza al
        flujo máximo para planificar la distribución.
        """
        und = Grafo("troncal", dirigido=False, multiple=True)
        for n in self.g.nodos.values():
            if n.activo:
                und.agregar_nodo(n.id, n.tipo, n.nombre, n.lat, n.lon)
        mejor: dict[tuple[str, str], Any] = {}
        for a in self.g.aristas(incluir_inactivas=False):
            par = tuple(sorted((a.origen, a.destino)))
            if par not in mejor or float(a.get(criterio, 0)) < float(mejor[par].get(criterio, 0)):
                mejor[par] = a
        for (u, v), a in mejor.items():
            und.agregar_arista(u, v, a.id, modo=a.get("modo"), **{criterio: float(a.get(criterio, 0))})
        peso = lambda a: float(a.get(criterio, 0))
        (arbol, total), ms, _ = medir(lambda: (kruskal if algoritmo == "kruskal" else prim)(und, peso))
        return {"algoritmo": algoritmo, "criterio": criterio, "costo_total": round(total, 3),
                "aristas": [{"id": a.id, "origen": a.origen, "destino": a.destino, "modo": a.get("modo"),
                             criterio: a.get(criterio)} for a in arbol],
                "nodos": und.num_nodos, "tiempo_ms": ms,
                "rutas_descartadas": len(mejor) - len(arbol)}
