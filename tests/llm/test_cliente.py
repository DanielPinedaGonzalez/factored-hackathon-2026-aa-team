"""Cliente del proveedor: una respuesta cortada por el límite de tokens es una falla, y los modelos que razonan reciben
presupuesto para razonar y responder (también el respaldo de OpenRouter)."""
import pytest

from servicio.llm import cliente as modulo
from servicio.llm.cliente import ProveedorOpenAI, RespuestaCortada


class _Resp:
    status_code, headers = 200, {}

    def __init__(self, finish):
        self._finish = finish

    def json(self):
        return {"choices": [{"message": {"content": "TEXTO: a las {HORA"}, "finish_reason": self._finish}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 900}}


def _llamar(monkeypatch, proveedor, modelo, finish="stop"):
    cuerpos = []
    monkeypatch.setattr(modulo.httpx, "post", lambda url, json, timeout, headers: cuerpos.append(json) or _Resp(finish))
    ProveedorOpenAI(proveedor, modelo, "llave-falsa").completar("s", "u", "redactar")
    return cuerpos[0]


def test_respuesta_cortada_por_el_limite_es_una_falla(monkeypatch):
    with pytest.raises(RespuestaCortada, match="cortada"):
        _llamar(monkeypatch, "groq", "openai/gpt-oss-120b", finish="length")


def test_el_respaldo_que_razona_recibe_presupuesto_de_razonamiento(monkeypatch):
    cuerpo = _llamar(monkeypatch, "openrouter", "nvidia/nemotron-3-super-120b-a12b:free")
    assert cuerpo["max_tokens"] >= 1200 and cuerpo["reasoning"]["effort"] == "low"
    cuerpo = _llamar(monkeypatch, "groq", "openai/gpt-oss-120b")
    assert cuerpo["max_tokens"] >= 1200 and cuerpo["reasoning_effort"] == "low"
