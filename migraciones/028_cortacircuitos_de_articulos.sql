-- Cortacircuitos por artículo (GOBERNANZA §11.8): cada respuesta con un artículo informa si pasó la verificación al
-- primer intento. Las fallas seguidas se cuentan; al llegar al tope, el artículo se retira solo (inactivo) y queda el
-- evento para su dueño. Un acierto vuelve el contador a cero. La aplicación no escribe la tabla: solo esta función.
CREATE OR REPLACE FUNCTION atencion.resultado_articulo(p_id text, p_version int, p_ok boolean, p_tope int)
RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = atencion, pg_temp AS $$
DECLARE n int; e text;
BEGIN
  UPDATE atencion.conocimiento_articulos
     SET fallas_seguidas = CASE WHEN p_ok THEN 0 ELSE fallas_seguidas + 1 END
   WHERE id = p_id AND version = p_version
  RETURNING fallas_seguidas, estado INTO n, e;
  IF n IS NULL THEN
    RETURN NULL;
  END IF;
  IF NOT p_ok AND n >= p_tope AND e <> 'inactivo' THEN
    UPDATE atencion.conocimiento_articulos SET estado = 'inactivo' WHERE id = p_id AND version = p_version;
    INSERT INTO atencion.conocimiento_eventos (articulo, version, evento, detalle)
    VALUES (p_id, p_version, 'cortacircuitos', jsonb_build_object('fallas_seguidas', n, 'estado_anterior', e));
    RETURN 'inactivo';
  END IF;
  RETURN e;
END $$;
REVOKE ALL ON FUNCTION atencion.resultado_articulo(text, int, boolean, int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION atencion.resultado_articulo(text, int, boolean, int) TO app_ejecucion;
