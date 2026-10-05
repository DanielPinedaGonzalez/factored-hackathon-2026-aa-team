-- Identidad, conversaciones, casos, acciones y atención humana (MODELO_DATOS §2.2, §3).
-- Nada que registre un hecho se borra: ningún rol de la aplicación tiene DELETE.

-- ---------- Identidad (rol app_identidad; el cliente todavía no es sujeto) ----------
CREATE TABLE IF NOT EXISTS atencion.identidades_demo (
  customer_id text PRIMARY KEY REFERENCES servicio.clientes,
  documento_demo text UNIQUE NOT NULL,          -- creado por el equipo; el del organizador no se despliega
  canales text[] NOT NULL                       -- enmascarados: {"celular ••77", "correo s•••@proton"}
);
CREATE TABLE IF NOT EXISTS atencion.desafios_otp (
  desafio_id text PRIMARY KEY,
  documento_hash text NOT NULL,
  customer_id text,                             -- NULL si el documento no existe (misma respuesta hacia afuera)
  codigo_hash text,
  intentos int NOT NULL DEFAULT 0,
  ip text,
  vence timestamptz NOT NULL,
  consumido boolean NOT NULL DEFAULT false,
  creado timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS desafios_doc ON atencion.desafios_otp (documento_hash, creado);
CREATE INDEX IF NOT EXISTS desafios_ip ON atencion.desafios_otp (ip, creado);
CREATE TABLE IF NOT EXISTS atencion.buzon_sandbox (   -- el "celular" y el "correo" de la demo
  id bigserial PRIMARY KEY,
  customer_id text NOT NULL,
  canal text NOT NULL,
  mensaje text NOT NULL,
  creado timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS atencion.sesiones (
  session_id text PRIMARY KEY,
  customer_id text NOT NULL,
  vence timestamptz NOT NULL,
  estado text NOT NULL DEFAULT 'activa',
  creado timestamptz NOT NULL DEFAULT now()
);

-- ---------- Conversación ----------
CREATE TABLE IF NOT EXISTS atencion.conversaciones (
  conversation_id text PRIMARY KEY,
  customer_id text,
  canal text NOT NULL DEFAULT 'chat',
  idioma text NOT NULL DEFAULT 'es',
  estado text NOT NULL DEFAULT 'abierta' CHECK (estado IN ('abierta','inactiva','con_humano','cerrada')),
  reloj date NOT NULL,                          -- reloj del sandbox de esta conversación
  version int NOT NULL DEFAULT 0,
  creado timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS atencion.estado_conversacion (
  conversation_id text PRIMARY KEY REFERENCES atencion.conversaciones,
  customer_id text,
  version int NOT NULL,
  estado jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS atencion.turnos (
  conversation_id text REFERENCES atencion.conversaciones,
  n int,
  customer_id text,
  rol text NOT NULL,
  texto text NOT NULL,                          -- con marcadores; nunca números de tarjeta ni secretos
  mensaje_cliente_id text,                      -- identificador del cliente: un reenvío no se procesa dos veces
  respuesta jsonb,
  creado timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (conversation_id, n)
);
CREATE UNIQUE INDEX IF NOT EXISTS turnos_mensaje_unico ON atencion.turnos (conversation_id, mensaje_cliente_id)
  WHERE mensaje_cliente_id IS NOT NULL;

-- ---------- Reclamo (el caso) ----------
CREATE SEQUENCE IF NOT EXISTS atencion.reclamo_numero START 101;
CREATE TABLE IF NOT EXISTS atencion.reclamos (
  reclamo_id text PRIMARY KEY,
  numero text UNIQUE NOT NULL,                  -- visible para el cliente: R-000101
  customer_id text NOT NULL,
  transaction_id text NOT NULL,
  product_id text,
  tipo_disputa text NOT NULL,
  estado text NOT NULL DEFAULT 'abierto' CHECK (estado IN ('abierto','en_revision','esperando_cliente',
         'resuelto_a_favor','resuelto_en_contra','no_procede','cerrado','retirado')),
  prioridad int NOT NULL DEFAULT 4,
  plazo_vence date,
  plazo_fuente text,
  grupo text,
  habilidad text,
  asesor text,
  investigacion_vence timestamptz,
  conversation_id text,
  action_intent_id text UNIQUE,
  explicacion text,
  documentos text[],
  referencia_abono text,
  version int NOT NULL DEFAULT 0,
  creado timestamptz NOT NULL DEFAULT now()
);
-- Un reclamo por cargo mientras esté activo; el tipo se corrige dentro del mismo reclamo.
CREATE UNIQUE INDEX IF NOT EXISTS reclamo_activo_por_cargo ON atencion.reclamos (customer_id, transaction_id)
  WHERE estado IN ('abierto','en_revision','esperando_cliente');
CREATE INDEX IF NOT EXISTS reclamos_cola ON atencion.reclamos (habilidad, prioridad, creado);
CREATE TABLE IF NOT EXISTS atencion.reclamo_eventos (
  id bigserial PRIMARY KEY,
  reclamo_id text NOT NULL REFERENCES atencion.reclamos,
  customer_id text NOT NULL,
  estado_anterior text,
  estado_nuevo text NOT NULL,
  autor_tipo text NOT NULL CHECK (autor_tipo IN ('cliente','sistema','asesor')),
  autor text,
  motivo text,
  creado timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS atencion.reclamo_notas (
  id bigserial PRIMARY KEY,
  reclamo_id text NOT NULL REFERENCES atencion.reclamos,
  customer_id text NOT NULL,
  autor_tipo text NOT NULL,
  texto text,
  adjunto_id text,
  action_intent_id text UNIQUE,
  creado timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS atencion.adjuntos (
  adjunto_id text PRIMARY KEY,
  customer_id text,
  conversation_id text NOT NULL,
  reclamo_id text,
  tipo text NOT NULL,
  tamano int NOT NULL,
  hash text NOT NULL,
  contenido bytea,                              -- nivel restringido: nunca a un modelo
  creado timestamptz NOT NULL DEFAULT now()
);

-- ---------- Intención de acción (una confirmación = una acción exacta, una vez) ----------
CREATE TABLE IF NOT EXISTS atencion.intenciones_accion (
  action_intent_id text PRIMARY KEY,
  conversation_id text NOT NULL,
  customer_id text NOT NULL,
  session_id text NOT NULL,
  conversation_version int NOT NULL,
  accion text NOT NULL,
  recurso text NOT NULL,
  parametros jsonb NOT NULL DEFAULT '{}',
  hash_propuesta text NOT NULL,
  estado text NOT NULL DEFAULT 'propuesta' CHECK (estado IN ('propuesta','confirmada','ejecutando','completada',
         'fallida','desconocida','descartada')),
  resultado jsonb,
  expira timestamptz NOT NULL,
  creado timestamptz NOT NULL DEFAULT now()
);

-- ---------- Bloqueo temporal ----------
CREATE TABLE IF NOT EXISTS atencion.bloqueos (
  bloqueo_id text PRIMARY KEY,
  customer_id text NOT NULL,
  product_id text NOT NULL,
  origen text NOT NULL CHECK (origen IN ('cliente','riesgo','asesor')),
  motivo text,
  estado text NOT NULL DEFAULT 'bloqueado_temporal' CHECK (estado IN ('bloqueado_temporal','activo','escalado_a_reemplazo')),
  action_intent_id text UNIQUE,
  version int NOT NULL DEFAULT 0,
  creado timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS bloqueo_activo_por_producto ON atencion.bloqueos (product_id) WHERE estado = 'bloqueado_temporal';
CREATE TABLE IF NOT EXISTS atencion.bloqueo_eventos (
  id bigserial PRIMARY KEY,
  bloqueo_id text NOT NULL REFERENCES atencion.bloqueos,
  customer_id text NOT NULL,
  estado_anterior text,
  estado_nuevo text NOT NULL,
  autor_tipo text NOT NULL,
  motivo text,
  creado timestamptz NOT NULL DEFAULT now()
);

-- ---------- Avisos al cliente (quedan no leídos hasta que vuelve) ----------
CREATE TABLE IF NOT EXISTS atencion.avisos_cliente (
  id bigserial PRIMARY KEY,
  customer_id text NOT NULL,
  conversation_id text,
  hechos jsonb NOT NULL,                        -- el aviso se redacta al mostrarlo, con estos hechos
  leido boolean NOT NULL DEFAULT false,
  creado timestamptz NOT NULL DEFAULT now()
);
