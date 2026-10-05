"""Recorrido de punta a punta en un navegador sin interfaz, contra la API local con el modelo real.
Guarda capturas (y video si se pide). Uso: python scripts/dev/recorrido_navegador.py DIR [--video]"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

salida = Path(sys.argv[1]); salida.mkdir(parents=True, exist_ok=True)
video = "--video" in sys.argv
BASE = "http://127.0.0.1:8020/app/"
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1280, "height": 860}, record_video_dir=str(salida) if video else None)
    pg = ctx.new_page()
    pg.goto(BASE + "#/vista")
    pg.wait_for_timeout(1500)
    entrada = pg.locator("input[aria-label='Mensaje']")
    entrada.fill("me salió un cobro raro de ayer, yo no hice eso")
    entrada.press("Enter")
    pg.wait_for_selector("text=Formulario seguro", timeout=120000)
    pg.screenshot(path=str(salida / "1_formulario.png"))
    pg.fill("input[placeholder^='Documento']", "DEMO-1001")
    pg.click("text=Enviar código")
    pg.wait_for_selector("text=Buzón del sandbox", timeout=30000)
    aviso = pg.locator("text=Buzón del sandbox").inner_text()
    codigo = aviso.split("Buzón del sandbox:")[1].strip(" )")
    pg.fill("input[placeholder='Código']", codigo)
    pg.click("text=Verificar")
    pg.wait_for_selector("text=Sí, hazlo", timeout=180000)
    pg.wait_for_timeout(1500)
    pg.screenshot(path=str(salida / "2_cargo_y_propuesta.png"))
    pg.click("text=Sí, hazlo")
    pg.wait_for_selector("text=Tu caso", timeout=180000)
    pg.wait_for_timeout(2500)
    pg.screenshot(path=str(salida / "3_reclamo_verificado.png"), full_page=True)
    ctx.close()
    b.close()
print("recorrido completo")
