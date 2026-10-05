"""Pool de llaves (A12): LRU, enfriamiento por fallo, paso a la siguiente llave, SATURADO y un guardián por llave."""
import pytest

from servicio.llm import pool as modulo
from servicio.llm.cliente import ModeloNoDisponible, RespuestaCortada, RespuestaModelo


class _Falso:
    """Reemplaza al proveedor: responde o falla según la llave, y anota qué llave usó."""
    usadas: list[str] = []
    fallan: set[str] = set()
    cortan: set[str] = set()

    def __init__(self, proveedor, modelo, llave, guardian, temperatura=0.2, cero_retencion=True):
        self.llave, self.modelo, self.guardian = llave, modelo, guardian

    def completar(self, sistema, usuario, proposito, max_tokens=900):
        _Falso.usadas.append(self.llave)
        if self.llave in _Falso.fallan:
            raise ModeloNoDisponible("429")
        if self.llave in _Falso.cortan:
            raise RespuestaCortada("respuesta cortada por el límite de tokens")
        return RespuestaModelo("ok", "groq", self.modelo, proposito=proposito)


@pytest.fixture(autouse=True)
def _proveedor_falso(monkeypatch):
    monkeypatch.setattr(modulo, "ProveedorOpenAI", _Falso)
    _Falso.usadas, _Falso.fallan, _Falso.cortan = [], set(), set()


def _pool(n=3):
    return modulo.PoolLlaves("groq", [f"llave-{i}" for i in range(1, n + 1)], {"interpretar": "m1", "redactar": "m2"}, "m1",
                             nombres=[f"GROQ_API_KEY_{i}" for i in range(1, n + 1)])


def test_lru_reparte_y_un_guardian_por_llave_para_todos_los_componentes():
    p = _pool()
    for proposito in ("interpretar", "redactar", "interpretar"):
        p.completar("s", "u", proposito)
    assert _Falso.usadas == ["llave-1", "llave-2", "llave-3"]
    k = p._llaves[0]
    assert len({id(x.guardian) for x in k.proveedores.values()}) == 1 and p.estado_formal() == "NOMINAL"


def test_una_llave_con_429_se_enfria_y_la_llamada_pasa_a_la_siguiente():
    p = _pool()
    _Falso.fallan = {"llave-1"}
    r = p.completar("s", "u", "interpretar")
    assert r.llave == 2 and p.estado_formal() == "DEGRADADO"
    publico = p.estado()["llaves"][0]
    assert publico["disponible"] is False and publico["llave"] == "GROQ_API_KEY_1" and publico["fallos"] == 1
    assert "llave-1" not in str(p.estado())           # de la llave sale su nombre, ni un fragmento del valor


def test_todas_enfriadas_es_saturado_y_falla_de_inmediato():
    p = _pool(2)
    _Falso.fallan = {"llave-1", "llave-2"}
    with pytest.raises(ModeloNoDisponible, match="SATURADO"):
        p.completar("s", "u", "redactar")
    assert p.estado_formal() == "SATURADO"


def test_nadie_espera_si_ninguna_llave_puede_atender_falla_en_milisegundos():
    """Diseño del pool de origen: todas en enfriamiento → no disponible de inmediato, sin espera."""
    import time as t
    p = modulo.PoolLlaves("groq", ["llave-1", "llave-2"], {"interpretar": "m1"}, "m1")
    for k in p._llaves:
        k.enfriada_hasta = t.monotonic() + 30
    t0 = t.monotonic()
    with pytest.raises(ModeloNoDisponible, match="SATURADO"):
        p.completar("s", "u", "interpretar")
    assert t.monotonic() - t0 < 0.5


def test_el_pool_no_golpea_una_llave_que_el_proveedor_saco_aunque_el_proceso_se_reinicie():
    p = _pool(2)
    p.cargar_enfriamientos({1: 600})
    assert p.completar("s", "u", "interpretar").llave == 2 and p.estado()["llaves"][0]["enfriada_s"] > 500


def test_la_cadena_rota_groq_y_si_todas_caen_responde_openrouter():
    """Orden de proveedores de la demo: primero las llaves de Groq; con todas caídas, OpenRouter."""
    groq = modulo.PoolLlaves("groq", ["llave-1", "llave-2"], {"interpretar": "m1"}, "m1", espera_saturado_s=0)
    orouter = modulo.PoolLlaves("openrouter", ["or-1"], {}, "m-or", cero_retencion=False)
    cadena = modulo.CadenaProveedores([groq, orouter])
    assert cadena.completar("s", "u", "interpretar").llave in (1, 2) and cadena.estado_formal() == "NOMINAL"
    _Falso.fallan = {"llave-1", "llave-2"}
    r = cadena.completar("s", "u", "interpretar")
    assert r.modelo == "m-or" and cadena.estado_formal() == "DEGRADADO"
    assert [k["proveedor"] for k in cadena.estado()["llaves"]] == ["groq", "groq", "openrouter"]
    _Falso.fallan = {"llave-1", "llave-2", "or-1"}
    with pytest.raises(ModeloNoDisponible, match="TODOS LOS PROVEEDORES"):
        cadena.completar("s", "u", "interpretar")


def test_una_respuesta_cortada_pasa_al_siguiente_proveedor_sin_enfriar_la_llave():
    """El texto incompleto no se usa; la llave está sana y el mismo modelo en otra llave cortaría igual."""
    groq = modulo.PoolLlaves("groq", ["llave-1", "llave-2"], {"redactar": "m1"}, "m1", espera_saturado_s=0)
    orouter = modulo.PoolLlaves("openrouter", ["or-1"], {}, "m-or", cero_retencion=False)
    _Falso.cortan = {"llave-1", "llave-2"}
    r = modulo.CadenaProveedores([groq, orouter]).completar("s", "u", "redactar")
    assert r.modelo == "m-or" and len([u for u in _Falso.usadas if u.startswith("llave-")]) == 1
    assert all(k["enfriada_s"] == 0 for k in groq.estado()["llaves"])


@pytest.mark.db          # necesita los datos de demo cargados (servicio.datos_version), que no se publican
def test_sin_llaves_en_el_entorno_no_revienta_y_la_conversacion_pasa_a_una_persona(monkeypatch):
    """La API arrancada sin el archivo de llaves: cada llamada falla con su razón real (no un error 500), la
    conversación sigue el camino sin modelo y la cabina lo ve como SIN_LLAVES."""
    import os
    import secrets
    import pytest
    from servicio.llm.cliente import ModeloNoDisponible, modelo_desde_entorno
    from servicio.llm.pool import pool_del_sistema
    for k in list(os.environ):
        if k.startswith(("GROQ_API_KEY", "OPENROUTER_API_KEY")):
            monkeypatch.delenv(k)
    monkeypatch.setenv("MODELO_MODO", "groq")
    m = modelo_desde_entorno("sistema")
    assert pool_del_sistema().estado()["estado"] == "SIN_LLAVES"
    with pytest.raises(ModeloNoDisponible, match="SIN LLAVES"):
        m.completar("s", "u", "interpretar")
    from servicio.orquestador.orquestador import Entrada, procesar
    s = procesar("c_" + secrets.token_hex(6), Entrada(texto="no reconozco un cargo"), None, m)
    assert s.sin_modelo and any(u["tipo"] == "aviso_espera" for u in s.ui)


def test_un_valor_de_relleno_no_cuenta_como_llave(monkeypatch):
    """5-oct: la variable de la llave de pago se dejó con «.» en el despliegue y la cabina la contaba como una llave que falla (401)."""
    from servicio.llm.pool import llaves_del_entorno
    monkeypatch.setenv("GROQ_API_KEY", "gsk_" + "a" * 40)
    monkeypatch.setenv("GROQ_API_KEY_2", ".")
    assert [n for n, _ in llaves_del_entorno()] == ["GROQ_API_KEY"]

