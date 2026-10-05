"""Modo "personajes" de la vista en vivo (solo local y para el video): un personaje conversa solo con el sistema.

Corre en un hilo; la vista pregunta por el avance. El personaje lo mueve un modelo de otra familia (E1) con la meta de
un caso canónico; nunca ve la verdad de referencia.
"""
from __future__ import annotations

import secrets
import threading
from datetime import date

from evaluacion.cliente import ClientePersonaje

CORRIDAS: dict[str, dict] = {}


def iniciar(caso: dict, datos: dict, modelo_sistema, simulador, documento: str) -> str:
    cid = f"pers_{caso['id']}_{secrets.token_hex(3)}"
    CORRIDAS[cid] = {"caso": caso["id"], "personaje": caso["personaje"], "turnos": [], "fin": False, "error": None}
    threading.Thread(target=_correr, args=(cid, caso, datos, modelo_sistema, simulador, documento), daemon=True).start()
    return cid


def _correr(cid: str, caso: dict, datos: dict, modelo, simulador, documento: str):
    from evaluacion.corredor import _datos_del_cargo, _token
    from evaluacion.preparacion import preparar
    from servicio.orquestador.orquestador import Entrada, procesar
    try:
        preparar(datos["customer_id"], caso["perfil"])
        cliente = ClientePersonaje(caso, simulador, datos=_datos_del_cargo(datos))
        token, salida = None, None
        while True:
            paso = cliente.siguiente(salida)
            if paso is None:
                break
            if paso.get("identidad"):
                token = _token(documento)
                entrada, visto = Entrada(evento={"tipo": "identidad_verificada"}), "(se identifica en el formulario)"
            elif "evento" in paso:
                entrada, visto = Entrada(evento=paso["evento"]), f"(pulsa: {paso['evento']['tipo']})"
            else:
                entrada, visto = Entrada(texto=paso["texto"]), paso["texto"]
            s = procesar(cid, entrada, token, modelo, reloj=date.fromisoformat(datos["reloj"]))
            CORRIDAS[cid]["turnos"].append({"cliente": visto, "asistente": s.texto, "ui": s.ui, "nodo": s.nodo})
            salida = s.__dict__
    except Exception as e:                      # la vista muestra el error; nunca inventa un turno
        CORRIDAS[cid]["error"] = f"{type(e).__name__}: {e}"
    CORRIDAS[cid]["fin"] = True
