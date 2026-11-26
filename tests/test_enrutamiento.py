"""Módulo 3: ruta de menor comisión, límites, cierres y promociones."""
import pytest

from src.enrutamiento_financiero import Enrutador, nodos_criticos
from src.gestion_red import cargar_red


@pytest.fixture(scope="module")
def E():
    return Enrutador(cargar_red("enrutamiento"))


def test_ruta_mas_barata(E):
    r = E.ruta_optima("AG_LIM", "CORR_CAB", 1500)
    assert r.algoritmo == "dijkstra" and r.comision == pytest.approx(5.75)
    assert r.nodos == ["AG_LIM", "BILL_A", "BILL_B", "CMS_IQT", "CORR_CAB"]


def test_limite_transaccional(E):
    assert E.ruta_optima("AG_LIM", "CORR_CAB", 5000).comision == pytest.approx(18.5)
    r = E.ruta_optima("AG_LIM", "CORR_CAB", 25000)
    assert not r.existe and "límite" in r.motivo_sin_ruta


def test_sucursal_cerrada(E):
    r = E.ruta_optima("AG_LIM", "CORR_CAB", 800, cerrar_nodos=["CMS_IQT"])
    assert r.nodos == ["AG_LIM", "BILL_A", "CORR_CAB"] and r.comision == pytest.approx(13.0)


def test_todos_los_algoritmos_coinciden(E):
    filas = E.comparar_algoritmos("AG_LIM", "AG_CAB", 20000)
    assert all(f["coincide_con_optimo"] for f in filas)


def test_promociones(E):
    r = E.ruta_optima("AG_LIM", "CORR_CAB", 1500, promocion="cashback_recarga")
    assert r.algoritmo == "bellman_ford" and r.comision == pytest.approx(2.75)
    r = E.ruta_optima("AG_LIM", "CORR_CAB", 1500, promocion="promo_interoperabilidad")
    assert r.ciclo_negativo and not r.existe


def test_criterios(E):
    for c in ("comision", "tiempo", "riesgo", "combinado"):
        assert E.ruta_optima("AG_LIM", "AG_IQT", 3000, c).existe


def test_nodos_criticos():
    filas = nodos_criticos(cargar_red("enrutamiento"), "AG_LIM")
    assert filas[0]["nodo_cerrado"] == "AG_IQT"
