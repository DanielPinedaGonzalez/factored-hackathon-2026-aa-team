-- Esquemas y roles (MODELO_DATOS §1 y §4; SEGURIDAD §3). Todos NOSUPERUSER NOBYPASSRLS.
-- app_api solo se conecta; en cada transacción asume un rol con SET LOCAL ROLE (PostgreSQL 16: INHERIT FALSE, SET TRUE).
DO $$
DECLARE r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['app_ejecucion','app_identidad','app_asesor','app_supervisor','app_observador'] LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
      EXECUTE format('CREATE ROLE %I NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE', r);
    END IF;
  END LOOP;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_api') THEN
    CREATE ROLE app_api LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD 'app_api_local';
  END IF;
END $$;

GRANT app_ejecucion, app_identidad, app_asesor, app_supervisor, app_observador TO app_api WITH INHERIT FALSE, SET TRUE;

CREATE SCHEMA IF NOT EXISTS servicio;
CREATE SCHEMA IF NOT EXISTS atencion;
CREATE SCHEMA IF NOT EXISTS operacion;
CREATE SCHEMA IF NOT EXISTS evaluacion;

GRANT USAGE ON SCHEMA servicio, atencion, operacion TO app_ejecucion, app_asesor, app_supervisor, app_observador;
GRANT USAGE ON SCHEMA atencion TO app_identidad;
GRANT USAGE ON SCHEMA servicio, atencion, operacion TO app_api;

-- Sujeto de la transacción: lo fija la API con SET LOCAL desde el token, nunca desde el modelo ni el mensaje.
CREATE OR REPLACE FUNCTION atencion.sujeto() RETURNS text LANGUAGE sql STABLE AS
$$ SELECT nullif(current_setting('app.customer_id', true), '') $$;
CREATE OR REPLACE FUNCTION atencion.conversacion_actual() RETURNS text LANGUAGE sql STABLE AS
$$ SELECT nullif(current_setting('app.conversation_id', true), '') $$;
CREATE OR REPLACE FUNCTION atencion.asesor_actual() RETURNS text LANGUAGE sql STABLE AS
$$ SELECT nullif(current_setting('app.asesor_id', true), '') $$;
