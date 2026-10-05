-- El servicio de identidad registra sus eventos de seguridad (código fallido, límite alcanzado).
GRANT USAGE ON SCHEMA operacion TO app_identidad;
GRANT USAGE ON SEQUENCE operacion.eventos_seguridad_id_seq, atencion.buzon_sandbox_id_seq TO app_identidad;
