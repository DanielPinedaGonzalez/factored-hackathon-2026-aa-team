"""Puente de archivos: corre una conversación real (orquestador + base) con el asistente de desarrollo como modelo.

Adaptado de un sistema propio del autor. No gasta cupo. Prueba que el código haga lo correcto dada una salida bien
formada y que los prompts lleven lo que deben; no prueba si un modelo real sigue las reglas (eso es la corrida con
llaves, espaciada).

Uso: python scripts/dev/puente_conversacion.py --carpeta DIR --documento DEMO-1001 --turnos turnos.json
     turnos.json: ["texto", {"evento": {...}}, "identidad"]   ("identidad" = verificar la identidad del documento)
El script escribe DIR/prompt_NNN.txt y espera DIR/respuesta_NNN.txt; al final escribe DIR/conversacion.json y DIR/FIN.
"""
import argparse
import json
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from servicio.llm.cliente import PuenteArchivos  # noqa: E402
from servicio.orquestador.orquestador import Entrada, procesar  # noqa: E402
from tests.apoyo import limpiar_cliente, token_de  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--carpeta", required=True)
ap.add_argument("--documento", default=None)
ap.add_argument("--turnos", required=True)
a = ap.parse_args()
carpeta = Path(a.carpeta)
modelo = PuenteArchivos(carpeta)
token = None
cid = None
if a.documento:
    _, cid = token_de(a.documento)
    limpiar_cliente(cid)
conv = "puente_" + secrets.token_hex(4)
salida = []
for t in json.loads(Path(a.turnos).read_text()):
    if t == "identidad":
        token, _ = token_de(a.documento)
        entrada = Entrada(evento={"tipo": "identidad_verificada"})
    elif isinstance(t, dict):
        entrada = Entrada(evento=t["evento"])
    else:
        entrada = Entrada(texto=t)
    s = procesar(conv, entrada, token, modelo)
    salida.append({"entrada": t, "nodo": s.nodo, "texto": s.texto, "ui": s.ui, "sin_modelo": s.sin_modelo, "traspaso": s.traspaso})
    (carpeta / "conversacion.json").write_text(json.dumps(salida, ensure_ascii=False, indent=1, default=str))
(carpeta / "FIN").write_text(conv)
