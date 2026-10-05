// Idioma de la INTERFAZ del personal (cabina, operación, vista en vivo). No es el idioma de la conversación con el cliente,
// que decide el sistema (ARQUITECTURA §8.5). El texto en español es la clave: lo que no tenga traducción se ve en español.
import { EN } from "./i18n_en.js";

const CLAVE = "ui_idioma_v2";            // v2: la elección anterior (por idioma del navegador) ya no cuenta
// Inglés por defecto, sea cual sea el idioma del navegador: los jurados leen inglés. El español es una opción que se elige.
export function idiomaUI() {
  try { const g = localStorage.getItem(CLAVE); if (g === "es" || g === "en") return g; } catch { }
  return "en";
}
export function fijarIdiomaUI(idioma) { try { localStorage.setItem(CLAVE, idioma); } catch { } location.reload(); }

export const faltantes = new Set();          // rótulos sin traducción vistos en esta sesión (para completarlos)
export function t(es) {
  if (idiomaUI() !== "en") return es;
  const en = EN[es];
  if (en === undefined) { faltantes.add(es); return es; }
  return en;
}
// Texto de la API con números dentro (avisos de la cabina): se traduce la plantilla con {} y se reponen los números.
export function tn(es) {
  if (idiomaUI() !== "en") return es;
  const nums = [];
  // el código de una llave (…ab1Z) también es un dato variable, aunque mezcle letras y dígitos
  const plantilla = es.replace(/…\w+|\d[\d.,]*\d|\d/g, m => { nums.push(m); return "{}"; });
  const en = EN[plantilla];
  if (en === undefined) { faltantes.add(plantilla); return es; }
  let k = 0;
  return en.replace(/\{\}/g, () => nums[k++]);
}
window.__faltantes = faltantes;

// El CHAT es Lora, no la demo: va en español o portugués (el idioma de la conversación), nunca en el idioma de la interfaz de la demo.
// Español es la clave; el portugués solo se usa si la conversación está en portugués (revisión nativa pendiente, declarada).
const LORA_PT = {
  " · plazo: ": " · prazo: ", "Abrir reclamo": "Abrir reclamação", "Agregar al reclamo": "Adicionar à reclamação", "Atención desde": "Atendimento desde",
  "Bloquear temporalmente": "Bloquear temporariamente", "Buzón del sandbox": "Caixa de entrada do sandbox", "Cargo": "Cobrança", "Con una persona del equipo": "Com uma pessoa da equipe",
  "Confirmación": "Confirmação", "Código incorrecto. Intentos restantes:": "Código incorreto. Tentativas restantes:", "Elige una opción": "Escolha uma opção",
  "Escribe aquí…": "Escreva aqui…", "Estado": "Status", "Formulario seguro": "Formulário seguro", "Hablar con una persona": "Falar com uma pessoa",
  "Idioma de la conversación": "Idioma da conversa", "La espera superó la estimación inicial de": "A espera superou a estimativa inicial de", "Lo reconozco": "Eu reconheço",
  "Lora · asistente virtual": "Lora · assistente virtual", "Mensaje": "Mensagem", "Mis movimientos": "Minhas movimentações", "Ninguno de estos": "Nenhum destes",
  "No estoy seguro": "Não tenho certeza", "No lo reconozco": "Não reconheço", "No reconozco este cargo": "Não reconheço esta cobrança",
  "No se pudo enviar. Intenta de nuevo.": "Não foi possível enviar. Tente novamente.", "Nueva conversación": "Nova conversa", "Persona del equipo": "Pessoa da equipe",
  "Posición": "Posição", "Retirar reclamo": "Retirar reclamação", "Si el documento existe, el código llegó a tus canales registrados.": "Se o documento existir, o código chegou aos seus canais cadastrados.",
  "Sí, hazlo": "Sim, faça isso", "Tu caso": "Seu caso", "Tú": "Você", "Una persona del equipo tiene tu caso": "Uma pessoa da equipe está com o seu caso",
  "tu caso sigue en la fila": "seu caso continua na fila", "📎 Adjuntar": "📎 Anexar", "Desbloquear": "Desbloquear", "Espera estimada": "Espera estimada",
  "Enviar código": "Enviar código", "Documento (demo: DEMO-1001)": "Documento (demo: DEMO-1001)",
};
export const idiomaChat = () => { try { return sessionStorage.getItem("idioma_chat") === "pt" ? "pt" : "es"; } catch { return "es"; } };
export const fijarIdiomaChat = idioma => { try { sessionStorage.setItem("idioma_chat", idioma); } catch { } };
export const tLora = es => (idiomaChat() === "pt" ? (LORA_PT[es] ?? es) : es);

