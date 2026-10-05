-- Quién cambió un bloqueo, no solo qué tipo de autor: sin esto un desbloqueo hecho por un asesor no se puede atribuir.
ALTER TABLE atencion.bloqueo_eventos ADD COLUMN IF NOT EXISTS autor text;
