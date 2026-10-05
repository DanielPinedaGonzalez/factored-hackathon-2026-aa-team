-- Toda falla con su razón real: cada llamada al modelo que falla queda con el código y el mensaje del proveedor, y
-- lo inesperado (una excepción no prevista) queda como incidente con dónde, qué y el rastro. Solo inserciones.
ALTER TABLE operacion.consumo_modelos ADD COLUMN IF NOT EXISTS error text;
ALTER TABLE operacion.consumo_modelos ADD COLUMN IF NOT EXISTS http_estado smallint;
CREATE TABLE IF NOT EXISTS operacion.incidentes (
  id bigserial PRIMARY KEY,
  creado timestamptz NOT NULL DEFAULT now(),
  donde text NOT NULL,                         -- componente o ruta: 'api POST /conversacion/turno', 'orquestador'...
  tipo text NOT NULL,                          -- clase de la excepción o tipo de incidente
  mensaje text NOT NULL DEFAULT '',
  severidad text NOT NULL DEFAULT 'error' CHECK (severidad IN ('critica','error','advertencia')),
  rastro text,                                 -- el traceback; nunca datos de la cuenta
  conversation_id text,
  turn_id text,
  detalle jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS incidentes_por_fecha ON operacion.incidentes (creado);
GRANT INSERT ON operacion.incidentes TO app_ejecucion;
GRANT USAGE ON SEQUENCE operacion.incidentes_id_seq TO app_ejecucion;
GRANT SELECT ON operacion.incidentes TO app_supervisor, app_observador;
REVOKE UPDATE, DELETE ON operacion.incidentes FROM PUBLIC;
