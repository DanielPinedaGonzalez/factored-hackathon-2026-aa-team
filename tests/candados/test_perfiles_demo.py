"""Los clientes de demostración se muestran con sus rasgos reales, calculados de los datos (`scripts/perfiles_demo.py`), no con una etiqueta escrita a mano.

Antes cada cliente llevaba un texto («tres cargos del mismo comercio») y los datos lo desmintieron (eran seis)."""
import importlib.util
import json
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
JSON = RAIZ / "evaluacion" / "identidades_demo.json"
CLAVES = {"documento", "pais", "segmento", "productos", "movimientos", "cargos_ayer", "mayor", "comercio_repetido", "riesgo"}


def _perfiles():
    return json.loads(JSON.read_text(encoding="utf-8"))


def test_cada_cliente_de_demo_trae_sus_rasgos_y_ningun_texto_escrito_a_mano():
    perfiles = _perfiles()
    assert [p["documento"] for p in perfiles] == [f"DEMO-100{i}" for i in range(1, 8)]
    for p in perfiles:
        assert set(p) == CLAVES, p["documento"]
        assert "muestra" not in p and p["productos"] and p["movimientos"] > 0


def test_la_interfaz_pinta_los_rasgos_y_los_traduce():
    web = RAIZ / "apps" / "web"
    app = (web / "app.js").read_text(encoding="utf-8")
    assert "rasgos(i)" in app and "i.muestra" not in app
    en = (web / "i18n_en.js").read_text(encoding="utf-8")
    perfiles = _perfiles()
    tipos = {t for p in perfiles for t in p["productos"]} | {"México", "Argentina", "Colombia"}
    faltan = [t for t in tipos if f'"{t}":' not in en]
    assert not faltan, f"productos o países sin traducir al inglés: {faltan}"


@pytest.mark.db
def test_los_rasgos_publicados_son_los_de_los_datos_cargados():
    """Si se recargan los datos y no se corre `scripts/perfiles_demo.py`, el archivo miente."""
    import psycopg
    from servicio.datos.db import URL_ADMIN
    spec = importlib.util.spec_from_file_location("perfiles_demo", RAIZ / "scripts" / "perfiles_demo.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    with psycopg.connect(URL_ADMIN, autocommit=True) as c:
        assert m.calcular(c) == _perfiles(), "regenera: python scripts/perfiles_demo.py"
