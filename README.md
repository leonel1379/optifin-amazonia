# OptiFin Amazonía — Sistema de Análisis y Optimización de Redes Financieras

Proyecto II · **Programación III** · Universidad Nacional de San Antonio Abad del Cusco  
Docente: Mgt. Karla Catherine Rojas Pedraza  
**Integrantes:** Baca Pauccar, Elmer Leonel · Huillca Casa, Erik · Quispe Hermoza, Roberto Carlos · Quispe Huamanttupa, Alfredo

## ▶️ Inicio rápido (un clic)

1. Descargue el proyecto (**Code → Download ZIP**) y **extráigalo**.
2. Haga **doble clic en `INICIAR.bat`**.
   * La primera vez instala todo automáticamente (1–3 min, requiere internet; si falta Python, también lo instala).
   * Luego se abre el navegador con el programa. Las siguientes veces abre en segundos.

📘 **Manual completo con capturas: [GUIA_DE_USO.md](GUIA_DE_USO.md)** · versión PDF: [docs/GUIA_DE_USO.pdf](docs/GUIA_DE_USO.pdf)

---

Sistema en Python que modela la red de un banco nacional **ficticio**, el *Banco Andino Amazónico (BAA)*, con
presencia en costa, sierra y selva, y resuelve tres escenarios operativos con algoritmos de grafos implementados
desde cero:

| Escenario | Problema | Algoritmo elegido | Alternativas comparadas |
|---|---|---|---|
| 1. Fraude y lavado de activos | Ciclos de fondos, pitufeo, cuentas puente, dispersión, grupos cerrados, rastreo del dinero | BFS · DFS acotada · Tarjan (SCC) · búsqueda temporal | Kosaraju |
| 2. Enrutamiento y comisiones | ¿Por qué ruta la comisión es más baja? | **Dijkstra** (heap binario) | Bellman-Ford · Floyd-Warshall · backtracking · Yen |
| 3. Liquidez hacia bóvedas | ¿Cuánto efectivo puede llegar a cada agencia y dónde está el cuello de botella? | **Dinic** + corte mínimo + flujo de costo mínimo | Edmonds-Karp · Kruskal/Prim (MST) |

> Las entidades, cuentas, montos y tarifas son **simulados**. Las ciudades, coordenadas y la geografía
> (Iquitos sin acceso por carretera, rutas fluviales del Ucayali, Huallaga y Amazonas, triple frontera
> Perú–Colombia–Brasil) corresponden a la realidad peruana. Los patrones detectados son **indicadores** para revisión;
> no constituyen prueba de delito.

---

## 1. Estructura del repositorio

```
proyecto_optifin/
├── main.py                     # punto de entrada: python main.py
├── INICIAR.bat                 # Windows: instala (1.ª vez) y abre el programa con doble clic
├── iniciar.sh                  # Linux / macOS: bash iniciar.sh
├── GUIA_DE_USO.md              # guía de uso detallada con capturas
├── README.md                   # este manual de instalación y reproducibilidad
├── requirements.txt            # dependencias con versión fija
├── .gitignore
├── .streamlit/config.toml      # tema y servidor de la interfaz web
├── data/                       # datos simulados (CSV / JSON) listos para cargar
├── scripts/generar_datos.py    # regenera data/ de forma reproducible (semilla 2026)
├── src/
│   ├── graph.py                # estructura común: lista de adyacencia (dirigida/no dirigida, multigrafo)
│   ├── gestion_red.py          # Módulo 1: carga, CRUD, importación/exportación, validación
│   ├── analisis_transacciones.py   # Módulo 2: fraude y lavado de activos
│   ├── enrutamiento_financiero.py  # Módulo 3: rutas y comisiones
│   ├── distribucion_liquidez.py    # Módulo 4: liquidez hacia bóvedas
│   ├── evaluacion_resultados.py    # Módulo 5: casos de prueba, benchmarks, validación
│   ├── utils.py                # medición de tiempo/memoria, formato y reportes
│   ├── algoritmos/             # BFS, DFS, Tarjan, Kosaraju, Dijkstra, Bellman-Ford, Floyd-Warshall,
│   │                           # Yen, backtracking, Edmonds-Karp, Dinic, costo mínimo, Kruskal, Prim
│   └── ui/                     # app.py (web Streamlit), cli.py (terminal), visual.py (gráficos)
│       └── static/             # mapa base del Perú (TopoJSON) para usar el mapa sin internet
├── tests/                      # pruebas automatizadas (pytest)
├── reports/                    # reportes generados al ejecutar (no se versionan)
└── docs/                       # informe técnico (PDF), diapositivas e imágenes de la guía
```

---

## 2. Requisitos

### Software
| Componente | Versión |
|---|---|
| Python | **3.11, 3.12 o 3.13** (probado con 3.13) |
| pip | 23 o superior |
| Navegador | Chrome, Edge o Firefox actualizados |
| Git | 2.30 o superior (solo para clonar el repositorio) |
| Sistema operativo | Windows 10/11, Ubuntu 22.04+ o macOS 12+ |

Bibliotecas (ver `requirements.txt`): `streamlit 1.67.0`, `plotly 7.2.0`, `pandas 3.0.5`, `networkx 3.7`,
`pytest 9.1.1`. **NetworkX no se usa para resolver los problemas**: solo valida los resultados (Módulo 5) y ubica
los nodos en los diagramas de cuentas.

### Hardware
| | Mínimo | Recomendado |
|---|---|---|
| Procesador | 2 núcleos, 64 bits | 4 núcleos o más |
| Memoria RAM | 4 GB | 8 GB |
| Disco libre | 500 MB (entorno virtual + dependencias) | 1 GB |
| Pantalla | 1366 × 768 | 1920 × 1080 |
| Internet | Solo para instalar dependencias | — |

Una vez instalado, el sistema funciona **sin conexión** (incluido el mapa del Perú).

---

## 3. Instalación paso a paso

> **Atajo:** en Windows, doble clic en `INICIAR.bat`; en Linux/macOS, `bash iniciar.sh`. Hacen automáticamente
> todo lo de esta sección. Los pasos siguientes son la alternativa manual.

### 3.1 Obtener el proyecto
```bash
git clone https://github.com/<usuario>/proyecto_optifin.git
cd proyecto_optifin
```
(o descargar el ZIP desde GitHub → *Code* → *Download ZIP* y descomprimirlo).

### 3.2 Crear y activar un entorno virtual

**Windows (PowerShell)**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```
Si PowerShell bloquea el script: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` y repetir.

**Linux / macOS**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3.3 Instalar dependencias
```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 3.4 Verificar la instalación
```bash
python -m pytest -q
```
Resultado esperado: **`38 passed`**.

---

## 4. Ejecución

| Comando | Qué hace |
|---|---|
| Doble clic en `INICIAR.bat` | Windows: instala la primera vez y abre la interfaz web. |
| `python main.py` | Abre la interfaz web local en `http://localhost:8501` (se abre el navegador automáticamente). |
| `python main.py --cli` | Menú interactivo en la terminal (respaldo sin navegador). |
| `python main.py --demo` | Ejecuta los 5 módulos sin intervención y guarda reportes CSV/JSON en `reports/`. |
| `python main.py --puerto 8502` | Usa otro puerto (si el 8501 está ocupado se elige el siguiente libre automáticamente). |
| `python main.py --sin-navegador` | Inicia el servidor sin abrir el navegador. |

Para detener la interfaz web: cerrar la ventana de la terminal o `Ctrl + C`.
La descripción detallada de cada pantalla está en **[GUIA_DE_USO.md](GUIA_DE_USO.md)**.

### Uso de la interfaz web
El menú lateral tiene un módulo por sección:

1. **Gestión de redes** — mapa, tablas de nodos y aristas, crear/modificar/eliminar, **cerrar sucursales y rutas**,
   importar (CSV/JSON/TXT), exportar y validar consistencia. Los cierres afectan a todos los módulos.
2. **Fraude y lavado** — ranking de riesgo, ciclos, pitufeo, cuentas puente, dispersión, grupos cerrados,
   rastreo cronológico de fondos, proximidad entre cuentas y validación contra los patrones plantados.
3. **Enrutamiento y comisiones** — elegir origen, destino, monto y criterio (comisión, tiempo, riesgo o
   combinado). Muestra la ruta en el mapa, la justificación del algoritmo, rutas alternativas (Yen), todas las rutas
   (backtracking), comparación de algoritmos, impacto del cierre de sucursales y la matriz de comisiones
   (Floyd-Warshall).
4. **Liquidez hacia bóvedas** — escenarios (normal, vaciante, diciembre, vuelo cancelado, bloqueo de carretera,
   crisis amazónica), política equitativa o de costo mínimo, mapa de flujos, Sankey, cuellos de botella con
   simulación de ampliación, comparación de escenarios y red troncal (MST).
5. **Evaluación** — casos de prueba (esperado vs obtenido), comparación empírica de tiempos con gráfico log-log,
   tabla de complejidad y decisiones, validación contra NetworkX y reporte descargable.

---

## 5. Datos de prueba (`data/`)

| Archivo | Módulo | Contenido |
|---|---|---|
| `nodos_enrutamiento.csv` | 3 | 30 puntos: 14 agencias, CCE, 2 billeteras, procesador de tarjetas (débito y crédito), red ATM, 3 entidades, 3 corresponsales, 5 cajeros. Columnas: `id,tipo,nombre,ciudad,region,lat,lon,entidad` |
| `red_enrutamiento.csv` | 3 | 75 canales (incluye tarjetas de débito y crédito). `id,origen,destino,tipo_operacion,canal,comision_fija,comision_pct,tiempo_min,riesgo,limite,bonificacion` |
| `nodos_liquidez.csv` | 4 | 7 bóvedas y 15 agencias. `oferta` y `demanda` en **miles de soles por ciclo semanal** |
| `distribucion_liquidez.csv` | 4 | 31 rutas de traslado: `modo` (terrestre/aereo/fluvial), `capacidad`, `costo` (S/ por S/ 1 000), `tiempo_h`, `riesgo`, `distancia_km` |
| `escenarios_liquidez.json` | 4 | Factores de capacidad y demanda y cierres de cada escenario |
| `cuentas.csv` | 2 | 404 cuentas: `tipo` (cuenta/empresa), titular, ciudad, actividad, ingreso mensual declarado |
| `transacciones.csv` | 2 | 2 711 transferencias (sep–oct 2026): `monto,fecha,canal,concepto` |
| `patrones_plantados.json` | 2 | Verdad de referencia: 5 patrones sospechosos insertados (ciclo, pitufeo, cadena de mulas, dispersión, grupo cerrado) |
| `red_ejemplo.json` | 1 | Red pequeña con nodos de todos los tipos (cliente, cuenta, ATM, billetera, servidor, bóveda) |
| `ejemplo_minimo.csv` | 1 | Formato mínimo de la guía (`origen,destino,comision`) |
| `ejemplo_con_errores.csv` | 1 | Datos inválidos a propósito (duplicada, bucle, negativa, riesgo > 1, destino vacío) |

**Por qué estos datos son adecuados:** la red de enrutamiento tiene canales con compromisos reales
(la billetera es más barata pero tiene límite de S/ 2 000; la CCE diferida es barata pero tarda un día; la inmediata
es rápida pero cara), de modo que la ruta óptima cambia con el monto y el criterio. La red de liquidez reproduce la
restricción física de Loreto (Iquitos solo recibe efectivo por avión o por río), lo que crea cuellos de botella
verificables. Las transacciones mezclan comportamiento normal (incluidas planillas, que son dispersión legítima) con
patrones plantados cuya ubicación se conoce, lo que permite medir aciertos y falsos positivos.

Para regenerar exactamente los mismos datos: `python scripts/generar_datos.py`.

### Formatos aceptados al importar
* **CSV**: columnas obligatorias `origen,destino`; el resto se toma como atributos. Archivo de nodos opcional con `id,tipo,nombre,lat,lon,…`.
* **JSON**: el que produce *Exportar → JSON* (`{"nombre", "dirigido", "ponderado", "multiple", "nodos": [...], "aristas": [...]}`).
* **TXT**: una conexión por línea, `origen destino peso`; `#` inicia un comentario.

---

## 6. Reproducir los resultados del informe

```bash
python -m pytest -q          # 38 pruebas automatizadas
python main.py --demo        # casos de prueba (24/24), análisis de los 3 escenarios y benchmarks → reports/
```
Valores de referencia que deben obtenerse:

| Prueba | Resultado |
|---|---|
| Comisión mínima AG_LIM → CORR_CAB, S/ 1 500 | S/ 5.75 (Lima → billetera A → billetera B → Caja Selva → corresponsal Caballococha) |
| Mismo envío con S/ 5 000 (supera el límite de billetera) | S/ 18.50 vía CCE diferida |
| Flujo máximo de efectivo, escenario normal | S/ 120 000 mil de S/ 123 500 mil (97.2 %) |
| Vuelo Lima–Iquitos cancelado | baja a S/ 112 000 mil |
| Patrones plantados detectados | 5 de 5, 0 falsos positivos de riesgo alto/medio |

Los **tiempos de ejecución** de los benchmarks dependen del equipo; lo que debe mantenerse es el orden relativo
(Dijkstra < Bellman-Ford ≪ Floyd-Warshall; Dinic ≪ Edmonds-Karp) y los exponentes empíricos aproximados.

---

## 7. Pruebas automatizadas (`tests/`)

| Archivo | Verifica |
|---|---|
| `test_gestion_red.py` | Carga de redes, CSV/JSON/TXT, CRUD, cierres, validación de datos inválidos, multigrafo |
| `test_algoritmos.py` | Cada algoritmo sobre redes pequeñas con resultado calculado a mano |
| `test_transacciones.py` | Detección de los 5 patrones, rastreo cronológico y proximidad |
| `test_enrutamiento.py` | Rutas óptimas, límites, sucursales cerradas, promociones (pesos negativos) y criterios |
| `test_liquidez.py` | Flujo máximo por escenario, corte mínimo, políticas, ampliación de rutas y MST |
| `test_evaluacion.py` | Los 24 casos de prueba integrales, benchmarks y validación contra NetworkX |

---

## 8. Solución de problemas

| Síntoma | Solución |
|---|---|
| `python` no se reconoce | Instalar Python marcando *Add Python to PATH* o usar `py` en Windows. |
| `ModuleNotFoundError: streamlit` | Activar el entorno virtual y ejecutar `pip install -r requirements.txt`. |
| El puerto 8501 está ocupado | El programa usa automáticamente el siguiente libre (8502…); la terminal muestra la dirección. |
| El navegador no se abre | Abrir manualmente `http://localhost:8501`. |
| No hay navegador disponible | `python main.py --cli`. |
| El mapa no muestra el contorno del Perú | En el menú lateral elegir *Vista esquemática*. |

---

## 9. Control de versiones

* Cada cambio se registra con commits descriptivos (`git log --oneline`).
* La versión entregada se identifica con la etiqueta **`v1.0.0`**: `git checkout v1.0.0`.

## 10. Integrantes

| Integrante | Responsable de |
|---|---|
| Baca Pauccar, Elmer Leonel | Modelamiento del grafo, arquitectura y Módulo 1 (gestión de redes) |
| Huillca Casa, Erik | Escenario 1: fraude y lavado de activos (Módulo 2) |
| Quispe Hermoza, Roberto Carlos | Escenario 2: enrutamiento y comisiones (Módulo 3) |
| Quispe Huamanttupa, Alfredo | Escenario 3: liquidez, evaluación y validación (Módulos 4 y 5) |
