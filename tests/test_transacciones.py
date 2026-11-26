"""Módulo 2: detección de patrones sospechosos contra la verdad de referencia."""
import json

import pytest

from src.analisis_transacciones import AnalizadorTransacciones, evaluar_contra_patrones
from src.gestion_red import cargar_red
from src.utils import DATA_DIR


@pytest.fixture(scope="module")
def datos():
    g = cargar_red("transacciones")
    pat = json.loads((DATA_DIR / "patrones_plantados.json").read_text(encoding="utf-8"))
    semilla = pat["patrones"][1]["cuenta_reportada"]
    return g, pat, AnalizadorTransacciones(g).analisis_completo(semilla)


def test_todos_los_patrones_detectados(datos):
    _, pat, res = datos
    filas = evaluar_contra_patrones(res, pat)
    assert all(f["resultado"] == "DETECTADO" for f in filas if f["patron"] != "—")
    assert filas[-1]["detectadas_por_su_regla"] == 0          # sin falsos positivos alto/medio


def test_ciclo_y_pitufeo(datos):
    _, pat, res = datos
    assert len(res["ciclos"]) == 2
    assert set(res["ciclos"][0]["cuentas"]) == set(pat["patrones"][0]["cuentas"])
    assert res["fragmentacion"][0]["cuenta"] == pat["patrones"][1]["concentradora"]
    assert res["fragmentacion"][0]["emisores"] == 14


def test_rastreo_cronologico(datos):
    g, pat, _ = datos
    p3 = next(p for p in pat["patrones"] if p["id"] == "P3")
    r = AnalizadorTransacciones(g).rastrear_fondos(p3["origen"], max_saltos=8, monto_minimo=20000)
    alcanzadas = [f["cuenta"] for f in r["filas"]]
    assert all(m in alcanzadas for m in p3["cuentas"])


def test_proximidad(datos):
    g, pat, _ = datos
    p2 = pat["patrones"][1]
    p = AnalizadorTransacciones(g).proximidad(p2["concentradora"], p2["cuentas"][1])
    assert p["saltos"] == 1
