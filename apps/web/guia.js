// Presenter notes (Notas del presentador): short on-screen commentary that says what each screen shows and what just happened.
// (Comentarios cortos en pantalla: qué muestra cada pantalla y qué acaba de pasar.)
// Always English first, Spanish in parentheses, whatever the interface language is: the jurors read English and the presenter reads the Spanish.
// (Siempre inglés primero y el español entre paréntesis, sin importar el idioma de la interfaz.)
// These are interface labels, not conversation with the customer: the assistant's replies are still written by the model.
// (Son rótulos de la interfaz, no conversación con el cliente: las respuestas del asistente las sigue escribiendo el modelo.)

import { EN } from "./i18n_en.js";

const CLAVE = "guia_activa";

export function guiaActiva() {
  try { return localStorage.getItem(CLAVE) !== "no"; } catch { return true; }      // on by default (activa por defecto)
}
export function fijarGuia(activa) {
  try { localStorage.setItem(CLAVE, activa ? "si" : "no"); } catch { }
  document.body.classList.toggle("sin-guia", !activa);
}

function el(tag, attrs = {}, ...hijos) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  e.append(...hijos.filter(h => h !== null && h !== undefined));
  return e;
}

// One note: English line + Spanish line in parentheses (una nota: línea en inglés y su sentido en español entre paréntesis).
export function nota([en, es], { titulo = "Presenter note" } = {}) {
  return el("div", { class: "nota-guia", role: "note" },
    el("strong", {}, `🎙 ${titulo}`), el("span", { class: "nota-en" }, en), el("span", { class: "nota-es" }, `(${es})`));
}

// What each screen is for (qué es cada pantalla). Key: the hash route.
export const NOTAS_VISTA = {
  "#/jurado": ["Seven test customers, picked from the bank's 150,000 so they differ in country, products and history. Pick one, then write anything you like to Lora.",
    "Siete clientes de prueba, escogidos entre los 150.000 del banco para que se diferencien en país, productos e historial. Elige uno y escríbele a Lora lo que quieras."],
  "#/cliente": ["What the customer sees: the bank app.", "Lo que ve el cliente: la app del banco."],
  "#/vista": ["The conversation, and what the system did.", "La conversación, y lo que hizo el sistema."],
  "#/operacion": ["The bank's side: a person gets the case.", "El lado del banco: una persona recibe el caso."],
  "#/sistema": ["System health: model, spend, alerts.", "Salud del sistema: modelo, gasto, alertas."],
};

// What just happened in the turn, by the state the conversation ends in (qué pasó en el turno, según el nodo en que termina).
export const NOTAS_NODO = {
  N0: ["Not signed in. It only gives public information.",
    "Sin sesión. Solo da información pública."],
  N1: ["Waiting for sign-in. The form never goes to the model.",
    "Esperando el inicio de sesión. El formulario nunca llega al modelo."],
  N2: ["The model understood the message. Nothing ran yet.",
    "El modelo entendió el mensaje. Todavía no se ejecutó nada."],
  N4: ["One detail is missing, or several charges match. It asks. It does not guess.",
    "Falta un dato, o varios cargos coinciden. Pregunta. No adivina."],
  N5: ["The real transaction, from the database. The customer says if they recognize it.",
    "La transacción real, de la base de datos. El cliente dice si la reconoce."],
  N7: ["The policy allows an action. It waits for the customer to confirm.",
    "La política permite una acción. Espera que el cliente confirme."],
  N10: ["Done and checked: the code read the database again. Only now does it say so.",
    "Hecho y comprobado: el código volvió a leer la base de datos. Solo ahora lo dice."],
  N11: ["A person takes the case, with the facts, the actions taken and a priority.",
    "Una persona toma el caso, con los hechos, las acciones hechas y una prioridad."],
  N12: ["The customer recognized the charge. Closed, but they can still claim.",
    "El cliente reconoció el cargo. Se cierra, pero aún puede reclamar."],
  N13: ["Not something it can do. It says what it can do. It promises nothing.",
    "No es algo que pueda hacer. Dice qué sí puede hacer. No promete nada."],
  N14: ["Not a banking request, or a trick. It does nothing and stays neutral.",
    "No es una petición bancaria, o es un truco. No hace nada y se mantiene neutral."],
};
export const NOTA_SIN_MODELO = ["The model was not available, so a person takes over. That is the design.",
  "El modelo no estuvo disponible, así que una persona toma el caso. Es el diseño."];

export const NOTA_NO_SE_LEYO = ["The model answered, but its answer could not be read. Nothing ran: the customer is asked to say it another way.",
  "El modelo respondió, pero su respuesta no se pudo leer. No se ejecutó nada: se le pide al cliente que lo diga de otra forma."];
export const NOTA_PASO_FALLO = ["A step of this turn did not complete. The steps below show what each part reported; nothing more is claimed.",
  "Un paso de este turno no se completó. Los pasos de abajo muestran lo que informó cada parte; no se afirma nada más."];

// The note for the last turn of a conversation (la nota del último turno), read from its trace record. The node's sentence says what the node means,
// so it is shown only when no step of the turn failed: a note must never claim something the trace contradicts (la nota no afirma lo que la traza contradice).
export function notaDeTurno(registro) {
  if (!registro) return null;
  const fallos = (registro.pasos || []).filter(p => p.estado === "fallo");
  const par = registro.sin_modelo ? NOTA_SIN_MODELO
    : fallos.some(p => p.componente === "interprete") ? NOTA_NO_SE_LEYO
    : fallos.length ? NOTA_PASO_FALLO
    : NOTAS_NODO[registro.nodo_despues];
  return par ? nota(par, { titulo: "What just happened" }) : null;
}

// A plain explanatory line, English first and the Spanish in parentheses (una línea explicativa: inglés y el español entre paréntesis).
// `par` is [english, spanish]; a bare Spanish string is looked up in the interface dictionary (un texto en español se busca en el diccionario).
export function bilingue(par, clase = "suave") {
  const [en, es] = typeof par === "string" ? [EN[par] ?? par, par] : par;
  return el("div", { class: `bil ${clase}` }, el("span", { class: "nota-en" }, en), " ", el("span", { class: "nota-es" }, `(${es})`));
}

// Texts of the demo screen (textos de la pantalla de demostración).
export const TEXTOS_DEMO = {
  elegir: ["Pick a customer. Hover over a card to see what is in their account; once picked, you are signed in as them.",
    "Elige un cliente. Pasa el mouse sobre una tarjeta para ver lo que hay en su cuenta; al elegirlo, ya estás dentro como ese cliente."],
  probar: ["Click a message, or write your own, in Spanish or Portuguese.",
    "Pulsa un mensaje, o escribe el tuyo, en español o portugués."],
  noPuede: ["What it cannot do: it says so and offers a person. A trick does nothing.",
    "Lo que no puede hacer: lo dice y ofrece una persona. Un truco no hace nada."],
  siPuede: ["What it can do: pass your case to a person with everything gathered, and answer from the bank's articles.",
    "Lo que sí puede hacer: pasar tu caso a una persona con todo reunido, y responder con los artículos del banco."],
  movimientos: ["The customer's account, straight from the database.",
    "La cuenta del cliente, directo de la base de datos."],
  sinSesion: ["Not signed in. The assistant gives public information and shows the secure sign-in form. After you sign in, the account appears here.",
    "Sin sesión. El asistente da información pública y muestra el formulario seguro. Al iniciar sesión, aquí aparece la cuenta."],
  vacio: ["Send a message and see what the system does, step by step. A ✗ means that step had nothing to do.",
    "Envía un mensaje y mira qué hace el sistema, paso a paso. Una ✗ significa que ese paso no tenía nada que hacer."],
};

// The "About" screen: the key lines and the honest limits, in one place (la pantalla About: las frases clave y los límites, en un solo lugar).
// Same format as everything else: English first, Spanish in parentheses.
export const ACERCA = [
  ["The idea", "La idea", [
    ["Lora understands what you say. Fixed rules decide what is allowed. Lora never acts on its own.",
      "Lora entiende lo que dices. Reglas fijas deciden qué está permitido. Lora nunca actúa por su cuenta."],
    ["Lora says it is done only after checking the database again. No empty promises.",
      "Lora dice que está hecho solo después de volver a revisar la base de datos. Sin promesas vacías."],
    ["If the AI is down or unsure, a person takes the case with everything already gathered.",
      "Si la IA no está disponible o no está segura, una persona toma el caso con todo ya reunido."],
  ]],
  ["What is real", "Qué es real", [
    ["The customers and their transactions come from the hackathon's synthetic bank data.",
      "Los clientes y sus transacciones vienen de los datos sintéticos del banco del hackathon."],
    ["The language model is real, and so are the database, the security per customer and the checks.",
      "El modelo de lenguaje es real, y también la base de datos, la seguridad por cliente y las verificaciones."],
  ]],
  ["Honest limits", "Límites, con honestidad", [
    ["Built with very limited resources: 131 customers are loaded, and the free model quota allows about 180 turns a day. If it runs out, a person takes over. That is the design, not a crash.",
      "Hecho con recursos muy limitados: hay 131 clientes cargados y el cupo gratuito del modelo alcanza para unos 180 turnos al día. Si se acaba, pasa a una persona. Es el diseño, no una caída."],
    ["Tested on 62 cases, one pass each: 55 pass, against 23 for a plain baseline. Small sample, wide intervals. We say tested, not proven.",
      "Probado con 62 casos, una pasada cada uno: pasan 55, frente a 23 de una línea base simple. Muestra pequeña, intervalos anchos. Decimos probado, no demostrado."],
    ["Portuguese was checked by back-translation, not by a native speaker.",
      "El portugués se verificó por retrotraducción, no con un hablante nativo."],
    ["The knowledge articles are drafts. A bank would have to approve them.",
      "Los artículos de conocimiento son borradores. Un banco tendría que aprobarlos."],
    ["Out of scope: deposits and loan disbursements. Lora searches and disputes charges. For anything else she says it is another process and, if the article does not answer it, offers a person.",
      "Fuera de alcance: depósitos y desembolsos de crédito. Lora busca y reclama cargos. Para lo demás dice que es otra gestión y, si el artículo no lo responde, ofrece una persona."],
  ]],
  ["With a real bank", "Con un banco real", [
    ["Designed for any customer, not only these. The bank would point the data entry at its own tables; the model never touches the database.",
      "Diseñado para cualquier cliente, no solo estos. El banco apuntaría la entrada de datos a sus propias tablas; el modelo nunca toca la base de datos."],
    ["The legal texts (the assistant's introduction and the privacy notice) are demo wording. Each bank sets its own text and its policy link in one configuration file, with no code changes.",
      "Los textos legales (la presentación de la asistente y el aviso de privacidad) son de demostración. Cada banco fija el suyo, y el enlace a su política, en un solo archivo de configuración, sin cambiar código."],
    ["Not built: connection to a real core banking system, to the contact center, and voice. We designed them and say so.",
      "No construido: la conexión con un sistema bancario real, con el centro de contacto y la voz. Los diseñamos y lo decimos."],
  ]],
  ["Credits and use", "Créditos y uso", [
    ["Built by Daniel Pineda (AA TEAM) during the Factored AI & Data Hackathon 2026.",
      "Hecho por Daniel Pineda (AA TEAM) durante el Factored AI & Data Hackathon 2026."],
    ["Free to read, run and build on for noncommercial use, keeping the author's name (PolyForm Noncommercial). Commercial use needs an agreement with the author.",
      "Libre para leer, ejecutar y construir encima sin fines comerciales, manteniendo el nombre del autor (PolyForm Noncommercial). El uso comercial requiere un acuerdo con el autor."],
    ["The data is synthetic and belongs to the hackathon organizer. No real customer appears here.",
      "Los datos son sintéticos y son del organizador del hackathon. Aquí no aparece ningún cliente real."],
    ["Factored's name and logo belong to Factored. They appear only because this was made for their event.",
      "El nombre y el logo de Factored son de Factored. Aparecen solo porque esto se hizo para su evento."],
  ]],
];
