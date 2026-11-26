"""
OptiFin Amazonía — punto de entrada.

    python main.py            → abre la interfaz web local en el navegador
    python main.py --cli      → menú en la terminal
    python main.py --demo     → ejecuta todos los módulos y guarda reportes en reports/
    python main.py --puerto 8502   → usa otro puerto para la interfaz web

En Windows basta con hacer doble clic en INICIAR.bat (instala todo la primera vez).
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

RAIZ = Path(__file__).resolve().parent


def puerto_libre(inicial: int) -> int:
    """Primer puerto libre desde `inicial` (si 8501 está ocupado se usa 8502, 8503…)."""
    for p in range(inicial, inicial + 30):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    return inicial


def abrir_navegador_cuando_este_listo(url: str, espera_max: float = 90.0) -> None:
    """Espera a que el servidor responda y abre el navegador predeterminado."""
    limite = time.time() + espera_max
    while time.time() < limite:
        try:
            with urllib.request.urlopen(url + "/_stcore/health", timeout=2) as r:
                if r.status == 200:
                    webbrowser.open(url)
                    return
        except OSError:
            time.sleep(0.5)
    print(f"No se pudo abrir el navegador automáticamente. Abra manualmente: {url}")


def main() -> int:
    p = argparse.ArgumentParser(description="Sistema de análisis y optimización de redes financieras")
    p.add_argument("--cli", action="store_true", help="interfaz de terminal")
    p.add_argument("--demo", action="store_true", help="ejecución completa no interactiva con reportes")
    p.add_argument("--puerto", type=int, default=8501, help="puerto de la interfaz web (por defecto 8501)")
    p.add_argument("--sin-navegador", action="store_true", help="no abrir el navegador automáticamente")
    args = p.parse_args()

    sys.path.insert(0, str(RAIZ))
    if args.demo:
        from src.ui.cli import demo
        demo()
        return 0
    if args.cli:
        from src.ui.cli import menu
        menu()
        return 0
    if importlib.util.find_spec("streamlit") is None:
        print("Faltan las bibliotecas del programa.\n"
              "  · Windows: haga doble clic en INICIAR.bat (las instala automáticamente).\n"
              "  · Manual:  python -m pip install -r requirements.txt\n"
              "Mientras tanto se abre el modo terminal.\n")
        from src.ui.cli import menu
        menu()
        return 0

    puerto = puerto_libre(args.puerto)
    url = f"http://localhost:{puerto}"
    app = RAIZ / "src" / "ui" / "app.py"
    # headless=true evita las preguntas interactivas de Streamlit (correo, novedades);
    # el navegador lo abre este mismo programa cuando el servidor está listo.
    cmd = [sys.executable, "-m", "streamlit", "run", str(app), "--server.port", str(puerto),
           "--server.headless", "true", "--browser.gatherUsageStats", "false"]
    print("=" * 64)
    print("  OptiFin Amazonía")
    print(f"  Abriendo el programa en el navegador: {url}")
    print("  No cierre esta ventana mientras use el programa.")
    print("  Para salir: cierre esta ventana o presione Ctrl + C.")
    print("=" * 64)
    if not args.sin_navegador:
        threading.Thread(target=abrir_navegador_cuando_este_listo, args=(url,), daemon=True).start()
    try:
        return subprocess.call(cmd, cwd=RAIZ, env={**os.environ, "PYTHONPATH": str(RAIZ)})
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
