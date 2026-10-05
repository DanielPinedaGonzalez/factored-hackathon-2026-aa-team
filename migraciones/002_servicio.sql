-- Datos del banco para atender: solo lectura para la aplicación; los escribe el pipeline (MODELO_DATOS §2.1).
-- Sin documento, teléfono ni correo: no hacen falta para atender.
CREATE TABLE IF NOT EXISTS servicio.clientes (
  customer_id text PRIMARY KEY,
  pais text,                          -- MX | CO | AR; NULL = desconocido
  segmento text,
  estado text,
  acento text,
  nombre_pila text                    -- solo el primer nombre, para que el asesor salude
);
CREATE TABLE IF NOT EXISTS servicio.productos (
  product_id text PRIMARY KEY,
  customer_id text NOT NULL REFERENCES servicio.clientes,
  tipo text NOT NULL,
  estado text,
  moneda text,
  ultimos4 text                       -- últimos cuatro del número de producto; nunca el número completo
);
CREATE TABLE IF NOT EXISTS servicio.transacciones (
  transaction_id text PRIMARY KEY,
  customer_id text NOT NULL REFERENCES servicio.clientes,
  product_id text REFERENCES servicio.productos,
  fecha timestamp NOT NULL,
  tipo text,
  categoria text,
  monto numeric(18,2),
  moneda text,
  amount_usd numeric(18,2),           -- del organizador o derivado con tasa del día; NULL = desconocido
  canal text,
  comercio text,
  categoria_comercio text,
  pais_transaccion text,
  ciudad text,
  estado text,
  codigo_respuesta text,
  fraud_score double precision,       -- NULL = sin score
  canal_tipo_coherente boolean,
  moneda_pais_coherente boolean,
  fecha_producto_coherente boolean
);
CREATE INDEX IF NOT EXISTS transacciones_cliente_fecha ON servicio.transacciones (customer_id, fecha DESC);
CREATE TABLE IF NOT EXISTS servicio.tasas_cambio (fecha date, moneda text, tasa numeric, PRIMARY KEY (fecha, moneda));
CREATE TABLE IF NOT EXISTS servicio.datos_version (
  id int PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  data_as_of date NOT NULL,
  hash_manifest text NOT NULL,
  cargado timestamptz NOT NULL DEFAULT now()
);

GRANT SELECT ON ALL TABLES IN SCHEMA servicio TO app_ejecucion, app_asesor, app_supervisor, app_observador;

ALTER TABLE servicio.clientes ENABLE ROW LEVEL SECURITY;      ALTER TABLE servicio.clientes FORCE ROW LEVEL SECURITY;
ALTER TABLE servicio.productos ENABLE ROW LEVEL SECURITY;     ALTER TABLE servicio.productos FORCE ROW LEVEL SECURITY;
ALTER TABLE servicio.transacciones ENABLE ROW LEVEL SECURITY; ALTER TABLE servicio.transacciones FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS cliente_propio ON servicio.clientes;
CREATE POLICY cliente_propio ON servicio.clientes FOR SELECT TO app_ejecucion USING (customer_id = atencion.sujeto());
DROP POLICY IF EXISTS cliente_propio ON servicio.productos;
CREATE POLICY cliente_propio ON servicio.productos FOR SELECT TO app_ejecucion USING (customer_id = atencion.sujeto());
DROP POLICY IF EXISTS cliente_propio ON servicio.transacciones;
CREATE POLICY cliente_propio ON servicio.transacciones FOR SELECT TO app_ejecucion USING (customer_id = atencion.sujeto());
-- El equipo humano ve los datos del cliente de un caso asignado (políticas en 005).
