-- Saber si una conversación existe sin ver sus datos: con la sesión vencida, la RLS la oculta y el sistema debe pedir
-- la identidad otra vez en lugar de crear otra conversación con el mismo identificador.
CREATE OR REPLACE FUNCTION atencion.conversacion_existe(p_conversation text) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = atencion, pg_temp AS $$
  SELECT EXISTS (SELECT 1 FROM atencion.conversaciones WHERE conversation_id = p_conversation)
$$;
REVOKE ALL ON FUNCTION atencion.conversacion_existe(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION atencion.conversacion_existe(text) TO app_ejecucion;
