"""Cada pantalla de la interfaz se abre en un navegador real y no debe lanzar ningún error de JavaScript.

`node --check` solo mira la sintaxis: un paréntesis de más pasó esa prueba y rompió la Vista en vivo al abrirla. Aquí se sirve `apps/web`
en un puerto libre (sin API: las llamadas que fallan las atrapa la propia interfaz) y se visitan todas las rutas, en español y en inglés."""
import functools
import http.server
import threading
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[2] / "apps" / "web"
RUTAS = ["#/jurado", "#/cliente", "#/vista", "#/operacion", "#/sistema", "#/acerca"]


@pytest.fixture(scope="module")
def sitio():
    manejador = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(WEB))
    manejador.log_message = lambda *a, **k: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), manejador)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/index.html"
    srv.shutdown()


@pytest.mark.parametrize("idioma", ["es", "en"])
def test_ninguna_pantalla_lanza_errores_de_javascript(sitio, idioma):
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        try:
            navegador = p.chromium.launch()
        except Exception as e:                                   # sin Chromium instalado en esta máquina
            pytest.skip(f"sin navegador: {e}")
        pagina = navegador.new_context(locale=idioma).new_page()
        errores = []
        pagina.on("pageerror", lambda e: errores.append(str(e)))
        for ruta in RUTAS:
            pagina.goto(sitio + ruta)
            pagina.wait_for_timeout(500)
            assert pagina.locator("#app").inner_text().strip(), f"{ruta} quedó en blanco"
        navegador.close()
    assert not errores, errores


def test_las_tarjetas_de_los_clientes_se_dibujan_con_sus_rasgos_y_se_marca_la_elegida(sitio):
    """La prueba de arriba no llega a dibujar las tarjetas (no hay API): aquí se simulan las identidades y se comprueba lo que ve el jurado.
    Un borrado accidental de la función que calcula los rasgos pasó todas las pruebas hasta que se escribió esta."""
    import json

    sync_api = pytest.importorskip("playwright.sync_api")
    perfiles = json.loads((WEB.parents[1] / "evaluacion" / "identidades_demo.json").read_text(encoding="utf-8"))
    cabeceras = {"access-control-allow-origin": "*", "content-type": "application/json"}
    with sync_api.sync_playwright() as p:
        try:
            navegador = p.chromium.launch()
        except Exception as e:
            pytest.skip(f"sin navegador: {e}")
        pagina = navegador.new_context(locale="en").new_page()
        errores = []
        pagina.on("pageerror", lambda e: errores.append(str(e)))
        pagina.route("**/demo/identidades", lambda r: r.fulfill(status=200, headers=cabeceras, body=json.dumps(perfiles)))
        pagina.goto(sitio + "#/jurado")
        pagina.wait_for_selector("button.perfil", timeout=5000)
        tarjetas = pagina.locator("button.perfil")
        assert tarjetas.count() == len(perfiles) + 1                                  # los clientes y el visitante sin sesión
        assert "Customer 1" in tarjetas.nth(0).inner_text() and "transactions" in tarjetas.nth(0).inner_text()
        assert "Visitor" in tarjetas.nth(len(perfiles)).inner_text()
        assert "Lora demo" not in pagina.locator("#escenarios").inner_text()          # Lora es una sola asistente: las tarjetas son clientes
        navegador.close()
    assert not errores, errores
