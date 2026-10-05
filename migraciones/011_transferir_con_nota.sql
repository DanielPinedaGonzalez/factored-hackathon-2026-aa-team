-- Transferir con nota (PROCESOS §P2.8): el asesor deja de ver el caso al transferirlo, así que la RLS no le permite
-- escribir la fila nueva. La función valida que quien transfiere sea el asesor asignado (o un supervisor) y hace todo
-- en una transacción: vuelve a la cola con su hora de llegada, agrega la nota al paquete, libera la carga y deja el evento.
CREATE OR REPLACE FUNCTION atencion.transferir(p_traspaso text, p_habilidad text, p_nota text, p_autor text, p_es_supervisor boolean)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = atencion, pg_temp AS $$
DECLARE t record;
BEGIN
  IF coalesce(trim(p_nota), '') = '' THEN RAISE EXCEPTION 'NO_PERMITIDO: no existe la transferencia sin nota'; END IF;
  IF p_habilidad NOT IN ('fraude','reclamos','general') THEN RAISE EXCEPTION 'NO_PERMITIDO: habilidad'; END IF;
  SELECT * INTO t FROM atencion.traspasos WHERE traspaso_id = p_traspaso FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'NO_ENCONTRADO'; END IF;
  IF NOT p_es_supervisor AND t.asesor IS DISTINCT FROM atencion.asesor_actual() THEN
    RAISE EXCEPTION 'NO_AUTORIZADO';
  END IF;
  UPDATE atencion.traspasos SET estado = 'en_cola', asesor = NULL, habilidad = p_habilidad, nivel_desborde = 0,
         paquete = jsonb_set(paquete, '{notas}', coalesce(paquete->'notas', '[]'::jsonb) ||
                   jsonb_build_array(jsonb_build_object('autor', p_autor, 'habilidad_destino', p_habilidad, 'texto', p_nota))),
         version = version + 1
   WHERE traspaso_id = p_traspaso;
  IF t.asesor IS NOT NULL THEN
    UPDATE atencion.asesor_carga SET carga = greatest(carga - 1, 0) WHERE employee_code = t.asesor;
  END IF;
  INSERT INTO atencion.traspaso_eventos (traspaso_id, evento, autor, detalle)
    VALUES (p_traspaso, 'transferido', p_autor, jsonb_build_object('habilidad', p_habilidad));
END $$;
REVOKE ALL ON FUNCTION atencion.transferir(text, text, text, text, boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION atencion.transferir(text, text, text, text, boolean) TO app_asesor, app_supervisor;
