"""
Generador reproducible de los datos simulados del proyecto (semilla fija).

    python scripts/generar_datos.py

Produce en data/:
  * nodos_enrutamiento.csv / red_enrutamiento.csv  -> Módulo 3
  * nodos_liquidez.csv     / distribucion_liquidez.csv / escenarios_liquidez.json -> Módulo 4
  * cuentas.csv            / transacciones.csv / patrones_plantados.json -> Módulo 2
  * red_ejemplo.json, ejemplo_minimo.csv, ejemplo_con_errores.csv -> Módulo 1

Todas las entidades, montos y tarifas son FICTICIOS; las ciudades,
coordenadas y la geografía (Iquitos sin acceso por carretera, rutas
fluviales del Ucayali/Huallaga/Amazonas) corresponden a la realidad peruana.
"""

from __future__ import annotations

import csv
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DATA = RAIZ / "data"
SEMILLA = 2026

CIUDADES = {
    "Lima": (-12.046, -77.043, "Costa"),
    "Trujillo": (-8.112, -79.029, "Costa"),
    "Chiclayo": (-6.771, -79.841, "Costa"),
    "Piura": (-5.194, -80.632, "Costa"),
    "Arequipa": (-16.409, -71.537, "Sierra"),
    "Huancayo": (-12.065, -75.204, "Sierra"),
    "Pucallpa": (-8.379, -74.553, "Selva"),
    "Tarapoto": (-6.487, -76.360, "Selva"),
    "Yurimaguas": (-5.902, -76.123, "Selva"),
    "Iquitos": (-3.749, -73.253, "Selva"),
    "Nauta": (-4.507, -73.583, "Selva"),
    "Requena": (-5.063, -73.856, "Selva"),
    "Caballococha": (-3.906, -70.517, "Selva"),
    "Santa Rosa": (-4.220, -69.955, "Selva"),
    "Puerto Maldonado": (-12.593, -69.189, "Selva"),
}


def coord(ciudad: str, dlat: float = 0.0, dlon: float = 0.0) -> tuple[float, float, str]:
    lat, lon, region = CIUDADES[ciudad]
    return round(lat + dlat, 4), round(lon + dlon, 4), region


def escribir_csv(ruta: Path, filas: list[dict]) -> None:
    columnas: list[str] = []
    for f in filas:
        for k in f:
            if k not in columnas:
                columnas.append(k)
    with open(ruta, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=columnas)
        w.writeheader()
        w.writerows(filas)


# =====================================================================
# MÓDULO 3 — Red de enrutamiento de operaciones
# =====================================================================
def red_enrutamiento() -> tuple[list[dict], list[dict]]:
    nodos: list[dict] = []

    def nodo(id, tipo, nombre, ciudad, dlat=0.0, dlon=0.0, **extra):
        lat, lon, region = coord(ciudad, dlat, dlon)
        nodos.append({"id": id, "tipo": tipo, "nombre": nombre, "ciudad": ciudad,
                      "region": region, "lat": lat, "lon": lon, **extra})

    agencias = [("AG_LIM", "Lima"), ("AG_TRU", "Trujillo"), ("AG_CIX", "Chiclayo"),
                ("AG_PIU", "Piura"), ("AG_AQP", "Arequipa"), ("AG_HYO", "Huancayo"),
                ("AG_PUC", "Pucallpa"), ("AG_TPP", "Tarapoto"), ("AG_YUR", "Yurimaguas"),
                ("AG_IQT", "Iquitos"), ("AG_NAU", "Nauta"), ("AG_REQ", "Requena"),
                ("AG_CAB", "Caballococha"), ("AG_PEM", "Puerto Maldonado")]
    for id, c in agencias:
        nodo(id, "agencia", f"Agencia BAA {c}", c, entidad="Banco Andino Amazónico (BAA)")

    nodo("CCE", "compensacion", "Cámara de Compensación Electrónica", "Lima", 0.35, 0.25,
         entidad="Sistema de pagos")
    nodo("BILL_A", "billetera", "Billetera digital A (del BAA)", "Lima", -0.35, 0.35, entidad="BAA")
    nodo("BILL_B", "billetera", "Billetera digital B (otros bancos)", "Lima", -0.6, 0.0, entidad="Consorcio B")
    nodo("PROC_TARJ", "procesador", "Procesador de tarjetas", "Lima", 0.0, -0.45, entidad="Red de tarjetas")
    nodo("RED_ATM", "servidor", "Red interbancaria de cajeros", "Lima", 0.4, -0.35, entidad="Red ATM")
    nodo("BCN_LIM", "entidad", "Banco Costa Norte - Lima", "Lima", 0.65, 0.05, entidad="Banco Costa Norte")
    nodo("BCN_IQT", "entidad", "Banco Costa Norte - Iquitos", "Iquitos", 0.12, -0.18, entidad="Banco Costa Norte")
    nodo("CMS_IQT", "entidad", "Caja Municipal Selva - Iquitos", "Iquitos", -0.15, 0.2, entidad="Caja Municipal Selva")
    nodo("CORR_CAB", "corresponsal", "Agente corresponsal Caballococha", "Caballococha", 0.1, 0.1,
         entidad="Caja Municipal Selva")
    nodo("CORR_SRO", "corresponsal", "Agente corresponsal Santa Rosa", "Santa Rosa", entidad="Caja Municipal Selva")
    nodo("CORR_NAU", "corresponsal", "Agente corresponsal Nauta", "Nauta", 0.1, 0.12, entidad="Caja Municipal Selva")
    for id, c, d in (("ATM_IQT", "Iquitos", (0.2, 0.15)), ("ATM_PUC", "Pucallpa", (0.15, 0.15)),
                     ("ATM_YUR", "Yurimaguas", (0.12, 0.12)), ("ATM_CAB", "Caballococha", (-0.12, -0.1)),
                     ("ATM_PEM", "Puerto Maldonado", (0.15, 0.12))):
        nodo(id, "atm", f"Cajero automático {c}", c, *d, entidad="BAA")

    aristas: list[dict] = []
    cont = [0]

    def arista(o, d, tipo_op, canal, fija, pct, tmin, riesgo, limite, bidir=False, **extra):
        for a, b in ((o, d), (d, o)) if bidir else ((o, d),):
            cont[0] += 1
            aristas.append({"id": f"R{cont[0]:03d}", "origen": a, "destino": b,
                            "tipo_operacion": tipo_op, "canal": canal,
                            "comision_fija": fija, "comision_pct": pct, "tiempo_min": tmin,
                            "riesgo": riesgo, "limite": limite, **extra})

    # --- transferencias interplaza (intrabancarias BAA) --------------------
    interplaza = [("AG_LIM", "AG_TRU", 0.30), ("AG_TRU", "AG_CIX", 0.25), ("AG_CIX", "AG_PIU", 0.25),
                  ("AG_LIM", "AG_AQP", 0.35), ("AG_LIM", "AG_HYO", 0.30), ("AG_HYO", "AG_PUC", 0.40),
                  ("AG_LIM", "AG_PUC", 0.50), ("AG_CIX", "AG_TPP", 0.45), ("AG_TPP", "AG_YUR", 0.30),
                  ("AG_YUR", "AG_IQT", 0.50), ("AG_PUC", "AG_IQT", 0.55), ("AG_LIM", "AG_IQT", 1.20),
                  ("AG_IQT", "AG_NAU", 0.35), ("AG_NAU", "AG_REQ", 0.35), ("AG_AQP", "AG_PEM", 0.60),
                  ("AG_LIM", "AG_PEM", 0.95)]
    for o, d, pct in interplaza:
        arista(o, d, "interplaza", "interplaza", 0.0, pct, 2, 0.001, 100000, bidir=True)
    arista("AG_IQT", "AG_CAB", "interplaza", "giro", 5.0, 0.90, 30, 0.004, 30000, bidir=True)

    # --- interbancarias vía cámara de compensación ------------------------
    for ag in ("AG_LIM", "AG_IQT", "AG_PUC", "AG_TRU", "AG_AQP"):
        arista(ag, "CCE", "interbancaria", "diferida", 3.50, 0.0, 1440, 0.0005, 300000)
        arista(ag, "CCE", "interbancaria", "inmediata", 7.00, 0.0, 1, 0.001, 30000)
    arista("CCE", "BCN_LIM", "compensacion", "liquidacion", 0.0, 0.0, 1, 0.0002, 1000000)
    arista("CCE", "CMS_IQT", "compensacion", "liquidacion", 0.50, 0.0, 2, 0.0003, 1000000)
    arista("BCN_LIM", "BCN_IQT", "interplaza", "interplaza", 0.0, 0.45, 2, 0.001, 100000)
    arista("BCN_IQT", "CMS_IQT", "interbancaria", "convenio", 2.50, 0.10, 20, 0.002, 50000)
    arista("CMS_IQT", "CORR_CAB", "corresponsal", "retiro_agente", 2.00, 0.25, 10, 0.010, 5000)
    arista("CMS_IQT", "CORR_SRO", "corresponsal", "retiro_agente", 2.50, 0.30, 15, 0.015, 3000)
    arista("CMS_IQT", "CORR_NAU", "corresponsal", "retiro_agente", 1.50, 0.20, 10, 0.008, 5000)

    # --- billeteras digitales (interoperables) -----------------------------
    arista("AG_LIM", "BILL_A", "billetera", "recarga", 0.0, 0.0, 1, 0.002, 2000, bonificacion=3.0)
    arista("AG_IQT", "BILL_A", "billetera", "recarga", 0.0, 0.0, 1, 0.002, 2000)
    arista("BILL_A", "BILL_B", "billetera", "interoperabilidad", 0.0, 0.0, 1, 0.002, 2000, bonificacion=1.5)
    arista("BILL_B", "BILL_A", "billetera", "interoperabilidad", 0.0, 0.0, 1, 0.002, 2000, bonificacion=1.5)
    arista("BILL_B", "CMS_IQT", "billetera", "abono_cuenta", 0.0, 0.0, 1, 0.003, 2000)
    arista("BILL_A", "CORR_CAB", "billetera", "retiro_agente", 1.00, 1.50, 5, 0.010, 1000)
    arista("BILL_B", "CORR_SRO", "billetera", "retiro_agente", 1.00, 1.20, 5, 0.012, 1000)
    arista("BILL_A", "CORR_NAU", "billetera", "retiro_agente", 1.00, 1.00, 5, 0.008, 1000)

    # --- tarjetas y red de cajeros ------------------------------------------
    arista("AG_LIM", "PROC_TARJ", "tarjeta", "debito", 0.0, 0.0, 1, 0.003, 5000)
    # tarjeta de crédito: disposición de efectivo (comisión fija + % alto), canal más caro pero sin saldo previo
    arista("AG_LIM", "PROC_TARJ", "tarjeta", "credito", 12.0, 4.50, 1, 0.004, 3000)
    arista("AG_IQT", "PROC_TARJ", "tarjeta", "credito", 12.0, 4.50, 1, 0.004, 3000)
    arista("PROC_TARJ", "RED_ATM", "tarjeta", "autorizacion", 0.0, 0.0, 1, 0.002, 5000)
    for atm, fija, lim, r in (("ATM_IQT", 8.50, 2000, 0.005), ("ATM_PUC", 8.50, 2000, 0.005),
                              ("ATM_YUR", 9.50, 2000, 0.008), ("ATM_CAB", 12.00, 1000, 0.020),
                              ("ATM_PEM", 9.50, 2000, 0.010)):
        arista("RED_ATM", atm, "atm", "retiro_otra_red", fija, 0.0, 1, r, lim)
    for ag, atm in (("AG_IQT", "ATM_IQT"), ("AG_PUC", "ATM_PUC"), ("AG_YUR", "ATM_YUR"),
                    ("AG_CAB", "ATM_CAB"), ("AG_PEM", "ATM_PEM")):
        arista(ag, atm, "atm", "retiro_propio", 0.0, 0.0, 1, 0.003, 3000)

    # --- traslado físico de última milla en la triple frontera ------------
    arista("AG_CAB", "CORR_SRO", "interplaza", "giro_fluvial", 15.0, 0.50, 360, 0.030, 20000)
    arista("AG_NAU", "CORR_NAU", "corresponsal", "retiro_agente", 1.0, 0.10, 10, 0.005, 5000)
    return nodos, aristas


# =====================================================================
# MÓDULO 4 — Distribución de liquidez (miles de soles por ciclo semanal)
# =====================================================================
def red_liquidez() -> tuple[list[dict], list[dict], dict]:
    nodos: list[dict] = []

    def nodo(id, tipo, nombre, ciudad, oferta=0, demanda=0, dlat=0.0, dlon=0.0):
        lat, lon, region = coord(ciudad, dlat, dlon)
        nodos.append({"id": id, "tipo": tipo, "nombre": nombre, "ciudad": ciudad, "region": region,
                      "lat": lat, "lon": lon, "oferta": oferta, "demanda": demanda})

    nodo("BOV_LIM", "boveda_central", "Bóveda central Lima", "Lima", oferta=140000, dlat=0.3, dlon=0.3)
    nodo("BOV_TRU", "boveda_regional", "Bóveda regional Trujillo", "Trujillo", oferta=6000, dlat=0.25, dlon=0.25)
    nodo("BOV_AQP", "boveda_regional", "Bóveda regional Arequipa", "Arequipa", oferta=5000, dlat=0.25, dlon=0.25)
    nodo("BOV_HYO", "boveda_regional", "Bóveda regional Huancayo", "Huancayo", oferta=2000, dlat=0.25, dlon=0.25)
    nodo("BOV_PUC", "boveda_regional", "Bóveda de custodia Pucallpa", "Pucallpa", dlat=0.25, dlon=0.25)
    nodo("BOV_TPP", "boveda_regional", "Bóveda de custodia Tarapoto", "Tarapoto", dlat=0.25, dlon=0.25)
    nodo("BOV_IQT", "boveda_regional", "Bóveda regional Iquitos", "Iquitos", oferta=2500, dlat=0.25, dlon=0.25)
    demandas = [("AG_LIM", "Lima", 45000), ("AG_TRU", "Trujillo", 9000), ("AG_CIX", "Chiclayo", 8000),
                ("AG_PIU", "Piura", 7000), ("AG_AQP", "Arequipa", 10000), ("AG_HYO", "Huancayo", 6000),
                ("AG_PUC", "Pucallpa", 7500), ("AG_TPP", "Tarapoto", 4500), ("AG_YUR", "Yurimaguas", 3000),
                ("AG_IQT", "Iquitos", 14000), ("AG_NAU", "Nauta", 1600), ("AG_REQ", "Requena", 1300),
                ("AG_CAB", "Caballococha", 1900), ("AG_SRO", "Santa Rosa", 700),
                ("AG_PEM", "Puerto Maldonado", 4000)]
    for id, c, d in demandas:
        nodo(id, "agencia", f"Agencia BAA {c}", c, demanda=d)

    aristas: list[dict] = []
    cont = [0]

    def ruta(o, d, modo, cap, costo, horas, riesgo, km):
        cont[0] += 1
        aristas.append({"id": f"L{cont[0]:03d}", "origen": o, "destino": d, "modo": modo,
                        "capacidad": cap, "costo": costo, "tiempo_h": horas, "riesgo": riesgo,
                        "distancia_km": km})

    # costo = soles por cada S/ 1 000 trasladados (blindado, seguro, custodia)
    ruta("BOV_LIM", "AG_LIM", "terrestre", 60000, 0.30, 1, 0.002, 15)
    ruta("BOV_LIM", "BOV_TRU", "terrestre", 20000, 1.80, 9, 0.010, 560)
    ruta("BOV_TRU", "AG_TRU", "terrestre", 12000, 0.30, 1, 0.002, 10)
    ruta("BOV_TRU", "AG_CIX", "terrestre", 10000, 1.00, 3.5, 0.006, 210)
    ruta("BOV_TRU", "AG_PIU", "terrestre", 8000, 1.40, 6, 0.008, 420)
    ruta("BOV_LIM", "AG_PIU", "aereo", 3000, 4.50, 1.7, 0.003, 860)
    ruta("BOV_LIM", "BOV_AQP", "terrestre", 15000, 2.00, 16, 0.012, 1010)
    ruta("BOV_LIM", "BOV_AQP", "aereo", 6000, 4.00, 1.5, 0.003, 765)
    ruta("BOV_AQP", "AG_AQP", "terrestre", 14000, 0.30, 1, 0.002, 10)
    ruta("BOV_AQP", "AG_PEM", "terrestre", 2500, 2.80, 18, 0.030, 920)
    ruta("BOV_LIM", "AG_PEM", "aereo", 2000, 5.00, 1.7, 0.004, 855)
    ruta("BOV_LIM", "BOV_HYO", "terrestre", 10000, 1.60, 7, 0.020, 300)
    ruta("BOV_HYO", "AG_HYO", "terrestre", 8000, 0.30, 1, 0.002, 10)
    ruta("BOV_HYO", "BOV_PUC", "terrestre", 5000, 2.20, 14, 0.030, 620)
    ruta("BOV_LIM", "BOV_PUC", "aereo", 4000, 4.20, 1.2, 0.004, 490)
    ruta("BOV_LIM", "BOV_PUC", "terrestre", 6000, 2.50, 18, 0.035, 790)
    ruta("BOV_PUC", "AG_PUC", "terrestre", 9000, 0.30, 1, 0.002, 10)
    ruta("BOV_TRU", "BOV_TPP", "terrestre", 5000, 2.60, 15, 0.030, 700)
    ruta("BOV_LIM", "BOV_TPP", "aereo", 3000, 4.40, 1.3, 0.004, 615)
    ruta("BOV_TPP", "AG_TPP", "terrestre", 6000, 0.30, 1, 0.002, 10)
    ruta("BOV_TPP", "AG_YUR", "terrestre", 4500, 1.00, 2.5, 0.010, 130)
    ruta("AG_YUR", "BOV_IQT", "fluvial", 3500, 1.20, 60, 0.050, 640)
    ruta("BOV_PUC", "BOV_IQT", "fluvial", 5000, 1.40, 96, 0.060, 930)
    ruta("BOV_LIM", "BOV_IQT", "aereo", 8000, 4.80, 1.8, 0.005, 1010)
    ruta("BOV_IQT", "AG_IQT", "terrestre", 16000, 0.20, 0.5, 0.002, 8)
    ruta("BOV_IQT", "AG_NAU", "terrestre", 2500, 0.80, 2, 0.008, 95)
    ruta("AG_NAU", "AG_REQ", "fluvial", 1500, 1.00, 12, 0.040, 190)
    ruta("BOV_IQT", "AG_REQ", "fluvial", 800, 1.50, 20, 0.045, 260)
    ruta("BOV_IQT", "AG_CAB", "fluvial", 1600, 1.60, 30, 0.060, 380)
    ruta("BOV_IQT", "AG_CAB", "aereo", 500, 7.50, 1.5, 0.010, 310)
    ruta("AG_CAB", "AG_SRO", "fluvial", 900, 1.20, 6, 0.050, 70)

    escenarios = {
        "normal": {"descripcion": "Operación habitual, ríos en nivel medio.",
                   "factor_fluvial": 1.0, "factor_aereo": 1.0, "factor_terrestre": 1.0,
                   "factor_demanda": 1.0, "cerrar_aristas": [], "cerrar_nodos": []},
        "vaciante": {"descripcion": "Temporada de aguas bajas: los ríos amazónicos reducen la carga "
                                    "navegable (capacidad fluvial al 45 %).",
                     "factor_fluvial": 0.45, "factor_aereo": 1.0, "factor_terrestre": 1.0,
                     "factor_demanda": 1.0, "cerrar_aristas": [], "cerrar_nodos": []},
        "diciembre": {"descripcion": "Pago de gratificaciones y fiestas: la demanda de efectivo sube 35 %.",
                      "factor_fluvial": 1.0, "factor_aereo": 1.0, "factor_terrestre": 1.0,
                      "factor_demanda": 1.35, "cerrar_aristas": [], "cerrar_nodos": []},
        "vuelo_cancelado": {"descripcion": "Se cancela el vuelo de valores Lima-Iquitos (mal tiempo).",
                            "factor_fluvial": 1.0, "factor_aereo": 1.0, "factor_terrestre": 1.0,
                            "factor_demanda": 1.0, "cerrar_aristas": ["L024"], "cerrar_nodos": []},
        "bloqueo_carretera_central": {"descripcion": "Huaico bloquea la Carretera Central Lima-Huancayo.",
                                      "factor_fluvial": 1.0, "factor_aereo": 1.0, "factor_terrestre": 1.0,
                                      "factor_demanda": 1.0, "cerrar_aristas": ["L012"], "cerrar_nodos": []},
        "crisis_amazonica": {"descripcion": "Vaciante + demanda de diciembre + agencia Nauta en mantenimiento.",
                             "factor_fluvial": 0.45, "factor_aereo": 1.0, "factor_terrestre": 1.0,
                             "factor_demanda": 1.35, "cerrar_aristas": [], "cerrar_nodos": ["AG_NAU"]},
    }
    return nodos, aristas, escenarios


# =====================================================================
# MÓDULO 2 — Transacciones con patrones sospechosos plantados
# =====================================================================
NOMBRES = ["Rosa", "Juan", "María", "Luis", "Carmen", "José", "Ana", "Jorge", "Lucía", "Carlos",
           "Elena", "Pedro", "Sofía", "Miguel", "Julia", "Raúl", "Diana", "Víctor", "Patricia",
           "Hugo", "Gladys", "César", "Milagros", "Óscar", "Liliana", "Wilmer", "Nelly", "Edwin",
           "Roxana", "Félix", "Yesenia", "Alberto", "Karina", "Teófilo", "Maribel", "Segundo"]
APELLIDOS = ["Huamán", "Flores", "Ríos", "Panaifo", "Vásquez", "Tello", "Shapiama", "Mozombite",
             "Ramírez", "Quispe", "Ahuanari", "Sánchez", "Pinedo", "Tuesta", "Del Águila", "Cárdenas",
             "Mendoza", "Arévalo", "Tafur", "Rengifo", "Gonzales", "Chávez", "Torres", "Saavedra",
             "Macedo", "Lozano", "Ruiz", "Curitima", "Yumbato", "Pezo"]
EMPRESAS = ["Comercial", "Inversiones", "Maderera", "Servicios Generales", "Transportes Fluviales",
            "Agroindustrias", "Distribuidora", "Importaciones", "Constructora", "Grifo"]
LUGARES = ["Itaya", "Nanay", "Yavarí", "Ucayali", "Amazonas", "Marañón", "Huallaga", "Selva Real",
           "Oriente", "Tres Fronteras", "Loreto", "Pacaya", "Samiria", "Napo", "Putumayo"]

PESOS_CIUDAD = {"Lima": 30, "Iquitos": 18, "Pucallpa": 10, "Tarapoto": 7, "Yurimaguas": 5,
                "Trujillo": 6, "Arequipa": 6, "Piura": 4, "Puerto Maldonado": 5,
                "Caballococha": 3, "Santa Rosa": 2, "Nauta": 2, "Huancayo": 2}


def transacciones() -> tuple[list[dict], list[dict], dict]:
    rnd = random.Random(SEMILLA)
    cuentas: list[dict] = []
    contador = [0]

    def nueva_cuenta(ciudad: str | None = None, tipo: str = "cuenta", actividad: str | None = None,
                     ingreso: float | None = None, nombre: str | None = None) -> str:
        contador[0] += 1
        cid = f"C{contador[0]:04d}"
        ciudad = ciudad or rnd.choices(list(PESOS_CIUDAD), weights=list(PESOS_CIUDAD.values()))[0]
        lat, lon, region = coord(ciudad, rnd.uniform(-0.18, 0.18), rnd.uniform(-0.18, 0.18))
        if tipo == "empresa":
            titular = nombre or f"{rnd.choice(EMPRESAS)} {rnd.choice(LUGARES)} {rnd.choice(['S.A.C.', 'E.I.R.L.', 'S.R.L.'])}"
            actividad = actividad or rnd.choice(["comercio", "transporte", "construccion", "madera",
                                                 "agroindustria", "servicios"])
            ingreso = ingreso or rnd.choice([20000, 45000, 80000, 150000])
        else:
            titular = nombre or f"{rnd.choice(NOMBRES)} {rnd.choice(APELLIDOS)} {rnd.choice(APELLIDOS)}"
            actividad = actividad or rnd.choice(["dependiente", "independiente", "comerciante",
                                                 "estudiante", "agricultor", "pescador"])
            ingreso = ingreso or rnd.choice([1100, 1500, 2200, 3500, 5000, 8000])
        cuentas.append({"id": cid, "tipo": tipo, "nombre": titular, "titular": titular,
                        "ciudad": ciudad, "region": region, "lat": lat, "lon": lon,
                        "actividad": actividad, "ingreso_mensual": ingreso,
                        "antiguedad_meses": rnd.randint(1, 180)})
        return cid

    inicio = datetime(2026, 9, 1, 8, 0)
    trans: list[dict] = []
    tc = [0]

    def transferir(o: str, d: str, monto: float, fecha: datetime, canal: str, concepto: str) -> None:
        tc[0] += 1
        trans.append({"id": f"T{tc[0]:05d}", "origen": o, "destino": d, "monto": round(monto, 2),
                      "fecha": fecha.strftime("%Y-%m-%dT%H:%M"), "canal": canal, "concepto": concepto})

    # ---------------- población normal ----------------
    normales = [nueva_cuenta() for _ in range(330)]
    empresas = [nueva_cuenta(tipo="empresa") for _ in range(25)]
    todas = normales + empresas
    por_ciudad: dict[str, list[str]] = {}
    for c in cuentas:
        por_ciudad.setdefault(c["ciudad"], []).append(c["id"])
    contactos: dict[str, list[str]] = {}
    for cid in todas:
        ciudad = next(c["ciudad"] for c in cuentas if c["id"] == cid)
        locales = [x for x in por_ciudad[ciudad] if x != cid]
        k_local = min(len(locales), rnd.randint(2, 5))
        contactos[cid] = rnd.sample(locales, k_local) + rnd.sample([x for x in todas if x != cid], rnd.randint(1, 3))

    canales = ["app", "app", "app", "billetera", "billetera", "agencia", "interbancaria", "atm"]
    for _ in range(2500):
        o = rnd.choice(todas)
        d = rnd.choice(contactos[o])
        monto = min(rnd.lognormvariate(6.2, 0.95), 25000)
        fecha = inicio + timedelta(minutes=rnd.randint(0, 60 * 24 * 60))
        transferir(o, d, monto, fecha, rnd.choice(canales),
                   rnd.choice(["pago", "compra", "servicios", "prestamo_familiar", "transferencia"]))

    # planillas legítimas (dispersión legítima: sirve para medir falsos positivos)
    for emp in rnd.sample(empresas, 4):
        trabajadores = rnd.sample(normales, rnd.randint(10, 18))
        for mes in (9, 10):
            for t in trabajadores:
                transferir(emp, t, rnd.choice([1300, 1800, 2400, 3200]),
                           datetime(2026, mes, 28, 9, rnd.randint(0, 59)), "agencia", "planilla")

    patrones: dict = {"descripcion": "Patrones sospechosos insertados deliberadamente (verdad de referencia "
                                     "para validar el Módulo 2). Los datos son ficticios.",
                      "umbral_reporte": 10000, "patrones": []}

    # ---------------- P1: ciclo de empresas fachada ----------------
    fachadas = [nueva_cuenta("Iquitos", "empresa", "madera", 30000, "Maderera Río Nanay S.A.C."),
                nueva_cuenta("Pucallpa", "empresa", "transporte", 25000, "Transportes Fluviales Ucayali E.I.R.L."),
                nueva_cuenta("Lima", "empresa", "importaciones", 40000, "Importaciones Selva Real S.A.C."),
                nueva_cuenta("Tarapoto", "empresa", "agroindustria", 20000, "Agroindustrias Huallaga S.R.L."),
                nueva_cuenta("Iquitos", "empresa", "comercio", 35000, "Comercial Tres Fronteras S.A.C.")]
    for base, dia in ((182000, datetime(2026, 9, 10, 9, 0)), (176500, datetime(2026, 10, 8, 10, 0))):
        monto, fecha = base, dia
        for i in range(len(fachadas)):
            transferir(fachadas[i], fachadas[(i + 1) % len(fachadas)], monto, fecha, "interbancaria", "servicios")
            monto *= rnd.uniform(0.975, 0.99)
            fecha += timedelta(hours=rnd.randint(5, 14))
    patrones["patrones"].append({"id": "P1", "tipo": "ciclo",
                                 "descripcion": "Circulación de fondos entre 5 empresas fachada (round-tripping), dos veces.",
                                 "cuentas": fachadas})

    # ---------------- P2: pitufeo hacia cuenta concentradora ----------------
    concentradora = nueva_cuenta("Iquitos", "cuenta", "independiente", 1500, "Wilmer Ahuanari Curitima")
    pitufos = [nueva_cuenta(rnd.choice(["Caballococha", "Santa Rosa"]), "cuenta",
                            rnd.choice(["pescador", "agricultor", "comerciante"]), 1100) for _ in range(14)]
    for p in pitufos:
        for _ in range(rnd.choice([1, 1, 2])):
            transferir(p, concentradora, rnd.uniform(8600, 9950),
                       datetime(2026, 10, 12, 8) + timedelta(hours=rnd.randint(0, 6 * 24)),
                       rnd.choice(["agencia", "billetera", "corresponsal"]), "transferencia")
    transferir(concentradora, fachadas[2], 120000, datetime(2026, 10, 20, 11, 30), "interbancaria", "compra")
    patrones["patrones"].append({"id": "P2", "tipo": "fragmentacion",
                                 "descripcion": "14 cuentas de la triple frontera depositan montos justo bajo el umbral "
                                                "en una cuenta concentradora que luego envía S/ 120 000 a Lima.",
                                 "cuentas": [concentradora] + pitufos, "concentradora": concentradora,
                                 "cuenta_reportada": concentradora})

    # ---------------- P4 + P3: dispersión minera y cadena de mulas ----------------
    minera = nueva_cuenta("Puerto Maldonado", "empresa", "comercio de oro", 15000, "Inversiones Oro Madre S.A.C.")
    receptores = [nueva_cuenta(rnd.choice(["Puerto Maldonado", "Lima", "Arequipa", "Iquitos"])) for _ in range(16)]
    for r in receptores:
        transferir(minera, r, rnd.uniform(4000, 9500),
                   datetime(2026, 9, 22, 9) + timedelta(hours=rnd.randint(0, 96)),
                   rnd.choice(["app", "interbancaria"]), "transferencia")
    patrones["patrones"].append({"id": "P4", "tipo": "dispersion",
                                 "descripcion": "Cuenta vinculada a comercio de oro dispersa fondos a 16 cuentas en 4 días.",
                                 "cuentas": [minera] + receptores, "emisora": minera})

    mulas = [nueva_cuenta(c, "cuenta", "estudiante", 1100) for c in
             ("Puerto Maldonado", "Arequipa", "Lima", "Lima", "Pucallpa", "Iquitos")]
    monto, fecha = 45000.0, datetime(2026, 10, 2, 9, 15)
    transferir(minera, mulas[0], monto, fecha, "interbancaria", "prestamo_familiar")
    for i in range(len(mulas) - 1):
        monto *= rnd.uniform(0.975, 0.99)
        fecha += timedelta(hours=rnd.uniform(1, 6))
        transferir(mulas[i], mulas[i + 1], monto, fecha, rnd.choice(["app", "billetera", "interbancaria"]),
                   "transferencia")
    patrones["patrones"].append({"id": "P3", "tipo": "cadena_puente",
                                 "descripcion": "Cadena de 6 cuentas puente (mulas): cada una reenvía ~98 % en pocas horas.",
                                 "cuentas": mulas, "origen": minera})

    # ---------------- P5: grupo cerrado de cuentas (tala ilegal) ----------------
    grupo = [nueva_cuenta("Pucallpa", rnd.choice(["cuenta", "empresa"]),
                          rnd.choice(["madera", "transporte", "independiente"])) for _ in range(6)]
    for _ in range(40):
        a, b = rnd.sample(grupo, 2)
        transferir(a, b, rnd.uniform(6000, 22000), inicio + timedelta(hours=rnd.randint(0, 60 * 24)),
                   rnd.choice(["app", "agencia"]), rnd.choice(["compra", "servicios", "transferencia"]))
    patrones["patrones"].append({"id": "P5", "tipo": "grupo_cerrado",
                                 "descripcion": "6 cuentas de Pucallpa con transferencias cruzadas intensas (grupo fuertemente conexo).",
                                 "cuentas": grupo})

    trans.sort(key=lambda t: t["fecha"])
    for i, t in enumerate(trans, start=1):
        t["id"] = f"T{i:05d}"
    return cuentas, trans, patrones


# =====================================================================
# MÓDULO 1 — red pequeña de ejemplo con tipos variados
# =====================================================================
def red_ejemplo() -> dict:
    lat, lon, _ = coord("Iquitos")
    n = lambda id, tipo, nombre, dl, dn: {"id": id, "tipo": tipo, "nombre": nombre,
                                          "lat": round(lat + dl, 4), "lon": round(lon + dn, 4)}
    return {
        "nombre": "Red de ejemplo Iquitos", "dirigido": True, "ponderado": True, "multiple": False,
        "nodos": [n("CLI_01", "cliente", "Cliente Ana Pinedo", 0.05, -0.05),
                  n("CTA_01", "cuenta", "Cuenta de ahorros 001", 0.03, 0.02),
                  n("CTA_02", "cuenta", "Cuenta corriente 002", -0.02, 0.06),
                  n("AG_IQT", "agencia", "Agencia BAA Iquitos", 0.0, 0.0),
                  n("ATM_01", "atm", "Cajero Plaza de Armas", 0.06, 0.08),
                  n("BILL_A", "billetera", "Billetera digital A", -0.05, -0.08),
                  n("SRV_01", "servidor", "Servidor de autorización", -0.08, 0.02),
                  n("BOV_IQT", "boveda_regional", "Bóveda regional Iquitos", 0.09, -0.02)],
        "aristas": [
            {"origen": "CLI_01", "destino": "CTA_01", "tipo_operacion": "titularidad", "comision_fija": 0},
            {"origen": "CTA_01", "destino": "CTA_02", "comision_fija": 0, "comision_pct": 0.0, "tiempo_min": 1, "limite": 50000},
            {"origen": "CTA_01", "destino": "BILL_A", "comision_fija": 0, "tiempo_min": 1, "limite": 2000, "riesgo": 0.002},
            {"origen": "CTA_02", "destino": "ATM_01", "comision_fija": 0, "tiempo_min": 2, "limite": 3000},
            {"origen": "BILL_A", "destino": "SRV_01", "tiempo_min": 0.2, "riesgo": 0.001},
            {"origen": "SRV_01", "destino": "AG_IQT", "tiempo_min": 0.1},
            {"origen": "BOV_IQT", "destino": "AG_IQT", "capacidad": 16000, "costo": 0.2},
            {"origen": "BOV_IQT", "destino": "ATM_01", "capacidad": 400, "costo": 0.6},
        ],
    }


def main() -> None:
    DATA.mkdir(exist_ok=True)
    n, a = red_enrutamiento()
    escribir_csv(DATA / "nodos_enrutamiento.csv", n)
    escribir_csv(DATA / "red_enrutamiento.csv", a)

    n, a, esc = red_liquidez()
    escribir_csv(DATA / "nodos_liquidez.csv", n)
    escribir_csv(DATA / "distribucion_liquidez.csv", a)
    (DATA / "escenarios_liquidez.json").write_text(json.dumps(esc, ensure_ascii=False, indent=2), encoding="utf-8")

    c, t, p = transacciones()
    escribir_csv(DATA / "cuentas.csv", c)
    escribir_csv(DATA / "transacciones.csv", t)
    (DATA / "patrones_plantados.json").write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")

    (DATA / "red_ejemplo.json").write_text(json.dumps(red_ejemplo(), ensure_ascii=False, indent=2), encoding="utf-8")
    escribir_csv(DATA / "ejemplo_minimo.csv", [
        {"origen": "CuentaA", "destino": "CuentaB", "comision": 4.50},
        {"origen": "CuentaA", "destino": "CuentaC", "comision": 2.00},
        {"origen": "CuentaB", "destino": "CuentaD", "comision": 5.10},
        {"origen": "CuentaC", "destino": "CuentaD", "comision": 1.00},
        {"origen": "CuentaD", "destino": "CuentaE", "comision": 3.00},
    ])
    escribir_csv(DATA / "ejemplo_con_errores.csv", [
        {"origen": "CuentaA", "destino": "CuentaB", "comision_fija": 4.50},
        {"origen": "CuentaA", "destino": "CuentaB", "comision_fija": 4.50},     # duplicada
        {"origen": "CuentaB", "destino": "CuentaB", "comision_fija": 1.00},     # bucle
        {"origen": "CuentaC", "destino": "CuentaD", "comision_fija": -2.00},    # negativa
        {"origen": "CuentaD", "destino": "CuentaE", "riesgo": 1.7},             # fuera de [0,1]
        {"origen": "CuentaE", "destino": "", "comision_fija": 3.00},            # destino vacío
    ])
    print(f"Datos generados en {DATA} (cuentas: {len(c)}, transacciones: {len(t)})")


if __name__ == "__main__":
    main()
