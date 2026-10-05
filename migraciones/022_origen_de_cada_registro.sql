-- Cada registro dice de dónde viene: la operación, las pruebas automáticas o la evaluación. La cabina y los
-- indicadores muestran solo la operación; nada se borra.
ALTER TABLE operacion.consumo_modelos ADD COLUMN IF NOT EXISTS origen text NOT NULL DEFAULT 'operacion';
ALTER TABLE operacion.incidentes ADD COLUMN IF NOT EXISTS origen text NOT NULL DEFAULT 'operacion';
ALTER TABLE operacion.eventos_seguridad ADD COLUMN IF NOT EXISTS origen text NOT NULL DEFAULT 'operacion';
