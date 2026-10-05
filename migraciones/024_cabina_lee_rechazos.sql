-- La cabina muestra los rechazos de la API (eventos de seguridad) al supervisor y al observador.
GRANT SELECT ON operacion.eventos_seguridad TO app_supervisor, app_observador;
