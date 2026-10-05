"""La interfaz web del personal es bilingüe (apps/web/i18n.js): el español es la clave y el inglés su traducción."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[2] / "apps" / "web"


def _traducciones() -> dict:
    js = (WEB / "i18n_en.js").read_text(encoding="utf-8")
    return json.loads(js[js.index("export const EN = ") + len("export const EN = "): js.rindex(";")])


def test_todo_rotulo_de_la_interfaz_tiene_traduccion():
    """Un `tr("…")` sin traducción se vería en español dentro de una pantalla en inglés."""
    app = (WEB / "app.js").read_text(encoding="utf-8")
    en = _traducciones()
    usados = {m.group(1) for m in re.finditer(r'(?<![\w.$])tr\("((?:[^"\\\n]|\\.)*)"\)', app)}
    faltan = sorted(u for u in usados if u not in en)
    assert not faltan, f"rótulos sin traducir al inglés: {faltan}"


def test_las_traducciones_no_estan_vacias_ni_son_iguales_salvo_nombres_propios():
    iguales = sorted(k for k, v in _traducciones().items() if not v.strip())
    assert not iguales


@pytest.mark.skipif(shutil.which("node") is None, reason="sin node")
def test_el_javascript_de_la_interfaz_tiene_sintaxis_valida():
    # Como módulo (así lo carga el navegador): `node --check` sobre un .js a veces lo da por bueno y el navegador no (pasó con un paréntesis sin cerrar).
    import tempfile
    for archivo in ("app.js", "i18n.js", "i18n_en.js", "guia.js", "flujo.js", "marca.js"):
        with tempfile.TemporaryDirectory() as d:
            copia = Path(d) / (Path(archivo).stem + ".mjs")
            copia.write_text((WEB / archivo).read_text(encoding="utf-8"), encoding="utf-8")
            r = subprocess.run(["node", "--check", str(copia)], capture_output=True, text=True)
        assert r.returncode == 0, f"{archivo}: {r.stderr[:300]}"


def test_modo_jurado_es_la_entrada_y_no_muestra_identificadores_internos():
    """El jurado entra por «Probar» (#/jurado), elige un escenario y ve la cuenta y la traza sin CLI-/TRX-/PRD- (los datos del organizador)."""
    app = (WEB / "app.js").read_text(encoding="utf-8")
    assert '"#/jurado": vistaJurado' in app and 'location.hash : "#/jurado"' in app
    assert "ID_INTERNO" in app and "sinIds(traza[traza.length - 1])" in app            # la traza pasa por el enmascarado
    assert 'href="#/jurado"' in (WEB / "index.html").read_text(encoding="utf-8")
    assert "sugerencias(perfil)" in app and "SUGERENCIAS = {" not in app            # lo sugerido sale del perfil del cliente, no de un caso escrito a mano


def test_las_leyendas_de_los_pasos_del_modo_jurado_tienen_traduccion():
    """`tr(AYUDA_PASOS[...])` no es un literal: el candado de rótulos no lo ve, así que se comprueba aquí."""
    app = (WEB / "app.js").read_text(encoding="utf-8")
    bloque = app[app.index("const AYUDA_PASOS = {"): app.index("function pintarRegistro")]
    frases = re.findall(r':\s*"((?:[^"\\\n]|\\.)*)",', bloque) + re.findall(r'tr\("((?:[^"\\\n]|\\.)*)"\)', bloque)
    en = _traducciones()
    assert len(frases) >= 13
    assert not sorted(f for f in frases if f not in en), "leyendas sin traducir"


def test_las_notas_del_presentador_cubren_cada_escenario_cada_nodo_y_van_en_ingles_con_el_espanol_entre_parentesis():
    """`guia.js`: cada nota es un par [inglés, español] (el jurado lee inglés; el presentador, el español). Debe haber una por cliente DEMO y por nodo terminal."""
    from contratos.modelos import Nodo
    guia = (WEB / "guia.js").read_text(encoding="utf-8")
    bloque = lambda nombre: guia[guia.index(f"export const {nombre} = {{"): guia.index("\n};", guia.index(f"export const {nombre} = {{"))]
    assert "NOTAS_ESCENARIO" not in guia, "las notas por cliente escritas a mano se quitaron: los rasgos salen de los datos"
    nodos = set(re.findall(r'^\s+(N\d+):', bloque("NOTAS_NODO"), flags=re.M))
    assert nodos <= {n.name for n in Nodo}
    assert {"N0", "N1", "N4", "N5", "N7", "N10", "N11", "N12", "N13", "N14"} <= nodos          # los nodos donde un turno termina y habla
    for nombre in ("NOTAS_VISTA", "NOTAS_NODO"):
        pares = re.findall(r'\["([^"]+)",\s*"([^"]+)"\]', bloque(nombre))
        assert pares and all(es != en for en, es in pares)
    assert 'body.sin-guia' in (WEB / "estilos.css").read_text(encoding="utf-8")                  # el interruptor las oculta todas


def test_el_mapa_del_flujo_dibuja_solo_nodos_y_bordes_que_existen_en_el_grafo():
    """`flujo.js` es una copia de la forma del grafo (ARQUITECTURA §6): sus nodos existen y sus bordes están en el plano."""
    from contratos.modelos import Nodo
    js = (WEB / "flujo.js").read_text(encoding="utf-8")
    nodos = set(re.findall(r'(N\d+): \[', js[js.index("const NODOS"): js.index("const BORDES")]))
    assert nodos == {n.name for n in Nodo}                       # los quince nodos, ni uno inventado ni uno que falte
    plano = (Path(__file__).resolve().parents[2] / "docs" / "ARQUITECTURA.md").read_text(encoding="utf-8")
    for a, b in re.findall(r'\["(N\d+)", "(N\d+)"\]', js[js.index("const BORDES"): js.index("// Which trace step")]):
        assert re.search(rf"{a}[^|\n]*→ {b}|{a}/[^|\n]*→ {b}|{b} → {a}", plano), f"el borde {a}→{b} no está en ARQUITECTURA.md §6.2"


def test_la_pantalla_about_reune_las_frases_clave_y_los_limites_en_ingles_con_espanol_entre_parentesis():
    guia = (WEB / "guia.js").read_text(encoding="utf-8")
    bloque = guia[guia.index("export const ACERCA"):]
    assert 'Honest limits' in bloque and 'With a real bank' in bloque
    pares = re.findall(r'\["([^"]+)",\s*"([^"]+)"\]', bloque)
    assert len(pares) >= 15 and all(es != en for en, es in pares)
    assert 'href="#/acerca"' in (WEB / "index.html").read_text(encoding="utf-8") and '"#/acerca": vistaAcerca' in (WEB / "app.js").read_text(encoding="utf-8")


def test_todo_enlace_del_menu_tiene_su_rotulo_traducible():
    """El menú de `index.html` está escrito en español y `cabecera()` lo traduce por ruta: una ruta sin rótulo se quedaría en español en inglés."""
    index = (WEB / "index.html").read_text(encoding="utf-8")
    app = (WEB / "app.js").read_text(encoding="utf-8")
    rutas = re.findall(r'<a href="(#/[a-z]+)">([^<]+)</a>', index)
    rotulos = dict(re.findall(r'"(#/[a-z]+)": "([^"]+)"', app[app.index("const rotulos = {"): app.index("document.querySelectorAll(\".barra a\")")]))
    en = _traducciones()
    for ruta, texto in rutas:
        assert rotulos.get(ruta) == texto and texto in en, f"el enlace {ruta} ({texto}) no se traduce"


def test_los_mensajes_de_lo_que_no_puede_hacer_no_incluyen_lo_que_si_hace():
    """Pedir una persona y preguntar el horario SÍ los hace (traspaso con paquete; artículo del banco): no pueden ir bajo «lo que no puede hacer»."""
    app = (WEB / "app.js").read_text(encoding="utf-8")
    no_puede = app[app.index("const NO_PUEDE = ["): app.index("]", app.index("const NO_PUEDE = ["))]
    si_puede = app[app.index("const SI_PUEDE = ["): app.index("]", app.index("const SI_PUEDE = ["))]
    assert "persona" not in no_puede.replace("personas", "") and "hora" not in no_puede
    assert "quiero hablar con una persona" in si_puede and "atienden las personas" in si_puede
    assert "SUGERENCIAS_GENERALES" not in app


def test_el_asesor_descarga_el_pdf_y_ve_el_aviso_sobre_qr_y_enlaces():
    """SEGURIDAD T-4: el PDF nunca se abre en el navegador del asesor; un QR de un adjunto lo escanea una persona, y la interfaz se lo advierte."""
    app = (WEB / "app.js").read_text(encoding="utf-8")
    assert 'blob.type === "application/pdf"' in app and "download:" in app and '"noopener"' in app
    assert "No escanees códigos QR ni abras enlaces que aparezcan en un adjunto" in app


def test_elegir_un_cliente_no_cambia_de_pantalla_y_la_tarjeta_elegida_queda_marcada():
    """Las tarjetas quedan a la vista (fila compacta) y la elegida se marca; el chat aparece debajo. Sin «Cambiar de cliente» ni desplazamientos que escondan la tarjeta."""
    app = (WEB / "app.js").read_text(encoding="utf-8")
    css = (WEB / "estilos.css").read_text(encoding="utf-8")
    jurado = app[app.index("function vistaJurado"): app.index("async function tokenObservador")]
    assert 'classList.add("compacto")' in jurado and 'setAttribute("aria-pressed"' in jurado and "scrollIntoView" not in jurado
    assert 'tr("Cambiar de cliente")' not in jurado
    assert "button.perfil.elegido" in css and ".panel.compacto" in css
