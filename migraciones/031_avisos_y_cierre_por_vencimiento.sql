-- Avisos al cliente (PROCESOS §P3, §P5): cada cambio de estado de un reclamo que no hizo el propio cliente (una
-- decisión del asesor, un cierre del sistema) deja un aviso con sus hechos; el cliente lo ve al volver.
CREATE OR REPLACE FUNCTION atencion.aviso_por_evento_de_reclamo() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = atencion, pg_temp AS $$
DECLARE r record;
BEGIN
  IF NEW.autor_tipo = 'cliente' OR NEW.estado_anterior IS NULL THEN
    RETURN NEW;
  END IF;
  SELECT numero, conversation_id INTO r FROM atencion.reclamos WHERE reclamo_id = NEW.reclamo_id;
  INSERT INTO atencion.avisos_cliente (customer_id, conversation_id, hechos)
  VALUES (NEW.customer_id, r.conversation_id,
          jsonb_build_object('reclamo', r.numero, 'estado_anterior', NEW.estado_anterior, 'estado_nuevo', NEW.estado_nuevo,
                             'autor_tipo', NEW.autor_tipo, 'motivo', NEW.motivo));
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS aviso_al_cliente ON atencion.reclamo_eventos;
CREATE TRIGGER aviso_al_cliente AFTER INSERT ON atencion.reclamo_eventos
  FOR EACH ROW EXECUTE FUNCTION atencion.aviso_por_evento_de_reclamo();
GRANT UPDATE (leido) ON atencion.avisos_cliente TO app_ejecucion;

-- Cierre por vencimiento (MODELO_DATOS §3.1): un reclamo que espera al cliente y no recibe respuesta en el plazo que
-- decide el banco (parámetro de operación) se cierra con evento del sistema; el disparador de arriba deja el aviso.
CREATE OR REPLACE FUNCTION atencion.cerrar_reclamos_sin_respuesta(p_dias int) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = atencion, pg_temp AS $$
DECLARE r record; n int := 0;
BEGIN
  FOR r IN
    SELECT c.reclamo_id, c.version FROM atencion.reclamos c
     WHERE c.estado = 'esperando_cliente'
       AND (SELECT max(e.creado) FROM atencion.reclamo_eventos e
             WHERE e.reclamo_id = c.reclamo_id AND e.estado_nuevo = 'esperando_cliente') < now() - make_interval(days => p_dias)
  LOOP
    PERFORM atencion.transicion_reclamo(r.reclamo_id, 'cerrado', 'sistema', NULL,
                                        format('vencimiento administrativo: sin respuesta del cliente en %s días', p_dias), r.version);
    n := n + 1;
  END LOOP;
  RETURN n;
END $$;
REVOKE ALL ON FUNCTION atencion.cerrar_reclamos_sin_respuesta(int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION atencion.cerrar_reclamos_sin_respuesta(int) TO app_enrutador;
