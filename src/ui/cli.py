"""
Interfaz de terminal (respaldo de la interfaz web).

    python main.py --cli     → menú interactivo
    python main.py --demo    → ejecuta todos los módulos y guarda reportes en reports/
"""

from __future__ import annotations

import json

from ..analisis_transacciones import AnalizadorTransacciones, evaluar_contra_patrones
from ..distribucion_liquidez import PlanificadorLiquidez, cargar_escenarios
from ..enrutamiento_financiero import CRITERIOS, Enrutador, nodos_criticos
from ..evaluacion_resultados import (TABLA_COMPLEJIDAD, benchmark_caminos, benchmark_flujo, casos_de_prueba,
                                     pendientes_loglog)
from ..gestion_red import GestorRedes
from ..utils import DATA_DIR, REPORTS_DIR, exportar_csv, exportar_json, marca_tiempo, tabla_texto

LINEA = "=" * 78


def titulo(t: str) -> None:
    print(f"\n{LINEA}\n  {t}\n{LINEA}")


def pedir(msg: str, defecto: str) -> str:
    v = input(f"{msg} [{defecto}]: ").strip()
    return v or defecto


def modulo1(G: GestorRedes) -> None:
    titulo("MÓDULO 1 · Gestión y modelamiento de redes")
    print(tabla_texto(G.resumen()))
    for nombre, g in G.redes.items():
        err = [h for h in g.validar() if h["nivel"] == "error"]
        print(f"  {nombre:<14} → {'consistente' if not err else f'{len(err)} errores'}")


def modulo2(G: GestorRedes, guardar: bool = False) -> dict:
    titulo("MÓDULO 2 · Detección de operaciones sospechosas")
    patrones = json.loads((DATA_DIR / "patrones_plantados.json").read_text(encoding="utf-8"))
    semilla = next(p["cuenta_reportada"] for p in patrones["patrones"] if p.get("cuenta_reportada"))
    res = AnalizadorTransacciones(G["transacciones"]).analisis_completo(semilla)
    print("\nCiclos de fondos:")
    print(tabla_texto(res["ciclos"], ["cuentas", "monto_inicial", "retencion_pct", "duracion_h"]))
    print("\nFragmentación (pitufeo):")
    print(tabla_texto(res["fragmentacion"], ["cuenta", "emisores", "operaciones", "total_recibido", "salida_posterior_7d"]))
    print("\nCadenas de cuentas puente:", res["puente"]["cadenas"])
    print("\nDispersión:")
    print(tabla_texto(res["dispersion"], ["cuenta", "receptores", "total_enviado"]))
    print("\nGrupos cerrados:")
    print(tabla_texto(res["grupos"], ["cuentas", "tamano", "densidad", "monto_interno"]))
    print("\nRanking de riesgo (top 15):")
    print(tabla_texto(res["ranking"][:15], ["cuenta", "titular", "puntaje", "nivel_riesgo", "motivos"]))
    print("\nValidación contra patrones plantados:")
    print(tabla_texto(evaluar_contra_patrones(res, patrones)))
    if guardar:
        exportar_json(res, f"fraude_{marca_tiempo()}.json")
        exportar_csv(res["ranking"], f"ranking_riesgo_{marca_tiempo()}.csv")
    return res


def modulo3(G: GestorRedes, interactivo: bool = True, guardar: bool = False) -> None:
    titulo("MÓDULO 3 · Enrutamiento y comisiones")
    E = Enrutador(G["enrutamiento"])
    if interactivo:
        print("Nodos:", ", ".join(G["enrutamiento"].nodos))
        o = pedir("Origen", "AG_LIM")
        d = pedir("Destino", "CORR_CAB")
        m = float(pedir("Monto S/", "1500"))
        c = pedir(f"Criterio {list(CRITERIOS)}", "comision")
        cerrar = [x.strip() for x in pedir("Nodos cerrados (coma)", "").split(",") if x.strip()]
    else:
        o, d, m, c, cerrar = "AG_LIM", "CORR_CAB", 1500.0, "comision", []
    try:
        r = E.ruta_optima(o, d, m, c, cerrar_nodos=cerrar)
    except Exception as e:  # noqa: BLE001 - mensaje amigable en terminal
        print("Error:", e)
        return
    if r.existe:
        print(f"\nRuta óptima ({r.algoritmo}): {' → '.join(r.nodos)}")
        print(f"Comisión S/ {r.comision:.2f} · tiempo {r.tiempo_min:.0f} min · prob. falla {100 * r.riesgo:.2f} %")
    else:
        print("\nSin ruta:", r.motivo_sin_ruta)
    print("\nJustificación:", r.justificacion)
    alt = E.rutas_alternativas(o, d, m, c, 5, cerrar_nodos=cerrar)
    comp = E.comparar_algoritmos(o, d, m, c, cerrar_nodos=cerrar)
    print("\nRutas alternativas (Yen):")
    print(tabla_texto(alt, ["opcion", "ruta", "comision_S/", "tiempo_min", "prob_falla_%"]))
    print("\nComparación de algoritmos:")
    print(tabla_texto(comp, ["algoritmo", "comision_S/", "tiempo_ejecucion_ms", "operaciones", "coincide_con_optimo"]))
    if guardar:
        exportar_csv(alt, f"rutas_alternativas_{marca_tiempo()}.csv")
        exportar_csv(comp, f"comparacion_algoritmos_{marca_tiempo()}.csv")
    print("\nPuntos únicos de falla desde", o)
    print(tabla_texto(nodos_criticos(G["enrutamiento"], o)))


def modulo4(G: GestorRedes, interactivo: bool = True, guardar: bool = False) -> None:
    titulo("MÓDULO 4 · Distribución de liquidez")
    P = PlanificadorLiquidez(G["liquidez"])
    esc = cargar_escenarios()
    nombre = pedir(f"Escenario {list(esc)}", "normal") if interactivo else "normal"
    r = P.calcular(esc.get(nombre, esc["normal"]))
    print(f"\nEscenario: {r.escenario} · flujo máximo S/ {r.flujo_maximo:,.0f} mil de S/ {r.demanda_total:,.0f} mil "
          f"({r.cobertura_pct:.1f} %) · costo S/ {r.costo_total:,.0f} · cobertura garantizada "
          f"{r.estadisticas['cobertura_garantizada_pct']} %")
    print(tabla_texto(r.agencias, ["id", "ciudad", "demanda", "recibido", "pendiente", "cobertura_pct", "estado"]))
    print("\nCuellos de botella (corte mínimo):")
    print(tabla_texto(r.cuellos_botella, ["id", "origen", "destino", "modo", "capacidad", "ganancia_si_amplia_20pct"]))
    print("\n".join("  • " + a for a in r.alertas))
    print("\nVerificación:", r.verificacion)
    print("\nComparación de escenarios:")
    filas = []
    for k, e in esc.items():
        rr = P.calcular(e, evaluar_ampliaciones=False)
        filas.append({"escenario": k, "flujo": rr.flujo_maximo, "cobertura_%": round(rr.cobertura_pct, 1),
                      "garantizada_%": rr.estadisticas["cobertura_garantizada_pct"], "costo": round(rr.costo_total)})
    print(tabla_texto(filas))
    if guardar:
        exportar_csv(r.agencias, f"liquidez_agencias_{marca_tiempo()}.csv")
        exportar_csv(r.rutas, f"liquidez_rutas_{marca_tiempo()}.csv")
        exportar_csv(filas, f"liquidez_escenarios_{marca_tiempo()}.csv")


def modulo5(guardar: bool = False, rapido: bool = True) -> None:
    titulo("MÓDULO 5 · Evaluación y validación")
    casos = casos_de_prueba()
    print(tabla_texto(casos, ["modulo", "caso", "esperado", "obtenido", "estado"], max_filas=100))
    print(f"\nCasos superados: {sum(c['estado'] == '✔' for c in casos)} / {len(casos)}")
    tam = (100, 200, 400) if rapido else (100, 200, 400, 800, 1600)
    bc = benchmark_caminos(tam, memoria=False)
    bf = benchmark_flujo(tam, memoria=False)
    print("\nRutas más cortas:")
    print(tabla_texto(bc))
    print(tabla_texto(pendientes_loglog(bc)))
    print("\nFlujo máximo:")
    print(tabla_texto(bf))
    print(tabla_texto(pendientes_loglog(bf)))
    if guardar:
        exportar_csv(casos, f"casos_prueba_{marca_tiempo()}.csv")
        exportar_csv(bc + bf, f"benchmarks_{marca_tiempo()}.csv")
        exportar_csv(TABLA_COMPLEJIDAD, "tabla_complejidad.csv")


def demo() -> None:
    G = GestorRedes().cargar_todas()
    modulo1(G)
    modulo2(G, guardar=True)
    modulo3(G, interactivo=False, guardar=True)
    modulo4(G, interactivo=False, guardar=True)
    modulo5(guardar=True)
    print(f"\nReportes guardados en {REPORTS_DIR}")


def menu() -> None:
    G = GestorRedes().cargar_todas()
    opciones = {"1": ("Gestión y validación de redes", lambda: modulo1(G)),
                "2": ("Detección de fraude y lavado", lambda: modulo2(G)),
                "3": ("Ruta de menor comisión", lambda: modulo3(G)),
                "4": ("Distribución de liquidez", lambda: modulo4(G)),
                "5": ("Casos de prueba y benchmarks", lambda: modulo5()),
                "6": ("Ejecutar todo y guardar reportes", demo)}
    while True:
        titulo("OptiFin Amazonía — modo terminal")
        for k, (t, _) in opciones.items():
            print(f"  {k}. {t}")
        print("  0. Salir")
        op = input("\nOpción: ").strip()
        if op == "0":
            break
        if op in opciones:
            opciones[op][1]()
            input("\nPresione Enter para continuar…")
