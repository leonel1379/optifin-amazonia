"""
Interfaz web local (Streamlit) de OptiFin Amazonía.

Se inicia con:  python main.py      (o: streamlit run src/ui/app.py)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src.analisis_transacciones import (AnalizadorTransacciones, ConfigAnalisis,  # noqa: E402
                                        evaluar_contra_patrones)
from src.distribucion_liquidez import Escenario, PlanificadorLiquidez, cargar_escenarios  # noqa: E402
from src.enrutamiento_financiero import (CRITERIOS, DESCRIPCION_PROMOCIONES, PROMOCIONES,  # noqa: E402
                                         Enrutador, nodos_criticos)
from src.evaluacion_resultados import (TABLA_COMPLEJIDAD, benchmark_caminos, benchmark_flujo,  # noqa: E402
                                       benchmark_mst, benchmark_recorridos, casos_de_prueba,
                                       pendientes_loglog, validar_con_networkx)
from src.gestion_red import REDES_PROYECTO, GestorRedes, importar, tabla_aristas, tabla_nodos  # noqa: E402
from src.graph import TIPOS_NODO, Grafo, _convertir  # noqa: E402
from src.ui import visual as V  # noqa: E402
from src.utils import DATA_DIR, markdown_tabla  # noqa: E402

st.set_page_config(page_title="OptiFin Amazonía", page_icon="🏦", layout="wide",
                   initial_sidebar_state="expanded")

st.markdown("""
<style>
.block-container {padding-top: 1.6rem; padding-bottom: 2rem;}
div[data-testid="stMetricValue"] {font-size: 1.55rem;}
.ruta-chip {display:inline-block; background:#ecfeff; border:1px solid #0e7490; color:#0e7490;
            border-radius:14px; padding:2px 10px; margin:2px; font-size:0.86rem; font-family:monospace;}
.flecha {color:#94a3b8; margin:0 2px;}
.caja-respuesta {background:#f0fdf4; border-left:6px solid #16a34a; padding:14px 18px; border-radius:6px;
                 font-size:1.02rem; margin: 6px 0 14px 0;}
.caja-alerta {background:#fef2f2; border-left:6px solid #dc2626; padding:12px 16px; border-radius:6px; margin:6px 0;}
.subtitulo {color:#475569; font-size:1.02rem; margin-top:-10px;}
</style>
""", unsafe_allow_html=True)


# ============================================================ estado
def gestor() -> GestorRedes:
    if "gestor" not in st.session_state:
        st.session_state.gestor = GestorRedes().cargar_todas()
    return st.session_state.gestor


def df(filas, columnas=None) -> pd.DataFrame:
    d = pd.DataFrame(filas)
    if columnas and not d.empty:
        d = d[[c for c in columnas if c in d.columns]]
    for c in d.columns:
        if d[c].map(lambda x: isinstance(x, (list, tuple, set))).any():
            d[c] = d[c].map(lambda x: " → ".join(map(str, x)) if isinstance(x, (list, tuple)) else
                            (", ".join(sorted(map(str, x))) if isinstance(x, set) else x))
    return d


def chips(nodos: list[str]) -> str:
    return '<span class="flecha">→</span>'.join(f'<span class="ruta-chip">{n}</span>' for n in nodos)


def etiqueta_nodo(g: Grafo):
    return lambda i: f"{i} · {g.nodos[i].nombre}" + (f" ({g.nodos[i].get('ciudad')})" if g.nodos[i].get("ciudad") else "")


def etiqueta_arista(g: Grafo):
    def f(aid):
        a = g.arista(aid)
        extra = a.get("modo") or a.get("canal") or ""
        return f"{aid}: {a.origen} → {a.destino} ({extra})"
    return f


def parsear_atributos(texto: str) -> dict:
    """'comision_fija=2.5; tiempo_min=10' → {'comision_fija': 2.5, 'tiempo_min': 10}"""
    attrs = {}
    for parte in texto.replace("\n", ";").split(";"):
        if "=" in parte:
            k, v = parte.split("=", 1)
            attrs[k.strip()] = _convertir(v.strip(), k.strip())
    return attrs


CONFIG_PLOTLY = {"topojsonURL": "app/static/", "displaylogo": False,
                 "modeBarButtonsToRemove": ["select2d", "lasso2d"]}


def grafico(fig, donde=None, **kw) -> None:
    """Muestra una figura Plotly. El mapa base del Perú se sirve localmente (src/ui/static): funciona sin internet."""
    kw.setdefault("width", "stretch")
    (donde or st).plotly_chart(fig, config=CONFIG_PLOTLY, **kw)


def multi(donde, *args, **kw):
    """multiselect con textos en español."""
    kw.setdefault("placeholder", "Elegir una o varias opciones…")
    return donde.multiselect(*args, **kw)


def usar_mapa_geo() -> bool:
    return st.session_state.get("vista_mapa", "Mapa del Perú") == "Mapa del Perú"


# ============================================================ sidebar
PAGINAS = ["🏠 Inicio", "🗺️ 1 · Gestión de redes", "🕵️ 2 · Fraude y lavado de activos",
           "💸 3 · Enrutamiento y comisiones", "🚚 4 · Liquidez hacia bóvedas", "📊 5 · Evaluación y validación"]
with st.sidebar:
    st.markdown("## 🏦 OptiFin Amazonía")
    st.caption("Sistema de análisis y optimización de redes financieras · Programación III — UNSAAC")
    pagina = st.radio("Módulo", PAGINAS, label_visibility="collapsed")
    st.divider()
    st.radio("Vista de los mapas", ["Mapa del Perú", "Vista esquemática"], key="vista_mapa",
             help="La vista esquemática no necesita internet (el mapa base del Perú se descarga de plotly).")
    cerrados = sum(1 for g in gestor().redes.values() for n in g.nodos.values() if not n.activo) + \
        sum(1 for g in gestor().redes.values() for a in g.aristas() if not a.activa)
    if cerrados:
        st.warning(f"{cerrados} elemento(s) cerrados en la sesión (Módulo 1).")
    if st.button("↺ Restaurar todas las redes", width="stretch"):
        st.session_state.gestor = GestorRedes().cargar_todas()
        st.rerun()
    st.caption("Banco Andino Amazónico (BAA) es ficticio. Montos, tarifas y cuentas son simulados; "
               "la geografía y las rutas sí corresponden al Perú.")


# ============================================================ INICIO
def pagina_inicio():
    st.title("OptiFin Amazonía")
    st.markdown('<p class="subtitulo">Red nacional del <b>Banco Andino Amazónico</b> (ficticio): costa, sierra '
                'y una Amazonía donde Iquitos solo se abastece por avión o por río.</p>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1.container(border=True):
        st.markdown("#### 🕵️ Fraude y lavado")
        st.write("Ciclos de fondos, pitufeo en la triple frontera, cuentas puente y dispersión desde "
                 "cuentas mineras.")
        st.caption("BFS · DFS acotada · Tarjan (SCC) · búsqueda temporal")
    with c2.container(border=True):
        st.markdown("#### 💸 Enrutamiento y comisiones")
        st.write("¿Por qué ruta la comisión es más baja? Interplaza, CCE, billeteras, tarjetas, cajeros y "
                 "corresponsales, con límites por canal.")
        st.caption("Dijkstra · (Bellman-Ford / Floyd-Warshall solo cuando corresponde) · Yen")
    with c3.container(border=True):
        st.markdown("#### 🚚 Liquidez hacia bóvedas")
        st.write("Cuánto efectivo puede llegar a cada agencia por carretera, avión y río, y dónde están los "
                 "cuellos de botella.")
        st.caption("Dinic · corte mínimo · flujo de costo mínimo · MST")

    izq, der = st.columns([1.35, 1])
    with izq:
        st.markdown("##### Red de traslado de valores (color = modo de transporte)")
        g = gestor()["liquidez"]
        grafico(V.mapa_red(g, color_por_modo=True, geo=usar_mapa_geo(), altura=520,
                                   leyenda_extra={"Terrestre": V.COLOR_MODO["terrestre"],
                                                  "Aérea": V.COLOR_MODO["aereo"], "Fluvial": V.COLOR_MODO["fluvial"]}),
                        width="stretch")
    with der:
        st.markdown("##### Redes cargadas")
        st.dataframe(df(gestor().resumen()), hide_index=True, width="stretch")
        st.markdown("##### Cómo usar")
        st.markdown("1. **Módulo 1**: revisa, edita, importa o cierra nodos y rutas.\n"
                    "2. **Módulos 2–4**: cada uno resuelve un escenario y explica qué algoritmo usa y por qué.\n"
                    "3. **Módulo 5**: casos de prueba, tiempos reales y validación con NetworkX.\n\n"
                    "Los cierres hechos en el Módulo 1 afectan a todos los módulos.")
    with st.expander("Decisiones algorítmicas por escenario", expanded=False):
        st.dataframe(df(TABLA_COMPLEJIDAD), hide_index=True, width="stretch")


# ============================================================ MÓDULO 1
def pagina_gestion():
    st.title("1 · Gestión y modelamiento de redes")
    G = gestor()
    nombre = st.selectbox("Red", list(G.redes), format_func=lambda n: f"{n} — {REDES_PROYECTO.get(n, ('', '', {}, 'red importada / ejemplo'))[3]}")
    g = G[nombre]
    e = g.estadisticas()
    m = st.columns(6)
    m[0].metric("Nodos", e["nodos"], border=True)
    m[1].metric("Aristas", e["aristas"], border=True)
    m[2].metric("Densidad", f"{e['densidad']:.4f}", border=True)
    m[3].metric("Tipo", "Dirigida" if e["dirigido"] else "No dirigida", border=True)
    m[4].metric("Pesos", "Ponderada" if e["ponderado"] else "No ponderada", border=True)
    m[5].metric("Cerrados", e["nodos_cerrados"] + e["aristas_cerradas"], border=True)

    t_mapa, t_nodos, t_aristas, t_editar, t_cerrar, t_io, t_valid = st.tabs(
        ["Mapa", "Nodos", "Aristas", "Crear / modificar / eliminar", "Cerrar sucursales y rutas",
         "Importar / exportar", "Validación"])
    with t_mapa:
        grafico(V.mapa_red(g, color_por_modo=nombre == "liquidez", geo=usar_mapa_geo(), altura=600,
                                   hover_aristas=g.num_aristas <= 600),
                        width="stretch")
        st.caption("Pasa el cursor por los nodos y por los rombos de las aristas para ver sus atributos. "
                   "Los elementos cerrados se muestran en rojo claro.")
    with t_nodos:
        tipos = sorted({n.tipo for n in g.nodos.values()})
        filtro = multi(st, "Filtrar por tipo", tipos, default=tipos)
        st.dataframe(df([n for n in tabla_nodos(g) if n["tipo"] in filtro]), hide_index=True, width="stretch",
                     height=420)
    with t_aristas:
        st.dataframe(df(tabla_aristas(g)), hide_index=True, width="stretch", height=460)
    with t_editar:
        _editor(G, nombre, g)
    with t_cerrar:
        st.info("Simula sucursales en mantenimiento o rutas bloqueadas. Un elemento cerrado no se elimina: "
                "los algoritmos simplemente no lo recorren (como una calle cerrada).")
        actuales_n = [n for n in g.nodos if not g.nodos[n].activo]
        actuales_a = [a.id for a in g.aristas() if not a.activa]
        with st.form(f"cerrar_{nombre}"):
            sel_n = multi(st, "Nodos cerrados", list(g.nodos), default=actuales_n, format_func=etiqueta_nodo(g))
            sel_a = multi(st, "Aristas cerradas", [a.id for a in g.aristas()], default=actuales_a,
                                   format_func=etiqueta_arista(g)) if g.num_aristas <= 800 else \
                multi(st, "Aristas cerradas (ids)", [a.id for a in g.aristas()], default=actuales_a)
            if st.form_submit_button("Aplicar", type="primary"):
                for n in g.nodos.values():
                    n.activo = n.id not in sel_n
                for a in g.aristas():
                    a.activa = a.id not in sel_a
                st.success(f"{len(sel_n)} nodo(s) y {len(sel_a)} arista(s) cerrados.")
                st.rerun()
    with t_io:
        _importar_exportar(G, nombre, g)
    with t_valid:
        hallazgos = g.validar()
        errores = [h for h in hallazgos if h["nivel"] == "error"]
        if not errores:
            st.success(f"Red consistente: 0 errores ({len(hallazgos)} advertencias).")
        else:
            st.error(f"{len(errores)} errores de consistencia.")
        if hallazgos:
            st.dataframe(df(hallazgos), hide_index=True, width="stretch")
        st.markdown("##### Representación interna (lista de adyacencia)")
        attr = {"enrutamiento": "comision_pct", "liquidez": "capacidad", "transacciones": "monto"}.get(nombre)
        ady = g.lista_adyacencia(attr)
        muestra = {k: ady[k] for k in list(ady)[:8]}
        st.code("grafo = " + json.dumps(muestra, ensure_ascii=False, indent=2)[:2500], language="python")
        st.caption(f"Memoria O(V + E). Peso mostrado: {attr or 'sin peso'}. Recorrer los vecinos de un nodo "
                   "cuesta O(grado), ideal para redes dispersas como estas (densidad < 0.1).")


def _editor(G: GestorRedes, nombre: str, g: Grafo):
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### Nodos")
        with st.form(f"nuevo_nodo_{nombre}", clear_on_submit=True):
            a, b = st.columns(2)
            nid = a.text_input("Id", placeholder="AG_NUEVA")
            tipo = b.selectbox("Tipo", sorted(TIPOS_NODO), index=sorted(TIPOS_NODO).index("agencia"))
            nom = st.text_input("Nombre")
            a, b = st.columns(2)
            lat = a.number_input("Latitud", value=None, format="%.4f")
            lon = b.number_input("Longitud", value=None, format="%.4f")
            extra = st.text_input("Atributos extra (clave=valor; …)", placeholder="ciudad=Iquitos; demanda=500")
            if st.form_submit_button("➕ Crear nodo"):
                r = G.agregar_nodo(nombre, nid, tipo, nombre=nom, lat=lat, lon=lon, **parsear_atributos(extra))
                (st.success if r.ok else st.error)(r.mensaje)
        with st.form(f"mod_nodo_{nombre}"):
            nodo = st.selectbox("Nodo a modificar", list(g.nodos), format_func=etiqueta_nodo(g))
            cambios = st.text_input("Cambios (clave=valor; …)", placeholder="nombre=Agencia Belén; demanda=900")
            a, b = st.columns(2)
            if a.form_submit_button("✏️ Modificar"):
                r = G.modificar_nodo(nombre, nodo, **parsear_atributos(cambios))
                (st.success if r.ok else st.error)(r.mensaje)
            if b.form_submit_button("🗑️ Eliminar nodo"):
                r = G.eliminar_nodo(nombre, nodo)
                (st.success if r.ok else st.error)(r.mensaje)
                st.rerun()
    with c2:
        st.markdown("##### Aristas")
        ids = list(g.nodos)
        with st.form(f"nueva_arista_{nombre}", clear_on_submit=True):
            a, b = st.columns(2)
            o = a.selectbox("Origen", ids, format_func=etiqueta_nodo(g))
            d = b.selectbox("Destino", ids, index=min(1, len(ids) - 1), format_func=etiqueta_nodo(g))
            ejemplo = {"enrutamiento": "canal=interplaza; comision_fija=0; comision_pct=0.4; tiempo_min=2; riesgo=0.001; limite=50000",
                       "liquidez": "modo=fluvial; capacidad=1200; costo=1.3; tiempo_h=20; riesgo=0.04",
                       "transacciones": "monto=8500; fecha=2026-10-15T10:30; canal=app; concepto=transferencia"}.get(nombre, "comision=2.5")
            attrs = st.text_input("Atributos (clave=valor; …)", value=ejemplo)
            if st.form_submit_button("➕ Crear arista"):
                r = G.agregar_arista(nombre, o, d, **parsear_atributos(attrs))
                (st.success if r.ok else st.error)(r.mensaje)
        if g.num_aristas:
            with st.form(f"mod_arista_{nombre}"):
                opciones = [a.id for a in g.aristas()]
                aid = st.selectbox("Arista", opciones, format_func=etiqueta_arista(g) if len(opciones) <= 800 else str)
                cambios = st.text_input("Cambios (clave=valor; …)", placeholder="comision_pct=0.25")
                a, b = st.columns(2)
                if a.form_submit_button("✏️ Modificar"):
                    r = G.modificar_arista(nombre, aid, **parsear_atributos(cambios))
                    (st.success if r.ok else st.error)(r.mensaje)
                if b.form_submit_button("🗑️ Eliminar arista"):
                    r = G.eliminar_arista(nombre, aid)
                    (st.success if r.ok else st.error)(r.mensaje)
                    st.rerun()
    if nombre in REDES_PROYECTO or nombre == "ejemplo":
        if st.button(f"↺ Restaurar '{nombre}' desde data/"):
            st.info(G.restaurar(nombre).mensaje)
            st.rerun()


def _importar_exportar(G: GestorRedes, nombre: str, g: Grafo):
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### Importar red")
        st.caption("CSV con columnas origen,destino,… (+ CSV de nodos opcional) · JSON exportado por el sistema · "
                   "TXT con líneas 'origen destino peso'.")
        arch = st.file_uploader("Archivo de aristas / red", type=["csv", "json", "txt"])
        arch_n = st.file_uploader("Archivo de nodos (opcional, CSV)", type=["csv"])
        a, b, c = st.columns(3)
        dirigido = a.checkbox("Dirigida", True)
        ponderado = b.checkbox("Ponderada", True)
        multiple = c.checkbox("Multigrafo", False)
        nuevo = st.text_input("Nombre de la red", value="importada")
        if st.button("📥 Importar", type="primary", disabled=arch is None):
            ext = arch.name.rsplit(".", 1)[-1]
            gi, errores = importar(arch.getvalue(), ext, arch_n.getvalue() if arch_n else None, nuevo,
                                   dirigido, ponderado, multiple)
            if gi is not None:
                G.registrar(gi, nuevo)
                st.success(f"Red '{nuevo}' importada: {gi.num_nodos} nodos, {gi.num_aristas} aristas.")
            for err in errores:
                st.warning(err)
    with c2:
        st.markdown(f"##### Exportar '{nombre}'")
        st.download_button("⬇️ JSON (red completa)", json.dumps(g.a_dict(), ensure_ascii=False, indent=2),
                           f"{nombre}.json", "application/json")
        st.download_button("⬇️ CSV de nodos", df(tabla_nodos(g)).to_csv(index=False), f"nodos_{nombre}.csv", "text/csv")
        st.download_button("⬇️ CSV de aristas", df(tabla_aristas(g)).to_csv(index=False), f"aristas_{nombre}.csv",
                           "text/csv")


# ============================================================ MÓDULO 2
def pagina_fraude():
    st.title("2 · Fraude y lavado de activos")
    G = gestor()
    candidatas = [n for n, g in G.redes.items() if any(a.get("monto") is not None and a.get("fecha") for a in g.aristas()[:50])]
    nombre = st.selectbox("Red transaccional", candidatas or ["transacciones"], key="red_fraude")
    g = G[nombre]
    patrones = json.loads((DATA_DIR / "patrones_plantados.json").read_text(encoding="utf-8"))
    reportada = next((p["cuenta_reportada"] for p in patrones["patrones"] if p.get("cuenta_reportada")), None)

    with st.expander("⚙️ Parámetros de detección", expanded=False):
        c = st.columns(4)
        cfg = ConfigAnalisis(
            umbral_reporte=c[0].number_input("Umbral de reporte (S/)", 1000.0, 100000.0, 10000.0, 500.0),
            margen_fragmentacion=c[1].slider("Margen bajo el umbral", 0.05, 0.40, 0.15, 0.01),
            ventana_fragmentacion_dias=c[2].slider("Ventana pitufeo (días)", 1.0, 30.0, 7.0, 1.0),
            min_emisores_fragmentacion=c[3].slider("Mín. emisores", 2, 20, 5),
            max_longitud_ciclo=c[0].slider("Longitud máx. de ciclo", 3, 8, 6),
            ventana_ciclo_dias=c[1].slider("Ventana de ciclo (días)", 1.0, 30.0, 10.0, 1.0),
            tolerancia_monto_ciclo=c[2].slider("Variación de monto en ciclo", 0.02, 0.5, 0.10, 0.01),
            ventana_puente_horas=c[3].slider("Ventana cuenta puente (h)", 1.0, 96.0, 24.0, 1.0),
            ratio_puente=c[0].slider("% reenviado (puente)", 0.5, 1.0, 0.85, 0.01),
            min_receptores_dispersion=c[1].slider("Mín. receptores (dispersión)", 3, 30, 10),
            ventana_dispersion_dias=c[2].slider("Ventana dispersión (días)", 1.0, 30.0, 5.0, 1.0),
            monto_minimo_ciclo=c[3].number_input("Monto mínimo analizado (S/)", 0.0, 100000.0, 5000.0, 500.0))
    cuentas = sorted(g.nodos)
    semilla = st.selectbox("Cuenta reportada (alerta externa, opcional)", ["(ninguna)"] + cuentas,
                           index=(cuentas.index(reportada) + 1) if reportada in cuentas else 0,
                           format_func=lambda x: x if x == "(ninguna)" else etiqueta_nodo(g)(x))
    A = AnalizadorTransacciones(g, cfg)
    res = A.analisis_completo(None if semilla == "(ninguna)" else semilla)
    rk = res["ranking"]
    m = st.columns(7)
    m[0].metric("Riesgo ALTO", sum(r["nivel_riesgo"] == "ALTO" for r in rk), border=True)
    m[1].metric("Riesgo MEDIO", sum(r["nivel_riesgo"] == "MEDIO" for r in rk), border=True)
    m[2].metric("Ciclos", len(res["ciclos"]), border=True)
    m[3].metric("Pitufeo", len(res["fragmentacion"]), border=True)
    m[4].metric("Cadenas puente", len(res["puente"]["cadenas"]), border=True)
    m[5].metric("Dispersión", len(res["dispersion"]), border=True)
    m[6].metric("Grupos cerrados", len(res["grupos"]), border=True)
    st.caption("⚠️ Los patrones son **indicadores** para revisión del oficial de cumplimiento; la detección "
               "computacional no constituye, por sí sola, prueba de fraude o lavado de activos.")

    tabs = st.tabs(["Ranking de riesgo", "Ciclos", "Pitufeo", "Cuentas puente", "Dispersión", "Grupos cerrados",
                    "Rastreo de fondos", "Proximidad", "Validación"])
    colores_nivel = {"ALTO": V.ROJO, "MEDIO": V.NARANJA, "BAJO": "#facc15"}
    with tabs[0]:
        c1, c2 = st.columns([1.6, 1])
        with c1:
            st.dataframe(df(rk, ["cuenta", "titular", "ciudad", "puntaje", "nivel_riesgo", "motivos"]),
                         hide_index=True, width="stretch", height=520,
                         column_config={"puntaje": st.column_config.ProgressColumn("puntaje", min_value=0,
                                                                                    max_value=100, format="%d")})
        with c2:
            marcadas = {r["cuenta"]: colores_nivel[r["nivel_riesgo"]] for r in rk}
            susp = [a.id for a in g.aristas() if a.origen in marcadas and a.destino in marcadas]
            grafico(V.mapa_red(g, nodos=list(marcadas), aristas=susp,
                                       color_arista={x: "#f87171" for x in susp}, nodos_resaltados=marcadas,
                                       geo=usar_mapa_geo(), altura=520, etiquetas=False), width="stretch")
            st.caption("Cuentas con alertas y las transferencias entre ellas (borde rojo = ALTO, naranja = MEDIO).")
        st.download_button("⬇️ Reporte completo (JSON)", json.dumps(res, ensure_ascii=False, indent=2, default=str),
                           "reporte_fraude.json", "application/json")
    with tabs[1]:
        st.markdown("**Circulación de fondos (round-tripping):** el dinero sale y vuelve a la cuenta de origen "
                    "en orden cronológico, con montos casi iguales. Algoritmo: Tarjan para hallar las SCC y DFS "
                    "acotada dentro de cada una (fuera de una SCC no puede haber ciclos).")
        if res["ciclos"]:
            st.dataframe(df(res["ciclos"]), hide_index=True, width="stretch")
            i = st.selectbox("Ver ciclo", range(len(res["ciclos"])),
                             format_func=lambda k: " → ".join(res["ciclos"][k]["cuentas"]))
            cy = res["ciclos"][i]
            grafico(V.diagrama_red(g, cy["cuentas"][:-1], cy["transferencias"],
                                           {c: V.ROJO for c in cy["cuentas"]}), width="stretch")
        else:
            st.info("No se detectaron ciclos con los parámetros actuales.")
    with tabs[2]:
        st.markdown(f"**Fragmentación (pitufeo):** muchas cuentas depositan montos justo debajo del umbral "
                    f"(S/ {cfg.umbral_reporte:,.0f}) en una cuenta concentradora dentro de una ventana corta.")
        if res["fragmentacion"]:
            st.dataframe(df(res["fragmentacion"], ["cuenta", "titular", "ciudad", "emisores", "operaciones",
                                                   "total_recibido", "monto_promedio", "desde", "hasta",
                                                   "salida_posterior_7d", "destinos_posteriores"]),
                         hide_index=True, width="stretch")
            f = res["fragmentacion"][0]
            sal = [a.id for _, a in g.vecinos(f["cuenta"]) if a.destino in f["destinos_posteriores"]]
            nodos = [f["cuenta"]] + f["lista_emisores"] + f["destinos_posteriores"]
            grafico(V.mapa_red(g, nodos=nodos, aristas=f["transferencias"] + sal,
                                       color_arista={**{x: V.NARANJA for x in f["transferencias"]}, **{x: V.ROJO for x in sal}},
                                       grosor_arista={x: 4 for x in sal},
                                       nodos_resaltados={f["cuenta"]: V.ROJO}, geo=usar_mapa_geo(), altura=480),
                            width="stretch")
            st.caption("Naranja: depósitos fraccionados desde la triple frontera · Rojo: salida consolidada posterior.")
        else:
            st.info("Sin casos de fragmentación con los parámetros actuales.")
    with tabs[3]:
        st.markdown("**Cuentas puente (mulas):** reciben un monto alto y reenvían casi todo en pocas horas.")
        if res["puente"]["cadenas"]:
            for cad in res["puente"]["cadenas"]:
                st.markdown(chips(cad), unsafe_allow_html=True)
            cad = res["puente"]["cadenas"][0]
            aristas = [a.id for u, v in zip(cad, cad[1:]) for a in g.aristas_entre(u, v)]
            grafico(V.diagrama_red(g, cad, aristas, {c: V.NARANJA for c in cad}, altura=360), width="stretch")
        st.dataframe(df(res["puente"]["filas"]), hide_index=True, width="stretch")
    with tabs[4]:
        st.markdown("**Dispersión masiva:** una cuenta reparte fondos a muchas cuentas en pocos días "
                    "(se excluyen pagos de planilla, que son dispersión legítima).")
        if res["dispersion"]:
            st.dataframe(df(res["dispersion"]), hide_index=True, width="stretch")
            d0 = res["dispersion"][0]
            ar = [a.id for _, a in g.vecinos(d0["cuenta"]) if a.destino in d0["lista_receptores"]]
            grafico(V.mapa_red(g, nodos=[d0["cuenta"]] + d0["lista_receptores"], aristas=ar,
                                       color_arista={x: V.NARANJA for x in ar}, nodos_resaltados={d0["cuenta"]: V.ROJO},
                                       geo=usar_mapa_geo(), altura=460), width="stretch")
        else:
            st.info("Sin casos de dispersión.")
    with tabs[5]:
        st.markdown("**Grupos cerrados:** componentes fuertemente conexas (Tarjan) de transferencias de monto "
                    "relevante; la densidad indica qué tan entrelazadas están las cuentas.")
        if res["grupos"]:
            st.dataframe(df(res["grupos"]), hide_index=True, width="stretch")
            j = st.selectbox("Ver grupo", range(len(res["grupos"])), format_func=lambda k: ", ".join(res["grupos"][k]["cuentas"]))
            gr = res["grupos"][j]
            grafico(V.diagrama_red(g, gr["cuentas"], None, altura=420), width="stretch")
    with tabs[6]:
        st.markdown("**Rastreo cronológico:** el dinero solo avanza por transferencias posteriores a la que lo "
                    "trajo (árbol de llegada más temprana, variante de Dijkstra sobre el tiempo).")
        p3 = next((p for p in patrones["patrones"] if p["tipo"] == "cadena_puente"), None)
        defecto = p3["origen"] if p3 and p3["origen"] in g.nodos else cuentas[0]
        c = st.columns(4)
        origen = c[0].selectbox("Cuenta de origen", cuentas, index=cuentas.index(defecto), format_func=etiqueta_nodo(g))
        minimo = c[1].number_input("Monto mínimo por tramo (S/)", 0.0, 500000.0, 20000.0, 1000.0)
        saltos = c[2].slider("Saltos máximos", 1, 10, 8)
        desde = c[3].text_input("Desde (AAAA-MM-DD)", "2026-09-01")
        try:
            rast = A.rastrear_fondos(origen, desde or None, saltos, minimo)
        except ValueError:
            st.error("Fecha inválida. Use AAAA-MM-DD.")
            rast = None
        if rast:
            k = st.columns(3)
            k[0].metric("Cuentas alcanzadas", rast["alcanzadas"])
            k[1].metric("Intermediarios", len(rast["intermediarios"]))
            k[2].metric("Receptores finales", len(rast["receptores_finales"]))
            if rast["filas"]:
                grafico(V.diagrama_red(g, [origen] + [f["cuenta"] for f in rast["filas"]], rast["aristas_arbol"],
                                               {origen: V.ROJO, **{x: V.NARANJA for x in rast["intermediarios"]}},
                                               altura=420), width="stretch")
                st.dataframe(df(rast["filas"]), hide_index=True, width="stretch")
    with tabs[7]:
        c1, c2 = st.columns(2)
        a = c1.selectbox("Cuenta A", cuentas, index=cuentas.index(reportada) if reportada in cuentas else 0,
                         format_func=etiqueta_nodo(g), key="prox_a")
        b = c2.selectbox("Cuenta B", cuentas, index=min(len(cuentas) - 1, 359), format_func=etiqueta_nodo(g), key="prox_b")
        p = A.proximidad(a, b)
        if p["saltos"] is None:
            st.warning("Las cuentas no están conectadas.")
        else:
            st.markdown(f"**Distancia: {p['saltos']} salto(s)** (BFS, sin importar el sentido del dinero)")
            st.markdown(chips(p["camino"]), unsafe_allow_html=True)
        st.markdown("##### Relaciones de la cuenta A por nivel")
        nivel = st.slider("Nivel máximo", 1, 3, 2)
        rel = A.relaciones(a, nivel)
        st.dataframe(df(rel), hide_index=True, width="stretch", height=320)
    with tabs[8]:
        st.markdown("Comparación con los **patrones plantados** en los datos simulados (verdad de referencia).")
        st.dataframe(df(evaluar_contra_patrones(res, patrones)), hide_index=True, width="stretch")
        for p in patrones["patrones"]:
            st.markdown(f"- **{p['id']} · {p['tipo']}**: {p['descripcion']}")


# ============================================================ MÓDULO 3
def pagina_enrutamiento():
    st.title("3 · Enrutamiento de operaciones y comisiones")
    g = gestor()["enrutamiento"]
    E = Enrutador(g)
    ids = list(g.nodos)
    fmt = etiqueta_nodo(g)
    c = st.columns([1.3, 1.3, 0.9, 1.1])
    origen = c[0].selectbox("Origen", ids, index=ids.index("AG_LIM") if "AG_LIM" in ids else 0, format_func=fmt)
    destino = c[1].selectbox("Destino", ids, index=ids.index("CORR_CAB") if "CORR_CAB" in ids else 1, format_func=fmt)
    monto = c[2].number_input("Monto (S/)", 1.0, 1_000_000.0, 1500.0, 100.0)
    criterio = c[3].selectbox("Minimizar", list(CRITERIOS), format_func=CRITERIOS.get)
    with st.expander("Opciones avanzadas: algoritmo, promociones, cierres temporales", expanded=False):
        a1, a2 = st.columns(2)
        algoritmo = a1.selectbox("Algoritmo", ["auto", "dijkstra", "bellman_ford", "floyd_warshall", "backtracking"],
                                 format_func=lambda x: {"auto": "Automático (selección justificada)"}.get(x, x))
        promo = a2.selectbox("Promociones vigentes", list(PROMOCIONES), format_func=lambda x: f"{x}: {DESCRIPCION_PROMOCIONES[x]}")
        b1, b2 = st.columns(2)
        cerrar_n = multi(b1, "Cerrar temporalmente (sucursales / entidades)", [i for i in ids if i not in (origen, destino)],
                                  format_func=fmt)
        cerrar_a = multi(b2, "Cerrar temporalmente (canales)", [a.id for a in g.aristas()],
                                  format_func=etiqueta_arista(g))
        pesos = (0.5, 0.3, 0.2)
        if criterio == "combinado":
            w = st.columns(3)
            pesos = (w[0].slider("Peso comisión", 0.0, 1.0, 0.5), w[1].slider("Peso tiempo", 0.0, 1.0, 0.3),
                     w[2].slider("Peso riesgo", 0.0, 1.0, 0.2))
    if origen == destino:
        st.warning("Elige un origen y un destino distintos.")
        return
    r = E.ruta_optima(origen, destino, monto, criterio, algoritmo, promo, cerrar_n, cerrar_a, pesos)

    if r.existe:
        tramo = ", ".join(f"{a.get('tipo_operacion')}/{a.get('canal')}" for a in r.aristas)
        st.markdown(f'<div class="caja-respuesta">💡 <b>¿Por qué ruta la comisión es más baja?</b> '
                    f'Para enviar <b>S/ {monto:,.2f}</b> de <b>{origen}</b> a <b>{destino}</b> minimizando '
                    f'<i>{CRITERIOS[criterio][0].lower() + CRITERIOS[criterio][1:]}</i>, la mejor ruta cuesta <b>S/ {r.comision:,.2f}</b> '
                    f'en comisiones y tarda {r.tiempo_min:,.0f} min ({tramo}).</div>', unsafe_allow_html=True)
        st.markdown(chips(r.nodos), unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="caja-alerta">❌ <b>Sin ruta factible.</b> {r.motivo_sin_ruta}</div>',
                    unsafe_allow_html=True)
        if r.ciclo_negativo:
            st.markdown("Ciclo negativo: " + chips(r.ciclo_negativo), unsafe_allow_html=True)
    m = st.columns(5)
    m[0].metric("Comisión total", f"S/ {r.comision:,.2f}" if r.existe else "—", border=True)
    m[1].metric("Tiempo", f"{r.tiempo_min:,.0f} min" if r.existe else "—", border=True)
    m[2].metric("Prob. de falla", f"{100 * r.riesgo:.2f} %" if r.existe else "—", border=True)
    m[3].metric("Saltos", len(r.aristas), border=True)
    m[4].metric("Algoritmo", r.algoritmo.replace("_", "-").title(), f"{r.tiempo_ejecucion_ms:.3f} ms", delta_color="off",
                delta_arrow="off", border=True)
    if r.justificacion:
        with st.expander("¿Por qué este algoritmo?", expanded=True):
            st.write(r.justificacion)

    tabs = st.tabs(["Ruta en el mapa", "Rutas alternativas (Yen)", "Todas las rutas (backtracking)",
                    "Comparar algoritmos", "Cierre de sucursales", "Matriz de comisiones (Floyd-Warshall)"])
    with tabs[0]:
        col_r = {a.id: V.ROJO for a in r.aristas}
        grafico(V.mapa_red(g, color_arista=col_r, grosor_arista={a.id: 4.5 for a in r.aristas},
                                   orden_ruta=r.nodos, geo=usar_mapa_geo(), altura=560), width="stretch")
        if r.existe:
            pasos = [{"paso": i, "de": a.origen, "a": a.destino, "operación": a.get("tipo_operacion"),
                      "canal": a.get("canal"), "comisión S/": round(E.comision_arista(a, monto, promo), 2),
                      "fija": a.get("comision_fija"), "%": a.get("comision_pct"), "tiempo_min": a.get("tiempo_min"),
                      "riesgo": a.get("riesgo"), "límite S/": a.get("limite")} for i, a in enumerate(r.aristas, 1)]
            st.dataframe(df(pasos), hide_index=True, width="stretch")
    with tabs[1]:
        k = st.slider("Número de rutas", 2, 10, 5)
        alt = E.rutas_alternativas(origen, destino, monto, criterio, k, promo, cerrar_n, cerrar_a)
        if alt:
            st.dataframe(df(alt, ["opcion", "ruta", "canales", "comision_S/", "tiempo_min", "prob_falla_%",
                                  "valor_criterio"]), hide_index=True, width="stretch")
            st.download_button("⬇️ Reporte comparativo de rutas y comisiones (CSV)",
                               df(alt).to_csv(index=False), f"rutas_{origen}_{destino}.csv", "text/csv")
            sel = st.radio("Ver en el mapa", [f["opcion"] for f in alt], horizontal=True)
            f = alt[sel - 1]
            grafico(V.mapa_red(g, color_arista={x: V.NARANJA for x in f["aristas"]},
                                       grosor_arista={x: 4.5 for x in f["aristas"]}, orden_ruta=f["ruta"],
                                       geo=usar_mapa_geo(), altura=480), width="stretch")
        else:
            st.info("No hay rutas factibles.")
    with tabs[2]:
        saltos = st.slider("Saltos máximos", 2, 10, 6)
        todas, stats = E.enumerar_alternativas(origen, destino, monto, saltos, cerrar_n, cerrar_a)
        st.markdown(f"**{len(todas)} rutas simples disponibles** · nodos explorados: {stats['nodos_explorados']} · "
                    f"podas por saltos: {stats['podas_por_saltos']}. El backtracking lista todas las alternativas; "
                    "su costo crece exponencialmente con los saltos, por eso no se usa para optimizar.")
        st.dataframe(df(todas), hide_index=True, width="stretch", height=380)
    with tabs[3]:
        comp = E.comparar_algoritmos(origen, destino, monto, criterio, promo, cerrar_n, cerrar_a)
        st.dataframe(df(comp, ["algoritmo", "ruta", "comision_S/", "valor_criterio", "tiempo_ejecucion_ms",
                               "operaciones", "coincide_con_optimo", "observacion"]), hide_index=True, width="stretch")
        st.download_button("⬇️ Reporte de comparación de algoritmos (CSV)", df(comp).to_csv(index=False),
                           "comparacion_algoritmos.csv", "text/csv")
        import plotly.graph_objects as go
        fig = go.Figure(go.Bar(x=[c["algoritmo"] for c in comp], y=[c["tiempo_ejecucion_ms"] for c in comp],
                               marker_color=["#16a34a", "#2563eb", "#9333ea", "#ea580c"],
                               text=[f"{c['tiempo_ejecucion_ms']:.3f} ms" for c in comp], textposition="outside"))
        fig.update_layout(height=320, yaxis_title="tiempo (ms)", margin={"t": 20, "b": 0})
        grafico(fig, width="stretch")
        st.caption("Con pesos ≥ 0 todos llegan al mismo óptimo; Dijkstra lo hace con menos operaciones. Prueba la "
                   "promoción 'promo_interoperabilidad' para ver por qué Dijkstra no sirve con pesos negativos.")
    with tabs[4]:
        st.markdown("Cierra una o varias sucursales/canales y compara la ruta antes y después.")
        cerrar_sim = multi(st, "Simular cierre de", [i for i in ids if i not in (origen, destino)],
                                    default=[x for x in ["BILL_B"] if x in ids and x not in (origen, destino)],
                                    format_func=fmt, key="sim_cierre")
        imp = E.impacto_cierre(origen, destino, monto, criterio, cerrar_sim)
        a, b = st.columns(2)
        with a:
            st.markdown("**Antes**")
            st.markdown(chips(imp["antes"].nodos) if imp["antes"].existe else "sin ruta", unsafe_allow_html=True)
            st.metric("Comisión", f"S/ {imp['antes'].comision:,.2f}")
        with b:
            st.markdown("**Después del cierre**")
            if imp["sin_ruta"]:
                st.error(imp["despues"].motivo_sin_ruta)
            else:
                st.markdown(chips(imp["despues"].nodos), unsafe_allow_html=True)
                st.metric("Comisión", f"S/ {imp['despues'].comision:,.2f}", f"{imp['incremento_comision']:+,.2f} S/",
                          delta_color="inverse")
        st.markdown("##### Puntos únicos de falla (si se cierra el nodo, quedan puntos inalcanzables)")
        st.dataframe(df(nodos_criticos(g, origen)), hide_index=True, width="stretch")
    with tabs[5]:
        agencias = [i for i in ids if g.nodos[i].tipo == "agencia"]
        mt = E.matriz_costos(agencias, monto, "comision")
        st.markdown(f"Comisión mínima entre todas las agencias para S/ {monto:,.0f} · Floyd-Warshall sobre "
                    f"{mt['nodos_red']} nodos en {mt['tiempo_ms']:.2f} ms (O(V³)). Aquí sí conviene, porque se "
                    "piden **todos** los pares a la vez.")
        grafico(V.heatmap_matriz(mt["matriz"]), width="stretch")


# ============================================================ MÓDULO 4
def pagina_liquidez():
    st.title("4 · Distribución de liquidez hacia bóvedas")
    g = gestor()["liquidez"]
    P = PlanificadorLiquidez(g)
    escenarios = cargar_escenarios()
    c = st.columns([1.2, 1, 1])
    etiquetas = {"normal": "Normal", "vaciante": "Vaciante (ríos bajos)", "diciembre": "Diciembre (alta demanda)",
                 "vuelo_cancelado": "Vuelo cancelado", "bloqueo_carretera_central": "Bloqueo carretera central",
                 "crisis_amazonica": "Crisis amazónica"}
    nombre = c[0].selectbox("Escenario", list(escenarios), format_func=lambda k: etiquetas.get(k, k.replace("_", " ").capitalize()))
    politica = c[1].radio("Política de asignación", ["equitativa", "costo_minimo"], horizontal=True,
                          format_func=lambda x: {"equitativa": "Equitativa", "costo_minimo": "Costo mínimo puro"}[x],
                          help="Equitativa: primero garantiza a todas las agencias la misma cobertura mínima y luego "
                               "completa al menor costo. Costo mínimo puro: puede dejar sin efectivo a las agencias "
                               "más caras de abastecer.")
    algoritmo = c[2].radio("Algoritmo de flujo máximo", ["dinic", "edmonds_karp"], horizontal=True,
                           format_func=lambda x: {"dinic": "Dinic", "edmonds_karp": "Edmonds-Karp"}[x])
    base = escenarios[nombre]
    st.caption(f"📌 {base.descripcion}")
    with st.expander("Ajustar el escenario", expanded=False):
        s = st.columns(4)
        esc = Escenario(nombre=nombre, descripcion=base.descripcion,
                        factor_fluvial=s[0].slider("Capacidad fluvial", 0.0, 1.5, base.factor_fluvial, 0.05),
                        factor_aereo=s[1].slider("Capacidad aérea", 0.0, 1.5, base.factor_aereo, 0.05),
                        factor_terrestre=s[2].slider("Capacidad terrestre", 0.0, 1.5, base.factor_terrestre, 0.05),
                        factor_demanda=s[3].slider("Demanda", 0.5, 2.0, base.factor_demanda, 0.05),
                        cerrar_aristas=multi(st, "Rutas cerradas", [a.id for a in g.aristas()],
                                                      default=base.cerrar_aristas, format_func=etiqueta_arista(g)),
                        cerrar_nodos=multi(st, "Agencias / bóvedas cerradas", list(g.nodos),
                                                    default=base.cerrar_nodos, format_func=etiqueta_nodo(g)))
    r = P.calcular(esc, algoritmo, politica)
    m = st.columns(6)
    m[0].metric("Efectivo distribuido", f"S/ {r.flujo_maximo / 1000:,.1f} M", border=True)
    m[1].metric("Demanda total", f"S/ {r.demanda_total / 1000:,.1f} M", border=True)
    m[2].metric("Cobertura", f"{r.cobertura_pct:.1f} %", border=True)
    m[3].metric("Déficit", f"S/ {r.deficit / 1000:,.2f} M", border=True)
    m[4].metric("Costo de traslado", f"S/ {r.costo_total:,.0f}", border=True)
    m[5].metric("Cobertura garantizada", f"{r.estadisticas['cobertura_garantizada_pct']:.1f} %" if politica == "equitativa"
                else "—", help="Fracción mínima de su demanda que recibe TODA agencia (búsqueda binaria + Dinic).",
                border=True)
    if r.alertas:
        st.markdown('<div class="caja-alerta">' + "<br>".join("• " + al for al in r.alertas) + "</div>",
                    unsafe_allow_html=True)
    else:
        st.success("Todas las agencias reciben el 100 % de su demanda.")

    tabs = st.tabs(["Mapa de distribución", "Flujo (Sankey)", "Agencias", "Rutas", "Cuellos de botella",
                    "Comparar escenarios", "Red troncal (MST)", "Verificación"])
    with tabs[0]:
        maxf = max((x["flujo"] for x in r.rutas), default=1) or 1
        ganancia = {c["id"]: c.get("ganancia_si_amplia_20pct", 0) for c in r.cuellos_botella}
        colores = {x["id"]: ((V.ROJO if ganancia.get(x["id"], 0) > 0 else V.NARANJA) if x["cuello_botella"]
                             else V.COLOR_MODO.get(x["modo"], V.GRIS))
                   for x in r.rutas if x["flujo"] > 0 or x["cuello_botella"]}
        grosor = {x["id"]: 1.5 + 8 * x["flujo"] / maxf for x in r.rutas}
        textos = {x["id"]: f"flujo {x['flujo']:,.0f} / cap {x['capacidad']:,.0f} ({x['utilizacion_pct']} %)"
                  for x in r.rutas}
        deficit = {a["id"]: V.ROJO for a in r.agencias if a["estado"] != "atendida"}
        grafico(V.mapa_red(g, color_arista=colores, grosor_arista=grosor, texto_arista=textos,
                                   nodos_resaltados=deficit, color_por_modo=True, geo=usar_mapa_geo(), altura=620,
                                   leyenda_extra={"Terrestre": V.COLOR_MODO["terrestre"], "Aérea": V.COLOR_MODO["aereo"],
                                                  "Fluvial": V.COLOR_MODO["fluvial"], "Cuello crítico": V.ROJO,
                                                  "Corte mínimo (sin ganancia al ampliar)": V.NARANJA}),
                        width="stretch")
        st.caption("Grosor ∝ efectivo trasladado. Rojo: cuellos críticos (ampliarlos aumenta el flujo). Naranja: otras rutas del "
                   "corte mínimo. Borde rojo: agencias con déficit.")
    with tabs[1]:
        grafico(V.sankey_liquidez(g, r.rutas), width="stretch")
    with tabs[2]:
        a, b = st.columns([1, 1])
        grafico(V.barras_cobertura(r.agencias), a)
        b.dataframe(df(r.regiones), hide_index=True, width="stretch")
        b.dataframe(df(r.bovedas), hide_index=True, width="stretch")
        st.dataframe(df(r.agencias), hide_index=True, width="stretch",
                     column_config={"cobertura_pct": st.column_config.ProgressColumn("cobertura %", min_value=0,
                                                                                     max_value=100, format="%.1f")})
        st.download_button("⬇️ Reporte de distribución: cantidades y necesidades pendientes (CSV)",
                           df(r.agencias).to_csv(index=False), f"liquidez_agencias_{esc.nombre}.csv", "text/csv")
    with tabs[3]:
        st.dataframe(df(r.rutas), hide_index=True, width="stretch", height=520,
                     column_config={"utilizacion_pct": st.column_config.ProgressColumn("utilización %", min_value=0,
                                                                                       max_value=100, format="%.0f")})
        st.download_button("⬇️ Reporte de capacidades utilizadas por ruta (CSV)", df(r.rutas).to_csv(index=False),
                           f"liquidez_rutas_{esc.nombre}.csv", "text/csv")
    with tabs[4]:
        st.markdown("**Teorema flujo máximo – corte mínimo:** el efectivo que puede llegar está limitado por la "
                    "capacidad total de las rutas del corte mínimo. Ampliar una ruta del corte puede aumentar el flujo.")
        st.dataframe(df(r.cuellos_botella, ["id", "origen", "destino", "modo", "capacidad", "flujo",
                                            "ganancia_si_amplia_20pct"]), hide_index=True, width="stretch")
        if r.bovedas_agotadas:
            st.write("Bóvedas que despachan todo su efectivo: " + ", ".join(r.bovedas_agotadas))
        if r.cuellos_botella:
            x1, x2 = st.columns(2)
            ruta = x1.selectbox("Simular ampliación de", [c["id"] for c in sorted(r.cuellos_botella, key=lambda c: -c.get("ganancia_si_amplia_20pct", 0))],
                                 format_func=etiqueta_arista(g))
            inc = x2.slider("Capacidad adicional (miles de S/)", 0, 10000, 2000, 250)
            b = P.beneficio_ampliacion(esc, ruta, inc)
            st.metric("Efectivo adicional distribuido", f"S/ {b['ganancia'] * 1000:,.0f}",
                      f"de {b['flujo_antes']:,.0f} a {b['flujo_despues']:,.0f} mil")
    with tabs[5]:
        filas = []
        for k, e in escenarios.items():
            rr = P.calcular(e, algoritmo, politica, evaluar_ampliaciones=False)
            selva = next((x for x in rr.regiones if x["region"] == "Selva"), {"cobertura_pct": None})
            filas.append({"escenario": k, "flujo_mil_S/": round(rr.flujo_maximo), "demanda_mil_S/": round(rr.demanda_total),
                          "cobertura_%": round(rr.cobertura_pct, 1), "cobertura_selva_%": selva["cobertura_pct"],
                          "garantizada_%": rr.estadisticas["cobertura_garantizada_pct"],
                          "costo_S/": round(rr.costo_total), "agencias_con_deficit": sum(a["estado"] != "atendida" for a in rr.agencias)})
        st.dataframe(df(filas), hide_index=True, width="stretch")
        import plotly.graph_objects as go
        fig = go.Figure([go.Bar(name="Cobertura total", x=[f["escenario"] for f in filas], y=[f["cobertura_%"] for f in filas],
                                marker_color="#2563eb"),
                         go.Bar(name="Cobertura Selva", x=[f["escenario"] for f in filas], y=[f["cobertura_selva_%"] for f in filas],
                                marker_color="#10b981")])
        fig.update_layout(barmode="group", height=360, yaxis_title="%", margin={"t": 20, "b": 0}, yaxis_range=[0, 105])
        grafico(fig, width="stretch")
    with tabs[6]:
        x1, x2 = st.columns(2)
        alg = x1.radio("Algoritmo", ["kruskal", "prim"], horizontal=True, format_func=str.capitalize)
        crit = x2.radio("Peso", ["costo", "distancia_km"], horizontal=True)
        t = P.red_troncal(alg, crit)
        st.markdown(f"**Red troncal mínima:** {len(t['aristas'])} rutas conectan los {t['nodos']} puntos con "
                    f"{crit} total {t['costo_total']:,.2f} ({t['rutas_descartadas']} rutas fuera del árbol) · "
                    f"{t['tiempo_ms']:.3f} ms.")
        ids_t = [x["id"] for x in t["aristas"]]
        grafico(V.mapa_red(g, color_arista={x: "#7c3aed" for x in ids_t}, grosor_arista={x: 4 for x in ids_t},
                                   geo=usar_mapa_geo(), altura=520), width="stretch")
        st.info("El MST responde '¿qué rutas mínimas mantienen todo conectado?' (útil para decidir qué rutas "
                "custodiar o contratar), pero ignora capacidades, ofertas y demandas: no puede decir cuánto "
                "efectivo llega a cada agencia. Por eso la distribución se resuelve con flujo máximo.")
    with tabs[7]:
        st.json(r.verificacion)
        st.json(r.estadisticas)


# ============================================================ MÓDULO 5
def pagina_evaluacion():
    st.title("5 · Evaluación, comparación y validación")
    tabs = st.tabs(["Casos de prueba", "Comparación empírica", "Complejidad y decisiones", "Validación con NetworkX",
                    "Reporte"])
    with tabs[0]:
        if st.button("▶️ Ejecutar casos de prueba", type="primary") or "casos" not in st.session_state:
            with st.spinner("Ejecutando…"):
                st.session_state.casos = casos_de_prueba()
        casos = st.session_state.casos
        ok = sum(c["estado"] == "✔" for c in casos)
        st.metric("Casos superados", f"{ok} / {len(casos)}")
        st.dataframe(df(casos), hide_index=True, width="stretch", height=620)
    with tabs[1]:
        familias = {"Rutas más cortas (Dijkstra · Bellman-Ford · Floyd-Warshall)": "caminos",
                    "Flujo máximo (Edmonds-Karp · Dinic · costo mínimo)": "flujo",
                    "Recorridos (BFS · DFS · Tarjan · Kosaraju)": "recorridos",
                    "Árbol de expansión mínima (Kruskal · Prim)": "mst"}
        fam = familias[st.selectbox("Familia de algoritmos", list(familias))]
        tam_def = {"caminos": [100, 200, 400, 800], "flujo": [100, 200, 400, 800],
                   "recorridos": [500, 1000, 2000, 4000, 8000], "mst": [500, 1000, 2000, 4000, 8000]}[fam]
        opciones = sorted(set(tam_def + [50, 100, 200, 400, 800, 1600, 3200, 8000, 16000]))
        c = st.columns(3)
        tams = multi(c[0], "Tamaños (nodos)", opciones, default=tam_def)
        rep = c[1].slider("Repeticiones (se toma el mínimo)", 1, 5, 3)
        mem = c[2].checkbox("Medir memoria (más lento)", False)
        if st.button("▶️ Ejecutar comparación", type="primary"):
            f = {"caminos": benchmark_caminos, "flujo": benchmark_flujo, "recorridos": benchmark_recorridos,
                 "mst": benchmark_mst}[fam]
            with st.spinner("Midiendo tiempos…"):
                st.session_state[f"bench_{fam}"] = f(tuple(sorted(tams)), repeticiones=rep, memoria=mem)
        filas = st.session_state.get(f"bench_{fam}")
        if filas:
            a, b = st.columns([1.3, 1])
            grafico(V.lineas_benchmark(filas), a)
            b.markdown("**Exponente empírico** (pendiente en escala log-log)")
            b.dataframe(df(pendientes_loglog(filas)), hide_index=True, width="stretch")
            b.caption("Floyd-Warshall se limita a n ≤ 200 y Bellman-Ford a n ≤ 800; el flujo de costo mínimo a "
                      "n ≤ 400 (crecen demasiado rápido).")
            st.dataframe(df(filas), hide_index=True, width="stretch")
        else:
            st.info("Elige los tamaños y pulsa «Ejecutar comparación».")
    with tabs[2]:
        st.dataframe(df(TABLA_COMPLEJIDAD), hide_index=True, width="stretch", height=480)
    with tabs[3]:
        n = st.slider("Redes aleatorias a comparar", 5, 50, 15)
        if st.button("▶️ Validar contra NetworkX"):
            with st.spinner("Comparando…"):
                st.session_state.val_nx = validar_con_networkx(n)
        if "val_nx" in st.session_state:
            st.dataframe(df(st.session_state.val_nx), hide_index=True, width="stretch")
    with tabs[4]:
        partes = ["# Reporte de evaluación — OptiFin Amazonía\n"]
        if "casos" in st.session_state:
            partes += ["## Casos de prueba\n", markdown_tabla(st.session_state.casos)]
        for fam in ("caminos", "flujo", "recorridos", "mst"):
            if st.session_state.get(f"bench_{fam}"):
                partes += [f"## Benchmark: {fam}\n", markdown_tabla(st.session_state[f"bench_{fam}"]),
                           "\n", markdown_tabla(pendientes_loglog(st.session_state[f"bench_{fam}"]))]
        partes += ["## Decisiones algorítmicas\n", markdown_tabla(TABLA_COMPLEJIDAD)]
        texto = "\n".join(partes)
        st.download_button("⬇️ Descargar reporte (Markdown)", texto, "reporte_evaluacion.md", "text/markdown")
        st.markdown(texto)


RUTAS = dict(zip(PAGINAS, [pagina_inicio, pagina_gestion, pagina_fraude, pagina_enrutamiento,
                           pagina_liquidez, pagina_evaluacion]))
RUTAS[pagina]()
