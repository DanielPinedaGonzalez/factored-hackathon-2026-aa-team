-- La posición en la cola se calcula sin ver datos de otros clientes: solo prioridad, segmento y llegada.
CREATE OR REPLACE FUNCTION atencion.fila_cola(p_habilidad text, p_idioma text)
RETURNS TABLE (traspaso_id text, numero text, prioridad int, segmento text, llegada timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = atencion, pg_temp AS $$
  SELECT traspaso_id, numero, prioridad, CASE WHEN segmento = 'Premium' THEN 'Premium' END, llegada
  FROM atencion.traspasos WHERE estado = 'en_cola' AND habilidad = p_habilidad AND idioma = p_idioma
$$;
REVOKE ALL ON FUNCTION atencion.fila_cola(text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION atencion.fila_cola(text, text) TO app_ejecucion, app_enrutador, app_asesor, app_supervisor;
