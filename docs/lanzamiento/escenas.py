"""Las escenas de la película de lanzamiento: una sola fuente para la película (`lanzamiento.html`) y para el guion (`privado/GUION_VIDEO.md`).

Historia de una sola clienta, de la notificación al cierre (guion v6). Cada frase de voz va en inglés sencillo y, entre paréntesis, su sentido en español.
Las cifras son las medidas y están en `docs/REPORTE_EVALUACION.md`, `docs/01_DIAGNOSTICO.md` y `artefactos/`.
`seg` es la duración de la escena; si existe `audio/duraciones.json` (lo escribe `voz.py` con la voz elegida), manda la duración real del audio más una pausa.
`sync` ata cada frase a lo que se enciende en pantalla: [fragmento de la frase, acción]; la película calcula cuándo se dice ese fragmento por su posición en el texto."""
import json
from pathlib import Path

PAUSA_S = 0.5
ESCENAS = [
    {"id": 'hook', "bloque": 'WHY', "seg": 10,
     "en": 'A customer gets a notification: a charge she does not recognize. She cannot tell if it is hers, a mistake, or fraud.',
     "es": 'Una clienta recibe un aviso: un cargo que no reconoce. No sabe si es suyo, un error o un fraude.',
     "visual": "El aviso de un cargo en un teléfono, sin canal ni marca; el título «A charge you don't recognize».",
     "sync": []},
    {"id": 'problem', "bloque": 'WHY', "seg": 10,
     "en": 'She calls the bank, and waits. In its synthetic data, only forty-four percent of complaint calls are resolved, against ninety-two for simple transactions.',
     "es": 'Llama al banco y espera. En sus datos sintéticos, solo el 44 % de las llamadas por quejas se resuelve, frente al 92 % de las transacciones simples.',
     "visual": 'Barras de motivos de llamada que crecen; la de quejas, en rojo, se queda en 44 %; pie con la fuente (datos sintéticos del organizador).',
     "sync": []},
    {"id": 'core', "bloque": 'WHY', "seg": 7,
     "en": "I chose this complaint because a system can check it against the customer's own account data.",
     "es": 'Elegí esta queja porque un sistema puede comprobarla con los datos de la cuenta del propio cliente.',
     "visual": 'Del cargo salen tres tarjetas, una por una al nombrarlas: compra olvidada · error de procesamiento · fraude; al final, «a system can check the facts».',
     "sync": [["I chose this complaint", "c1"], ["a system can check", "c4"]]},
    {"id": 'reveal', "bloque": 'WHAT', "seg": 10,
     "en": "Instead of waiting on the phone, she opens the bank's app and meets Lora. Lora answers by text, in Spanish and Portuguese.",
     "es": 'En lugar de esperar al teléfono, abre la app del banco y conoce a Lora. Lora responde por texto, en español y portugués.',
     "visual": 'Abre el chat dentro de la app del banco; el loro llega volando, aterriza; el nombre «Lora».',
     "sync": []},
    {"id": 'map', "bloque": 'HOW', "seg": 15,
     "en": 'Behind her words are fifteen steps. Lora checks who she is and searches only her own transactions. The model understands her message; the code finds the charge, and the database lets her read only her own rows.',
     "es": 'Detrás de sus palabras hay quince pasos. Lora verifica quién es y busca solo en sus propias transacciones. El modelo entiende su mensaje; el código encuentra el cargo, y la base solo le deja leer sus propias filas.',
     "visual": 'Aparece el mapa de 15 pasos; el chat con la tarjeta del cargo; los nodos se encienden cuando la voz los nombra.',
     "sync": [["fifteen steps", "mapa"], ["checks who she is", "N1"], ["her own transactions", "N3"], ["The model understands", "N2"], ["the code finds the charge", "N5"], ["only her own rows", "candado"]]},
    {"id": 'policy', "bloque": 'HOW', "seg": 10,
     "en": 'Then the policy decides. Four checks must all pass: irreversibility against certainty; same case, same treatment; a person always available; care for the relationship.',
     "es": 'Entonces decide la política. Deben cumplirse las cuatro verificaciones: irreversibilidad frente a certeza; mismo caso, mismo trato; una persona siempre disponible; cuidado de la relación.',
     "visual": 'El nodo Policy se abre en cuatro tarjetas, una por una al nombrarse; al final el sello «all four must pass».',
     "sync": [["Then the policy decides", "N6"], ["irreversibility against certainty", "v1"], ["same case, same treatment", "v2"], ["a person always available", "v3"], ["care for the relationship", "v4"]]},
    {"id": 'outcomes', "bloque": 'HOW', "seg": 17,
     "en": 'If she recognizes it, it ends there. If not, with her confirmation, Lora opens a claim and re-reads the database. If the fraud score is above a certified cut-off, Lora offers to block the card, she decides, and the case goes to a human fraud agent at priority one.',
     "es": 'Si ella lo reconoce, termina ahí. Si no, con su confirmación, Lora abre un reclamo y relee la base. Si el puntaje de fraude está por encima de un corte certificado, Lora ofrece bloquear la tarjeta, ella decide, y el caso va a un agente humano de fraude con prioridad uno.',
     "visual": 'Tres caminos: cerrado sin reclamo · reclamo con su confirmación y relectura · puntaje sobre el corte certificado: se ofrece bloquear y un agente humano de fraude con prioridad.',
     "sync": [["If she recognizes it", "N12"], ["with her confirmation", "N7"], ["re-reads the database", "N9"], ["above a certified cut-off", "score"], ["offers to block the card", "bloqueo"], ["the case goes to a human fraud agent", "agente"]]},
    {"id": 'm1', "bloque": 'HOW', "seg": 23,
     "en": "The bank already provides a fraud score for most transactions. I calibrated it on two years of data. A separate six-month set certified that wrong blocks stay below one percent, with ninety-five percent confidence. In the final test it caught fifty-seven percent of fraud, against forty-two with the bank's own cut-off, and none of the 347 recommended blocks was wrong.",
     "es": 'El banco ya da un puntaje de fraude para la mayoría de las transacciones. Lo calibré con dos años de datos. Un conjunto aparte de seis meses certificó que los bloqueos equivocados quedan por debajo del uno por ciento, con 95 % de confianza. En la prueba final atrapó el 57 % del fraude, frente al 42 % con el corte del propio banco, y ninguno de los 347 bloqueos recomendados fue incorrecto.',
     "visual": 'La escala de 0 a 100 con el corte certificado (30) y el del banco (50); tres tramos de tiempo (aprender · certificar · probar); dos barras 57,5 % contra 42,0 %; «0 of 347».',
     "sync": [["The bank already provides a fraud score", "escala"], ["two years of data", "t1"], ["A separate six-month set", "t2"], ["In the final test", "t3"], ["fifty-seven percent", "b57"], ["forty-two", "b42"], ["none of the 347", "cero"]]},
    {"id": 'person', "bloque": 'HOW', "seg": 12,
     "en": 'At any moment she can ask for a person. The human agent receives the whole case, so she repeats nothing. Lora shows her the current queue position and estimated wait.',
     "es": 'En cualquier momento puede pedir una persona. El agente humano recibe todo el caso, así que ella no repite nada. Lora le muestra su posición actual en la fila y la espera estimada.',
     "visual": 'La barra «Handover to a person (from any step)»; el paquete del caso; la posición en la fila y la espera estimada.',
     "sync": [["ask for a person", "N11"], ["receives the whole case", "paquete"], ["current queue position", "fila"]]},
    {"id": 'checks', "bloque": 'HOW', "seg": 17,
     "en": 'The model writes with placeholders; the code fills in the real figures, rejects free-standing numbers, and checks that every claimed action was completed. We tested the policy on all 98,304 combinations of facts: none let an action through with a check unmet.',
     "es": 'El modelo escribe con marcadores; el código pone las cifras reales, rechaza los números sueltos y comprueba que cada acción mencionada se haya completado. Probamos la política con las 98.304 combinaciones de hechos: ninguna dejó pasar una acción con una verificación sin cumplir.',
     "visual": 'Sellos sobre el mapa: «text check» (marcadores llenos, cifra suelta rechazada) y «re-read» en Verify; el contador de 98,304 combinaciones y 0 violaciones.',
     "sync": [["writes with placeholders", "texto"], ["fills in the real figures", "rellena"], ["free-standing numbers", "rechaza"], ["every claimed action", "N9"], ["98,304 combinations", "contador"]]},
    {"id": 'proof', "bloque": 'HOW', "seg": 19,
     "en": 'On sixty-two test cases run once, Lora passed fifty-five. A generic assistant, same model and tools, with the rules only in its prompt, passed twenty-three, with eleven out-of-policy actions. Lora had one, and we report it. These are offline results on synthetic data, not production.',
     "es": 'En 62 casos de prueba corridos una vez, Lora pasó 55. Un asistente genérico, mismo modelo y herramientas, con las reglas solo en el prompt, pasó 23, con 11 acciones fuera de política. Lora tuvo una, y lo reportamos. Son resultados fuera de línea con datos sintéticos, no de producción.',
     "visual": 'Barras: 55 de 62 contra 23 de 62; acciones fuera de política 1 contra 11; intervalo de Wilson al 95 % rotulado; «offline · synthetic data».',
     "sync": [["passed fifty-five", "p55"], ["passed twenty-three", "p23"], ["eleven out-of-policy", "u11"], ["Lora had one", "u1"]]},
    {"id": 'close', "bloque": 'CLOSE', "seg": 17,
     "en": 'For her, a clear answer. For the human agent, a complete case. For the bank, every action with its rule and its evidence. Lora: the virtual assistant for banks, for the charges customers do not recognize. Thank you.',
     "es": 'Para ella, una respuesta clara. Para el agente humano, un caso completo. Para el banco, cada acción con su regla y su evidencia. Lora: la asistente virtual para bancos, para los cargos que el cliente no reconoce. Gracias.',
     "visual": 'Tres columnas (la clienta, el agente humano, el banco); Lora y su descripción; el loro se va; créditos y «narration: AI voice».',
     "sync": []},
]

_DUR = Path(__file__).resolve().parent / "audio" / "duraciones.json"
if _DUR.exists():
    _d = json.loads(_DUR.read_text())
    for _e in ESCENAS:
        if _e["id"] in _d:
            _e["dur"] = _d[_e["id"]]
            _e["seg"] = round(_d[_e["id"]] + PAUSA_S, 1)

# El chat de «demo1»: lo que dijo el modelo real en una corrida grabada (`evaluacion/corridas/20261004T041117_propuesto_desarrollo.json`, caso A1,
# sistema 8b0cfffd5f73), copiado tal cual, sin retocar. El mensaje del cliente es la sugerencia de la demo. Cliente sintético, sin identificadores.
CHAT_REAL = [
    {"quien": "cliente", "texto": "me salió un cobro raro ayer, yo no hice eso"},
    {"quien": "lora", "texto": "Detecté un movimiento de $ 68.693,69 ARS en tu cuenta el 25 de julio de 2025 a las 02:12 en Cable TV, Mendoza. ¿Reconoces este cargo?",
     "tarjeta": {"titulo": "Charge C1", "linea": "Cable TV · $ 68.693,69 ARS", "detalle": "25 Jul 2025 · 02:12 · Mendoza"}},
    {"quien": "cliente", "texto": "No lo reconozco", "boton": True},
    {"quien": "lora", "texto": "Entiendo que ese cargo no lo reconoces. Puedes abrir un reclamo para que revisemos el movimiento; abrir un reclamo inicia una revisión y una persona del banco decidirá si corresponde una devolución, aunque abrirlo no asegura que la devolución se realice. ¿Quieres que proceda a abrir el reclamo?",
     "boton_accion": "Yes, do it"},
    {"quien": "cliente", "texto": "Yes, do it", "boton": True},
    {"quien": "lora", "texto": "Tu reclamo quedó registrado con el número de caso R-000442. El banco tiene hasta 8 de agosto de 2025 para responder. Abrir un reclamo inicia una revisión y una persona del banco decidirá si corresponde una devolución, aunque abrirlo no asegura que la devolución se realice. ¿Necesitas ayuda con algo más?",
     "caso": {"numero": "R-000442", "estado": "open", "plazo": "8 Aug 2025"}},
]
