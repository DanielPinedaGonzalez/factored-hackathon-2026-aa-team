-- El origen lo fija la conexión en cada transacción (app.origen: operacion | pruebas | evaluacion); toda fila nueva
-- de registro lo toma por defecto, sin que cada inserción tenga que recordarlo.
CREATE OR REPLACE FUNCTION operacion.origen_actual() RETURNS text LANGUAGE sql STABLE AS
  $$ SELECT coalesce(nullif(current_setting('app.origen', true), ''), 'operacion') $$;
ALTER TABLE operacion.consumo_modelos ALTER COLUMN origen SET DEFAULT operacion.origen_actual();
ALTER TABLE operacion.incidentes ALTER COLUMN origen SET DEFAULT operacion.origen_actual();
ALTER TABLE operacion.eventos_seguridad ALTER COLUMN origen SET DEFAULT operacion.origen_actual();
ALTER TABLE operacion.registro_turnos ADD COLUMN IF NOT EXISTS origen text NOT NULL DEFAULT operacion.origen_actual();
GRANT EXECUTE ON FUNCTION operacion.origen_actual() TO PUBLIC;
