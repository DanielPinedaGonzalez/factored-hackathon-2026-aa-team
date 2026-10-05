-- Investigación del reclamo en back-office (PROCESOS §P3). El asesor ve la cola de reclamos de su habilidad sin datos
-- del cliente, toma el siguiente y, desde ese momento, ve lo necesario para investigarlo: la misma regla de acceso que
-- un caso en vivo asignado (clientes_del_asesor), ampliada a los reclamos que tomó.

-- Reclamos que el asesor tiene en investigación. SECURITY DEFINER: lee reclamos sin pasar por su propia política,
-- que a su vez usa clientes_del_asesor (así no hay recursión).
CREATE OR REPLACE FUNCTION atencion.clientes_en_investigacion() RETURNS SETOF text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = atencion, pg_temp AS $$
  SELECT customer_id FROM atencion.reclamos
   WHERE asesor = atencion.asesor_actual() AND estado IN ('en_revision','esperando_cliente','resuelto_a_favor','resuelto_en_contra','no_procede')
$$;
CREATE OR REPLACE FUNCTION atencion.clientes_del_asesor() RETURNS SETOF text LANGUAGE sql STABLE AS $$
  SELECT customer_id FROM atencion.traspasos
  WHERE asesor = atencion.asesor_actual() AND estado IN ('asignado','en_atencion','esperando_cliente')
    AND customer_id IS NOT NULL
  UNION
  SELECT atencion.clientes_en_investigacion()
$$;

-- Cola de investigación, sin datos del cliente: lo que hace falta para elegir qué tomar.
CREATE OR REPLACE FUNCTION atencion.cola_reclamos(p_habilidad text)
RETURNS TABLE (reclamo_id text, numero text, tipo_disputa text, prioridad int, habilidad text, plazo_vence date, creado timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = atencion, pg_temp AS $$
  SELECT reclamo_id, numero, tipo_disputa, prioridad, habilidad, plazo_vence, creado FROM atencion.reclamos
   WHERE estado = 'abierto' AND asesor IS NULL AND habilidad = p_habilidad
   ORDER BY prioridad, plazo_vence NULLS LAST, creado
$$;

-- Tomar el siguiente: uno a la vez (PROCESOS §P2.1). Solo si la habilidad del asesor es la del reclamo; escritura
-- condicional para que dos asesores no tomen el mismo.
CREATE OR REPLACE FUNCTION atencion.tomar_siguiente_reclamo(p_asesor text) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = atencion, pg_temp AS $$
DECLARE hab text; elegido text;
BEGIN
  SELECT habilidad INTO hab FROM atencion.asesores WHERE employee_code = p_asesor;
  IF hab IS NULL OR hab NOT IN ('fraude','reclamos') THEN RAISE EXCEPTION 'NO_PERMITIDO: habilidad %', hab; END IF;
  IF EXISTS (SELECT 1 FROM atencion.reclamos WHERE asesor = p_asesor AND estado = 'en_revision') THEN
    RAISE EXCEPTION 'NO_PERMITIDO: ya tiene un reclamo en revisión';
  END IF;
  SELECT c.reclamo_id INTO elegido FROM atencion.cola_reclamos(hab) c LIMIT 1;
  IF elegido IS NULL THEN RETURN NULL; END IF;
  UPDATE atencion.reclamos SET asesor = p_asesor WHERE reclamo_id = elegido AND asesor IS NULL AND estado = 'abierto';
  IF NOT FOUND THEN RAISE EXCEPTION 'CONFLICTO'; END IF;
  PERFORM atencion.transicion_reclamo(elegido, 'en_revision', 'asesor', p_asesor, 'tomado para investigar',
                                      (SELECT version FROM atencion.reclamos WHERE reclamo_id = elegido));
  RETURN elegido;
END $$;
REVOKE ALL ON FUNCTION atencion.cola_reclamos(text), atencion.tomar_siguiente_reclamo(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION atencion.cola_reclamos(text) TO app_asesor, app_supervisor, app_observador;
GRANT EXECUTE ON FUNCTION atencion.tomar_siguiente_reclamo(text) TO app_asesor;
GRANT EXECUTE ON FUNCTION atencion.clientes_en_investigacion() TO app_asesor;
