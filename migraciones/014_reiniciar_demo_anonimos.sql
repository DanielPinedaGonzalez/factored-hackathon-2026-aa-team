-- Reinicio de la demo, también para quien pidió una persona sin identificarse: sus casos no tienen cliente, y si no se
-- liberan ocupan para siempre la capacidad de los asesores de demo. Los de clientes de la evaluación no se tocan.
CREATE OR REPLACE FUNCTION atencion.reiniciar_demo() RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = atencion, pg_temp AS $$
DECLARE ids text[]; casos text[];
BEGIN
  SELECT array_agg(customer_id) INTO ids FROM atencion.identidades_demo WHERE documento_demo LIKE 'DEMO-%';
  SELECT array_agg(traspaso_id) INTO casos FROM atencion.traspasos WHERE customer_id = ANY(ids) OR customer_id IS NULL;
  DELETE FROM atencion.reclamo_eventos WHERE customer_id = ANY(ids);
  DELETE FROM atencion.reclamo_notas WHERE customer_id = ANY(ids);
  DELETE FROM atencion.reclamos WHERE customer_id = ANY(ids);
  DELETE FROM atencion.bloqueo_eventos WHERE customer_id = ANY(ids);
  DELETE FROM atencion.bloqueos WHERE customer_id = ANY(ids);
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
