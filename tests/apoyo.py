"""Apoyos de prueba: un redactor falso que cumple el contrato con cualquier estado comunicable y guiones del Intérprete."""
import json
import re

import psycopg

from servicio.datos.db import URL_ADMIN as ADMIN


def redactor_falso(usuario: str, idioma: str = "es") -> str:
    ec = json.loads(usuario.split("ESTADO COMUNICABLE:\n", 1)[1])
    exactos = [m for e in ec if e["clase"] == "EXACTO" for m in e["marcadores"]]
    acciones = sorted({e["accion"] for e in ec if e["clase"] == "RESULTADO"})
    responder = next((e for e in ec if e["clase"] == "RESPONDER"), None)
    cuerpo = "Te cuento lo que encontré y lo que sigue en tu caso. " if idioma == "es" else "Vou te contar o que encontrei e o que segue. "
    cuerpo += " ".join(exactos)
    return (f"IDIOMA: {idioma}\nACCIONES_AFIRMADAS: {', '.join(acciones) or 'ninguna'}\n"
            f"CITA: {responder['articulo'] if responder else 'ninguna'}\n"
            f"SUFICIENCIA: {'completa' if responder else 'no_aplica'}\nRESUMEN_HUMANO: caso de prueba\n"
            + ("SALUDO: Saludo de prueba.\n" if "MOMENTO DEL DÍA DEL CLIENTE:" in usuario else "")
            + f"TEXTO: {cuerpo}")


class Guion:
    """El Intérprete responde en orden los textos dados; el Redactor siempre con `redactor_falso`. El Comparador, con
    `comparar(opciones: dict alias→descripción) -> str`; por defecto dice que todas las opciones corresponden."""

    def __init__(self, interpretaciones: list[str], idioma: str = "es", comparar=None):
        self.interpretaciones = list(interpretaciones)
        self.idioma = idioma
        self.comparar = comparar or (lambda opciones: "COINCIDEN: " + ", ".join(opciones))

    def __call__(self, sistema, usuario, proposito):
        if proposito == "interpretar":
            return self.interpretaciones.pop(0)
        if proposito == "comparar":
            bloque = usuario.split("<<<OPCIONES\n", 1)[1].split("\nOPCIONES>>>", 1)[0]
            return self.comparar(dict(l.split(": ", 1) for l in bloque.splitlines()))
        return redactor_falso(usuario, self.idioma)


def admin():
    return psycopg.connect(ADMIN, autocommit=True)


def limpiar_cliente(customer_id: str):
    """Deja al cliente sin reclamos, bloqueos ni conversaciones previas (solo para pruebas locales)."""
    with admin() as c:
        for t in ["reclamo_eventos", "reclamo_notas"]:
            c.execute(f"delete from atencion.{t} where customer_id = %s", (customer_id,))
        c.execute("delete from atencion.reclamos where customer_id = %s", (customer_id,))
        c.execute("delete from atencion.bloqueo_eventos where customer_id = %s", (customer_id,))
        c.execute("delete from atencion.bloqueos where customer_id = %s", (customer_id,))


def token_de(documento: str) -> tuple[str, str]:
    from servicio.identidad.identidad import pedir_codigo, verificar_codigo
    with admin() as c:
        c.execute("delete from atencion.desafios_otp where ip = '127.0.0.1'")     # solo los de las pruebas
        cid = c.execute("select customer_id from atencion.identidades_demo where documento_demo = %s", (documento,)).fetchone()[0]
    d = pedir_codigo(documento, "127.0.0.1")
    with admin() as c:
        codigo = c.execute("select mensaje from atencion.buzon_sandbox where customer_id = %s order by id desc limit 1", (cid,)).fetchone()[0]
    return verificar_codigo(d["desafio_id"], codigo, "127.0.0.1")["token"], cid
