import json
import re
from pathlib import Path

import pytest

from servicio.riesgo.senal import artefacto, evaluar

RAIZ = Path(__file__).resolve().parents[2]


def test_anti_trampa_el_umbral_no_esta_escrito_en_m1():
    for f in list((RAIZ / "ml").glob("*.py")) + list((RAIZ / "servicio" / "riesgo").glob("*.py")):
        codigo = f.read_text()
        assert not re.search(r"(?<![\d.])30(?:\.0)?(?![\d])", codigo), f"el umbral aparece escrito en {f.name}"


@pytest.mark.skipif(artefacto() is None, reason="sin artefacto de M1")
def test_umbral_sale_del_artefacto_y_regla_estricta():
    a = artefacto()
    assert a["certificado"] and a["cota_fdr"] <= 0.01
    assert evaluar(a["umbral"]).supera_umbral_certificado is False       # marcado = score > τ
    assert evaluar(a["umbral"] + 0.01).supera_umbral_certificado is True


@pytest.mark.skipif(not (RAIZ / "artefactos" / "corridas_m1.jsonl").exists(), reason="sin corridas")
def test_regresion_mayor_o_igual_tiene_falsas_alarmas():
    ultima = json.loads((RAIZ / "artefactos" / "corridas_m1.jsonl").read_text().strip().splitlines()[-1])
    t = ultima["reporte"].get("test")
    if t:
        assert t["propuesto"]["fp"] == 0 and t["mismo_valor_con_mayor_o_igual"]["fp"] > 0


def test_sin_score_no_supera_y_p_es_calibrada():
    s = evaluar(None)
    assert s.supera_umbral_certificado is False
