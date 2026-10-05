"""GOBERNANZA §11.6: la huella de cada fuente se guarda; si cambia, sus artículos quedan marcados y uno de criticidad
alta deja de servirse hasta la revisión. Una fuente que no responde no cuenta como cambiada."""
from datetime import date

import yaml

import scripts.vigilar_fuentes as v
from servicio.conocimiento import conocimiento as k


def test_una_fuente_cambiada_saca_de_servicio_a_sus_articulos_de_criticidad_alta(tmp_path, monkeypatch):
    monkeypatch.setattr(v, "HUELLAS", tmp_path / "huellas.json")
    monkeypatch.setattr(v, "CAMBIADAS", tmp_path / "cambiadas.json")
    monkeypatch.setattr(k, "FUENTES_CAMBIADAS", tmp_path / "cambiadas.json")
    monkeypatch.setenv("CONOCIMIENTO_INCLUIR_PENDIENTES", "1")
    refs = {r["clave"]: r["url"] for r in yaml.safe_load(v.REGISTRO.read_text()) if r.get("url")}
    citan = v.articulos_por_fuente()
    arts = {a["cabecera"]["id"]: a["cabecera"] for a in k.articulos_en_disco()}
    clave, art = next((c, a) for c, ids in citan.items() if c in refs for a in ids if arts[a]["criticidad"] == "alta")
    contenido = {u: f"<html><body><p>Texto de {c}</p><script>x()</script></body></html>" for c, u in refs.items()}
    caida = next(u for c, u in refs.items() if c != clave)

    def descarga(url):
        if url == caida:
            raise TimeoutError("sin respuesta")
        return contenido[url]
    primera = v.vigilar(descarga)
    assert not primera["cambiadas_nuevas"] and primera["sin_respuesta"][0]["razon"].startswith("TimeoutError")
    assert k.vigente(arts[art], date(2026, 6, 18))
    contenido[refs[clave]] = contenido[refs[clave]].replace("Texto", "Texto nuevo")
    contenido[refs[next(iter(refs))]] += "<div class='otro-diseño'></div>"      # solo diseño: no es un cambio
    segunda = v.vigilar(descarga)
    assert segunda["cambiadas_nuevas"] == [clave]
    assert art in __import__("json").loads((tmp_path / "cambiadas.json").read_text())[clave]["articulos"]
    assert not k.vigente(arts[art], date(2026, 6, 18))
    v.revisado(clave)
    assert k.vigente(arts[art], date(2026, 6, 18)) and not v.vigilar(descarga)["cambiadas_nuevas"]
