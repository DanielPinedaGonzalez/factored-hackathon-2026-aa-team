-- El registro devuelve el número del incidente (referencia para el cliente): necesita leer solo esa columna.
GRANT SELECT (id) ON operacion.incidentes TO app_ejecucion;
