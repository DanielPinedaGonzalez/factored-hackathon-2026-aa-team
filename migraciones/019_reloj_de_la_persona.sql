-- El reloj de una conversación en vivo es el de la persona (zona de su país), calculado en cada turno: la columna
-- guarda solo el reloj fijado de la evaluación. Nulo = conversación en vivo.
ALTER TABLE atencion.conversaciones ALTER COLUMN reloj DROP NOT NULL;
