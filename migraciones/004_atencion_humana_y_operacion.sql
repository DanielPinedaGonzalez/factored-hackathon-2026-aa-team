-- Atención humana (PROCESOS §P2), base de conocimiento (ARQUITECTURA §8.8) y operación (MODELO_DATOS §2.3).

CREATE TABLE IF NOT EXISTS atencion.asesores (
  employee_code text PRIMARY KEY,
  habilidad text NOT NULL CHECK (habilidad IN ('fraude','reclamos','general')),
  idiomas text[] NOT NULL,
  canal text NOT NULL,                          -- Digital | Hybrid
  turno text NOT NULL,                          -- Morning | Afternoon | Night | Rotating
  pais text,
  rol text NOT NULL DEFAULT 'asesor' CHECK (rol IN ('asesor','supervisor')),
  demo boolean NOT NULL DEFAULT false           -- identidades con las que entran el jurado y el equipo
);
CREATE TABLE IF NOT EXISTS atencion.asesor_presencia_eventos (
  id bigserial PRIMARY KEY,
  employee_code text NOT NULL REFERENCES atencion.asesores,
  presencia text NOT NULL CHECK (presencia IN ('desconectado','disponible','en_pausa','ausente')),
  capacidad int NOT NULL DEFAULT 1 CHECK (capacidad BETWEEN 1 AND 3),
  creado timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS atencion.asesor_carga (   -- carga actual; se incrementa con escritura condicional
  employee_code text PRIMARY KEY REFERENCES atencion.asesores,
  carga int NOT NULL DEFAULT 0 CHECK (carga >= 0),
  ultima_asignacion timestamptz
);
CREATE TABLE IF NOT EXISTS atencion.traspasos (
  traspaso_id text PRIMARY KEY,
  numero text UNIQUE NOT NULL,                  -- visible: T-000101
  conversation_id text NOT NULL,
  customer_id text,
  paquete jsonb NOT NULL,
  habilidad text NOT NULL,
  idioma text NOT NULL,
  prioridad int NOT NULL CHECK (prioridad BETWEEN 1 AND 4),
  segmento text,                                -- solo para ordenar la espera (D-17)
  nivel_desborde int NOT NULL DEFAULT 0,
  asesor text,
  estado text NOT NULL DEFAULT 'en_cola' CHECK (estado IN ('en_cola','asignado','en_atencion','esperando_cliente',
         'resuelto','devuelto_al_sistema')),
  llegada timestamptz NOT NULL DEFAULT now(),
  primera_respuesta_vence timestamptz NOT NULL,
  seguimiento_vence timestamptz,
  asignado_en timestamptz,
  version_config text NOT NULL,
  version int NOT NULL DEFAULT 0
);
CREATE SEQUENCE IF NOT EXISTS atencion.traspaso_numero START 101;
-- Un solo traspaso activo por conversación.
CREATE UNIQUE INDEX IF NOT EXISTS traspaso_activo ON atencion.traspasos (conversation_id)
  WHERE estado IN ('en_cola','asignado','en_atencion','esperando_cliente');
CREATE INDEX IF NOT EXISTS traspasos_cola ON atencion.traspasos (habilidad, idioma, prioridad, llegada);
CREATE TABLE IF NOT EXISTS atencion.traspaso_eventos (
  id bigserial PRIMARY KEY,
  traspaso_id text NOT NULL REFERENCES atencion.traspasos,
  evento text NOT NULL,
  autor text,
  detalle jsonb NOT NULL DEFAULT '{}',
  creado timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS atencion.mensajes_asesor (
  id bigserial PRIMARY KEY,
  traspaso_id text NOT NULL REFERENCES atencion.traspasos,
  conversation_id text NOT NULL,
  customer_id text,
  asesor text NOT NULL,
  texto text NOT NULL,
  origen text NOT NULL CHECK (origen IN ('escrito','sugerido_sin_editar','sugerido_editado')),
  version_prompt text,
  creado timestamptz NOT NULL DEFAULT now()
);

-- ---------- Base de conocimiento ----------
CREATE TABLE IF NOT EXISTS atencion.conocimiento_articulos (
  id text NOT NULL,
  version int NOT NULL,
  estado text NOT NULL,
  audiencia text NOT NULL CHECK (audiencia IN ('publico','interno')),
  paises text[] NOT NULL,
  criticidad text NOT NULL,
  titulo text NOT NULL,
  cabecera jsonb NOT NULL,
  cuerpo_es text NOT NULL,
  cuerpo_pt text,
  fallas_seguidas int NOT NULL DEFAULT 0,
  busqueda tsvector,
  PRIMARY KEY (id, version)
);
CREATE INDEX IF NOT EXISTS conocimiento_busqueda ON atencion.conocimiento_articulos USING gin (busqueda);
CREATE TABLE IF NOT EXISTS atencion.conocimiento_eventos (
  id bigserial PRIMARY KEY,
  articulo text NOT NULL,
  version int,
  evento text NOT NULL,
  detalle jsonb NOT NULL DEFAULT '{}',
  creado timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS atencion.conocimiento_marcas (
  id bigserial PRIMARY KEY,
  articulo text NOT NULL,
  asesor text NOT NULL,
  marca text NOT NULL CHECK (marca IN ('incorrecto','incompleto','falta')),
  traspaso_id text,
  nota text,
  creado timestamptz NOT NULL DEFAULT now()
);

-- ---------- Operación ----------
CREATE TABLE IF NOT EXISTS operacion.registro_turnos (
  turn_id text PRIMARY KEY,
  conversation_id text NOT NULL,
  customer_id text,
  n int NOT NULL,
  registro jsonb NOT NULL,                      -- sin PII: marcadores, versiones, decisiones, latencias
  creado timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS registro_por_conversacion ON operacion.registro_turnos (conversation_id, n);
CREATE TABLE IF NOT EXISTS operacion.consumo_modelos (
  id bigserial PRIMARY KEY,
  conversation_id text,
  turn_id text,
  proveedor text NOT NULL,
  modelo text NOT NULL,
  proposito text NOT NULL,
  tokens_entrada int NOT NULL DEFAULT 0,
  tokens_salida int NOT NULL DEFAULT 0,
  peticiones int NOT NULL DEFAULT 1,
  cupo_restante jsonb,
  tamano_mensaje int,
  latencia_ms double precision,
  espera_s double precision,
  resultado text NOT NULL,
  hash_prompt text,
  creado timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS operacion.accesos_pii (
  id bigserial PRIMARY KEY,
  persona text NOT NULL,
  rol text NOT NULL,
  traspaso_id text,
  motivo text,
  creado timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS operacion.eventos_seguridad (
  id bigserial PRIMARY KEY,
  tipo text NOT NULL,                           -- codigo_fallido, limite_alcanzado, token_invalido, rol_negado...
  ip text,
  detalle jsonb NOT NULL DEFAULT '{}',          -- sin PII
  creado timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS operacion.artefactos (
  nombre text,
  version text,
  hash text NOT NULL,
  contenido jsonb,
  creado timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (nombre, version)
);
