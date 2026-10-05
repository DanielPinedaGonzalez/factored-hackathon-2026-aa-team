-- El equipo humano registra sus eventos de seguridad (rol negado).
GRANT INSERT ON operacion.eventos_seguridad TO app_asesor, app_supervisor;
GRANT USAGE ON SEQUENCE operacion.eventos_seguridad_id_seq TO app_asesor, app_supervisor;
