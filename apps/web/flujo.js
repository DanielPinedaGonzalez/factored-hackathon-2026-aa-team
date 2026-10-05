// Flow map (mapa del flujo): the conversation's nodes N0..N14 with the path this conversation has taken highlighted.
// (Los nodos de la conversación con el recorrido de ESTA conversación resaltado.) Layout and edges follow ARQUITECTURA.md §6.
// The handover node (N11) is reachable from almost any step, so it is drawn as one bar instead of a dozen arrows.
// (El traspaso se puede alcanzar desde casi cualquier paso: se dibuja como una barra, no como una docena de flechas.)

const NS = "http://www.w3.org/2000/svg";
const NODOS = {                                   // id: [x, y, ancho, rótulo en inglés]
  N0: [60, 50, 96, "Signed out"], N1: [180, 50, 96, "Sign-in"], N2: [300, 50, 96, "Listening"], N3: [430, 50, 96, "Find charge"],
  N5: [560, 50, 96, "Show facts"], N6: [690, 50, 96, "Policy"], N7: [820, 50, 96, "Propose"],
  N13: [240, 140, 96, "Can't do"], N14: [350, 140, 96, "Not banking"], N4: [480, 140, 96, "Clarify"], N12: [610, 140, 110, "Closed, no claim"],
  N8: [820, 140, 96, "Execute"], N10: [700, 230, 96, "Done"], N9: [820, 230, 96, "Verify"],
  N11: [450, 320, 520, "Handover to a person (from any step)"],
};
const BORDES = [["N0", "N1"], ["N1", "N2"], ["N2", "N3"], ["N3", "N5"], ["N5", "N6"], ["N6", "N7"], ["N7", "N8"], ["N8", "N9"], ["N9", "N10"],
  ["N2", "N13"], ["N2", "N14"], ["N3", "N4"], ["N5", "N12"]];
// Which trace step passed through which node (qué paso de la traza pasó por qué nodo): lets the map show nodes a single turn crosses.
const PASO_A_NODO = { interprete: "N2", resolutor: "N3", politica: "N6", herramienta: "N8", verificacion_accion: "N9", traspaso: "N11" };

function svg(tag, attrs = {}, texto) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (texto !== undefined) e.textContent = texto;
  return e;
}

export function nodosVisitados(traza) {
  const vistos = new Set();
  for (const r of traza || []) {
    if (!r) continue;
    if (r.nodo_antes) vistos.add(r.nodo_antes);
    if (r.nodo_despues) vistos.add(r.nodo_despues);
    for (const p of r.pasos || []) if (PASO_A_NODO[p.componente]) vistos.add(PASO_A_NODO[p.componente]);
  }
  return vistos;
}

// Draws (or redraws) the map inside `contenedor` from the whole trace of the conversation.
export function pintarMapa(contenedor, traza) {
  const vistos = nodosVisitados(traza), ultimo = (traza || []).filter(Boolean).slice(-1)[0], actual = ultimo && ultimo.nodo_despues;
  const s = svg("svg", { viewBox: "0 0 900 350", class: "mapa-flujo", role: "img", "aria-label": "Conversation flow map" });
  for (const [a, b] of BORDES) {
    const [xa, ya, wa] = NODOS[a], [xb, yb, wb] = NODOS[b];
    const horizontal = ya === yb;
    s.append(svg("line", horizontal ? { x1: xa + wa / 2, y1: ya, x2: xb - wb / 2, y2: yb } : { x1: xa, y1: ya + 17, x2: xb, y2: yb - 17 },
      ));
    s.lastChild.setAttribute("class", vistos.has(a) && vistos.has(b) ? "borde-visto" : "borde");
  }
  for (const [id, [x, y, w, rotulo]] of Object.entries(NODOS)) {
    const clase = id === actual ? "nodo actual" : vistos.has(id) ? "nodo visto" : "nodo";
    s.append(svg("rect", { x: x - w / 2, y: y - 17, width: w, height: 34, rx: 6, class: clase }));
    s.append(svg("text", { x, y: y + 4, "text-anchor": "middle", class: "nodo-texto" }, `${id.slice(1)} ${rotulo}`));
  }
  contenedor.replaceChildren(s);
}
