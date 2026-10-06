"""Atención humana de punta a punta por la API: traspaso → asignación → respuesta → transferencia con nota → cierre."""
import pytest
from fastapi.testclient import TestClient

from servicio.api import app as api
from servicio.llm.cliente import ModeloFalso
from tests.apoyo import Guion, admin

pytestmark = pytest.mark.db
cli = TestClient(api.app)


def _limpiar_asesores():
    with admin() as c:
        c.execute("""delete from atencion.traspaso_eventos where traspaso_id in (select traspaso_id from atencion.traspasos
                     where estado in ('en_cola','asignado','en_atencion','esperando_cliente'))""")
        c.execute("delete from atencion.mensajes_asesor where traspaso_id in (select traspaso_id from atencion.traspasos where estado in ('en_cola','asignado','en_atencion','esperando_cliente'))")
        c.execute("delete from atencion.traspasos where estado in ('en_cola','asignado','en_atencion','esperando_cliente')")
        c.execute("update atencion.asesor_carga set carga = 0")
        c.execute("delete from atencion.asesor_presencia_eventos")


def _equipo(codigo, rol):
    tok = cli.post("/equipo/entrar", json={"employee_code": codigo, "rol": rol}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def _entrar(codigo):
    tok = cli.post("/equipo/entrar", json={"employee_code": codigo, "rol": "asesor"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    cli.post("/equipo/presencia", json={"presencia": "disponible", "capacidad": 2}, headers=h)
    return h


def test_traspaso_asignacion_respuesta_transferencia_y_cierre(monkeypatch):
    monkeypatch.setenv("CONOCIMIENTO_INCLUIR_PENDIENTES", "1")
    _limpiar_asesores()
    api._modelo = ModeloFalso(Guion(["IDIOMA: es\nCOMANDO: pedir_persona"]))
    r = cli.post("/conversacion/turno", json={"texto": "quiero hablar con una persona"}).json()
    assert r["nodo"] == "N11" and r["traspaso"]["habilidad"] == "general"
    general = _entrar("E17183")
    mios = cli.get("/equipo/cola", headers=general).json()["mios"]
    assert len(mios) == 1
    tid = mios[0]["traspaso_id"]
    caso = cli.get(f"/equipo/caso/{tid}", headers=general).json()
    assert caso["paquete"]["motivo_traspaso"] and caso["guia"]["pasos"]
    assert cli.post(f"/equipo/caso/{tid}/mensaje", json={"texto": "Hola, soy Ana del equipo. ¿En qué te ayudo?"}, headers=general).json()["ok"]
    visto = cli.get(f"/conversacion/{r['conversation_id']}").json()
    assert visto["asesor"][0]["texto"].startswith("Hola, soy Ana")
    # Transferir exige nota; conserva el contexto
    assert cli.post(f"/equipo/caso/{tid}/transferir", json={"habilidad": "reclamos", "nota": ""}, headers=general).status_code == 422
    assert cli.post(f"/equipo/caso/{tid}/transferir", json={"habilidad": "reclamos", "nota": "Quiere reclamar un cargo"}, headers=general).json()["ok"]
    reclamos = _entrar("E81176")
    caso2 = cli.get(f"/equipo/caso/{tid}", headers=reclamos).json()
    assert caso2["paquete"]["notas"][0]["texto"] == "Quiere reclamar un cargo"
    # El asesor anterior ya no ve el caso (RLS por asignación)
    assert cli.get(f"/equipo/caso/{tid}", headers=general).status_code == 404
    assert cli.post(f"/equipo/caso/{tid}/cerrar", json={"nota": "resuelto"}, headers=reclamos).json()["ok"]
    with admin() as c:
        eventos = [e[0] for e in c.execute("select evento from atencion.traspaso_eventos where traspaso_id = %s order by id", (tid,))]
        accesos = c.execute("select count(*) from operacion.accesos_pii where traspaso_id = %s", (tid,)).fetchone()[0]
    assert eventos[0] == "creado" and "transferido" in eventos and eventos[-1] == "resuelto" and accesos >= 2


def test_devuelto_vuelve_al_asistente_y_el_supervisor_lo_ve(monkeypatch):
    """Cierre de punta a punta: no se cierra dos veces, la conversación vuelve limpia al asistente y los indicadores
    del supervisor salen del registro de esos mismos turnos."""
    monkeypatch.setenv("CONOCIMIENTO_INCLUIR_PENDIENTES", "1")
    _limpiar_asesores()
    api._modelo = ModeloFalso(Guion(["IDIOMA: es\nCOMANDO: pedir_persona", "IDIOMA: es\nCOMANDO: charla\nBORRADOR: Hola de nuevo."]))
    r = cli.post("/conversacion/turno", json={"texto": "quiero una persona"}).json()
    general = _entrar("E17183")
    tid = cli.get("/equipo/cola", headers=general).json()["mios"][0]["traspaso_id"]
    assert cli.post(f"/equipo/caso/{tid}/cerrar", json={"nota": "sigue el asistente", "devolver": True}, headers=general).json()["ok"]
    assert cli.post(f"/equipo/caso/{tid}/cerrar", json={"nota": "otra vez"}, headers=general).status_code == 409
    r2 = cli.post("/conversacion/turno", json={"conversation_id": r["conversation_id"], "texto": "hola otra vez"}).json()
    assert r2["nodo"] != "N11" and not r2["sin_modelo"] and r2["texto"]
    visto = cli.get(f"/conversacion/{r['conversation_id']}").json()
    assert [t["texto"] for t in visto["turnos"] if t["rol"] == "cliente"] == ["quiero una persona", "hola otra vez"]
    sup = {"Authorization": "Bearer " + cli.post("/equipo/entrar", json={"employee_code": "SUP1", "rol": "supervisor"}).json()["token"]}
    d = cli.get("/supervisor/indicadores?horas=1&pruebas=true", headers=sup).json()
    assert d["operacion"]["conversaciones"] >= 1 and d["operacion"]["pasaron_a_una_persona"]["numerador"] >= 1
    assert any(e["numero"] and e["evento"] == "devuelto_al_sistema" for e in d["eventos"])
    obs = {"Authorization": "Bearer " + cli.post("/equipo/entrar", json={"employee_code": "OBS", "rol": "observador"}).json()["token"]}
    assert cli.get("/supervisor/indicadores", headers=obs).json()["eventos"] == []      # el observador no ve eventos de casos
    assert cli.get("/supervisor/indicadores", headers=general).status_code == 403


def test_reiniciar_demo_libera_los_casos_sin_identidad(monkeypatch):
    """Quien pide una persona sin identificarse deja un caso sin cliente; el reinicio lo libera con su carga."""
    monkeypatch.setenv("CONOCIMIENTO_INCLUIR_PENDIENTES", "1")
    _limpiar_asesores()
    api._modelo = ModeloFalso(Guion(["IDIOMA: es\nCOMANDO: pedir_persona"]))
    cli.post("/conversacion/turno", json={"texto": "una persona por favor"})
    _entrar("E17183")
    with admin() as c:
        assert c.execute("select carga from atencion.asesor_carga where employee_code = 'E17183'").fetchone()[0] == 1
    cli.post("/demo/reiniciar")
    with admin() as c:
        assert c.execute("""select count(*) from atencion.traspasos where customer_id is null
                            and estado in ('en_cola','asignado','en_atencion','esperando_cliente')""").fetchone()[0] == 0
        assert c.execute("select carga from atencion.asesor_carga where employee_code = 'E17183'").fetchone()[0] == 0


def test_envejecimiento_sube_de_4_a_3_y_no_mas(monkeypatch):
    """PROCESOS §P2.3: nadie queda olvidado; un caso de prioridad 4 vencido sube a 3 con hito nuevo, una sola vez."""
    from servicio.enrutador import enrutador
    monkeypatch.setenv("CONOCIMIENTO_INCLUIR_PENDIENTES", "1")
    _limpiar_asesores()
    api._modelo = ModeloFalso(Guion(["IDIOMA: es\nCOMANDO: pedir_persona"]))
    r = cli.post("/conversacion/turno", json={"texto": "una persona"}).json()
    assert r["traspaso"]["prioridad"] == 4
    with admin() as c:
        c.execute("update atencion.traspasos set primera_respuesta_vence = now() - interval '1 minute' where conversation_id = %s",
                  (r["conversation_id"],))
    enrutador.asignar()
    enrutador.asignar()
    with admin() as c:
        t = c.execute("""select prioridad, primera_respuesta_vence > now() from atencion.traspasos where conversation_id = %s""",
                      (r["conversation_id"],)).fetchone()
        eventos = c.execute("""select count(*) from atencion.traspaso_eventos e join atencion.traspasos t using (traspaso_id)
                               where t.conversation_id = %s and e.evento = 'envejecido'""", (r["conversation_id"],)).fetchone()[0]
    assert t == (3, True) and eventos == 1


def test_aceptacion_vencida_devuelve_el_caso_en_su_lugar_y_el_asesor_queda_ausente(monkeypatch):
    """PROCESOS §P2.4: 60 s para abrir el caso; si no, vuelve a la cola conservando su llegada."""
    from servicio.enrutador import enrutador
    monkeypatch.setenv("CONOCIMIENTO_INCLUIR_PENDIENTES", "1")
    _limpiar_asesores()
    api._modelo = ModeloFalso(Guion(["IDIOMA: es\nCOMANDO: pedir_persona"]))
    r = cli.post("/conversacion/turno", json={"texto": "una persona"}).json()
    h = _entrar("E17183")
    tid = cli.get("/equipo/cola", headers=h).json()["mios"][0]["traspaso_id"]
    with admin() as c:
        llegada = c.execute("select llegada from atencion.traspasos where traspaso_id = %s", (tid,)).fetchone()[0]
        c.execute("update atencion.traspasos set asignado_en = now() - interval '61 seconds' where traspaso_id = %s", (tid,))
    enrutador.asignar()
    cola = cli.get("/equipo/cola", headers=h).json()
    assert cola["mios"] == [] and cola["yo"]["presencia"] == "ausente"
    with admin() as c:
        t = c.execute("select estado, asesor, llegada from atencion.traspasos where traspaso_id = %s", (tid,)).fetchone()
        carga = c.execute("select carga from atencion.asesor_carga where employee_code = 'E17183'").fetchone()[0]
        ev = c.execute("select count(*) from atencion.traspaso_eventos where traspaso_id = %s and evento = 'aceptacion_vencida'",
                       (tid,)).fetchone()[0]
    assert t == ("en_cola", None, llegada) and carga == 0 and ev == 1
    # Abrir a tiempo sí lo conserva
    cli.post("/equipo/presencia", json={"presencia": "disponible", "capacidad": 2}, headers=h)
    assert cli.post(f"/equipo/caso/{tid}/tomar", headers=h).json()["ok"]
    enrutador.asignar()
    assert cli.get("/equipo/cola", headers=h).json()["mios"][0]["traspaso_id"] == tid


def test_auditoria_reconstruye_la_conversacion_aun_despues_del_reinicio(monkeypatch):
    """Quién, qué, dónde, cuándo: cliente, componentes, cada llamada al modelo con su componente, el caso humano y el
    acceso de quien audita. El reinicio de la demo archiva antes de borrar, así que la historia sigue ahí."""
    monkeypatch.setenv("CONOCIMIENTO_INCLUIR_PENDIENTES", "1")
    _limpiar_asesores()
    api._modelo = ModeloFalso(Guion(["IDIOMA: es\nCOMANDO: pedir_persona"]))
    r = cli.post("/conversacion/turno", json={"texto": "una persona"}).json()
    numero = r["traspaso"]["numero"]
    sup = {"Authorization": "Bearer " + cli.post("/equipo/entrar", json={"employee_code": "SUP1", "rol": "supervisor"}).json()["token"]}

    def revisar():
        a = cli.get(f"/supervisor/auditoria/{numero}", headers=sup).json()
        que = {(e["quien"], e["que"]) for e in a["eventos"]}
        assert ("cliente", "escribió") in que and ("enrutador", "creado") in que
        assert any(e["que"] == "llamada al modelo" and "redactar" in e["donde"] for e in a["eventos"])
        assert any(e["quien"] == "traspaso" and e["resultado"] == "ok" for e in a["eventos"])
        assert numero in a["casos_humanos"]
    revisar()
    cli.post("/demo/reiniciar")
    revisar()
    general = _entrar("E17183")
    assert cli.get(f"/supervisor/auditoria/{numero}", headers=general).status_code == 403
    with admin() as c:
        assert c.execute("select count(*) from operacion.accesos_pii where persona = 'SUP1' and motivo = %s",
                         (f"auditoría de {r['conversation_id']}",)).fetchone()[0] == 2


def test_toda_falla_queda_con_su_razon_real_y_el_caso_pasa_a_una_persona(monkeypatch):
    """Un error no previsto: el turno se revierte, el incidente guarda dónde, qué y el rastro, y la conversación pasa a
    una persona con esa referencia (el cliente ve el aviso de espera). Si el rescate también falla, el cliente recibe un
    500 genérico con la referencia. Una llamada al modelo que falla queda con su razón; un rechazo por rol, como evento
    de seguridad."""
    monkeypatch.setenv("CONOCIMIENTO_INCLUIR_PENDIENTES", "1")
    from servicio.orquestador import orquestador

    def explota(*a, **k):
        raise RuntimeError("falla de prueba en el grafo")
    monkeypatch.setattr(orquestador, "_decidir", explota)
    api._modelo = ModeloFalso(Guion(["IDIOMA: es\nCOMANDO: charla"]))
    no_lanza = TestClient(api.app, raise_server_exceptions=False)
    r = no_lanza.post("/conversacion/turno", json={"texto": "hola"})
    assert r.status_code == 200 and "falla de prueba" not in r.text
    s = r.json()
    assert s["texto"] == "" and any(u["tipo"] == "aviso_espera" for u in s["ui"])
    with admin() as c:
        tr = c.execute("select paquete from atencion.traspasos where conversation_id = %s", (s["conversation_id"],)).fetchone()[0]
        assert "falla_del_sistema" in tr["motivo_traspaso"] and "sin_modelo" not in tr["motivo_traspaso"]
        ref = int(tr["preguntas_abiertas"][0].split("incidente ")[1].split(")")[0])
        inc = c.execute("select donde, tipo, mensaje, rastro, turn_id from operacion.incidentes where id = %s", (ref,)).fetchone()
        assert inc[0] == "orquestador.procesar" and inc[1] == "RuntimeError" and "falla de prueba" in inc[2]
        assert "_decidir" in inc[3] or "explota" in inc[3]
        assert c.execute("select count(*) from operacion.consumo_modelos where turn_id = %s and proposito = 'interpretar'",
                         (inc[4],)).fetchone()[0] == 1       # la llamada previa a la falla quedó registrada
        assert c.execute("select count(*) from atencion.turnos where conversation_id = %s and rol = 'cliente'",
                         (s["conversation_id"],)).fetchone()[0] == 0     # el mensaje que falló no se guardó
    monkeypatch.setattr(orquestador, "_rescate", lambda *a, **k: None)   # si el rescate también falla: 500 con referencia
    api._modelo = ModeloFalso(Guion(["IDIOMA: es\nCOMANDO: charla"]))
    r = no_lanza.post("/conversacion/turno", json={"texto": "hola"})
    assert r.status_code == 500 and r.json()["error"] == "interno" and r.json()["referencia"]
    api._modelo = ModeloFalso(["FALLA"])
    cli.post("/conversacion/turno", json={"texto": "hola"})
    with admin() as c:
        assert c.execute("select error from operacion.consumo_modelos where resultado = 'fallo' order by id desc limit 1").fetchone()[0] == "falla programada"
    cli.get("/sistema")                                               # sin token de equipo
    with admin() as c:
        ev = c.execute("select tipo, detalle from operacion.eventos_seguridad order by id desc limit 1").fetchone()
    assert ev[0] == "rol_negado" and ev[1]["ruta"] == "/sistema"


def test_la_cabina_responde_al_supervisor_y_al_observador():
    for codigo, rol in (("SUP1", "supervisor"), ("OBS", "observador")):
        h = {"Authorization": "Bearer " + cli.post("/equipo/entrar", json={"employee_code": codigo, "rol": rol}).json()["token"]}
        d = cli.get("/sistema?horas=1", headers=h).json()
        assert {"sano", "modelo", "consumo", "llamadas_fallidas", "incidentes", "rechazos", "avisos", "salud"} <= set(d)


def test_el_presupuesto_por_conversacion_lo_decide_el_banco_desde_la_operacion():
    """PROCESOS §P9: el valor inicial sale de la configuración; un supervisor lo cambia con motivo, queda el evento, y
    rige desde el turno siguiente. Un asesor no puede cambiarlo; un valor fuera de rango o sin motivo se rechaza."""
    from servicio.registro import parametros
    sup = {"Authorization": f"Bearer {cli.post('/equipo/entrar', json={'employee_code': 'SUP1', 'rol': 'supervisor'}).json()['token']}"}
    ase = {"Authorization": f"Bearer {cli.post('/equipo/entrar', json={'employee_code': 'E30142', 'rol': 'asesor'}).json()['token']}"}
    clave = "presupuesto_tokens_conversacion"
    inicial = parametros.catalogo()[clave]["inicial"]
    try:
        ind = cli.get("/supervisor/indicadores", headers=sup).json()
        assert any(p["clave"] == clave for p in ind["parametros"])
        assert cli.put(f"/supervisor/parametros/{clave}", json={"valor": 5000, "motivo": "prueba"}, headers=ase).status_code == 403
        assert cli.put(f"/supervisor/parametros/{clave}", json={"valor": -1, "motivo": "prueba"}, headers=sup).status_code == 422
        assert cli.put(f"/supervisor/parametros/{clave}", json={"valor": 5000, "motivo": " "}, headers=sup).status_code == 422
        r = cli.put(f"/supervisor/parametros/{clave}", json={"valor": 0, "motivo": "sin tope para la demo"}, headers=sup)
        p = next(x for x in r.json()["parametros"] if x["clave"] == clave)
        assert p["valor"] == 0 and p["origen"] == "operacion" and p["cambiado_por"] == "SUP1"
        with admin() as c:
            ev = c.execute("select valor_nuevo, autor, motivo from operacion.parametro_eventos where clave = %s order by id desc limit 1",
                           (clave,)).fetchone()
        assert ev == (0, "SUP1", "sin tope para la demo")
        cab = cli.get("/sistema", headers=sup).json()
        assert next(x for x in cab["parametros"] if x["clave"] == clave)["conversaciones_al_tope"] >= 0
    finally:
        with admin() as c:
            c.execute("delete from operacion.parametros where clave = %s", (clave,))
    assert parametros.catalogo()[clave]["inicial"] == inicial


def test_sin_nadie_con_su_idioma_se_ofrece_espanol_y_decide_el_cliente(monkeypatch):
    """PROCESOS §P2.5, nivel 3: un caso en portugués sin nadie en turno que lo hable. El aviso ofrece seguir en español
    (solo si hay alguien en turno que lo hable); si el cliente acepta, el caso vuelve al nivel 0 en español con su
    llegada intacta y queda el evento. El sistema nunca cambia el idioma por su cuenta."""
    import secrets
    from servicio.enrutador import enrutador
    from servicio.llm.cliente import ModeloFalso
    from servicio.orquestador.orquestador import Entrada, procesar
    solo_es = [{"employee_code": "X1", "habilidad": "general", "idiomas": ["es"], "canal": "Digital", "turno": "Morning",
                "pais": "Colombia", "demo": True, "presencia": "disponible", "carga": 0, "capacidad": 2,
                "ultima_asignacion": None}]
    monkeypatch.setattr(enrutador, "_asesores", lambda c: solo_es)
    monkeypatch.setattr(enrutador, "asignar", lambda *a, **k: [])
    conv = "c_" + secrets.token_hex(6)
    procesar(conv, Entrada(evento={"tipo": "pedir_persona"}), None, ModeloFalso(Guion([])))
    with admin() as c:
        tid, llegada = c.execute("update atencion.traspasos set idioma = 'pt', estado = 'en_cola', asesor = null "
                                 "where conversation_id = %s returning traspaso_id, llegada", (conv,)).fetchone()
    aviso = enrutador.posicion_y_espera(tid)
    assert aviso["nivel_desborde"] == 3 and aviso["ofrece_idioma"] == "es"
    s = procesar(conv, Entrada(evento={"tipo": "aceptar_idioma", "idioma": "es"}), None, ModeloFalso(Guion([])))
    assert any(u["tipo"] == "aviso_espera" for u in s.ui)
    with admin() as c:
        fila = c.execute("select idioma, nivel_desborde, llegada from atencion.traspasos where traspaso_id = %s", (tid,)).fetchone()
        ev = c.execute("select detalle from atencion.traspaso_eventos where traspaso_id = %s and evento = 'idioma_aceptado_por_cliente'",
                       (tid,)).fetchone()
    assert fila == ("es", 0, llegada) and ev[0] == {"de": "pt", "a": "es"}
    # Un idioma que no se ofreció no se acepta
    assert not enrutador.cambiar_idioma_a_pedido(tid, "es")


def test_cambio_de_estado_avisa_al_cliente_y_el_silencio_cierra_por_vencimiento():
    """PROCESOS §P3: cada cambio de estado que no hizo el cliente deja un aviso. Un reclamo que espera al cliente más
    días de los que decide el banco se cierra solo, con evento del sistema y aviso; el cliente no lo cierra en silencio."""
    import secrets
    from servicio.enrutador import enrutador
    from servicio.registro import parametros
    from tests.apoyo import limpiar_cliente, token_de
    token, cid = token_de("DEMO-1001")
    limpiar_cliente(cid)
    with admin() as c:
        tx = c.execute("select transaction_id, product_id from servicio.transacciones where customer_id = %s limit 1", (cid,)).fetchone()
        rid = "rec_" + secrets.token_hex(6)
        c.execute("""insert into atencion.reclamos (reclamo_id, numero, customer_id, transaction_id, product_id, tipo_disputa,
                       prioridad, habilidad, estado) values (%s, %s, %s, %s, %s, 'no_autorizada', 4, 'fraude', 'abierto')""",
                  (rid, "R-T" + secrets.token_hex(3), cid, tx[0], tx[1]))
        c.execute("delete from atencion.avisos_cliente where customer_id = %s", (cid,))
        for anterior, nuevo, autor in (("abierto", "en_revision", "asesor"), ("en_revision", "esperando_cliente", "asesor")):
            v = c.execute("select version from atencion.reclamos where reclamo_id = %s", (rid,)).fetchone()[0]
            c.execute("select atencion.transicion_reclamo(%s, %s, %s, 'E30142', 'prueba', %s)", (rid, nuevo, autor, v))
        assert c.execute("select count(*) from atencion.avisos_cliente where customer_id = %s", (cid,)).fetchone()[0] == 2
        dias = parametros.catalogo()["dias_espera_respuesta_cliente"]["inicial"]
        c.execute("update atencion.reclamo_eventos set creado = now() - make_interval(days => %s) where reclamo_id = %s",
                  (dias + 1, rid))
    enrutador.asignar()
    with admin() as c:
        estado = c.execute("select estado from atencion.reclamos where reclamo_id = %s", (rid,)).fetchone()[0]
        ev = c.execute("""select autor_tipo, motivo from atencion.reclamo_eventos where reclamo_id = %s and estado_nuevo = 'cerrado'""",
                       (rid,)).fetchone()
        avisos = c.execute("select hechos->>'estado_nuevo' from atencion.avisos_cliente where customer_id = %s order by id", (cid,)).fetchall()
    assert estado == "cerrado" and ev[0] == "sistema" and "vencimiento" in ev[1]
    assert [a[0] for a in avisos] == ["en_revision", "esperando_cliente", "cerrado"]


def _regla(monkeypatch, cualquiera: bool):
    """La demo declara (config/atencion_humana.yaml) que sus identidades toman casos de cualquier habilidad; las pruebas de la regla de producción la apagan."""
    from servicio.enrutador import enrutador
    real = enrutador.config()
    monkeypatch.setattr(enrutador, "config", lambda: {**real, "asesores_demo_cualquier_habilidad": cualquiera})


def test_investigacion_en_back_office_de_punta_a_punta(monkeypatch):
    """PROCESOS §P3: la cola llega sin datos del cliente; el asesor de la habilidad toma el siguiente (uno a la vez), lo
    ve completo, pide información, decide con fundamento (la negativa sin explicación y documentos se rechaza), registra
    el abono solo si resolvió a favor y cierra; el supervisor reabre con motivo. Cada cambio avisa al cliente."""
    import secrets
    from tests.apoyo import limpiar_cliente, token_de
    _regla(monkeypatch, False)                            # la regla de producción: cada asesor toma solo lo de su habilidad
    _, cid = token_de("DEMO-1001")
    limpiar_cliente(cid)
    with admin() as c:
        c.execute("update atencion.reclamos set estado = 'cerrado' where estado = 'abierto' and asesor is null")   # cola limpia
        c.execute("update atencion.reclamos set estado = 'cerrado' where asesor = 'E30142' and estado = 'en_revision'")
        tx = c.execute("select transaction_id, product_id from servicio.transacciones where customer_id = %s limit 1", (cid,)).fetchone()
        rid, numero = "rec_" + secrets.token_hex(6), "R-B" + secrets.token_hex(3)
        c.execute("""insert into atencion.reclamos (reclamo_id, numero, customer_id, transaction_id, product_id, tipo_disputa,
                       prioridad, habilidad, estado, plazo_vence) values (%s,%s,%s,%s,%s,'no_autorizada',4,'fraude','abierto','2026-08-02')""",
                  (rid, numero, cid, tx[0], tx[1]))
    fraude, general, sup = (_equipo("E30142", "asesor"), _equipo("E17183", "asesor"), _equipo("SUP1", "supervisor"))
    cola = cli.get("/equipo/reclamos", headers=fraude).json()["cola"]
    assert [x["numero"] for x in cola] == [numero] and "customer_id" not in cola[0] and cola[0]["plazo"].endswith("2026")
    assert cola[0]["plazo_origen"] == "regla del país" and cola[0]["alarma"] is False and cola[0]["dias_habiles_restantes"] > 2
    assert cli.post("/equipo/reclamos/siguiente", headers=general).status_code == 422          # general no investiga
    assert cli.get(f"/equipo/reclamos/{rid}", headers=fraude).status_code == 404                # sin tomarlo, no lo ve
    assert cli.post("/equipo/reclamos/siguiente", headers=fraude).json()["reclamo_id"] == rid
    assert cli.post("/equipo/reclamos/siguiente", headers=fraude).status_code == 422            # uno a la vez
    reclamos = _equipo("E81176", "asesor")
    assert cli.post(f"/equipo/reclamos/{rid}/tipo", json={"tipo_disputa": "estafa_autorizada", "motivo": "x"}, headers=reclamos).status_code == 403
    assert cli.post(f"/equipo/reclamos/{rid}/tipo", json={"tipo_disputa": "estafa_autorizada", "motivo": "lo engañaron por teléfono"},
                    headers=fraude).status_code == 200
    det = cli.get(f"/equipo/reclamos/{rid}", headers=fraude).json()
    assert det["reclamo"]["tipo_disputa"] == "estafa_autorizada" and "no_autorizada a estafa_autorizada" in det["notas"][-1]["texto"]
    assert det["reclamo"]["estado"] == "en_revision" and det["movimiento"]["movimiento"]
    assert cli.post(f"/equipo/reclamos/{rid}/pedir-informacion", json={"nota": "envíe el comprobante"}, headers=fraude).status_code == 200
    with admin() as c:
        c.execute("select atencion.transicion_reclamo(%s,'en_revision','cliente',null,'respondió', (select version from atencion.reclamos where reclamo_id = %s))",
                  (rid, rid))
    assert cli.post(f"/equipo/reclamos/{rid}/decidir", json={"decision": "resuelto_en_contra"}, headers=fraude).status_code == 422
    assert cli.post(f"/equipo/reclamos/{rid}/decidir", headers=fraude, json={
        "decision": "resuelto_en_contra", "explicacion": "El movimiento se hizo con la tarjeta física y el PIN.",
        "documentos": ["registro de autorización del emisor"]}).status_code == 200
    assert cli.post(f"/equipo/reclamos/{rid}/abono", json={"referencia": "AB-1"}, headers=fraude).status_code == 422
    assert cli.post(f"/equipo/reclamos/{rid}/cerrar", headers=fraude).status_code == 200
    assert cli.post(f"/supervisor/reclamos/{rid}/reabrir", json={"motivo": " "}, headers=sup).status_code == 422
    assert cli.post(f"/supervisor/reclamos/{rid}/reabrir", json={"motivo": "el cliente pidió revisión"}, headers=sup).status_code == 200
    with admin() as c:
        estados = [r[0] for r in c.execute("select estado_nuevo from atencion.reclamo_eventos where reclamo_id = %s order by id", (rid,))]
        avisos = c.execute("select count(*) from atencion.avisos_cliente where hechos->>'reclamo' = %s", (numero,)).fetchone()[0]
        c.execute("update atencion.reclamos set estado = 'cerrado' where reclamo_id = %s", (rid,))
    assert estados == ["en_revision", "esperando_cliente", "en_revision", "resuelto_en_contra", "cerrado", "en_revision"]
    assert avisos == 5                                    # todos menos la respuesta del propio cliente


def test_supervisor_reasigna_cambia_presencia_y_el_asesor_marca_un_articulo():
    import secrets
    from servicio.llm.cliente import ModeloFalso
    from servicio.orquestador.orquestador import Entrada, procesar
    sup, ase = _equipo("SUP1", "supervisor"), _equipo("E81176", "asesor")
    conv = "c_" + secrets.token_hex(6)
    procesar(conv, Entrada(evento={"tipo": "pedir_persona"}), None, ModeloFalso(Guion([])))
    with admin() as c:
        tid = c.execute("select traspaso_id from atencion.traspasos where conversation_id = %s", (conv,)).fetchone()[0]
    assert cli.post(f"/supervisor/caso/{tid}/reasignar", json={"asesor": "E81176", "nota": ""}, headers=sup).status_code == 422
    assert cli.post(f"/supervisor/caso/{tid}/reasignar", json={"asesor": "E81176", "nota": "lo toma reclamos"}, headers=sup).status_code == 200
    assert cli.post(f"/supervisor/caso/{tid}/reasignar", json={"asesor": "E81176", "nota": "x"}, headers=ase).status_code == 403
    with admin() as c:
        asignado = c.execute("select asesor, estado from atencion.traspasos where traspaso_id = %s", (tid,)).fetchone()
        ev = c.execute("select autor, detalle->>'a' from atencion.traspaso_eventos where traspaso_id = %s and evento = 'reasignado'", (tid,)).fetchone()
    assert asignado == ("E81176", "asignado") and ev == ("SUP1", "E81176")
    assert cli.post("/supervisor/asesor/E81176/presencia", json={"presencia": "volando"}, headers=sup).status_code == 422
    assert cli.post("/supervisor/asesor/E81176/presencia", json={"presencia": "en_pausa", "capacidad": 2}, headers=sup).status_code == 200
    assert cli.post("/equipo/conocimiento/publico.plazos-por-pais/marca", json={"marca": "incompleto", "nota": "falta Brasil",
                                                                                "traspaso_id": tid}, headers=ase).status_code == 200
    with admin() as c:
        assert c.execute("select presencia from atencion.asesor_presencia_eventos where employee_code = 'E81176' order by id desc limit 1").fetchone()[0] == "en_pausa"
        assert c.execute("select marca from atencion.conocimiento_marcas where asesor = 'E81176' order by id desc limit 1").fetchone()[0] == "incompleto"
        c.execute("insert into atencion.asesor_presencia_eventos (employee_code, presencia, capacidad) values ('E81176','disponible',2)")


def _png():
    import struct
    import zlib

    def trozo(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    return (b"\x89PNG\r\n\x1a\n" + trozo(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) + trozo(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
            + trozo(b"IEND", b""))


def test_los_adjuntos_se_sirven_sin_ejecutar_nada_y_el_pdf_con_contenido_activo_se_rechaza(monkeypatch):
    """SEGURIDAD T-4: el PDF solo como descarga, la imagen en línea, ambos sin sniffing y con una política que no deja ejecutar nada."""
    monkeypatch.setenv("CONOCIMIENTO_INCLUIR_PENDIENTES", "1")
    _limpiar_asesores()
    from tests.apoyo import limpiar_cliente, token_de
    token, cid = token_de("DEMO-1001")
    limpiar_cliente(cid)
    cliente = {"Authorization": f"Bearer {token}"}                      # el archivo es de un cliente real: el asesor solo ve los del caso que atiende
    api._modelo = ModeloFalso(Guion(["IDIOMA: es\nCOMANDO: pedir_persona"]))
    r = cli.post("/conversacion/turno", json={"texto": "quiero hablar con una persona"}, headers=cliente).json()
    conv = r["conversation_id"]
    malo = b"%PDF-1.4\n1 0 obj << /OpenAction << /S /JavaScript /JS (app.alert(1)) >> >> endobj\n%%EOF"
    assert cli.post(f"/adjuntos?conversation_id={conv}", files={"archivo": ("a.pdf", malo, "application/pdf")}, headers=cliente).status_code == 415
    bueno = b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\n%%EOF"
    pdf = cli.post(f"/adjuntos?conversation_id={conv}", files={"archivo": ("a.pdf", bueno, "application/pdf")}, headers=cliente).json()["adjunto_id"]
    png = cli.post(f"/adjuntos?conversation_id={conv}", files={"archivo": ("a.png", _png(), "image/png")}, headers=cliente).json()["adjunto_id"]
    asesor = _entrar("E17183")
    tid = cli.get("/equipo/cola", headers=asesor).json()["mios"][0]["traspaso_id"]
    for aid, tipo, disposicion in ((pdf, "application/pdf", "attachment"), (png, "image/png", "inline")):
        v = cli.get(f"/equipo/caso/{tid}/adjunto/{aid}", headers=asesor)
        assert v.status_code == 200 and v.headers["content-type"] == tipo
        assert v.headers["content-disposition"].startswith(disposicion)
        assert v.headers["x-content-type-options"] == "nosniff" and "sandbox" in v.headers["content-security-policy"]


def test_en_la_demo_el_back_office_tambien_acepta_cualquier_habilidad(monkeypatch):
    """5-oct: un reclamo de fraude no aparecía en la cola de quien entró como asesor de reclamos y el back-office se veía vacío. Con la regla declarada de la demo
    lo ve y lo toma (la base comprueba que sea una identidad de demo)."""
    import secrets
    from tests.apoyo import limpiar_cliente, token_de
    _regla(monkeypatch, True)
    _, cid = token_de("DEMO-1001")
    limpiar_cliente(cid)
    with admin() as c:
        c.execute("update atencion.reclamos set estado = 'cerrado' where estado = 'abierto' and asesor is null")
        c.execute("update atencion.reclamos set estado = 'cerrado' where asesor in ('E30142','E81176','E17183') and estado = 'en_revision'")
        tx = c.execute("select transaction_id, product_id from servicio.transacciones where customer_id = %s limit 1", (cid,)).fetchone()
        rid = "rec_" + secrets.token_hex(6)
        c.execute("""insert into atencion.reclamos (reclamo_id, numero, customer_id, transaction_id, product_id, tipo_disputa,
                       prioridad, habilidad, estado, plazo_vence) values (%s,%s,%s,%s,%s,'no_autorizada',4,'fraude','abierto','2026-08-02')""",
                  (rid, "R-D" + secrets.token_hex(3), cid, tx[0], tx[1]))
    reclamos = _equipo("E81176", "asesor")                # habilidad «reclamos»: el reclamo es de «fraude»
    assert [x["habilidad"] for x in cli.get("/equipo/reclamos", headers=reclamos).json()["cola"]] == ["fraude"]
    assert cli.post("/equipo/reclamos/siguiente", headers=reclamos).json()["reclamo_id"] == rid
    with admin() as c:
        c.execute("update atencion.reclamos set estado = 'cerrado' where reclamo_id = %s", (rid,))


def test_la_web_se_revalida_siempre_y_la_cola_dice_quien_es_el_asesor():
    """5-oct: tras un despliegue el navegador mostraba el JavaScript viejo (no había `Cache-Control`) y la pantalla del asesor no decía quién es."""
    r = cli.get("/app/app.js")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-cache"
    yo = cli.get("/equipo/cola", headers=_equipo("E81176", "asesor")).json()["yo"]
    assert yo["employee_code"] == "E81176" and yo["habilidad"] == "reclamos" and "es" in yo["idiomas"] and yo["turno"] and yo["pais"]


def test_disponible_caduca_si_el_asesor_no_da_senales_de_vida():
    """5-oct: un asesor «disponible» de una prueba anterior se quedaba con los casos de quien sí estaba conectado (la presencia no caducaba)."""
    from servicio.datos.db import transaccion
    from servicio.enrutador import enrutador
    _limpiar_asesores()
    with admin() as c:
        c.execute("insert into atencion.asesor_presencia_eventos (employee_code, presencia, capacidad, creado) values ('E81176','disponible',2, now() - interval '10 minutes')")
        c.execute("insert into atencion.asesor_presencia_eventos (employee_code, presencia, capacidad) values ('E30142','disponible',2)")
    with transaccion("app_enrutador") as c:
        presencia = {a["employee_code"]: a["presencia"] for a in enrutador._asesores(c)}
    assert presencia["E81176"] == "desconectado" and presencia["E30142"] == "disponible"

