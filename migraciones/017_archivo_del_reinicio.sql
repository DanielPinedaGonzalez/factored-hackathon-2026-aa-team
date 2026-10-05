-- El reinicio de la demo no destruye la auditoría: antes de borrar, copia cada fila tal cual a un archivo que solo
-- admite inserciones. La reconstrucción de una conversación (A13) lee también de aquí.
CREATE TABLE IF NOT EXISTS operacion.archivo_reinicio (
  id bigserial PRIMARY KEY,
  tabla text NOT NULL,
  conversation_id text,
  fila jsonb NOT NULL,
  archivado timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS archivo_por_conversacion ON operacion.archivo_reinicio (conversation_id);
REVOKE UPDATE, DELETE ON operacion.archivo_reinicio FROM PUBLIC;
GRANT SELECT ON operacion.archivo_reinicio TO app_supervisor, app_observador;

CREATE OR REPLACE FUNCTION atencion.reiniciar_demo() RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = atencion, pg_temp AS $$
DECLARE ids text[]; casos text[]; recs text[]; blqs text[];
BEGIN
  SELECT array_agg(customer_id) INTO ids FROM atencion.identidades_demo WHERE documento_demo LIKE 'DEMO-%';
  SELECT array_agg(traspaso_id) INTO casos FROM atencion.traspasos WHERE customer_id = ANY(ids) OR customer_id IS NULL;
  SELECT array_agg(reclamo_id) INTO recs FROM atencion.reclamos WHERE customer_id = ANY(ids);
  SELECT array_agg(bloqueo_id) INTO blqs FROM atencion.bloqueos WHERE customer_id = ANY(ids);
  INSERT INTO operacion.archivo_reinicio (tabla, conversation_id, fila)
    SELECT 'reclamos', conversation_id, to_jsonb(r) FROM atencion.reclamos r WHERE reclamo_id = ANY(recs)
    UNION ALL SELECT 'reclamo_eventos', r.conversation_id, to_jsonb(e) FROM atencion.reclamo_eventos e
      JOIN atencion.reclamos r USING (reclamo_id) WHERE e.reclamo_id = ANY(recs)
    UNION ALL SELECT 'reclamo_notas', r.conversation_id, to_jsonb(n) FROM atencion.reclamo_notas n
      JOIN atencion.reclamos r USING (reclamo_id) WHERE n.reclamo_id = ANY(recs)
    UNION ALL SELECT 'bloqueos', i.conversation_id, to_jsonb(b) FROM atencion.bloqueos b
      LEFT JOIN atencion.intenciones_accion i USING (action_intent_id) WHERE b.bloqueo_id = ANY(blqs)
    UNION ALL SELECT 'bloqueo_eventos', i.conversation_id, to_jsonb(e) FROM atencion.bloqueo_eventos e
      JOIN atencion.bloqueos b USING (bloqueo_id) LEFT JOIN atencion.intenciones_accion i ON i.action_intent_id = b.action_intent_id
      WHERE e.bloqueo_id = ANY(blqs)
    UNION ALL SELECT 'traspasos', conversation_id, to_jsonb(t) FROM atencion.traspasos t WHERE traspaso_id = ANY(casos)
    UNION ALL SELECT 'traspaso_eventos', t.conversation_id, to_jsonb(e) || jsonb_build_object('numero', t.numero)
      FROM atencion.traspaso_eventos e JOIN atencion.traspasos t USING (traspaso_id) WHERE e.traspaso_id = ANY(casos)
    UNION ALL SELECT 'mensajes_asesor', conversation_id, to_jsonb(m) FROM atencion.mensajes_asesor m
      WHERE customer_id = ANY(ids) OR traspaso_id = ANY(casos);
  DELETE FROM atencion.reclamo_eventos WHERE reclamo_id = ANY(recs);
  DELETE FROM atencion.reclamo_notas WHERE reclamo_id = ANY(recs);
  DELETE FROM atencion.reclamos WHERE reclamo_id = ANY(recs);
  DELETE FROM atencion.bloqueo_eventos WHERE bloqueo_id = ANY(blqs);
  DELETE FROM atencion.bloqueos WHERE bloqueo_id = ANY(blqs);
  UPDATE atencion.asesor_carga k SET carga = greatest(k.carga - x.n, 0)
    FROM (SELECT asesor, count(*) n FROM atencion.traspasos WHERE traspaso_id = ANY(casos)
          AND estado IN ('asignado','en_atencion','esperando_cliente') AND asesor IS NOT NULL GROUP BY asesor) x
   WHERE k.employee_code = x.asesor;
  DELETE FROM atencion.mensajes_asesor WHERE customer_id = ANY(ids) OR traspaso_id = ANY(casos);
  DELETE FROM atencion.traspaso_eventos WHERE traspaso_id = ANY(casos);
  DELETE FROM atencion.traspasos WHERE traspaso_id = ANY(casos);
  RETURN coalesce(array_length(ids, 1), 0);
END $$;
REVOKE ALL ON FUNCTION atencion.reiniciar_demo() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION atencion.reiniciar_demo() TO app_identidad;
