-- Cerrar un reclamo decidido (PROCESOS §P3). Al cerrarse, el asesor deja de ver los datos de ese cliente (la regla de
-- acceso solo cubre reclamos en investigación), así que el cierre lo registra esta función: comprueba que el reclamo es
-- suyo y está decidido, y deja el evento por la transición de siempre.
CREATE OR REPLACE FUNCTION atencion.cerrar_reclamo_decidido(p_reclamo text, p_asesor text) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = atencion, pg_temp AS $$
DECLARE r record;
BEGIN
  SELECT estado, version, asesor INTO r FROM atencion.reclamos WHERE reclamo_id = p_reclamo;
  IF NOT FOUND OR r.asesor IS DISTINCT FROM p_asesor THEN RAISE EXCEPTION 'NO_ENCONTRADO'; END IF;
  IF r.estado NOT IN ('resuelto_a_favor','resuelto_en_contra','no_procede') THEN
    RAISE EXCEPTION 'NO_PERMITIDO: solo se cierra un reclamo decidido (está %)', r.estado;
  END IF;
  RETURN atencion.transicion_reclamo(p_reclamo, 'cerrado', 'asesor', p_asesor, 'cerrado por el asesor', r.version);
END $$;
REVOKE ALL ON FUNCTION atencion.cerrar_reclamo_decidido(text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION atencion.cerrar_reclamo_decidido(text, text) TO app_asesor;
