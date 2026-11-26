"""Construcción de figuras Plotly para la interfaz (mapas, diagramas, Sankey, gráficos)."""

from __future__ import annotations

import math
from typing import Any, Iterable

import plotly.graph_objects as go

from ..graph import Grafo

COLOR_TIPO = {
    "agencia": "#2563eb", "boveda_central": "#92400e", "boveda_regional": "#f59e0b",
    "compensacion": "#7c3aed", "billetera": "#db2777", "procesador": "#6b7280", "servidor": "#6b7280",
    "entidad": "#0d9488", "corresponsal": "#16a34a", "atm": "#0891b2", "cuenta": "#64748b",
    "empresa": "#334155", "cliente": "#94a3b8", "otro": "#94a3b8",
}
NOMBRE_TIPO = {
    "agencia": "Agencia", "boveda_central": "Bóveda central", "boveda_regional": "Bóveda regional",
    "compensacion": "Cámara de compensación", "billetera": "Billetera digital", "procesador": "Procesador",
    "servidor": "Servidor / red", "entidad": "Otra entidad", "corresponsal": "Agente corresponsal",
    "atm": "Cajero (ATM)", "cuenta": "Cuenta persona", "empresa": "Cuenta empresa", "cliente": "Cliente",
    "otro": "Otro",
}
COLOR_MODO = {"terrestre": "#a8a29e", "aereo": "#38bdf8", "fluvial": "#10b981"}
ROJO = "#dc2626"
NARANJA = "#ea580c"
GRIS = "#cbd5e1"


def _posiciones(g: Grafo, ids: Iterable[str]) -> dict[str, tuple[float, float]]:
    """lat/lon de cada nodo; los nodos sin coordenadas se ubican en círculo alrededor del centro."""
    ids = list(ids)
    pos = {}
    con = [g.nodos[i] for i in ids if g.nodos[i].lat is not None and g.nodos[i].lon is not None]
    clat = sum(n.lat for n in con) / len(con) if con else -9.0
    clon = sum(n.lon for n in con) / len(con) if con else -75.0
    sin = [i for i in ids if g.nodos[i].lat is None or g.nodos[i].lon is None]
    for i in ids:
        n = g.nodos[i]
        if n.lat is not None and n.lon is not None:
            pos[i] = (n.lat, n.lon)
    for k, i in enumerate(sin):
        ang = 2 * math.pi * k / max(len(sin), 1)
        pos[i] = (clat + 2.5 * math.sin(ang), clon + 2.5 * math.cos(ang))
    return pos


def mapa_red(g: Grafo, *, nodos: Iterable[str] | None = None, aristas: Iterable[str] | None = None,
             color_arista: dict[str, str] | None = None, grosor_arista: dict[str, float] | None = None,
             texto_arista: dict[str, str] | None = None, nodos_resaltados: dict[str, str] | None = None,
             orden_ruta: list[str] | None = None, color_por_modo: bool = False, etiquetas: bool = True,
             geo: bool = True, altura: int = 560, hover_aristas: bool = True,
             leyenda_extra: dict[str, str] | None = None) -> go.Figure:
    """
    Mapa de la red sobre el Perú.  Las aristas se agrupan por color en pocas trazas
    (líneas separadas por None) para que el dibujo sea rápido incluso con miles de aristas.
    """
    ids_n = list(nodos) if nodos is not None else list(g.nodos)
    conj = set(ids_n)
    lista_a = [g.arista(a) for a in aristas] if aristas is not None else \
        [a for a in g.aristas() if a.origen in conj and a.destino in conj]
    pos = _posiciones(g, ids_n)
    color_arista = color_arista or {}
    grosor_arista = grosor_arista or {}
    texto_arista = texto_arista or {}
    Scatter = go.Scattergeo if geo else go.Scatter

    def xy(lat, lon):
        return {"lat": lat, "lon": lon} if geo else {"x": lon, "y": lat}

    fig = go.Figure()
    grupos: dict[tuple[str, float, bool], list] = {}
    medios_lat, medios_lon, medios_txt = [], [], []
    for a in lista_a:
        if a.origen not in pos or a.destino not in pos:
            continue
        cerrada = not a.activa or not g.nodos[a.origen].activo or not g.nodos[a.destino].activo
        if a.id in color_arista:
            col = color_arista[a.id]
        elif cerrada:
            col = "#fca5a5"
        elif color_por_modo:
            col = COLOR_MODO.get(a.get("modo"), GRIS)
        else:
            col = GRIS
        w = grosor_arista.get(a.id, 1.2)
        clave = (col, round(w, 1), cerrada)
        (la1, lo1), (la2, lo2) = pos[a.origen], pos[a.destino]
        grupos.setdefault(clave, []).append((la1, lo1, la2, lo2))
        if hover_aristas and len(lista_a) <= 600:
            medios_lat.append(la1 + 0.62 * (la2 - la1))
            medios_lon.append(lo1 + 0.62 * (lo2 - lo1))
            extra = texto_arista.get(a.id, "")
            attrs = ", ".join(f"{k}={v}" for k, v in a.atributos.items()
                              if k in ("canal", "modo", "comision_fija", "comision_pct", "tiempo_min",
                                       "limite", "capacidad", "costo", "monto", "fecha", "riesgo"))
            medios_txt.append(f"<b>{a.id}</b> {a.origen} → {a.destino}<br>{attrs}"
                              + (f"<br>{extra}" if extra else "") + ("<br><b>CERRADA</b>" if cerrada else ""))
    for (col, w, cerrada), segs in sorted(grupos.items(), key=lambda x: (x[0][0] != GRIS, x[0][1])):
        lat, lon = [], []
        for la1, lo1, la2, lo2 in segs:
            lat += [la1, la2, None]
            lon += [lo1, lo2, None]
        fig.add_trace(Scatter(**xy(lat, lon), mode="lines", hoverinfo="skip", showlegend=False,
                              line={"color": col, "width": w, **({"dash": "dot"} if cerrada else {})}))
    if medios_lat:
        fig.add_trace(Scatter(**xy(medios_lat, medios_lon), mode="markers", showlegend=False,
                              marker={"size": 6, "color": "rgba(100,116,139,0.35)", "symbol": "diamond"},
                              hovertext=medios_txt, hoverinfo="text"))

    nodos_resaltados = nodos_resaltados or {}
    por_tipo: dict[str, list[str]] = {}
    for i in ids_n:
        por_tipo.setdefault(g.nodos[i].tipo, []).append(i)
    for tipo, lista in sorted(por_tipo.items()):
        lat = [pos[i][0] for i in lista]
        lon = [pos[i][1] for i in lista]
        hov = []
        for i in lista:
            n = g.nodos[i]
            extra = "".join(f"<br>{k}: {v}" for k, v in n.atributos.items()
                            if k in ("ciudad", "region", "oferta", "demanda", "entidad", "actividad", "ingreso_mensual"))
            hov.append(f"<b>{i}</b> — {n.nombre}{extra}" + ("" if n.activo else "<br><b>CERRADO</b>"))
        tam = 9 if len(ids_n) > 150 else 13
        fig.add_trace(Scatter(**xy(lat, lon), mode="markers", name=NOMBRE_TIPO.get(tipo, tipo),
                              marker={"size": [tam + 6 if i in nodos_resaltados else tam for i in lista],
                                      "color": [ "#fecaca" if not g.nodos[i].activo else COLOR_TIPO.get(tipo, "#94a3b8")
                                                for i in lista],
                                      "line": {"width": [3 if i in nodos_resaltados else 1 for i in lista],
                                               "color": [nodos_resaltados.get(i, "white") for i in lista]},
                                      "symbol": ["x" if not g.nodos[i].activo else "circle" for i in lista]},
                              hovertext=hov, hoverinfo="text"))
    if etiquetas and len(ids_n) <= 60:
        fig.add_trace(Scatter(**xy([pos[i][0] for i in ids_n], [pos[i][1] for i in ids_n]), mode="text",
                              text=[i for i in ids_n], textposition="top center", showlegend=False,
                              textfont={"size": 9, "color": "#334155"}, hoverinfo="skip"))
    if orden_ruta:
        fig.add_trace(Scatter(**xy([pos[i][0] for i in orden_ruta if i in pos],
                                   [pos[i][1] for i in orden_ruta if i in pos]),
                              mode="markers+text", showlegend=False, hoverinfo="skip",
                              text=[str(k) for k, i in enumerate(orden_ruta, 1) if i in pos],
                              textfont={"color": "white", "size": 10},
                              marker={"size": 20, "color": ROJO, "line": {"width": 2, "color": "white"}}))
    for nombre, col in (leyenda_extra or {}).items():
        fig.add_trace(Scatter(**xy([None], [None]), mode="lines", name=nombre, line={"color": col, "width": 4}))

    if geo:
        lats = [p[0] for p in pos.values()] or [-9]
        lons = [p[1] for p in pos.values()] or [-75]
        fig.update_geos(scope="south america", projection_type="mercator", showland=True, landcolor="#f8fafc",
                        showcountries=True, countrycolor="#94a3b8", showocean=True, oceancolor="#e0f2fe",
                        showrivers=True, rivercolor="#7dd3fc", riverwidth=1.2, showlakes=True,
                        lakecolor="#e0f2fe", showcoastlines=True, coastlinecolor="#94a3b8",
                        resolution=50,
                        lataxis_range=[min(lats) - 1.2, max(lats) + 1.2],
                        lonaxis_range=[min(lons) - 1.5, max(lons) + 1.5])
    else:
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False, scaleanchor="x", scaleratio=1)
        fig.update_layout(plot_bgcolor="#f8fafc")
    fig.update_layout(height=altura, margin={"l": 0, "r": 0, "t": 10, "b": 0},
                      legend={"orientation": "h", "yanchor": "bottom", "y": 1.0, "x": 0, "font": {"size": 11}})
    return fig


def diagrama_red(g: Grafo, nodos: Iterable[str], aristas: Iterable[str] | None = None,
                 resaltados: dict[str, str] | None = None, etiqueta_arista: str | None = "monto",
                 altura: int = 480, semilla: int = 4) -> go.Figure:
    """Diagrama abstracto con flechas (layout de fuerzas) para subredes de cuentas."""
    import networkx as nx
    nodos = list(dict.fromkeys(nodos))
    conj = set(nodos)
    lista = [g.arista(a) for a in aristas] if aristas is not None else \
        [a for a in g.aristas() if a.origen in conj and a.destino in conj]
    G = nx.DiGraph()
    G.add_nodes_from(nodos)
    for a in lista:
        G.add_edge(a.origen, a.destino)
    pos = nx.spring_layout(G, seed=semilla, k=1.6 / math.sqrt(max(len(nodos), 1)))
    fig = go.Figure()
    anot = []
    agrupadas: dict[tuple[str, str], list] = {}
    for a in lista:
        agrupadas.setdefault((a.origen, a.destino), []).append(a)
    for (u, v), grupo in agrupadas.items():
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        anot.append(dict(ax=x0, ay=y0, x=x1, y=y1, xref="x", yref="y", axref="x", ayref="y",
                         showarrow=True, arrowhead=3, arrowsize=1.2, arrowwidth=1.4,
                         arrowcolor="#64748b", standoff=11, startstandoff=8))
        if etiqueta_arista:
            total = sum(float(x.get(etiqueta_arista, 0) or 0) for x in grupo)
            txt = f"{len(grupo)}× " if len(grupo) > 1 else ""
            anot.append(dict(x=(x0 + x1) / 2, y=(y0 + y1) / 2, xref="x", yref="y", showarrow=False,
                             text=f"{txt}S/{total:,.0f}", font={"size": 9, "color": "#475569"},
                             bgcolor="rgba(255,255,255,0.7)"))
    resaltados = resaltados or {}
    fig.add_trace(go.Scatter(
        x=[pos[n][0] for n in nodos], y=[pos[n][1] for n in nodos], mode="markers+text",
        text=nodos, textposition="top center", textfont={"size": 10},
        marker={"size": 22, "color": [resaltados.get(n, COLOR_TIPO.get(g.nodos[n].tipo, "#64748b")) for n in nodos],
                "line": {"width": 2, "color": "white"}},
        hovertext=[f"<b>{n}</b> {g.nodos[n].nombre}<br>{g.nodos[n].get('ciudad', '')}" for n in nodos],
        hoverinfo="text", showlegend=False))
    fig.update_layout(annotations=anot, height=altura, margin={"l": 0, "r": 0, "t": 10, "b": 0},
                      xaxis={"visible": False}, yaxis={"visible": False}, plot_bgcolor="white")
    return fig


def sankey_liquidez(g: Grafo, rutas: list[dict[str, Any]], altura: int = 560) -> go.Figure:
    activos = [r for r in rutas if r["flujo"] > 0]
    nombres = list(dict.fromkeys([r["origen"] for r in activos] + [r["destino"] for r in activos]))
    idx = {n: i for i, n in enumerate(nombres)}
    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node={"label": [f"{n} ({g.nodos[n].get('ciudad', '')})" for n in nombres], "pad": 14, "thickness": 16,
              "color": [COLOR_TIPO.get(g.nodos[n].tipo, "#94a3b8") for n in nombres]},
        link={"source": [idx[r["origen"]] for r in activos], "target": [idx[r["destino"]] for r in activos],
              "value": [r["flujo"] for r in activos],
              "color": [{"terrestre": "rgba(168,162,158,0.45)", "aereo": "rgba(56,189,248,0.45)",
                         "fluvial": "rgba(16,185,129,0.5)"}.get(r["modo"], "rgba(148,163,184,0.4)") for r in activos],
              "customdata": [f"{r['id']} · {r['modo']} · {r['utilizacion_pct']} % de capacidad" for r in activos],
              "hovertemplate": "%{source.label} → %{target.label}<br>S/ %{value:,.0f} mil<br>%{customdata}<extra></extra>"}))
    fig.update_layout(height=altura, margin={"l": 5, "r": 5, "t": 10, "b": 10}, font={"size": 11})
    return fig


def barras_cobertura(agencias: list[dict[str, Any]], altura: int = 420) -> go.Figure:
    ag = sorted(agencias, key=lambda a: a["cobertura_pct"])
    fig = go.Figure()
    fig.add_trace(go.Bar(y=[a["id"] for a in ag], x=[a["recibido"] for a in ag], orientation="h",
                         name="Recibido", marker_color="#10b981",
                         hovertemplate="%{y}: S/ %{x:,.0f} mil recibidos<extra></extra>"))
    fig.add_trace(go.Bar(y=[a["id"] for a in ag], x=[a["pendiente"] for a in ag], orientation="h",
                         name="Pendiente", marker_color=ROJO,
                         hovertemplate="%{y}: S/ %{x:,.0f} mil pendientes<extra></extra>"))
    fig.update_layout(barmode="stack", height=altura, margin={"l": 0, "r": 0, "t": 10, "b": 0},
                      xaxis_title="miles de soles", legend={"orientation": "h", "y": 1.05})
    return fig


def lineas_benchmark(filas: list[dict[str, Any]], altura: int = 420, log: bool = True) -> go.Figure:
    fig = go.Figure()
    algs = list(dict.fromkeys(f["algoritmo"] for f in filas))
    paleta = ["#2563eb", "#dc2626", "#16a34a", "#9333ea", "#ea580c", "#0891b2"]
    for i, alg in enumerate(algs):
        pts = sorted((f["n"], f["tiempo_ms"]) for f in filas if f["algoritmo"] == alg)
        fig.add_trace(go.Scatter(x=[p[0] for p in pts], y=[p[1] for p in pts], mode="lines+markers", name=alg,
                                 line={"color": paleta[i % len(paleta)], "width": 2.5}))
    fig.update_layout(height=altura, margin={"l": 0, "r": 0, "t": 10, "b": 0},
                      xaxis_title="tamaño de la red (nodos)", yaxis_title="tiempo (ms)",
                      legend={"orientation": "h", "y": 1.08})
    if log:
        fig.update_xaxes(type="log")
        fig.update_yaxes(type="log")
    return fig


def heatmap_matriz(matriz: dict[str, dict[str, float | None]], altura: int = 520,
                   titulo_barra: str = "S/") -> go.Figure:
    filas = list(matriz)
    cols = list(next(iter(matriz.values())).keys()) if matriz else []
    z = [[matriz[f][c] for c in cols] for f in filas]
    fig = go.Figure(go.Heatmap(z=z, x=cols, y=filas, colorscale="YlOrRd", colorbar={"title": titulo_barra},
                               text=[[("—" if v is None else f"{v:,.2f}") for v in fila] for fila in z],
                               texttemplate="%{text}", textfont={"size": 9},
                               hovertemplate="%{y} → %{x}: %{text}<extra></extra>"))
    fig.update_layout(height=altura, margin={"l": 0, "r": 0, "t": 10, "b": 0}, yaxis={"autorange": "reversed"})
    return fig
