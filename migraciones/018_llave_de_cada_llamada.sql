-- Qué llave del pool respondió cada llamada (su índice, nunca la llave): el tablero del sistema reparte el consumo.
ALTER TABLE operacion.consumo_modelos ADD COLUMN IF NOT EXISTS llave smallint;
