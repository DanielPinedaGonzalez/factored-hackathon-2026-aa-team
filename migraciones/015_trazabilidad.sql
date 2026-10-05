-- Trazabilidad por llamada al modelo: el identificador que da el proveedor, para cruzar una falla con su registro.
ALTER TABLE operacion.consumo_modelos ADD COLUMN IF NOT EXISTS request_id text;
CREATE INDEX IF NOT EXISTS consumo_por_conversacion ON operacion.consumo_modelos (conversation_id, id);
