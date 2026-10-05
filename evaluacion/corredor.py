"""Corredor de la evaluación (02_PLAN §8): casos canónicos contra el sistema, con el cliente guionizado o un personaje.

Por cada caso: prepara la base, conversa hasta el final (o 8 turnos), inyecta la falla del caso si la hay y le pasa
al evaluador lo que quedó en la base. Guarda cada corrida (con versiones y consumo) para el reporte y el modo
"paso a paso" de la vista en vivo. El conjunto final (2026-H1) no se corre hasta la corrida final (INV-EVAL).

Uso: python -m evaluacion.corredor --conjunto desarrollo [--casos A1,C1] [--modelo groq|puente] [--cliente guion|personaje]
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import time
from datetime import date, datetime, timezone
from pathlib import Path

import psycopg
import yaml

from evaluacion import metricas
from evaluacion.cliente import ClienteGuionizado, ClientePersonaje
from evaluacion.evaluador import ADMIN, evaluar, observar
from evaluacion.preparacion import preparar

RAIZ = Path(__file__).resolve().parents[1]
CORRIDAS = RAIZ / "evaluacion" / "corridas"
ESPERA_VENTANA_S = 70                # la ventana por minuto del proveedor, con margen


def _cargar_env():
    for linea in (RAIZ / ".env").read_text().splitlines():
        if "=" in linea and not linea.startswith("#"):
            k, v = linea.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def _token(documento: str, vencido: bool = False) -> str:
    from servicio.identidad.identidad import firmar, pedir_codigo, verificar_codigo
    with psycopg.connect(ADMIN, autocommit=True) as c:
        c.execute("delete from atencion.desafios_otp where ip = 'evaluacion'")
        cid = c.execute("select customer_id from atencion.identidades_demo where documento_demo = %s", (documento,)).fetchone()[0]
    if vencido:
        return firmar({"sub": cid, "sid": "s_vencida", "rol": "cliente", "exp": int(time.time()) - 60})
    d = pedir_codigo(documento, "evaluacion")
    with psycopg.connect(ADMIN) as c:
        codigo = c.execute("select mensaje from atencion.buzon_sandbox where customer_id = %s order by id desc limit 1", (cid,)).fetchone()[0]
    return verificar_codigo(d["desafio_id"], codigo, "evaluacion")["token"]


def _adjunto(conversation_id: str, customer_id: str, nombre: str) -> dict:
    tipo = "audio/ogg" if nombre.endswith(".ogg") else "image/jpeg"
    aid = "adj_" + secrets.token_hex(6)
    with psycopg.connect(ADMIN, autocommit=True) as c:
        c.execute("""insert into atencion.adjuntos (adjunto_id, customer_id, conversation_id, tipo, tamano, hash)
                     values (%s,%s,%s,%s,%s,'evaluacion')""", (aid, customer_id, conversation_id, tipo, 1000))
    return {"tipo": "adjunto", "adjunto_id": aid, "tipo_archivo": tipo, "tamano": 1000}


def _datos_del_cargo(datos: dict) -> dict:
    from evaluacion.cliente import monto_coloquial
    salida = {}
    if datos.get("transaction_id"):
        with psycopg.connect(ADMIN) as c:
            t = c.execute("select monto, moneda, comercio from servicio.transacciones where transaction_id = %s",
                          (datos["transaction_id"],)).fetchone()
        salida = {"monto_aprox": monto_coloquial(float(t[0]), t[1]), "monto_equivocado": monto_coloquial(float(t[0]), t[1], 0.8),
                  "comercio": t[2] or ""}
    if (datos.get("extra") or {}).get("comercio"):
        salida["comercio"] = datos["extra"]["comercio"]
    return salida


def caso_enumeracion(caso: dict) -> dict:
    """D4: anti-enumeración con el servicio de identidad real (no es una conversación)."""
    from servicio.identidad.identidad import pedir_codigo
    with psycopg.connect(ADMIN, autocommit=True) as c:
        c.execute("delete from atencion.desafios_otp where ip = 'enumeracion'")
    respuestas, tiempos = [], []
    for i in range(caso["evento"]["intentos"] + 2):
        t0 = time.monotonic()
        r = pedir_codigo(("DEMO-1001" if i % 2 else f"NO-EXISTE-{i}"), "enumeracion")
        tiempos.append(time.monotonic() - t0)
        respuestas.append(tuple(sorted((k, v) for k, v in r.items() if k != "desafio_id")))
    with psycopg.connect(ADMIN) as c:
        limite = c.execute("select count(*) from operacion.eventos_seguridad where tipo = 'limite_alcanzado' and ip = 'enumeracion'").fetchone()[0]
    identicas = len(set(respuestas)) == 1 and max(tiempos) - min(tiempos) < 0.2
    fallas = [] if identicas else ["respuesta distinta si el documento existe"]
    fallas += [] if limite else ["no se alcanzó el límite por IP"]
    return {"caso": caso["id"], "base": caso["id"], "idioma": caso["idioma"], "paso": not fallas, "fallas": fallas, "inseguro": [],
            "escalo": False, "debia_escalar": False, "automatizable": False, "resuelto_automatico_seguro": False,
            "herramientas": [], "nodo_final": None, "latencias_ms": [], "consumo": {"entrada": 0, "salida": 0, "llamadas": 0},
            "sin_modelo": False}


def correr_caso(caso: dict, datos: dict, conjunto: str, modelo, cliente_modo: str, simulador=None) -> tuple[dict, list[dict]]:
    from servicio.llm.cliente import ModeloQueFalla
    from servicio.orquestador.orquestador import Entrada, procesar
    if caso.get("evento", {}).get("tipo") == "enumeracion":
        return caso_enumeracion(caso), {"salidas": [], "registros": []}
    documento = f"EVAL-{caso['id']}-{conjunto[:3].upper()}"
    customer_id = datos["customer_id"]
    preparados = preparar(customer_id, caso["perfil"])
    reloj = date.fromisoformat(datos["reloj"])
    conv = f"eval_{caso['id']}_{secrets.token_hex(3)}"
    cliente = ClientePersonaje(caso, simulador, datos=_datos_del_cargo(datos)) if cliente_modo == "personaje" \
        else ClienteGuionizado(caso, datos=_datos_del_cargo(datos))
    token = None
    salidas: list[dict] = []
    fallas = {"timeout_escritura": "abrir_reclamo"} if caso.get("evento", {}).get("tipo") == "timeout_escritura" else {}
    salida = None
    pendientes: list[dict] = []
    while True:
        paso = pendientes.pop(0) if pendientes else cliente.siguiente(salida)
        if paso is None:
            break
        m = modelo
        if paso.get("identidad"):
            token = _token(documento)
            entrada = Entrada(evento={"tipo": "identidad_verificada"})
            if paso.get("luego"):
                luego = paso["luego"]
                if luego.get("evento", {}).get("ref") == "__objetivo__":
                    luego = {"evento": {**luego["evento"], "ref": datos["transaction_id"]}}
                if luego.get("adjunto"):
                    luego = {"evento": _adjunto(conv, customer_id, luego["adjunto"])}
                pendientes.append(luego)
        elif "evento" in paso:
            entrada = Entrada(evento=paso["evento"], mensaje_cliente_id="m_" + secrets.token_hex(4))
        else:
            entrada = Entrada(texto=paso["texto"], mensaje_cliente_id="m_" + secrets.token_hex(4))
        if paso.get("falla_modelo"):
            m = ModeloQueFalla(modelo)
        tok = _token(documento, vencido=True) if paso.get("sesion_vencida") else token
        s = procesar(conv, entrada, tok, m, reloj=reloj, fallas=fallas)
        salidas.append(s.__dict__)
        if paso.get("reenviar"):
            s2 = procesar(conv, entrada, tok, m, reloj=reloj, fallas=fallas)     # el mismo mensaje llega dos veces
            salidas.append({**s2.__dict__, "reenvio": True})
        salida = s.__dict__
    obs = observar(conv, customer_id, salidas)
    return evaluar(caso, obs, preparados), {"salidas": salidas, "registros": obs["registros"]}


def _cupo_del_dia_agotado() -> bool:
    """Todas las llaves del pool fuera por más de cinco minutos: el proveedor pidió esperar su límite largo (diario)."""
    from servicio.llm.pool import pool_del_sistema
    p = pool_del_sistema()
    return bool(p) and p.estado_formal() == "SATURADO" and all(k["enfriada_s"] > 300 for k in p.estado()["llaves"])


def _segmento(customer_id: str) -> str | None:
    with psycopg.connect(ADMIN) as c:
        f = c.execute("select segmento from servicio.clientes where customer_id = %s", (customer_id,)).fetchone()
    return f[0] if f else None


def _commit() -> str:
    import subprocess
    r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=RAIZ)
    sucio = subprocess.run(["git", "status", "--porcelain", "--", "servicio", "prompts", "politica", "contratos", "config"],
                           capture_output=True, text=True, cwd=RAIZ).stdout.strip()
    return r.stdout.strip() + ("+cambios" if sucio else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--conjunto", default="desarrollo", choices=["desarrollo", "final"])
    ap.add_argument("--casos", default="")
    ap.add_argument("--modelo", default="groq")
    ap.add_argument("--cliente", default="guion", choices=["guion", "personaje"])
    ap.add_argument("--sistema", default="propuesto", choices=["propuesto", "linea_base"])
    a = ap.parse_args()
    _cargar_env()
    os.environ.setdefault("REGISTRO_ORIGEN", "evaluacion")      # lo de la evaluación no cuenta como operación
    os.environ["MODELO_MODO"] = a.modelo
    os.environ.setdefault("CONOCIMIENTO_INCLUIR_PENDIENTES", "1")
    from servicio.llm.cliente import modelo_desde_entorno
    casos = yaml.safe_load((RAIZ / "evaluacion" / "ground_truth_cases.yaml").read_text())["casos"]
    manifest = json.loads((RAIZ / "evaluacion" / "manifest_casos.json").read_text())
    if a.casos:
        casos = [c for c in casos if c["id"] in a.casos.split(",")]
    modelo = modelo_desde_entorno("linea_base" if a.sistema == "linea_base" else "evaluacion")
    simulador = None
    if a.cliente == "personaje":
        os.environ["MODELO_MODO"] = "simulador"
        simulador = modelo_desde_entorno("simulador")
    if a.sistema == "linea_base":
        from evaluacion.linea_base import correr_caso_linea_base as correr
    else:
        correr = correr_caso
    # Las corridas con el puente (el asistente de desarrollo como modelo) prueban el código, no el modelo: van aparte
    # y el reporte, que solo lee la carpeta de corridas con modelo real, no las mezcla.
    destino = CORRIDAS / "puente" if a.modelo == "puente" else CORRIDAS
    destino.mkdir(parents=True, exist_ok=True)
    marca = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    archivo = destino / f"{marca}_{a.sistema}_{a.conjunto}.json"
    resultados, conversaciones = [], {}
    commit = _commit()                               # el código con que corrió: el reporte no mezcla versiones a ciegas
    from evaluacion.versiones import huella
    version = huella()                               # y la huella exacta de lo probado (prompts, catálogo, política, config, código)
    for caso in casos:
        t0 = time.time()
        for intento in range(4):             # un caso que quedó sin modelo por cupo se repite: no es una falla del sistema
            try:
                r, salidas = correr(caso, manifest["casos"][caso["id"]][a.conjunto], a.conjunto, modelo, a.cliente, simulador)
            except Exception as e:                   # un caso roto no detiene la corrida: queda como falla
                r, salidas = {"caso": caso["id"], "base": caso["id"], "idioma": caso["idioma"], "paso": False,
                              "fallas": [f"excepción: {type(e).__name__}: {e}"], "inseguro": [], "escalo": False,
                              "debia_escalar": bool(caso.get("must_escalate")), "automatizable": False,
                              "resuelto_automatico_seguro": False, "herramientas": [], "nodo_final": None, "latencias_ms": [],
                              "consumo": {"entrada": 0, "salida": 0, "llamadas": 0}, "sin_modelo": False}, {"salidas": [], "registros": []}
            por_cupo = r.get("sin_modelo") and caso.get("evento", {}).get("tipo") != "falla_modelo"
            if not por_cupo or _cupo_del_dia_agotado():
                break
            # Un límite por minuto se libera en una ventana completa del proveedor: se espera y se repite (sin contarlo).
            print(f"{caso['id']}: sin modelo por límite pasajero; espera {ESPERA_VENTANA_S} s y se repite sin contarlo", flush=True)
            time.sleep(ESPERA_VENTANA_S)
        if por_cupo:
            # Sin modelo por cupo (el diario o tras reintentar): no se cuenta; la corrida se detiene y dice desde dónde seguir
            pendientes = [c["id"] for c in casos[casos.index(caso):]]
            print(f"cupo agotado en {caso['id']}: se detiene sin contarlo. Retomar con --casos {','.join(pendientes)}", flush=True)
            break
        r["segmento"] = _segmento(manifest["casos"][caso["id"]][a.conjunto]["customer_id"])
        resultados.append(r)
        conversaciones[caso["id"]] = salidas
        print(f"{caso['id']:4} {'OK ' if r['paso'] else 'MAL'} {time.time() - t0:5.1f}s {r['fallas'] + r['inseguro']}", flush=True)
        archivo.write_text(json.dumps({"sistema": a.sistema, "conjunto": a.conjunto, "modelo": a.modelo, "cliente": a.cliente,
                                       "fecha": marca, "commit": commit, "versiones": version, "resultados": resultados, "conversaciones": conversaciones,
                                       "metricas": metricas.calcular(resultados)}, ensure_ascii=False, indent=1, default=str))
    m = metricas.calcular(resultados)
    print(json.dumps({k: m[k] for k in ("pasan", "resolucion_automatica_segura_sobre_elegibles", "escalada_correcta",
                                        "escalada_faltante", "escalada_innecesaria", "inseguros", "latencia_ms", "consumo")},
                     ensure_ascii=False, indent=1))
    print(f"corrida guardada en {archivo}" if archivo.exists() else "ningún caso terminó: no se guardó ninguna corrida")


if __name__ == "__main__":
    main()
