"""Módulo 1: estructura de grafo, carga, CRUD y validación."""
import pytest

from src.gestion_red import GestorRedes, cargar_red, importar
from src.graph import Grafo, GrafoError
from src.utils import DATA_DIR


def test_carga_redes_del_proyecto():
    G = GestorRedes().cargar_todas()
    assert G["enrutamiento"].num_nodos == 30 and G["enrutamiento"].num_aristas == 75
    assert G["liquidez"].num_nodos == 22 and G["liquidez"].num_aristas == 31
    assert G["transacciones"].num_nodos == 404 and G["transacciones"].num_aristas == 2711
    for g in G.redes.values():
        assert not [h for h in g.validar() if h["nivel"] == "error"]


def test_csv_minimo_de_la_guia():
    g, err = importar((DATA_DIR / "ejemplo_minimo.csv").read_text(encoding="utf-8"), "csv")
    assert err == [] and g.num_nodos == 5 and g.num_aristas == 5
    assert g.lista_adyacencia("comision")["CuentaA"] == [("CuentaB", 4.5), ("CuentaC", 2.0)]


def test_detecta_datos_invalidos():
    _, err = importar((DATA_DIR / "ejemplo_con_errores.csv").read_text(encoding="utf-8"), "csv")
    assert len(err) == 5
    texto = " ".join(err)
    for clave in ("duplicada", "Bucle", "negativo", "entre 0 y 1", "inexistente"):
        assert clave in texto


def test_crud_y_cierres():
    g = Grafo("t", dirigido=True)
    g.agregar_nodo("A", "agencia")
    g.agregar_nodo("B", "atm")
    a = g.agregar_arista("A", "B", comision_fija=2.0)
    with pytest.raises(GrafoError):
        g.agregar_arista("A", "X")
    with pytest.raises(GrafoError):
        g.agregar_nodo("A")
    with pytest.raises(GrafoError):
        g.agregar_nodo("C", "tipo_raro")
    g.cerrar_nodo("B")
    assert g.vecinos("A") == []
    g.abrir_nodo("B")
    assert [v for v, _ in g.vecinos("A")] == ["B"]
    g.modificar_arista(a.id, comision_fija=3.0)
    assert g.arista(a.id)["comision_fija"] == 3.0
    assert g.eliminar_nodo("B") == 1 and g.num_aristas == 0


def test_no_dirigido_y_no_ponderado():
    g = Grafo("u", dirigido=False, ponderado=False)
    for x in "AB":
        g.agregar_nodo(x)
    a = g.agregar_arista("A", "B", peso=9)
    assert [v for v, _ in g.vecinos("B")] == ["A"]
    assert g.peso(a, "peso") == 1.0
    with pytest.raises(GrafoError):
        g.agregar_arista("B", "A")


def test_multigrafo_exige_justificacion():
    g = Grafo("m", multiple=True)
    g.agregar_nodo("A")
    g.agregar_nodo("B")
    g.agregar_arista("A", "B", canal="diferida")
    g.agregar_arista("A", "B", canal="inmediata")
    with pytest.raises(GrafoError):
        g.agregar_arista("A", "B", canal="inmediata")


def test_json_ida_y_vuelta(tmp_path):
    g = cargar_red("ejemplo")
    ruta = tmp_path / "red.json"
    g.guardar_json(ruta)
    h = Grafo.cargar_json(ruta)
    assert h.num_nodos == g.num_nodos and h.num_aristas == g.num_aristas


def test_txt():
    g, err = importar("A B 2\nB C 3  # comentario\n", "txt")
    assert err == [] and g.num_aristas == 2
