-- Espera estimada al entrar a la cola (PROCESOS §P2.6): con ella se sabe cuándo la espera real la supera y el cliente
-- y el supervisor reciben el aviso. La calcula el enrutador al crear el traspaso, con la conexión del cliente.
ALTER TABLE atencion.traspasos ADD COLUMN IF NOT EXISTS espera_estimada_min int;
GRANT UPDATE (espera_estimada_min) ON atencion.traspasos TO app_ejecucion;
