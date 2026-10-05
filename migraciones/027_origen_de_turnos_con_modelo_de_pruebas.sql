-- Corrección de datos (una vez), complemento de la 025: los turnos de pruebas anteriores al origen cuyo modelo falló
-- antes de dejar su versión (la falla inyectada) no los atrapó el criterio por versión. Se identifican sin ambigüedad
-- por su conversación, que llamó al modelo de pruebas. No se borra nada.
UPDATE operacion.registro_turnos SET origen = 'pruebas'
  WHERE origen = 'operacion'
    AND conversation_id IN (SELECT conversation_id FROM operacion.consumo_modelos
                            WHERE modelo = 'falso' AND conversation_id IS NOT NULL);
