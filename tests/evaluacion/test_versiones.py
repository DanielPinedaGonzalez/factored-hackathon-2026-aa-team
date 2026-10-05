"""La huella del sistema y la sección de reproducibilidad del reporte (evaluacion/versiones.py, evaluacion/reporte.py)."""
import json

from evaluacion import reporte
from evaluacion.versiones import huella, que_cambio


def test_la_huella_es_estable_y_no_depende_de_cuando_se_calcula():
    a, b = huella(), huella()
    assert a["sistema"] == b["sistema"] and a["componentes"] == b["componentes"]


def test_la_huella_trae_modelos_y_temperaturas_de_su_unica_fuente():
    h = huella()
    assert set(h["modelos"]) == set(h["temperaturas"]) == {"interpretar", "redactar"}
    assert h["temperaturas"]["interpretar"] == 0.0


def test_que_cambio_nombra_el_componente():
    base = {"componentes": {"prompts": "a", "catalogo": "b", "politica": "c", "config": "d", "codigo": "e"}, "modelos": {"x": "m"}}
    assert que_cambio(base, base) == []
    assert que_cambio(base, {**base, "componentes": {**base["componentes"], "prompts": "z"}}) == ["prompts"]
    assert que_cambio(base, {**base, "modelos": {"x": "otro"}}) == ["modelos"]


def _corrida(carpeta, nombre, sistema, resultados, componentes=None):
    v = {"sistema": sistema, "componentes": componentes or {"prompts": sistema, "catalogo": "b", "politica": "c", "config": "d", "codigo": "e"},
         "modelos": {"interpretar": "m"}}
    (carpeta / nombre).write_text(json.dumps({"versiones": v, "resultados": [{"caso": c, "paso": p} for c, p in resultados.items()]}))
    return nombre


def test_el_reporte_separa_repeticiones_del_mismo_sistema_de_un_sistema_distinto(tmp_path, monkeypatch):
    monkeypatch.setattr(reporte, "CORRIDAS", tmp_path)
    nombres = [_corrida(tmp_path, "1.json", "s1", {"A1": True, "B1": False}),
               _corrida(tmp_path, "2.json", "s1", {"A1": True, "B1": True}),        # misma huella, B1 cambia: azar del modelo
               _corrida(tmp_path, "3.json", "s2", {"A1": True, "B1": True})]        # otra huella: cambió un prompt
    texto = "\n".join(reporte._reproducibilidad(nombres))
    assert "2 casos observados más de una vez" in texto              # A1 y B1 se vieron en las dos repeticiones
    assert "B1 1/2" in texto and "A1" not in texto.split("sin que el sistema cambie")[1]   # solo B1 cambió sin que el sistema cambiara
    assert "prompts" in texto                                        # y lo que cambió entre s1 y s2


def test_sin_huella_el_reporte_no_finge_que_separo_el_azar(tmp_path, monkeypatch):
    monkeypatch.setattr(reporte, "CORRIDAS", tmp_path)
    (tmp_path / "v.json").write_text(json.dumps({"resultados": [{"caso": "A1", "paso": True}]}))
    texto = "\n".join(reporte._reproducibilidad(["v.json"]))
    assert "sin registrar" in texto and "Todavía no hay dos corridas con el mismo sistema" in texto


def test_el_reporte_avisa_cuando_el_sistema_actual_no_es_el_que_se_midio(tmp_path, monkeypatch):
    monkeypatch.setattr(reporte, "CORRIDAS", tmp_path)
    ahora = huella()
    _corrida(tmp_path, "igual.json", ahora["sistema"], {"A1": True}, componentes=ahora["componentes"])
    _corrida(tmp_path, "otro.json", "viejo", {"A1": True}, componentes={**ahora["componentes"], "prompts": "otro"})
    assert "es el que se midió" not in "\n".join(reporte._aviso_de_version(["igual.json"]))
    assert "Sistema medido = sistema actual" in "\n".join(reporte._aviso_de_version(["igual.json"]))
    aviso = "\n".join(reporte._aviso_de_version(["otro.json"]))
    assert "no es exactamente el que se midió" in aviso and "prompts" in aviso
    (tmp_path / "sin.json").write_text(json.dumps({"resultados": []}))
    assert "no dicen con qué versión" in "\n".join(reporte._aviso_de_version(["sin.json"]))
