"""Prioridad 3 por dinero en juego: umbral por tipo calculado de los datos; nunca pasa delante de seguridad."""
import json
from datetime import date
from pathlib import Path

import yaml

from servicio.traspaso.traspaso import ARTEFACTO_DINERO, dinero_en_juego, prioridad

HOY = date(2026, 6, 18)
RAIZ = Path(__file__).resolve().parents[2]


def test_el_umbral_sale_del_artefacto_y_cubre_todos_los_tipos_reclamables():
    a = json.loads(ARTEFACTO_DINERO.read_text())
    comun = yaml.safe_load((RAIZ / "politica" / "comun.yaml").read_text())
    assert a["cuantil"] == comun["dinero_en_juego"]["cuantil"]
    assert set(comun["tipos_operacion_reclamables"]) <= set(a["por_tipo"])


def test_alto_es_relativo_al_tipo():
    u = json.loads(ARTEFACTO_DINERO.read_text())["por_tipo"]
    assert dinero_en_juego("Purchase", u["Purchase"]["umbral_usd"] + 1)
    assert not dinero_en_juego("Transfer", u["Purchase"]["umbral_usd"] + 1)      # normal para una transferencia
    assert not dinero_en_juego("Transfer", None) and not dinero_en_juego(None, 10**6)


def test_prioridad_3_sin_pasar_delante_de_seguridad_ni_vulnerabilidad():
    assert prioridad([], [], False, None, "MX", HOY, dinero_en_juego=True) == 3
    assert prioridad([], [], False, None, "MX", HOY) == 4
    assert prioridad(["coaccion"], [], False, None, "MX", HOY, dinero_en_juego=True) == 1
    assert prioridad(["vulnerabilidad_declarada"], [], False, None, "MX", HOY, dinero_en_juego=True) == 2
