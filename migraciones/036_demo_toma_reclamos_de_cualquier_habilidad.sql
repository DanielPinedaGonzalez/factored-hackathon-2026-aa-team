-- La demo declara (config/atencion_humana.yaml) que sus identidades reciben casos de cualquier habilidad. El back-office de reclamos debe ser coherente:
-- una identidad de DEMO puede tomar el siguiente reclamo de cualquier habilidad; una que no lo es sigue limitada a la suya. Lo comprueba la base, no la API.
-- Aditiva: una firma nueva; la anterior sigue igual.
CREATE OR REPLACE FUNCTION atencion.tomar_siguiente_reclamo(p_asesor text, p_cualquiera boolean) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = atencion, pg_temp AS $$
DECLARE hab text; es_demo boolean; elegido text;
BEGIN
  SELECT habilidad, demo INTO hab, es_demo FROM atencion.asesores WHERE employee_code = p_asesor;
  IF hab IS NULL THEN RAISE EXCEPTION 'NO_PERMITIDO: asesor desconocido'; END IF;
  IF p_cualquiera AND NOT coalesce(es_demo, false) THEN RAISE EXCEPTION 'NO_PERMITIDO: solo las identidades de demo toman reclamos de cualquier habilidad'; END IF;
  IF NOT p_cualquiera AND hab NOT IN ('fraude','reclamos') THEN RAISE EXCEPTION 'NO_PERMITIDO: habilidad %', hab; END IF;
  IF EXISTS (SELECT 1 FROM atencion.reclamos WHERE asesor = p_asesor AND estado = 'en_revision') THEN
    RAISE EXCEPTION 'NO_PERMITIDO: ya tiene un reclamo en revisión';
  END IF;
  IF p_cualquiera THEN
    SELECT q.reclamo_id INTO elegido FROM (SELECT * FROM atencion.cola_reclamos('fraude') UNION ALL SELECT * FROM atencion.cola_reclamos('reclamos')) q
     ORDER BY q.prioridad, q.plazo_vence NULLS LAST, q.creado LIMIT 1;
  ELSE
    SELECT c.reclamo_id INTO elegido FROM atencion.cola_reclamos(hab) c LIMIT 1;
  END IF;
  IF elegido IS NULL THEN RETURN NULL; END IF;
  UPDATE atencion.reclamos SET asesor = p_asesor WHERE reclamo_id = elegido AND asesor IS NULL AND estado = 'abierto';
  IF NOT FOUND THEN RAISE EXCEPTION 'CONFLICTO'; END IF;
  PERFORM atencion.transicion_reclamo(elegido, 'en_revision', 'asesor', p_asesor, 'tomado para investigar',
                                      (SELECT version FROM atencion.reclamos WHERE reclamo_id = elegido));
  RETURN elegido;
END $$;
REVOKE ALL ON FUNCTION atencion.tomar_siguiente_reclamo(text, boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION atencion.tomar_siguiente_reclamo(text, boolean) TO app_asesor;
