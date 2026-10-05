-- Corrección de datos (una vez): lo que escribieron las pruebas y la evaluación antes de que existiera el origen se
-- re-etiqueta por lo que lo identifica sin ambigüedad (modelo de pruebas, IP ficticia de las pruebas, mensaje de la
-- falla inyectada). No se borra nada.
UPDATE operacion.consumo_modelos SET origen = 'pruebas' WHERE origen = 'operacion' AND modelo IN ('falso', 'm1', 'm2');
UPDATE operacion.consumo_modelos SET origen = 'evaluacion' WHERE origen = 'operacion' AND (conversation_id LIKE 'eval\_%' OR modelo = 'evaluacion');
UPDATE operacion.incidentes SET origen = 'pruebas' WHERE origen = 'operacion' AND mensaje LIKE 'falla de prueba%';
UPDATE operacion.eventos_seguridad SET origen = 'pruebas'
  WHERE origen = 'operacion' AND (ip LIKE '10.0.0.%' OR ip = 'testclient' OR ip LIKE 'prueba-%' OR (ip IS NULL AND tipo = 'rol_negado'));
UPDATE operacion.eventos_seguridad SET origen = 'evaluacion' WHERE origen = 'operacion' AND ip IN ('evaluacion', 'enumeracion');
UPDATE operacion.registro_turnos SET origen = 'evaluacion' WHERE origen = 'operacion' AND conversation_id LIKE 'eval\_%';
UPDATE operacion.registro_turnos SET origen = 'pruebas' WHERE origen = 'operacion' AND registro->'versiones'->>'modelo' LIKE '%falso%';
