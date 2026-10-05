// Brand (marca): Lora the parrot, a small original drawing, and the credit footer (el lorito y el pie con los créditos).
// "Lora" is a parrot (lora = loro): the drawing says it at a glance. (Lora es un loro: el dibujo lo dice de un vistazo.)
const NS = "http://www.w3.org/2000/svg";

function forma(tag, attrs) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
}

export function loro(tam = 28) {
  const s = forma("svg", { viewBox: "0 0 64 64", width: tam, height: tam, role: "img", "aria-label": "Lora, a parrot", class: "loro" });
  s.append(
    forma("path", { d: "M18 44 C10 54 12 60 20 62 C20 56 24 50 30 46 Z", fill: "#e5484d" }),                       // tail
    forma("path", { d: "M14 36 C14 18 28 8 40 12 C52 16 54 32 46 44 C40 54 22 56 14 36 Z", fill: "#2fb36d" }),      // body and head
    forma("path", { d: "M22 36 C24 28 34 28 38 36 C36 46 26 48 22 36 Z", fill: "#2f7de1" }),                        // wing
    forma("path", { d: "M44 18 C54 16 58 24 54 30 C52 26 48 24 44 24 Z", fill: "#f5b82e" }),                        // beak
    forma("circle", { cx: 38, cy: 20, r: 4, fill: "#fff" }), forma("circle", { cx: 39, cy: 20, r: 2, fill: "#111" }),  // eye
  );
  return s;
}

// Footer: who made it, and the hackathon's mark (white on black; the CSS blends the black away, so it sits on any dark background).
// Hidden if the file is missing. (El logo es blanco sobre negro: el CSS funde el negro con el fondo.)
export function pie(el) {
  const marca = el("img", { src: "hackathon_sobrenegro.jpg", alt: "Factored", class: "marca-hackathon" });
  marca.addEventListener("error", () => marca.remove());
  return el("footer", { class: "pie" }, loro(22),
    el("span", {}, "Lora · by Daniel Pineda · AA TEAM · AI & Data Hackathon 2026"), marca);
}
