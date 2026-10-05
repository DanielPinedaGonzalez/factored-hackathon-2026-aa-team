-- Parámetros de operación que decide el banco, no el código (PROCESOS §P9): se ven en la cabina y los cambia un
-- supervisor desde la operación, con motivo. Cada cambio queda como evento de solo agregar. Sin fila, rige el valor
-- inicial de la configuración del repositorio.
CREATE TABLE IF NOT EXISTS operacion.parametros (
  clave text PRIMARY KEY,
  valor jsonb NOT NULL,
  actualizado_por text NOT NULL,
  actualizado_en timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS operacion.parametro_eventos (
  id bigserial PRIMARY KEY,
  clave text NOT NULL,
  valor_anterior jsonb,
  valor_nuevo jsonb NOT NULL,
  autor text NOT NULL,
  motivo text NOT NULL CHECK (length(trim(motivo)) > 0),
  creado timestamptz NOT NULL DEFAULT now()
);
GRANT SELECT ON operacion.parametros TO app_ejecucion, app_asesor, app_supervisor, app_observador, app_enrutador;
GRANT SELECT ON operacion.parametro_eventos TO app_supervisor, app_observador;

CREATE OR REPLACE FUNCTION operacion.cambiar_parametro(p_clave text, p_valor jsonb, p_autor text, p_motivo text)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = operacion, pg_temp AS $$
DECLARE anterior jsonb;
BEGIN
  SELECT valor INTO anterior FROM operacion.parametros WHERE clave = p_clave;
  INSERT INTO operacion.parametros (clave, valor, actualizado_por) VALUES (p_clave, p_valor, p_autor)
  ON CONFLICT (clave) DO UPDATE SET valor = excluded.valor, actualizado_por = excluded.actualizado_por, actualizado_en = now();
  INSERT INTO operacion.parametro_eventos (clave, valor_anterior, valor_nuevo, autor, motivo)
  VALUES (p_clave, anterior, p_valor, p_autor, p_motivo);
END $$;
REVOKE ALL ON FUNCTION operacion.cambiar_parametro(text, jsonb, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION operacion.cambiar_parametro(text, jsonb, text, text) TO app_supervisor;
