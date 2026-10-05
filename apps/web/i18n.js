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
