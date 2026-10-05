-- Al arrancar, el pool lee del registro la última espera que pidió el proveedor por llave (sin datos personales).
GRANT SELECT (id, proveedor, llave, resultado, error, creado) ON operacion.consumo_modelos TO app_ejecucion;
