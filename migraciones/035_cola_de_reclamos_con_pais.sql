-- La cola de investigación incluye el país del cliente (jurisdicción, sin datos personales): con él se cuentan los
-- días hábiles que le quedan al plazo y se marca la alarma (PROCESOS §P3).
DROP FUNCTION IF EXISTS atencion.cola_reclamos(text);
CREATE FUNCTION atencion.cola_reclamos(p_habilidad text)
RETURNS TABLE (reclamo_id text, numero text, tipo_disputa text, prioridad int, habilidad text, plazo_vence date,
               creado timestamptz, pais text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = atencion, pg_temp AS $$
  SELECT r.reclamo_id, r.numero, r.tipo_disputa, r.prioridad, r.habilidad, r.plazo_vence, r.creado, c.pais
    FROM atencion.reclamos r LEFT JOIN servicio.clientes c USING (customer_id)
   WHERE r.estado = 'abierto' AND r.asesor IS NULL AND r.habilidad = p_habilidad
   ORDER BY r.prioridad, r.plazo_vence NULLS LAST, r.creado
$$;
REVOKE ALL ON FUNCTION atencion.cola_reclamos(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION atencion.cola_reclamos(text) TO app_asesor, app_supervisor, app_observador;
