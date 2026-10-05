-- Purga por retención (MODELO_DATOS §5): los plazos viven en config/retencion.yaml y los aprueba cumplimiento. Nada
-- que registre un hecho de un caso se borra: se vacía el contenido que ya no hace falta (el texto de conversaciones
-- viejas sin caso activo, el archivo de adjuntos sin reclamo) y se borran solo registros técnicos vencidos. Cada
-- corrida deja un evento con sus conteos, nunca con el contenido.
CREATE TABLE IF NOT EXISTS operacion.purga_eventos (
  id bigserial PRIMARY KEY,
  plazos jsonb NOT NULL,
  conteos jsonb NOT NULL,
  creado timestamptz NOT NULL DEFAULT now()
);
GRANT SELECT ON operacion.purga_eventos TO app_supervisor, app_observador;

CREATE OR REPLACE FUNCTION operacion.purgar_por_retencion(p_conversaciones_dias int, p_adjuntos_dias int, p_registro_dias int)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = operacion, atencion, pg_temp AS $$
DECLARE
  limite_conv timestamptz := now() - make_interval(days => p_conversaciones_dias);
  limite_adj timestamptz := now() - make_interval(days => p_adjuntos_dias);
  limite_reg timestamptz := now() - make_interval(days => p_registro_dias);
  n_turnos int; n_estados int; n_adjuntos int; n_registro int; n_accesos int; n_seguridad int; conteos jsonb;
BEGIN
  -- Conversaciones cuyo último turno venció y que no tienen un caso vivo (traspaso activo o reclamo sin cerrar)
  CREATE TEMP TABLE vencidas ON COMMIT DROP AS
    SELECT t.conversation_id FROM atencion.turnos t GROUP BY 1 HAVING max(t.creado) < limite_conv
    EXCEPT SELECT conversation_id FROM atencion.traspasos
            WHERE estado IN ('en_cola','asignado','en_atencion','esperando_cliente')
    EXCEPT SELECT conversation_id FROM atencion.reclamos
            WHERE conversation_id IS NOT NULL AND estado IN ('abierto','en_revision','esperando_cliente');
  UPDATE atencion.turnos t SET texto = '', respuesta = jsonb_build_object('depurado_por_retencion', true)
   WHERE t.conversation_id IN (SELECT conversation_id FROM vencidas) AND t.texto <> '';
  GET DIAGNOSTICS n_turnos = ROW_COUNT;
  UPDATE atencion.estado_conversacion e SET estado = jsonb_set(e.estado, '{historial}', '[]'::jsonb)
   WHERE e.conversation_id IN (SELECT conversation_id FROM vencidas) AND jsonb_array_length(e.estado->'historial') > 0;
  GET DIAGNOSTICS n_estados = ROW_COUNT;
  UPDATE atencion.adjuntos SET contenido = NULL
   WHERE reclamo_id IS NULL AND creado < limite_adj AND contenido IS NOT NULL;
  GET DIAGNOSTICS n_adjuntos = ROW_COUNT;
  DELETE FROM operacion.registro_turnos WHERE creado < limite_reg;
  GET DIAGNOSTICS n_registro = ROW_COUNT;
  DELETE FROM operacion.accesos_pii WHERE creado < limite_reg;
  GET DIAGNOSTICS n_accesos = ROW_COUNT;
  DELETE FROM operacion.eventos_seguridad WHERE creado < limite_reg;
  GET DIAGNOSTICS n_seguridad = ROW_COUNT;
  conteos := jsonb_build_object('turnos_vaciados', n_turnos, 'historiales_vaciados', n_estados, 'adjuntos_vaciados', n_adjuntos,
                                'registro_turnos', n_registro, 'accesos_pii', n_accesos, 'eventos_seguridad', n_seguridad);
  INSERT INTO operacion.purga_eventos (plazos, conteos)
  VALUES (jsonb_build_object('conversaciones_dias', p_conversaciones_dias, 'adjuntos_sin_reclamo_dias', p_adjuntos_dias,
                             'registro_dias', p_registro_dias), conteos);
  RETURN conteos;
END $$;
REVOKE ALL ON FUNCTION operacion.purgar_por_retencion(int, int, int) FROM PUBLIC;
