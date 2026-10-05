-- Permisos, RLS y transiciones validadas en la base (MODELO_DATOS §3-§4, ROLES_Y_ACCESOS §3, SEGURIDAD §3).
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_enrutador') THEN
    CREATE ROLE app_enrutador NOLOGIN NOSUPERUSER NOBYPASSRLS;
  END IF;
END $$;
GRANT app_enrutador TO app_api WITH INHERIT FALSE, SET TRUE;
GRANT USAGE ON SCHEMA atencion, operacion TO app_enrutador;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA atencion, operacion TO app_ejecucion, app_identidad, app_asesor, app_supervisor, app_enrutador;

-- ---------- Identidad ----------
GRANT SELECT ON atencion.identidades_demo TO app_identidad;
GRANT SELECT, INSERT, UPDATE ON atencion.desafios_otp, atencion.sesiones TO app_identidad;
GRANT INSERT ON atencion.buzon_sandbox, operacion.eventos_seguridad TO app_identidad;
GRANT SELECT ON atencion.buzon_sandbox TO app_supervisor;   -- el buzón lo lee la página de demo por su endpoint

-- ---------- Cliente y asistente ----------
GRANT SELECT, INSERT, UPDATE ON atencion.conversaciones, atencion.estado_conversacion, atencion.reclamos,
  atencion.intenciones_accion, atencion.bloqueos, atencion.adjuntos, atencion.avisos_cliente TO app_ejecucion;
GRANT SELECT, INSERT ON atencion.turnos, atencion.reclamo_eventos, atencion.reclamo_notas, atencion.bloqueo_eventos,
  atencion.traspasos, atencion.traspaso_eventos, atencion.mensajes_asesor TO app_ejecucion;
GRANT SELECT ON atencion.asesores, atencion.asesor_presencia_eventos, atencion.asesor_carga,
  atencion.conocimiento_articulos TO app_ejecucion;
GRANT INSERT ON atencion.conocimiento_eventos, operacion.registro_turnos, operacion.consumo_modelos,
  operacion.eventos_seguridad TO app_ejecucion;
GRANT SELECT ON operacion.registro_turnos TO app_ejecucion;
GRANT SELECT (id, articulo, version, evento) ON atencion.conocimiento_eventos TO app_ejecucion;

-- ---------- Enrutador (A14): trabaja sobre la cola, sin datos de la cuenta ----------
GRANT SELECT, UPDATE ON atencion.traspasos, atencion.asesor_carga TO app_enrutador;
GRANT SELECT, INSERT ON atencion.traspaso_eventos TO app_enrutador;
GRANT SELECT ON atencion.asesores, atencion.asesor_presencia_eventos TO app_enrutador;
GRANT INSERT ON atencion.asesor_carga, atencion.asesor_presencia_eventos TO app_enrutador;
GRANT SELECT (reclamo_id, numero, habilidad, prioridad, estado, asesor, creado, investigacion_vence) ON atencion.reclamos TO app_enrutador;

-- ---------- Equipo humano ----------
GRANT SELECT ON ALL TABLES IN SCHEMA atencion TO app_supervisor, app_asesor;
REVOKE SELECT ON atencion.identidades_demo, atencion.desafios_otp, atencion.sesiones FROM app_supervisor, app_asesor;
GRANT INSERT ON atencion.mensajes_asesor, atencion.traspaso_eventos, atencion.reclamo_eventos, atencion.reclamo_notas,
  atencion.conocimiento_marcas, atencion.asesor_presencia_eventos, atencion.bloqueo_eventos,
  operacion.accesos_pii, atencion.avisos_cliente TO app_asesor, app_supervisor;
GRANT UPDATE ON atencion.traspasos, atencion.reclamos, atencion.bloqueos, atencion.asesor_carga,
  atencion.conversaciones TO app_asesor, app_supervisor;
GRANT INSERT ON atencion.asesor_carga TO app_asesor, app_supervisor;
GRANT SELECT ON operacion.registro_turnos, operacion.accesos_pii, operacion.consumo_modelos TO app_supervisor, app_observador;
GRANT SELECT ON atencion.asesores, atencion.conocimiento_articulos TO app_observador;
REVOKE DELETE ON ALL TABLES IN SCHEMA atencion, operacion, servicio FROM PUBLIC, app_api, app_ejecucion,
  app_identidad, app_asesor, app_supervisor, app_observador, app_enrutador;

-- ---------- RLS ----------
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['conversaciones','estado_conversacion','turnos','reclamos','reclamo_eventos','reclamo_notas',
      'adjuntos','intenciones_accion','bloqueos','bloqueo_eventos','avisos_cliente','traspasos','traspaso_eventos',
      'mensajes_asesor','conocimiento_articulos'] LOOP
    EXECUTE format('ALTER TABLE atencion.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE atencion.%I FORCE ROW LEVEL SECURITY', t);
  END LOOP;
  FOREACH t IN ARRAY ARRAY['registro_turnos'] LOOP
    EXECUTE format('ALTER TABLE operacion.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE operacion.%I FORCE ROW LEVEL SECURITY', t);
  END LOOP;
END $$;

-- Casos asignados al asesor de la transacción (activos).
CREATE OR REPLACE FUNCTION atencion.clientes_del_asesor() RETURNS SETOF text LANGUAGE sql STABLE AS $$
  SELECT customer_id FROM atencion.traspasos
  WHERE asesor = atencion.asesor_actual() AND estado IN ('asignado','en_atencion','esperando_cliente')
    AND customer_id IS NOT NULL
$$;
CREATE OR REPLACE FUNCTION atencion.conversaciones_del_asesor() RETURNS SETOF text LANGUAGE sql STABLE AS $$
  SELECT conversation_id FROM atencion.traspasos
  WHERE asesor = atencion.asesor_actual() AND estado IN ('asignado','en_atencion','esperando_cliente')
$$;

DO $$
DECLARE t text;
BEGIN
  -- Tablas con customer_id y conversation_id: el cliente ve lo suyo; el visitante, solo su conversación.
  FOREACH t IN ARRAY ARRAY['conversaciones','estado_conversacion','turnos','adjuntos','traspasos','traspaso_eventos',
      'mensajes_asesor','avisos_cliente'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS propio ON atencion.%I', t);
    IF t = 'traspaso_eventos' THEN
      EXECUTE format($p$CREATE POLICY propio ON atencion.%I TO app_ejecucion USING (traspaso_id IN (
        SELECT traspaso_id FROM atencion.traspasos)) WITH CHECK (true)$p$, t);
    ELSE
      EXECUTE format($p$CREATE POLICY propio ON atencion.%I TO app_ejecucion
        USING (customer_id = atencion.sujeto() OR (customer_id IS NULL AND conversation_id = atencion.conversacion_actual()))
        WITH CHECK (customer_id = atencion.sujeto() OR (customer_id IS NULL AND conversation_id = atencion.conversacion_actual()))$p$, t);
    END IF;
  END LOOP;
  FOREACH t IN ARRAY ARRAY['reclamos','reclamo_eventos','reclamo_notas','intenciones_accion','bloqueos','bloqueo_eventos'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS propio ON atencion.%I', t);
    EXECUTE format($p$CREATE POLICY propio ON atencion.%I TO app_ejecucion
      USING (customer_id = atencion.sujeto()) WITH CHECK (customer_id = atencion.sujeto())$p$, t);
  END LOOP;
  -- Asesor: solo lo de sus casos asignados y abiertos.
  FOREACH t IN ARRAY ARRAY['conversaciones','estado_conversacion','turnos','adjuntos','mensajes_asesor','avisos_cliente',
      'reclamos','reclamo_eventos','reclamo_notas','bloqueos','bloqueo_eventos','intenciones_accion'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS asesor_asignado ON atencion.%I', t);
    EXECUTE format($p$CREATE POLICY asesor_asignado ON atencion.%I TO app_asesor
      USING (customer_id IN (SELECT atencion.clientes_del_asesor()))
      WITH CHECK (customer_id IN (SELECT atencion.clientes_del_asesor()))$p$, t);
    EXECUTE format('DROP POLICY IF EXISTS supervisor ON atencion.%I', t);
    EXECUTE format('CREATE POLICY supervisor ON atencion.%I TO app_supervisor USING (true) WITH CHECK (true)', t);
  END LOOP;
END $$;
-- Conversaciones sin cliente (identidad no verificada) que tiene asignadas el asesor.
DROP POLICY IF EXISTS asesor_conversacion ON atencion.turnos;
CREATE POLICY asesor_conversacion ON atencion.turnos TO app_asesor
  USING (conversation_id IN (SELECT atencion.conversaciones_del_asesor()));
DROP POLICY IF EXISTS asesor_conversacion ON atencion.mensajes_asesor;
CREATE POLICY asesor_conversacion ON atencion.mensajes_asesor TO app_asesor
  USING (conversation_id IN (SELECT atencion.conversaciones_del_asesor()))
  WITH CHECK (conversation_id IN (SELECT atencion.conversaciones_del_asesor()));

DROP POLICY IF EXISTS asesor_asignado ON atencion.traspasos;
CREATE POLICY asesor_asignado ON atencion.traspasos TO app_asesor USING (asesor = atencion.asesor_actual())
  WITH CHECK (true);
DROP POLICY IF EXISTS asesor_asignado ON atencion.traspaso_eventos;
CREATE POLICY asesor_asignado ON atencion.traspaso_eventos TO app_asesor
  USING (traspaso_id IN (SELECT traspaso_id FROM atencion.traspasos)) WITH CHECK (true);
DROP POLICY IF EXISTS supervisor ON atencion.traspasos;
CREATE POLICY supervisor ON atencion.traspasos TO app_supervisor USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS supervisor ON atencion.traspaso_eventos;
CREATE POLICY supervisor ON atencion.traspaso_eventos TO app_supervisor USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS enrutador ON atencion.traspasos;
CREATE POLICY enrutador ON atencion.traspasos TO app_enrutador USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS enrutador ON atencion.traspaso_eventos;
CREATE POLICY enrutador ON atencion.traspaso_eventos TO app_enrutador USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS enrutador ON atencion.reclamos;
CREATE POLICY enrutador ON atencion.reclamos TO app_enrutador USING (true);

-- Datos de la cuenta para el asesor de un caso asignado; el supervisor, todo (enmascarado por la API y auditado).
DROP POLICY IF EXISTS asesor_asignado ON servicio.clientes;
CREATE POLICY asesor_asignado ON servicio.clientes FOR SELECT TO app_asesor USING (customer_id IN (SELECT atencion.clientes_del_asesor()));
DROP POLICY IF EXISTS asesor_asignado ON servicio.productos;
CREATE POLICY asesor_asignado ON servicio.productos FOR SELECT TO app_asesor USING (customer_id IN (SELECT atencion.clientes_del_asesor()));
DROP POLICY IF EXISTS asesor_asignado ON servicio.transacciones;
CREATE POLICY asesor_asignado ON servicio.transacciones FOR SELECT TO app_asesor USING (customer_id IN (SELECT atencion.clientes_del_asesor()));
DROP POLICY IF EXISTS supervisor ON servicio.clientes;
CREATE POLICY supervisor ON servicio.clientes FOR SELECT TO app_supervisor USING (true);
DROP POLICY IF EXISTS supervisor ON servicio.productos;
CREATE POLICY supervisor ON servicio.productos FOR SELECT TO app_supervisor USING (true);
DROP POLICY IF EXISTS supervisor ON servicio.transacciones;
CREATE POLICY supervisor ON servicio.transacciones FOR SELECT TO app_supervisor USING (true);

-- Conocimiento: el cliente y el visitante solo ven artículos públicos (un interno "no existe" para ellos).
DROP POLICY IF EXISTS publico ON atencion.conocimiento_articulos;
CREATE POLICY publico ON atencion.conocimiento_articulos FOR SELECT TO app_ejecucion USING (audiencia = 'publico');
DROP POLICY IF EXISTS equipo ON atencion.conocimiento_articulos;
CREATE POLICY equipo ON atencion.conocimiento_articulos FOR SELECT TO app_asesor, app_supervisor, app_observador USING (true);

-- Registro de turnos: el cliente solo el de su conversación (la vista en vivo usa el rol observador).
DROP POLICY IF EXISTS propio ON operacion.registro_turnos;
CREATE POLICY propio ON operacion.registro_turnos TO app_ejecucion
  USING (conversation_id = atencion.conversacion_actual()) WITH CHECK (conversation_id = atencion.conversacion_actual());
DROP POLICY IF EXISTS equipo ON operacion.registro_turnos;
CREATE POLICY equipo ON operacion.registro_turnos FOR SELECT TO app_supervisor, app_observador USING (true);

-- Cola enmascarada: sin datos del cliente; la leen el asesor, el supervisor y el observador.
CREATE OR REPLACE VIEW atencion.cola_enmascarada WITH (security_barrier) AS
  SELECT numero, habilidad, idioma, prioridad, nivel_desborde, estado, asesor, llegada, primera_respuesta_vence
  FROM atencion.traspasos WHERE estado IN ('en_cola','asignado','en_atencion','esperando_cliente');
GRANT SELECT ON atencion.cola_enmascarada TO app_asesor, app_supervisor, app_observador;

-- ---------- Transiciones validadas en la base ----------
ALTER TABLE atencion.reclamos DROP CONSTRAINT IF EXISTS negativa_explicada;
ALTER TABLE atencion.reclamos ADD CONSTRAINT negativa_explicada
  CHECK (estado NOT IN ('resuelto_en_contra','no_procede') OR (explicacion IS NOT NULL AND documentos IS NOT NULL));

CREATE OR REPLACE FUNCTION atencion.transicion_permitida(anterior text, nuevo text, autor text) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$
  SELECT (anterior, nuevo, autor) IN (
    ('abierto','en_revision','sistema'), ('abierto','en_revision','asesor'),
    ('abierto','retirado','cliente'), ('en_revision','retirado','cliente'), ('esperando_cliente','retirado','cliente'),
    ('en_revision','esperando_cliente','asesor'),
    ('esperando_cliente','en_revision','cliente'), ('esperando_cliente','en_revision','asesor'),
    ('en_revision','resuelto_a_favor','asesor'), ('en_revision','resuelto_en_contra','asesor'),
    ('en_revision','no_procede','asesor'),
    ('resuelto_a_favor','cerrado','asesor'), ('resuelto_en_contra','cerrado','asesor'), ('no_procede','cerrado','asesor'),
    ('resuelto_a_favor','cerrado','sistema'), ('resuelto_en_contra','cerrado','sistema'), ('no_procede','cerrado','sistema'),
    ('esperando_cliente','cerrado','sistema'),
    ('cerrado','en_revision','asesor'))
$$;

-- Cambia el estado con escritura condicional (versión y estado esperado) y deja el evento en la misma transacción.
-- SECURITY INVOKER: la RLS del rol que llama sigue aplicando. Devuelve la versión nueva o lanza NO_PERMITIDO/CONFLICTO.
CREATE OR REPLACE FUNCTION atencion.transicion_reclamo(p_reclamo text, p_nuevo text, p_autor_tipo text, p_autor text,
    p_motivo text, p_version int) RETURNS int LANGUAGE plpgsql AS $$
DECLARE r record; filas int;
BEGIN
  SELECT estado, version, customer_id INTO r FROM atencion.reclamos WHERE reclamo_id = p_reclamo;
  IF NOT FOUND THEN RAISE EXCEPTION 'NO_ENCONTRADO'; END IF;
  IF NOT atencion.transicion_permitida(r.estado, p_nuevo, p_autor_tipo) THEN
    RAISE EXCEPTION 'NO_PERMITIDO: % -> % por %', r.estado, p_nuevo, p_autor_tipo;
  END IF;
  IF p_nuevo IN ('retirado','en_revision') AND r.estado = 'cerrado' AND coalesce(p_motivo,'') = '' THEN
    RAISE EXCEPTION 'NO_PERMITIDO: reabrir exige motivo';
  END IF;
  UPDATE atencion.reclamos SET estado = p_nuevo, version = version + 1
    WHERE reclamo_id = p_reclamo AND version = p_version AND estado = r.estado;
  GET DIAGNOSTICS filas = ROW_COUNT;
  IF filas = 0 THEN RAISE EXCEPTION 'CONFLICTO'; END IF;
  INSERT INTO atencion.reclamo_eventos (reclamo_id, customer_id, estado_anterior, estado_nuevo, autor_tipo, autor, motivo)
    VALUES (p_reclamo, r.customer_id, r.estado, p_nuevo, p_autor_tipo, p_autor, p_motivo);
  RETURN p_version + 1;
END $$;
GRANT EXECUTE ON FUNCTION atencion.transicion_reclamo(text, text, text, text, text, int) TO app_ejecucion, app_asesor, app_supervisor;
