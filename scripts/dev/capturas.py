"""Capturas de las tres interfaces con un navegador sin interfaz (revisión visual). Uso: python scripts/dev/capturas.py DIR"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

salida = Path(sys.argv[1]); salida.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    b = p.chromium.launch()
    for ancho, nombre in ((1280, "escritorio"), (390, "movil")):
        pg = b.new_page(viewport={"width": ancho, "height": 900})
        for ruta in ("cliente", "vista", "operacion"):
            pg.goto(f"http://127.0.0.1:8020/app/#/{ruta}")
            pg.wait_for_timeout(1200)
            pg.screenshot(path=str(salida / f"{ruta}_{nombre}.png"), full_page=True)
    b.close()
print("listo")
