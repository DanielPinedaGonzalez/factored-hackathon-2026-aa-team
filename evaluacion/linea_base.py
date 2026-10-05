"""Línea base justa (02_PLAN §8): misma identidad, misma RLS, mismas herramientas, mismos datos, mismo modelo.
Única diferencia: la política va solo en el prompt y no existe el motor determinista; el modelo decide la acción y el
código la ejecuta tal cual (con la RLS de la base, que sigue aplicando). Solo para evaluación.
"""
from __future__ import annotations

import json
import secrets
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import psycopg
import yaml

from evaluacion.cliente import ClienteGuionizado
from evaluacion.evaluador import ADMIN, evaluar, observar
from evaluacion.preparacion import preparar
from servicio.datos.db import transaccion
from servicio.enrutador import enrutador
from servicio.herramientas import banco
from servicio.herramientas.banco import ErrorHerramienta
from servicio.llm.cliente import ModeloNoDisponible
from servicio.redactor import formato

RAIZ = Path(__file__).resolve().parents[1]


def _prompt() -> str:
    comun = yaml.safe_load((RAIZ / "politica" / "comun.yaml").read_text())
    pais = {p: yaml.safe_load((RAIZ / "politica" / f"{p}.yaml").read_text()) for p in ("mx", "co", "ar")}
    return (RAIZ / "prompts" / "linea_base.md").read_text(encoding="utf-8").format(
        umbral=pais["mx"]["umbral_monto_usd"], tope=comun["tope_reclamos_90_dias"], mx=pais["mx"]["ventana_investigacion_dias"],
        co=pais["co"]["ventana_investigacion_dias"], ar=pais["ar"]["ventana_investigacion_dias"])


class AgenteLineaBase:
    def __init__(self, modelo, customer_id: str, reloj: date, conv: str):
        self.modelo, self.customer_id, self.reloj, self.conv = modelo, customer_id, reloj, conv
        self.identidad = False
        self.historial: list[str] = []
        self.n = 0
        self.cargos: dict[str, dict] = {}
        self.productos: dict[str, dict] = {}

    def _contexto(self, c) -> str:
        if not self.identidad:
            return "IDENTIDAD: no verificada\nCARGOS: (sin identidad)\nPRODUCTOS: (sin identidad)\nRECLAMOS: (sin identidad)"
        txs = banco.listar_transacciones(c, self.reloj - timedelta(days=45), self.reloj)[:25]
        self.cargos = {f"T{i}": t for i, t in enumerate(txs, 1)}
        self.productos = {f"P{i}": p for i, p in enumerate(banco.listar_productos(c), 1)}
        cargos = "\n".join(f"{a}: {formato.fecha(t['fecha'], 'es')} {t['hora']} · {' · '.join(x for x in (formato.movimiento(t['tipo'], 'es'), t['comercio']) if x)} · "
                           f"{formato.monto(t['monto'], t['moneda'])} · {t['ciudad']} · {t['estado']} · USD {t['amount_usd']}"
                           for a, t in self.cargos.items())
        prods = "\n".join(f"{a}: {p['tipo']} •••• {p['ultimos4']} · {'bloqueado' if p['bloqueo_id'] else p['estado']}"
                          for a, p in self.productos.items())
        recl = "\n".join(f"{r['numero']}: {r['estado']}" for r in banco.listar_reclamos(c)) or "ninguno"
        return f"IDENTIDAD: verificada\nCARGOS:\n{cargos}\nPRODUCTOS:\n{prods}\nRECLAMOS:\n{recl}"

    def turno(self, mensaje: str) -> dict:
        t0 = time.monotonic()
        self.n += 1
        self.historial.append(f"CLIENTE: {mensaje}")
        pasos, ui, traspaso = [], [], None
        with transaccion("app_ejecucion", customer_id=self.customer_id if self.identidad else None, conversation_id=self.conv) as c:
            if self.n == 1:
                c.execute("insert into atencion.conversaciones (conversation_id, customer_id, reloj) values (%s,%s,%s) on conflict do nothing",
                          (self.conv, self.customer_id if self.identidad else None, self.reloj))
            usuario = f"{self._contexto(c)}\n\nCONVERSACIÓN:\n" + "\n".join(self.historial[-10:]) + f"\n\nMENSAJE: {mensaje}"
            try:
                r = self.modelo.completar(_prompt(), usuario, "interpretar")
                tokens = {"entrada": r.tokens_entrada, "salida": r.tokens_salida, "llamadas": 1}
            except ModeloNoDisponible:
                return {"nodo": "N11", "texto": "", "ui": [{"tipo": "aviso_espera"}], "sin_modelo": True}
            accion, texto, resto = "responder", "", []
            from servicio.llm.formato_salida import normalizar
            lineas = normalizar(r.texto).splitlines()
            for i, linea in enumerate(lineas):
                if linea.upper().startswith("ACCION:"):
                    accion = linea.split(":", 1)[1].strip()
                elif linea.upper().startswith("TEXTO:"):
                    texto = "\n".join([linea.split(":", 1)[1].strip()] + lineas[i + 1:]).strip()
                    break
                else:
                    resto.append(linea)
            texto = texto or "\n".join(resto).strip()          # lector tolerante: la línea base no pierde su texto
            partes = accion.split()
            verbo = partes[0].lower() if partes else "responder"
            nodo = "N2"
            try:
                if verbo == "pedir_identidad":
                    ui.append({"tipo": "formulario_identidad"}); nodo = "N1"
                elif verbo == "mostrar_cargo" and len(partes) > 1 and partes[1] in self.cargos:
                    t = self.cargos[partes[1]]
                    ui.append({"tipo": "tarjeta_cargo", "alias": partes[1], "movimiento": formato.movimiento(t["tipo"], "es"), "comercio": t["comercio"], "monto": formato.monto(t["monto"], t["moneda"]),
                               "fecha": formato.fecha(t["fecha"], "es"), "hora": t["hora"], "ciudad": t["ciudad"], "producto": t["tipo_producto"]})
                    nodo = "N5"
                elif verbo == "opciones" and len(partes) > 1:
                    ops = [{"alias": a.strip()} for a in " ".join(partes[1:]).replace(" ", ",").split(",") if a.strip() in self.cargos]
                    if ops:
                        ui.append({"tipo": "opciones", "opciones": ops}); nodo = "N4"
                elif verbo in ("proponer_reclamo", "proponer_bloqueo"):
                    ui.append({"tipo": "confirmacion", "action_intent_id": "lb", "accion": verbo}); nodo = "N7"
                elif verbo == "abrir_reclamo" and len(partes) > 1 and partes[1] in self.cargos:
                    t = self.cargos[partes[1]]
                    rec = banco.abrir_reclamo(c, self.customer_id, t["transaction_id"], partes[2] if len(partes) > 2 else "no_autorizada",
                                              "lb_" + secrets.token_hex(6), self.conv, None)
                    pasos.append({"componente": "herramienta", "estado": "ok", "detalle": {"herramienta": "abrir_reclamo"}})
                    ui.append({"tipo": "estado_caso", "numero": rec["numero"]}); nodo = "N10"
                elif verbo in ("bloquear", "desbloquear") and len(partes) > 1 and partes[1] in self.productos:
                    p = self.productos[partes[1]]
                    if verbo == "bloquear":
                        banco.bloquear_producto(c, self.customer_id, p["product_id"], "cliente", None, "lb_" + secrets.token_hex(6))
                        pasos.append({"componente": "herramienta", "estado": "ok", "detalle": {"herramienta": "bloquear_producto"}})
                    else:
                        c.execute("update atencion.bloqueos set estado = 'activo' where product_id = %s and estado = 'bloqueado_temporal'",
                                  (p["product_id"],))      # sin motor: el modelo decide y el código ejecuta
                        pasos.append({"componente": "herramienta", "estado": "ok", "detalle": {"herramienta": "desbloquear_producto"}})
                    nodo = "N10"
                elif verbo == "traspaso":
                    hab = partes[1] if len(partes) > 1 and partes[1] in ("fraude", "reclamos", "general") else "general"
                    pri = int(partes[2]) if len(partes) > 2 and partes[2].isdigit() and 1 <= int(partes[2]) <= 4 else 4
                    fila = enrutador.crear_traspaso(c, {"motivo_traspaso": ["linea_base"], "habilidad_requerida": hab, "prioridad": pri,
                                                         "idioma": "es", "conversation_id": self.conv, "identidad_verificada": self.identidad},
                                                    self.conv, self.customer_id if self.identidad else None, None)
                    traspaso = {"habilidad": hab, "prioridad": pri, "numero": fila["numero"]}
                    ui.append({"tipo": "aviso_espera", "numero": fila["numero"]}); nodo = "N11"
                elif verbo == "consultar_reclamos":
                    pasos.append({"componente": "herramienta", "estado": "ok", "detalle": {"herramienta": "listar_reclamos"}})
            except ErrorHerramienta as e:
                pasos.append({"componente": "herramienta", "estado": "fallo", "detalle": {"error": e.codigo}})
            self.historial.append(f"ASISTENTE: {texto}")
            registro = {"turn_id": f"lb_{secrets.token_hex(4)}", "conversation_id": self.conv, "n": self.n, "pasos": pasos,
                        "tokens": tokens, "latencia_ms": round((time.monotonic() - t0) * 1000, 1), "senales": [],
                        "nodo_despues": nodo, "accion": accion}
            c.execute("insert into operacion.registro_turnos (turn_id, conversation_id, customer_id, n, registro) values (%s,%s,%s,%s,%s)",
                      (registro["turn_id"], self.conv, self.customer_id if self.identidad else None, self.n, json.dumps(registro)))
        return {"nodo": nodo, "texto": texto, "ui": ui, "sin_modelo": False, "traspaso": traspaso}


def _a_texto(paso: dict) -> str:
    ev = paso.get("evento", {})
    if ev.get("tipo") == "reconoce":
        return {"si": "sí, lo reconozco", "no": "no, no lo reconozco", "no_seguro": "no estoy seguro"}[ev["valor"]]
    if ev.get("tipo") == "confirmar":
        return "sí, hazlo"
    if ev.get("tipo") == "negar":
        return "no"
    if ev.get("tipo") == "elegir":
        return f"el {ev['alias']}"
    if ev.get("tipo") == "no_reconozco":
        return "no reconozco el cargo de ayer"
    if ev.get("tipo") == "adjunto":
        return "[adjunto]"
    return paso.get("texto", "")


def _respuestas_de_texto(caso: dict) -> list[str]:
    """Lo que contestaría el mismo cliente si el asistente le pregunta con texto en lugar de mostrar botones."""
    if caso["id"] == "A3":
        return ["sí, ya lo reconozco, era mío"]
    if caso.get("must_escalate"):
        return ["sí, por favor", "sí"]
    if "abrir_reclamo" in caso.get("expected_tool_calls", []) or "agregar_informacion_reclamo" in caso.get("expected_tool_calls", []):
        return ["sí, es ese cargo y no lo reconozco", "sí, ábrelo por favor", "sí"]
    return ["sí", "gracias"]


def correr_caso_linea_base(caso: dict, datos: dict, conjunto: str, modelo, cliente_modo: str, simulador=None):
    if caso.get("evento", {}).get("tipo") == "enumeracion":
        from evaluacion.corredor import caso_enumeracion
        return caso_enumeracion(caso), {"salidas": [], "registros": []}
    customer_id = datos["customer_id"]
    preparados = preparar(customer_id, caso["perfil"])
    conv = f"lb_{caso['id']}_{secrets.token_hex(3)}"
    from evaluacion.corredor import _datos_del_cargo
    agente = AgenteLineaBase(modelo, customer_id, date.fromisoformat(datos["reloj"]), conv)
    cliente = ClienteGuionizado(caso, datos=_datos_del_cargo(datos))
    salidas, salida, pendientes = [], None, []
    respuestas = list(_respuestas_de_texto(caso))
    while True:
        paso = pendientes.pop(0) if pendientes else cliente.siguiente(salida)
        if paso is None and salida is not None and not salida.get("ui") and salida.get("nodo") not in ("N10", "N11") and len(salidas) < 8:
            if not agente.identidad and caso["sesion"] == "con_identidad":
                paso = {"identidad": True}          # pidió la identidad con texto: el cliente se identifica igual
            elif respuestas:
                paso = {"texto": respuestas.pop(0)}  # pregunta solo con texto: el cliente contesta con texto
        if paso is None:
            break
        if paso.get("identidad"):
            agente.identidad = True
            if paso.get("luego"):
                pendientes.append(paso["luego"])
            mensaje = "ya me identifiqué"
        else:
            mensaje = _a_texto(paso)
        s = agente.turno(mensaje)
        salidas.append(s)
        salida = s
    obs = observar(conv, customer_id, salidas)
    return evaluar(caso, obs, preparados, "linea_base"), {"salidas": salidas, "registros": obs["registros"]}
