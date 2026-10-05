"""Pruebas SEG que faltaban (SEGURIDAD §4-§5): SQL parametrizado, número de tarjeta fuera del modelo, acciones
reservadas por habilidad y ráfagas desde una IP."""
import re
import secrets
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from servicio.api import app as api
from servicio.llm.cliente import ModeloFalso
from servicio.orquestador.orquestador import Entrada, procesar
from tests.apoyo import Guion, admin

RAIZ = Path(__file__).resolve().parents[2]
# SQL armado con f-string: solo se permiten fragmentos constantes del propio código, nunca un dato de entrada.
PERMITIDOS = {"SET LOCAL ROLE {rol}", "{tipos}", "{consulta}"}


def test_seg7_sql_siempre_parametrizado():
    hallados = []
    for p in (RAIZ / "servicio").rglob("*.py"):
        for m in re.finditer(r'execute\(\s*f"""?(.*?)"""?\s*[,)]', p.read_text(), re.S):
            for hueco in re.findall(r"\{[^}]+\}", m.group(1)):
                if not any(hueco in x for x in PERMITIDOS):
                    hallados.append(f"{p.name}: {hueco}")
    assert not hallados, hallados


@pytest.mark.db
def test_seg11_el_numero_de_tarjeta_nunca_llega_al_modelo():
    m = ModeloFalso(Guion(["IDIOMA: es\nCOMANDO: aclarar"]))
    procesar("c_" + secrets.token_hex(5), Entrada(texto="mi tarjeta es 4539 1488 0343 6467, ¿está bien?"), None, m)
    assert all("6467" not in x["usuario"] and "4539" not in x["usuario"] for x in m.llamadas)


@pytest.mark.db
def test_seg6_asesor_general_no_desbloquea_tras_riesgo():
    cli = TestClient(api.app)
    tok = cli.post("/equipo/entrar", json={"employee_code": "E17183", "rol": "asesor"}).json()["token"]
    r = cli.post("/equipo/caso/tr_inexistente/desbloquear", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403
    with admin() as c:
        assert c.execute("select count(*) from operacion.eventos_seguridad where tipo = 'rol_negado'").fetchone()[0] >= 1


def test_seg9_rafaga_desde_una_ip_llega_al_limite():
    from fastapi import HTTPException
    from servicio.api.app import limite
    clave = "ip:prueba-" + secrets.token_hex(3)
    with pytest.raises(HTTPException):
        for _ in range(61):
            limite(clave, 60)
