"""Módulo 4: flujo máximo, corte mínimo, escenarios y política equitativa."""
import pytest

from src.distribucion_liquidez import PlanificadorLiquidez, cargar_escenarios
from src.gestion_red import cargar_red


@pytest.fixture(scope="module")
def P():
    return PlanificadorLiquidez(cargar_red("liquidez"))


@pytest.fixture(scope="module")
def esc():
    return cargar_escenarios()


def test_flujo_normal(P, esc):
    r = P.calcular(esc["normal"])
    assert r.flujo_maximo == pytest.approx(120000)
    assert all(r.verificacion.values())


@pytest.mark.parametrize("nombre,esperado", [("vaciante", 117250), ("vuelo_cancelado", 112000),
                                             ("diciembre", 142500)])
def test_escenarios(P, esc, nombre, esperado):
    assert P.calcular(esc[nombre], evaluar_ampliaciones=False).flujo_maximo == pytest.approx(esperado)


def test_corte_minimo_loreto(P, esc):
    r = P.calcular(esc["normal"])
    criticos = {c["id"] for c in r.cuellos_botella if c["ganancia_si_amplia_20pct"] > 0}
    assert {"L023", "L024"} <= criticos


def test_politicas(P, esc):
    eq = P.calcular(esc["normal"], politica="equitativa")
    cm = P.calcular(esc["normal"], politica="costo_minimo")
    assert eq.flujo_maximo == pytest.approx(cm.flujo_maximo)
    assert min(a["cobertura_pct"] for a in eq.agencias) >= 80
    assert min(a["cobertura_pct"] for a in cm.agencias) == 0      # el costo puro deja agencias sin efectivo
    assert cm.costo_total <= eq.costo_total


def test_ampliacion(P, esc):
    assert P.beneficio_ampliacion(esc["normal"], "L024", 2000)["ganancia"] == pytest.approx(2000)


def test_mst(P):
    k, p = P.red_troncal("kruskal"), P.red_troncal("prim")
    assert k["costo_total"] == pytest.approx(p["costo_total"]) and len(k["aristas"]) == 21
