"""Genera las diapositivas (6, en inglés) en HTML y PDF, alineadas con el video (guion v6):
1 El problema · 2 Qué hace Lora · 3 Cómo funciona (el modelo del proceso) · 4 Los controles y la señal de fraude · 5 Evidencia · 6 Límites y ruta a la operación.

Las cifras salen de los datos del organizador (docs/01_DIAGNOSTICO.md), de la última corrida de M1 (artefactos/corridas_m1.jsonl) y del reporte de
evaluación (evaluacion/corridas/); nada se escribe a mano. Si no hay corrida del conjunto final, la diapositiva 5 lo dice ("Development run").
Uso: python docs/presentacion/generar.py [--conjunto final] [--propuesto CORRIDA ...]
Salida: docs/presentacion/presentacion.html y presentacion.pdf (1920 × 1080, modo presentador: F pantalla completa, P ventana del orador).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluacion.reporte import _combinar  # noqa: E402
import mapa_proceso  # noqa: E402

CORRIDAS = RAIZ / "evaluacion" / "corridas"
# Cifras del diagnóstico (docs/01_DIAGNOSTICO.md §2.2 y PRESENTACION_V3 §10), contadas en los datos crudos del organizador.
CLIENTES, LLAMADAS, QUEJAS_CARGO = "150,000", "686,296", "12,297"
TOTAL_QUEJAS, QUEJAS_LLAMADAS = "67,095", "117,021"       # quejas únicas del registro y llamadas por queja (verificado en los datos crudos, 4-oct)
RESUELTAS = [("Transactional", 91.5), ("Product", 89.6), ("Technical", 69.9), ("Commercial", 65.2), ("Retention", 60.2), ("Complaint", 43.6)]
DURACION_S, SEGUIMIENTO, CSAT_SI, CSAT_NO = 431, 63, "3.0", "2.0"
FILAS_M, TABLAS = "23.5 M", 13
EN_COMPONENTE = {"prompts": "prompts", "catalogo": "command catalog", "politica": "policy", "config": "configuration", "codigo": "code", "modelos": "models"}


def _pct(x: dict | None) -> str:
    return "—" if not x or x.get("tasa") is None else f"{100 * x['tasa']:.0f}% ({x['numerador']}/{x['denominador']})"


def _tamano_de_las_pruebas() -> str:
    try:
        r = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "--color=no", "-p", "no:cacheprovider"], cwd=RAIZ, capture_output=True, text=True, timeout=120)
        limpio = re.sub(r"\x1b\[[0-9;]*m", "", r.stdout)
        return next((ln.split()[0] for ln in limpio.splitlines() if "tests collected" in ln or "test collected" in ln), "—")
    except (subprocess.SubprocessError, OSError):
        return "—"


ESTILO_PRESENTADOR = """
@media screen { body { background:#111; overflow:hidden }
  section { display:none; position:absolute; left:50%; top:50%; transform-origin:0 0; margin:0 }
  section.activa { display:block; transform:translate(-50%,-50%) scale(var(--k,1)); transform-origin:center center }
  aside.notas { display:none } }
@media print { aside.notas, #barra { display:none } }
:fullscreen #barra { display:none }
#barra { position:fixed; bottom:8px; right:12px; font:13px system-ui; color:#9aa4b2; z-index:9 }
body.presentador { background:#1c2430; color:#e8ecf3 }
body.presentador > section { display:none !important }
#panel section { display:block !important; position:absolute; transform-origin:0 0 }
#panel { position:fixed; inset:0; display:grid; grid-template-columns:2fr 1fr; grid-template-rows:auto 1fr; gap:14px; padding:14px; font-family:system-ui }
#panel .caja2 { position:relative; overflow:hidden; background:#000; border-radius:8px }
#cabecera { grid-column:1/3; display:flex; justify-content:space-between; font-size:22px }
#notas-vivas { grid-column:1/3; background:#26303f; border-radius:8px; padding:12px 18px; overflow:auto; font-size:21px; line-height:1.4 }
#notas-vivas li { margin-bottom:8px } #notas-vivas i { color:#9fb4d1; display:block; font-size:17px }
body.presentador #panel { grid-template-rows:auto 38vh 1fr } body.presentador #notas-vivas { grid-row:3 }
"""

SCRIPT_PRESENTADOR = """
(function(){
  var secs=[].slice.call(document.querySelectorAll('section')), n=secs.length, i=0, otra=null;
  var esPres=location.hash==='#presentador';
  function fit(el,box){var w=box.clientWidth,h=box.clientHeight,k=Math.min(w/1920,h/1080);
    el.style.transform='translate('+((w-1920*k)/2)+'px,'+((h-1080*k)/2)+'px) scale('+k+')';el.style.left='0';el.style.top='0';}
  function aud(){secs.forEach(function(s,j){s.classList.toggle('activa',j===i);});
    document.documentElement.style.setProperty('--k',Math.min(innerWidth/1920,innerHeight/1080));
    document.getElementById('barra').textContent=(i+1)+' / '+n+'  ·  F pantalla completa  ·  P presentador';}
  function pres(){var ca=document.getElementById('actual'),cs=document.getElementById('siguiente');
    ca.innerHTML='';cs.innerHTML='';var a=secs[i].cloneNode(true),b=(secs[i+1]||secs[i]).cloneNode(true);
    [a,b].forEach(function(x){x.style.display='block';x.style.position='absolute';var nt=x.querySelector('aside.notas');if(nt)nt.remove();});
    ca.appendChild(a);cs.appendChild(b);fit(a,ca);fit(b,cs);
    var nt=secs[i].querySelector('aside.notas');document.getElementById('notas-vivas').innerHTML=nt?nt.innerHTML:'';
    document.getElementById('contador').textContent='Diapositiva '+(i+1)+' de '+n;}
  function ir(j,aviso){i=Math.max(0,Math.min(n-1,j));esPres?pres():aud();
    if(aviso!==false){var o=esPres?window.opener:otra;if(o&&!o.closed)o.postMessage({aa:'ir',i:i},'*');}}
  addEventListener('message',function(e){if(e.data&&e.data.aa==='ir')ir(e.data.i,false);});
  addEventListener('keydown',function(e){var k=e.key;
    if(k==='ArrowRight'||k==='PageDown'||k===' '||k==='Enter')ir(i+1);
    else if(k==='ArrowLeft'||k==='PageUp'||k==='Backspace')ir(i-1);
    else if(k==='Home')ir(0);else if(k==='End')ir(n-1);
    else if(k==='f'||k==='F'){if(!document.fullscreenElement)document.documentElement.requestFullscreen();else document.exitFullscreen();}
    else if((k==='p'||k==='P')&&!esPres){otra=window.open(location.pathname+'#presentador','aa-presentador','width=1200,height=800');
      setTimeout(function(){if(otra)otra.postMessage({aa:'ir',i:i},'*');},800);}});
  if(esPres){document.body.className='presentador';
    document.body.insertAdjacentHTML('beforeend','<div id="panel"><div id="cabecera"><span id="contador"></span><span id="reloj">00:00</span></div>'+
      '<div class="caja2" id="actual"></div><div class="caja2" id="siguiente"></div><div id="notas-vivas"></div></div>');
    var t0=Date.now();setInterval(function(){var s=Math.floor((Date.now()-t0)/1000);
      document.getElementById('reloj').textContent=('0'+Math.floor(s/60)).slice(-2)+':'+('0'+s%60).slice(-2);},500);
    addEventListener('resize',pres);}
  else{addEventListener('resize',aud);addEventListener('click',function(){ir(i+1);});}
  ir(0,false);
})();
"""


import base64

# Qué fue cada resultado inseguro, en una frase para la nota de la diapositiva 5. Si aparece un caso inseguro sin nota, la diapositiva no se genera: no se publica una cifra sin explicar.
NOTAS_INSEGUROS = {
    "F6": "a customer said a promised refund never arrived; Lora read it as a new unrecognized charge and opened a claim instead of handing the case to a person.",
}


def _explicar_inseguros(casos: list[str]) -> str:
    faltan = [c for c in casos if c not in NOTAS_INSEGUROS]
    if faltan:
        raise SystemExit(f"falta la nota de la diapositiva 5 para el caso inseguro {faltan} (NOTAS_INSEGUROS en generar.py)")
    return " ".join(f"{c}: {NOTAS_INSEGUROS[c]}" for c in casos) if casos else "none."

_FONDO = 'data:image/svg+xml;base64,' + base64.b64encode((RAIZ / 'apps' / 'web' / 'fondo.svg').read_bytes()).decode()

CSS = """
@page { size: 1920px 1080px; margin: 0 }
/* Convención de color (una sola, con leyenda en cada gráfico): verde = Lora (lo nuestro) · gris = línea base / comparación · rojo = el problema o lo inseguro ·
   azul acero = referencia (otras categorías) · ámbar = reglas (la política) · violeta = el modelo. Nada cambia de significado entre diapositivas. */
:root { --fondo:#141413; --tarjeta:#1f1f1d; --texto:#ffffff; --suave:#c4c3ba; --lora:#34c27a; --base:#8a8d93; --mal:#e66767; --ref:#6f8fb3; --regla:#f2b84b;
        --modelo:#9085e9; --marca:#2cc4e0 }
* { box-sizing:border-box }
body { margin:0; font-family: Inter, system-ui, "Segoe UI", Roboto, sans-serif; background:var(--fondo); color:var(--texto) }
section { width:1920px; height:1080px; padding:34px 80px 0; page-break-after:always; position:relative; background:var(--fondo); overflow:hidden; isolation:isolate; display:flex; flex-direction:column }
/* curvas de nivel de la demo (apps/web/fondo.svg) detrás del contenido; se aclaran hacia el centro, donde va el texto */
section::before { content:""; position:absolute; inset:0; z-index:-1; pointer-events:none; background:url("__FONDO__") center/cover no-repeat; opacity:.95;
  -webkit-mask-image:radial-gradient(ellipse 75% 70% at 50% 52%, rgba(0,0,0,.18) 0%, rgba(0,0,0,.45) 55%, #000 100%); mask-image:radial-gradient(ellipse 75% 70% at 50% 52%, rgba(0,0,0,.18) 0%, rgba(0,0,0,.45) 55%, #000 100%) }
.cab { display:flex; justify-content:space-between; align-items:center; height:60px; font-size:24px; letter-spacing:.14em; color:var(--suave); font-weight:600 }
.firma { display:flex; align-items:center; gap:14px; letter-spacing:0 } .firma b { font-size:32px; color:#fff } .firma i { font-style:normal; font-size:24px; color:var(--suave); border-left:2px solid #5a5a55; padding-left:14px }
.firma svg { display:block }
h1 { font-size:58px; line-height:1.08; margin:6px 0 6px; font-weight:800 }
.sub { font-size:31px; color:var(--suave); margin:0 0 4px }
.zona { flex:1; display:flex; flex-direction:column; justify-content:center; gap:26px; padding:14px 0 18px; min-height:0 }
.puente { margin:0 0 98px; border-left:8px solid var(--marca); padding:6px 0 6px 24px; font-size:36px; font-weight:700 }
.pie { position:absolute; left:80px; right:240px; bottom:22px; font-size:22px; line-height:1.3; color:var(--suave) } .num { position:absolute; right:80px; bottom:22px; font-size:22px; color:var(--suave) }
.tarj { background:var(--tarjeta); border-radius:22px; padding:30px 34px }
.tarj h3 { margin:0 0 16px; font-size:24px; letter-spacing:.1em; color:var(--suave); font-weight:700 }
.col3 { display:grid; grid-template-columns:repeat(3,1fr); gap:28px } .col2 { display:grid; grid-template-columns:1fr 1fr; gap:34px }
.fila-b { display:grid; grid-template-columns:240px 1fr 110px; gap:16px; align-items:center; margin:13px 0; font-size:30px }
.pista { height:40px; background:#2c2c29; border-radius:8px } .pista i { display:block; height:100%; border-radius:8px }
.ley { display:flex; gap:30px; font-size:24px; color:var(--suave); justify-content:center; flex-wrap:wrap } .ley i { display:inline-block; width:22px; height:22px; border-radius:6px; margin-right:10px; vertical-align:-4px }
.nota { color:var(--suave); font-size:24px; line-height:1.3 }
.notif { background:#f4f5f7; color:#1d2230; border-radius:24px; padding:22px 26px; font-size:29px; line-height:1.3; box-shadow:0 18px 50px #0008 } .notif small { display:block; color:#5b6272; font-size:22px; letter-spacing:.06em; margin-bottom:6px }
.notif b { display:block } .notif em { display:block; margin-top:8px; color:#c0392b; font-style:normal; font-weight:700 }
.flujo { display:grid; grid-template-columns:420px 56px 1fr 56px 640px; align-items:center; gap:0 }
.caja { background:var(--tarjeta); border-radius:22px; padding:24px 28px; font-size:30px; line-height:1.28 } .caja small { display:block; margin-top:10px; font-size:24px; color:var(--suave) }
.flecha { text-align:center; font-size:60px; color:var(--marca) }
.desenlaces { display:flex; flex-direction:column; gap:16px }
.des { background:var(--tarjeta); border-radius:18px; padding:12px 22px; font-size:26px; line-height:1.25; border-left:10px solid var(--ref) } .des b { display:block; font-size:29px; margin-bottom:2px }
.des.sena { border-color:var(--regla) } .des.cierra { border-color:var(--lora) }
.persona { background:#17382b; border:3px solid var(--lora); border-radius:18px; padding:16px 26px; font-size:31px; font-weight:700; text-align:center }
.fuera { background:#3a2423; border:3px solid var(--mal); border-radius:18px; padding:14px 22px; font-size:27px; font-weight:700; text-align:center; display:flex; align-items:center; justify-content:center; line-height:1.25 }
.tres-b { display:grid; grid-template-columns:repeat(3,1fr); gap:24px } .tres-b div { background:var(--tarjeta); border-radius:18px; padding:12px 22px; font-size:27px; text-align:center; line-height:1.25 } .tres-b b { display:block; color:var(--lora); font-size:30px }
.mapa { background:#fff; border-radius:16px; padding:6px; width:1640px; align-self:center } .mapa svg { display:block; width:100%; height:auto }
.chips { display:flex; gap:18px } .chip { flex:1; background:var(--tarjeta); border-radius:12px; padding:12px 20px; font-size:26px; line-height:1.25 } .chip.az { background:#2b5fc7; font-weight:700 }
.rls { background:#2b5fc7; color:#fff; border-radius:12px; padding:12px 22px; font-size:28px; font-weight:700 }
.cierre { font-size:42px; font-weight:800; text-align:center } .cierre span { color:var(--modelo) } .cierre em { color:var(--lora); font-style:normal }
.col3 .tarj h3.k { font-size:32px; color:#fff; margin-bottom:10px } .col3 li { font-size:27px; line-height:1.28; margin:8px 0 } .col3 ul { padding-left:28px; margin:0 }
.tabla { width:100%; font-size:28px; border-collapse:collapse } .tabla td { padding:8px 6px } .tabla td:first-child { white-space:nowrap }
.tiempo { display:grid; grid-template-columns:repeat(3,1fr); gap:12px } .tiempo div { background:#2a3039; border-radius:12px; padding:10px 14px; font-size:24px; text-align:center } .tiempo b { display:block }
.datos { display:flex; align-items:center; gap:16px; font-size:26px; background:var(--tarjeta); border-radius:16px; padding:12px 24px; justify-content:center }
.datos span.cap { background:#262c35; border-top:5px solid var(--ref); border-radius:10px; padding:6px 16px }
.limites { display:flex; gap:20px; font-size:26px } .limites div { display:flex; align-items:center; flex:1; background:#3a2423; border-left:8px solid var(--mal); border-radius:12px; padding:10px 18px; line-height:1.25 }
.credito { display:flex; align-items:center; justify-content:center; gap:22px; font-size:32px } .credito b { font-size:38px } .credito small { display:block; font-size:24px; color:var(--suave) }
"""

LORO = ('<svg viewBox="0 0 64 64" width="52" height="52"><path d="M18 44 C10 54 12 60 20 62 C20 56 24 50 30 46 Z" fill="#e5484d"/>'
        '<path d="M14 36 C14 18 28 8 40 12 C52 16 54 32 46 44 C40 54 22 56 14 36 Z" fill="#2fb36d"/><path d="M22 36 C24 28 34 28 38 36 C36 46 26 48 22 36 Z" fill="#2f7de1"/>'
        '<path d="M44 18 C54 16 58 24 54 30 C52 26 48 24 44 24 Z" fill="#f5b82e"/><circle cx="38" cy="20" r="4" fill="#fff"/><circle cx="39" cy="20" r="2" fill="#111"/></svg>')
FIRMA = f'<span class="firma">{LORO}<b>Lora</b><i>Daniel Pineda</i></span>'
C_LORA, C_BASE, C_MAL, C_REF = "#34c27a", "#8a8d93", "#e66767", "#6f8fb3"


def _marco(n: int, seccion: str, titulo: str, subtitulo: str, cuerpo: str, puente: str, pie: str) -> str:
    sub = f'<p class="sub">{subtitulo}</p>' if subtitulo else ""
    br = f'<div class="puente">{puente}</div>' if puente else '<div style="height:84px"></div>'
    return (f'<section><div class="cab"><span>{n:02d} · {seccion}</span>{FIRMA}</div><h1>{titulo}</h1>{sub}<div class="zona">{cuerpo}</div>{br}'
            f'<div class="pie">{pie}</div><div class="num">{n} / 6</div></section>')


def _barra_h(etiqueta: str, valor: float, color: str, maximo: float = 100, texto: str | None = None, col: int = 240) -> str:
    return (f'<div class="fila-b" style="grid-template-columns:{col}px 1fr 110px"><span>{etiqueta}</span><div class="pista"><i style="width:{100 * valor / maximo:.1f}%;background:{color}"></i></div>'
            f'<b>{texto or f"{valor:.0f}%"}</b></div>')


def _leyenda(items: list[tuple[str, str]]) -> str:
    return '<div class="ley">' + "".join(f'<span><i style="background:{c}"></i>{t}</span>' for c, t in items) + "</div>"


def _venn() -> str:
    """Las cuatro verificaciones de la política como cuatro conjuntos; su intersección es lo que Lora puede hacer sola. Las etiquetas van fuera de los círculos."""
    R, centros = 140, [(405, 240), (525, 240), (405, 350), (525, 350)]
    c = "".join(f'<clipPath id="k{i}"><circle cx="{x}" cy="{y}" r="{R}"/></clipPath>' for i, (x, y) in enumerate(centros))
    aros = "".join(f'<circle cx="{x}" cy="{y}" r="{R}" fill="#f2b84b" fill-opacity=".13" stroke="#f2b84b" stroke-width="4"/>' for x, y in centros)
    inter = ('<g clip-path="url(#k0)"><g clip-path="url(#k1)"><g clip-path="url(#k2)"><g clip-path="url(#k3)">'
             '<rect x="0" y="0" width="930" height="560" fill="#34c27a" fill-opacity=".9"/></g></g></g></g>')
    num = "".join(f'<text x="{x + dx}" y="{y + dy}" font-size="50" font-weight="800" fill="#fff" text-anchor="middle">{i}</text>'
                  for i, (x, y, dx, dy) in enumerate([(405, 240, -62, -30), (525, 240, 62, -30), (405, 350, -62, 52), (525, 350, 62, 52)], 1))
    ety = [(30, 38, "start", "1 · Irreversibility against"), (30, 82, "start", "certainty"), (900, 38, "end", "2 · Same case,"), (900, 82, "end", "same treatment"),
           (30, 528, "start", "3 · A person"), (30, 572, "start", "always available"), (900, 528, "end", "4 · Care for the"), (900, 572, "end", "relationship")]
    txt = "".join(f'<text x="{x}" y="{y}" font-size="36" font-weight="700" fill="#e8e6dc" text-anchor="{a}">{t}</text>' for x, y, a, t in ety)
    return (f'<svg viewBox="0 0 930 592" style="width:100%;height:auto;display:block"><defs>{c}</defs>{aros}{inter}{num}{txt}'
            '<text x="465" y="290" font-size="24" font-weight="800" fill="#0b2a1a" text-anchor="middle">Lora acts</text>'
            '<text x="465" y="318" font-size="24" font-weight="800" fill="#0b2a1a" text-anchor="middle">alone</text></svg>')


def diapositivas(conjunto: str, propuesto: list[str] | None, pruebas: str) -> tuple[list[str], dict]:
    prop_arch = [CORRIDAS / f for f in propuesto] if propuesto else sorted(CORRIDAS.glob(f"*_propuesto_{conjunto}.json"))
    prop = _combinar(prop_arch)
    base_arch = sorted(CORRIDAS.glob(f"*_linea_base_{conjunto}.json"))
    base = _combinar(base_arch) if base_arch else None
    if base:                     # la comparación es sobre los mismos casos que corrió la línea base
        comunes = {r["caso"] for r in base["resultados"]} & {r["caso"] for r in prop["resultados"]}
        mp_par, mb = _combinar(prop_arch, comunes)["metricas"], base["metricas"]
    else:
        mp_par, mb = prop["metricas"], None
    mp = prop["metricas"]
    m1 = json.loads((RAIZ / "artefactos" / "corridas_m1.jsonl").read_text().strip().splitlines()[-1])["reporte"]["test"]
    P, B = m1["propuesto"], m1["linea_base"]
    umbral = int(json.loads((RAIZ / "artefactos" / "m1.json").read_text())["umbral"])
    etiqueta = "Final run on unseen cases" if conjunto == "final" else "Development run"
    from evaluacion.versiones import huella, que_cambio
    medidas = [v for v in (json.loads(f.read_text()).get("versiones") or {} for f in prop_arch) if v.get("sistema")]
    ahora = huella()
    cambio = que_cambio(medidas[-1], ahora) if medidas and any(v["sistema"] != ahora["sistema"] for v in medidas) else []
    aviso = (f"Measured on version {medidas[-1]['sistema'][:7]}; later changes are listed in the report." if cambio else "")

    # ---- 1 · el problema (la clienta y los datos del banco)
    barras = "".join(_barra_h(n, v, C_MAL if n == "Complaint" else C_REF) for n, v in RESUELTAS)
    s1 = _marco(1, "THE PROBLEM", "“I don't recognize this charge”", "The least-resolved reason for calling a bank's contact center",
        f"""<div class="col3">
 <div class="tarj"><h3>1 · HER MOMENT</h3>
  <div class="notif"><small>BANK · now · SYNTHETIC EXAMPLE</small><b>Charge alert</b>Purchase of US$ 261.56 at EMPRESA TELEFONICA with card ••3240.<em>Do you know this charge?</em></div>
  <p style="font-size:31px;line-height:1.35;margin:26px 0 0">She cannot tell if it is hers, a mistake, or fraud. She calls the bank, and waits.</p></div>
 <div class="tarj"><h3>2 · WHAT THE BANK'S DATA SHOWS</h3><div class="nota" style="margin-bottom:6px">Calls resolved, by reason</div>{barras}
   <div style="margin-top:14px;font-size:27px"><b style="color:{C_MAL}">44%</b> of complaint calls resolved · <b>{DURACION_S} s</b> median call duration · <b>{SEGUIMIENTO}%</b> of complaint calls require follow-up</div></div>
 <div class="tarj"><h3>3 · WHY IT MATTERS</h3><div class="nota" style="margin-bottom:10px">Customer satisfaction (scale 1–4)</div>
   {_barra_h("Resolved", 3.0, C_REF, 4, CSAT_SI)}{_barra_h("Not resolved", 2.0, C_MAL, 4, CSAT_NO)}
   <div style="margin:22px 0 4px;font-size:92px;font-weight:800;color:var(--ref);line-height:1">1.0<small style="font-size:30px;font-weight:600;color:var(--suave);margin-left:12px">point satisfaction gap</small></div>
   <p style="margin:6px 0 0;font-size:28px;color:var(--suave);line-height:1.35">Resolved calls are associated with higher satisfaction. We do not claim cause.</p>
   <div class="nota" style="margin-top:14px">97,851 surveys after resolved calls · 30,005 after unresolved</div></div>
</div>
{_leyenda([(C_MAL, "the problem · not resolved"), (C_REF, "other reasons · resolved")])}""",
        f"<b>{QUEJAS_CARGO}</b> of {TOTAL_QUEJAS} complaints are tagged “unrecognized charge”. This is the case I chose.",
        f"Organizer's synthetic bank data · Mexico, Colombia, Argentina · {CLIENTES} customers · {LLAMADAS} calls ({QUEJAS_LLAMADAS} about complaints).")

    # ---- 2 · qué hace Lora
    s2 = _marco(2, "WHAT LORA DOES", "Lora handles the case, or hands it to a person",
        "Inside the bank's app, in Spanish and Portuguese.",
        """<div class="flujo">
 <div class="caja"><b>“I don't recognize this charge”</b><small>In her own words<br>Spanish or Portuguese</small></div><div class="flecha">→</div>
 <div class="caja"><b>Lora</b> checks who she is, finds the matching transaction in her account, shows it and asks:<br><b>do you recognize it?</b></div><div class="flecha">→</div>
 <div class="desenlaces">
  <div class="des cierra"><b>She recognizes the charge</b>The case closes. No claim.</div>
  <div class="des"><b>She does not recognize it</b>She confirms → Lora opens the claim → re-reads the database → real case number and deadline.</div>
  <div class="des sena"><b>Fraud signal above the certified cut-off</b>Lora offers to block the card; she decides. The case goes to a human fraud agent at priority one.</div></div></div>
<div style="display:grid;grid-template-columns:2fr 1fr;gap:20px"><div class="persona" style="font-size:29px">At any step she can ask for a person · the human agent receives the whole case · she repeats nothing</div>
 <div class="fuera">Out of scope today: deposits and disbursements → a person</div></div>
<div class="tres-b"><div><b>For her</b>A clear answer</div><div><b>For the human agent</b>A complete case</div><div><b>For the bank</b>Every action with its rule and evidence</div></div>""",
        "", "One case, three screens: customer · human agent · supervisor.")

    # ---- 3 · cómo funciona (el modelo del proceso)
    s3 = _marco(3, "HOW IT WORKS", "The model understands. The code decides and acts.", "",
        f"""<div class="mapa">{mapa_proceso.svg("en")}</div>
<div class="chips"><div class="chip">The model <b>cannot execute</b> any banking action.</div><div class="chip">Lora reports an action as done <b>only after the database confirms it</b>.</div>
 <div class="chip">If the model fails, <b>no further action runs</b>: a person takes the case.</div><div class="chip az">Row-Level Security: each customer reads only their own rows</div></div>""",
        "", "The policy's checks run in code, with each country's own deadlines and thresholds (Mexico, Colombia, Argentina: sourced where verified, otherwise declared synthetic). The fraud signal is a learned input, not a decision-maker.")
    s3 = s3.replace('<h1>', '<h1 style="font-size:52px;margin:2px 0 0">', 1)

    # ---- 4 · los controles y la señal de fraude
    caza = lambda x: f"{100 * x['recall']:.1f}%"
    ancho = lambda x: 100 * x["recall"] / 0.7
    s4 = _marco(4, "THE CONTROLS", "Four policy checks control actions. One learned signal informs them.", "",
        f"""<div class="col2" style="align-items:stretch">
 <div class="tarj"><h3 style="color:var(--regla)">THE POLICY · FOUR CHECKS, ALL MUST PASS</h3><div style="width:90%;margin:0 auto">{_venn()}</div>
  <div class="nota" style="text-align:center;margin-top:6px">The intersection defines which actions Lora may perform without a person. Conceptual view: the four conditions are evaluated in code.</div>
  <div class="chips" style="margin-top:14px"><div class="chip"><b>The database re-read</b> · after she acts</div><div class="chip"><b>The text check</b> · before Lora speaks</div></div></div>
 <div class="tarj"><h3 style="color:var(--lora)">THE FRAUD SIGNAL · CERTIFIED RULE: SCORE &gt; {umbral}</h3>
  <p style="font-size:28px;line-height:1.35;margin:0 0 14px">The bank already provides a fraud score for most transactions. We calibrated it and <b>certified</b> a cut-off: above it, Lora may offer a card block.</p>
  {_barra_h("Certified cut-off", ancho(P), C_LORA, 100, caza(P), 300)}{_barra_h("Bank's cut-off (50)", ancho(B), C_BASE, 100, caza(B), 300)}
  <div class="nota" style="margin:-4px 0 12px">Share of fraud caught · locked test, Jan–Jun 2026 · {P['fraudes']} frauds · {P['legitimas']:,} legitimate transactions</div>
  <table class="tabla"><tr style="color:var(--suave);font-size:23px"><td></td><td>Recommended blocks</td><td>Wrong, observed</td><td>95% upper bound (FDR)</td></tr>
   <tr style="color:var(--lora);font-weight:800"><td>Certified</td><td>{P['n_marcadas']}</td><td>{P['fp']}</td><td>{100 * P['cota_fdr_95']:.2f}%</td></tr>
   <tr><td>Bank's own</td><td>{B['n_marcadas']}</td><td>{B['fp']}</td><td>{100 * B['cota_fdr_95']:.2f}%</td></tr></table>
  <div class="tiempo" style="margin-top:14px"><div>Learn<b>2 years</b></div><div>Certify<b>6 months</b></div><div>Test once 🔒<b>6 months</b></div></div></div></div>
<div class="datos"><b style="color:var(--ref)">{FILAS_M} rows · {TABLAS} tables</b><span class="cap">Bronze · raw</span>→<span class="cap">Silver · contracts + quality checks</span>→<span class="cap">Gold · demo subset</span></div>""",
        "",
        "Synthetic data. The method can be applied to new data; the cut-off would have to be certified again. · Policy gate design: Daniel Pineda")

    s4 = s4.replace('<h1>', '<h1 style="font-size:49px;margin:10px 0 6px">', 1)

    # ---- 5 · evidencia
    def ic(x: dict | None) -> str:
        i = (x or {}).get("ic95")
        return f" [{round(float(f'{i[0]:.2f}') * 100)}–{round(float(f'{i[1]:.2f}') * 100)}%]" if i else ""      # como en REPORTE_EVALUACION (0.79-0.94)

    def par(nombre: str, a: dict | None, b: dict | None, nota: str = "") -> str:
        ba = f'<div class="pista" style="height:50px"><i style="width:{max(100 * (a or {}).get("tasa", 0), 1.5):.1f}%;background:{C_LORA}"></i></div>'
        bb = (f'<div class="pista" style="height:50px"><i style="width:{max(100 * b["tasa"], 1.5):.1f}%;background:{C_BASE}"></i></div>' if b and b.get("tasa") is not None
              else '<div class="pista" style="height:50px;color:var(--suave);padding:8px 14px;font-size:24px">plain assistant not measured</div>')
        va = f'<b style="color:{C_LORA}">{_pct(a)}</b><span class="nota" style="font-size:22px">{ic(a)}</span>'
        vb = f'<b style="color:{C_BASE}">{_pct(b)}</b><span class="nota" style="font-size:22px">{ic(b)}</span>' if b else ""
        return (f'<div style="display:grid;grid-template-columns:340px 1fr 330px;gap:12px 22px;align-items:center;margin:10px 0"><div style="font-size:31px;font-weight:700">{nombre}'
                f'<div class="nota" style="font-size:22px;font-weight:400">{nota}</div></div><div>{ba}<div style="height:10px"></div>{bb}</div><div style="font-size:28px;line-height:1.35">{va}<br>{vb}</div></div>')
    ins_b = mb["inseguros"] if mb else None
    n_pt = sum(1 for r in prop["resultados"] if r.get("idioma") == "pt")
    inseguros = [r["caso"] for r in prop["resultados"] if r.get("inseguro")]
    cuerpo5 = f"""<div style="display:flex;align-items:center;justify-content:center;gap:30px;flex-wrap:wrap"><span style="border:2px solid var(--suave);border-radius:999px;padding:6px 24px;font-size:26px;font-weight:700">{etiqueta}</span>
 <span class="nota">{mp['casos']} cases ({n_pt} in Portuguese) · normal · ambiguous · needs a person · attacks · tool failures · scored from the database, not from the text</span></div>
<div>{par("Cases passed", mp_par["pasan"], mb and mb["pasan"], "all expected outcomes met, no out-of-policy action")}{par("Correct escalation", mp_par["escalada_correcta"], mb and mb["escalada_correcta"], f"of the {mp_par['escalada_correcta']['denominador']} cases that needed a person")}
 {par("Out-of-policy actions", mp_par["inseguros"], ins_b, "an action the policy forbids, e.g. opening a claim that did not apply · lower is better")}</div>
{_leyenda([(C_LORA, "Lora"), (C_BASE, "plain assistant: same model, data, identity and tools; rules only in the prompt")])}
<div class="nota" style="text-align:center;font-size:26px">Latency p50 / p95 per turn: {mp_par['latencia_ms']['p50'] / 1000:.1f} / {mp_par['latencia_ms']['p95'] / 1000:.1f} s · cost per case ≈ {mp['consumo']['equivalente_usd_por_caso']:.4f} USD at public model prices · bars on one 0–100% scale · brackets: 95% Wilson interval</div>"""
    s5 = _marco(5, "EVIDENCE", "In our test, rules outside the prompt improved safety" if (mb and mb["inseguros"]["numerador"] > mp_par["inseguros"]["numerador"]) else "The system works on our battery of cases",
        "", cuerpo5,
        "Same model and tools. Different control architecture. Different results in this test.",
        f"Offline results on synthetic data, one pass on {mp['casos']} cases never used in development: “tested in our battery”, not “validated”. Lora's out-of-policy action{'s' if len(inseguros) != 1 else ''}: {_explicar_inseguros(inseguros)} {aviso}")

    # ---- 6 · límites y ruta a la operación
    s6 = _marco(6, "LIMITS AND ROUTE TO OPERATION", "What it would take to make it real", "",
        f"""<div class="col3">
 <div class="tarj"><h3 class="k" style="color:var(--lora)">BUILT</h3><ul><li>Traceability for every conversation turn and model call</li><li>Bounded retries · safe fallback to a person</li><li>Skills-based routing on the dataset's synthetic agent roster</li><li>Supervisor, audit and back-office screens</li><li>Recent-charge selection with “None of these” (tested; not yet evaluated with the live model)</li></ul></div>
 <div class="tarj"><h3 class="k" style="color:var(--ref)">TESTED</h3><ul><li>Prompt injection</li><li>Tool failures and model failures</li><li>Row-level security and identity</li><li>Spanish and Portuguese cases (Portuguese wording checked by back-translation)</li><li>Policy tested across 98,304 combinations of input facts</li><li>{pruebas} automated tests</li></ul></div>
 <div class="tarj"><h3 class="k" style="color:var(--modelo)">NEXT</h3><ul><li>Real bank systems integration</li><li>Native review of the Portuguese</li><li>A larger evaluation</li><li>Evaluate paid model capacity and latency</li><li>Deposits and disbursements (today: a person)</li></ul></div></div>
<div class="limites"><div>Synthetic data, not production</div><div>Small evaluation: 62 cases</div><div>Portuguese checked by back-translation, not by a native reviewer</div></div>
<div class="cierre"><span>The model understands.</span> The code decides and acts. <em>Every action is verified.</em></div>
<div class="credito">{LORO.replace('width="52" height="52"', 'width="76" height="76"')}<div><b>Lora · Daniel Pineda</b><small>Factored AI &amp; Data Hackathon 2026</small></div><div style="border-left:2px solid #5a5a55;padding-left:22px"><small>Code: github.com/DanielPinedaGonzalez/factored-hackathon-2026-aa-team</small><small>Live demo: aa-team-api.onrender.com/app/ · access code in the submission email</small></div></div>""",
        "", "A projection, not a measured improvement. Today it is a prototype on synthetic data.")
    contexto = {"mp": mp, "mp_par": mp_par, "mb": mb, "P": P, "B": B, "pruebas": pruebas, "etiqueta": etiqueta, "una": True, "umbral": umbral}
    return [s1, s2, s3, s4, s5, s6], contexto


def _li(en: str, es: str) -> str:
    return f"<li>{en}<i>({es})</i></li>"


def _notas(c: dict) -> list[str]:
    """Notas del orador por diapositiva: inglés sencillo y, debajo de cada frase, su sentido en español. Mismo vocabulario que el video."""
    mp, P, B, pct = c["mp"], c["P"], c["B"], _pct
    d = [
        [("A customer gets a notification: a charge she does not recognize. She cannot tell if it is hers, a mistake, or fraud.", "Una clienta recibe un aviso: un cargo que no reconoce. No sabe si es suyo, un error o un fraude."),
         ("She calls the bank, and waits. In the bank's synthetic data, only forty-four percent of complaint calls are resolved, against ninety-two for simple transactions.",
          "Llama al banco y espera. En los datos sintéticos del banco, solo el 44 % de las llamadas por quejas se resuelve, frente al 92 % de las transacciones simples."),
         (f"{QUEJAS_CARGO} of {TOTAL_QUEJAS} complaints are tagged as unrecognized charges. I chose this case because a system can check it against the customer's own account data.",
          f"{QUEJAS_CARGO} de {TOTAL_QUEJAS} quejas están etiquetadas como cargo no reconocido. Elegí este caso porque un sistema puede comprobarlo con los datos de la cuenta del propio cliente."),
         ("Do not say it is the most common complaint: the complaint categories are about equal. Do not say resolving causes satisfaction: it is an association. The tag does not prove a real unrecognized charge: in our diagnosis, none of 4,090 tagged complaints matched an amount in the customer's own transactions.",
          "No decir que es la queja más común: las categorías de queja son casi iguales. No decir que resolver causa la satisfacción: es una asociación. La etiqueta no prueba un cargo realmente no reconocido: en nuestro diagnóstico, ninguna de 4.090 quejas etiquetadas coincidía con un monto de las transacciones del propio cliente.")],
        [("Instead of waiting on the phone, she opens the bank's app and meets Lora.", "En lugar de esperar al teléfono, abre la app del banco y conoce a Lora."),
         ("Lora checks who she is, finds the matching transaction in her account, shows it and asks: do you recognize it?", "Lora verifica quién es, encuentra la transacción que coincide en su cuenta, se la muestra y pregunta: ¿la reconoces?"),
         ("If she recognizes it, it ends there. If she does not, with her confirmation Lora opens a claim and re-reads the database. Not recognizing a charge is not proof of fraud.", "Si lo reconoce, termina ahí. Si no, con su confirmación Lora abre un reclamo y relee la base. No reconocer un cargo no es prueba de fraude."),
         ("If the fraud score is above a certified cut-off, Lora offers to block the card; she decides, and the case goes to a human fraud agent at priority one.", "Si el puntaje de fraude está por encima de un corte certificado, Lora ofrece bloquear la tarjeta; ella decide, y el caso va a un agente humano de fraude con prioridad uno."),
         ("Deposits and disbursements are not covered: Lora hands them to a person.", "Depósitos y desembolsos no están cubiertos: Lora los pasa a una persona.")],
        [("This is the process model. The model reads the message and writes the answer from verified facts.", "Este es el modelo del proceso. El modelo lee el mensaje y escribe la respuesta desde hechos verificados."),
         ("But the model cannot execute any banking action. The code decides and executes, and after the action it reads the database again.", "Pero el modelo no puede ejecutar ninguna acción bancaria. El código decide y ejecuta, y tras la acción vuelve a leer la base."),
         ("Lora reports an action as done only after the database confirms it. If the model fails, no further action runs and a person takes the case with the full package.", "Lora informa una acción como hecha solo cuando la base la confirma. Si el modelo falla, no corre ninguna acción más y una persona toma el caso con el paquete completo."),
         ("Security is in the database: each customer can only read their own rows.", "La seguridad está en la base de datos: cada cliente solo puede leer sus propias filas."),
         ("The model is used in three places: the interpreter describes the message; the comparator chooses which of the real candidate descriptions (type and merchant name only) match her words; the writer drafts the answer. The model never sees amounts, dates or identifiers: only placeholders. Finding the candidates by amount and date is plain code.", "El modelo se usa en tres lugares: el intérprete describe el mensaje; el comparador elige cuáles de las descripciones reales de los candidatos (solo tipo y nombre del comercio) corresponden a sus palabras; el redactor escribe la respuesta. El modelo nunca ve montos, fechas ni identificadores: solo marcadores. Encontrar los candidatos por monto y fecha es código puro."),
         ("If asked whether Lora is an agent: it is a workflow with bounded model components, not an autonomous agent. A fixed 15-step graph decides each next step; three small model components (interpreter, comparator, writer) have no tools; the code executes actions after the policy and her confirmation. Here, agent means a human agent of the bank.", "Si preguntan si Lora es un agente: es un flujo de trabajo con componentes de modelo acotados, no un agente autónomo. Un grafo fijo de 15 pasos decide cada paso siguiente; tres componentes pequeños de modelo (intérprete, comparador y redactor) no tienen herramientas; el código ejecuta las acciones tras la política y su confirmación. Aquí, agente significa un asesor humano del banco.")],
        [("The policy decides with four checks that must all pass: irreversibility against certainty; same case, same treatment; a person always available; care for the relationship.",
          "La política decide con cuatro verificaciones que deben cumplirse todas: irreversibilidad frente a certeza; mismo caso, mismo trato; una persona siempre disponible; cuidado de la relación."),
         ("The intersection defines which actions Lora may perform without a person. It is a conceptual drawing: the four conditions are evaluated in code. Same case, same treatment means the same relevant facts give the same path, under the same country rules. Two more checks close the loop: the database re-read after she acts, and the text check before Lora speaks. The design of this policy gate is the author's: Daniel Pineda.",
          "La intersección define qué acciones puede hacer Lora sin una persona. Es un dibujo conceptual: las cuatro condiciones se evalúan en código. Mismo caso, mismo trato significa que los mismos hechos relevantes dan el mismo camino, con las mismas reglas del país. Dos comprobaciones más cierran el ciclo: la relectura de la base después de actuar y la revisión del texto antes de hablar. El diseño de esta puerta de política es del autor: Daniel Pineda."),
         (f"The bank already provides a fraud score for most transactions; about a quarter have none, and those go to a person. We calibrated it on two years of data and certified the rule score above {c['umbral']} on the next six months: the 95 percent upper bound on the share of wrong blocks is under one percent, on this data.",
          f"El banco ya da un puntaje de fraude para la mayoría de las transacciones; cerca de una cuarta parte no lo tiene, y esas van a una persona. Lo calibramos con dos años de datos y certificamos la regla puntaje mayor que {c['umbral']} con los seis meses siguientes: la cota superior al 95 % de la proporción de bloqueos equivocados es menor del 1 %, en estos datos."),
         (f"In the locked test it caught {100 * P['recall']:.1f} percent of fraud against {100 * B['recall']:.1f} with the bank's own cut-off, and none of the {P['n_marcadas']} recommended blocks was wrong.",
          f"En la prueba bloqueada atrapó el {100 * P['recall']:.1f} % del fraude frente al {100 * B['recall']:.1f} % con el corte del propio banco, y ninguno de los {P['n_marcadas']} bloqueos recomendados fue incorrecto."),
         ("The guarantee and the test result are two different things. Zero wrong blocks is a result on synthetic data. The method can be applied to new data, but the cut-off would have to be certified again.",
          "La garantía y el resultado de la prueba son dos cosas distintas. Cero bloqueos equivocados es un resultado con datos sintéticos. El método puede aplicarse a datos nuevos, pero el corte tendría que certificarse de nuevo.")],
        [("We compare Lora with a plain assistant: same model, data, identity, row-level security and tools, with the rules only in its prompt and no policy engine.", "Comparamos Lora con un asistente simple: mismo modelo, datos, identidad, seguridad por fila y herramientas, con las reglas solo en el prompt y sin motor de política."),
         (f"{c['etiqueta']}: Lora passes {pct(c['mp_par']['pasan'])} of cases; the plain assistant passes {pct(c['mb']['pasan']) if c['mb'] else 'not measured'}.",
          f"{'Corrida final' if c['etiqueta'].startswith('Final') else 'Corrida de desarrollo'}: Lora pasa {pct(c['mp_par']['pasan'])} de los casos; el asistente simple pasa {pct(c['mb']['pasan']) if c['mb'] else 'sin medir'}."),
         (f"Out-of-policy actions: Lora {pct(c['mp_par']['inseguros'])}, the plain assistant {pct(c['mb']['inseguros']) if c['mb'] else 'not measured'}. We report Lora's one out-of-policy action.",
          f"Resultados inseguros: Lora {pct(c['mp_par']['inseguros'])}, el asistente simple {pct(c['mb']['inseguros']) if c['mb'] else 'sin medir'}. Reportamos el único resultado inseguro de Lora."),
         ("The test is small and the brackets show it (95% Wilson intervals). Same model and tools, different control architecture, different results in this test. We say tested in our battery, not validated.", "La prueba es pequeña y los corchetes lo muestran (intervalos de Wilson al 95 %). Mismo modelo y herramientas, distinta arquitectura de control, resultados distintos en esta prueba. Decimos probado en nuestra batería, no validado.")],
        [("Today it is a prototype on synthetic data.", "Hoy es un prototipo con datos sintéticos."),
         ("For a real bank it would need its real systems, a native review of the Portuguese, a larger evaluation, and more model capacity.", "Para un banco real necesitaría sus sistemas reales, una revisión nativa del portugués, una evaluación más grande y más capacidad del modelo."),
         ("Deposits and disbursements go to a person today.", "Hoy los depósitos y desembolsos van a una persona."),
         ("The model understands. The code decides and acts. Every action is verified. Thank you.", "El modelo entiende. El código decide y actúa. Cada acción se verifica. Gracias.")],
    ]
    return ["<ul>" + "".join(_li(en, es) for en, es in diap) + "</ul>" for diap in d]


def _con_presentador(html: str, notas: list[str]) -> str:
    """Añade el modo presentador: navegación, pantalla completa y ventana de notas con cronómetro (tecla P)."""
    partes = html.split("</section>")
    assert len(partes) - 1 == len(notas), "una nota por diapositiva"
    html = "".join(f'{parte}<aside class="notas">{nota}</aside></section>' for parte, nota in zip(partes, notas)) + partes[-1]
    html = html.replace("</style>", ESTILO_PRESENTADOR + "</style>", 1)
    return html.replace("</body>", f'<div id="barra"></div><script>{SCRIPT_PRESENTADOR}</script></body>', 1)


def generar(conjunto: str, propuesto: list[str] | None = None, pruebas: str | None = None) -> str:
    secciones, contexto = diapositivas(conjunto, propuesto, pruebas or _tamano_de_las_pruebas())
    html = (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Lora · I don\'t recognize this charge</title><style>{CSS.replace('__FONDO__', _FONDO)}</style></head>'
            f'<body>{"".join(secciones)}</body></html>')
    return _con_presentador(html, _notas(contexto))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--conjunto", default="desarrollo")
    ap.add_argument("--propuesto", nargs="*", help="corridas del sistema propuesto, como en evaluacion.reporte")
    ap.add_argument("--pruebas", help="tamaño de la suite (por defecto, se cuenta con pytest --collect-only)")
    a = ap.parse_args()
    html = generar(a.conjunto, a.propuesto, a.pruebas)
    destino = RAIZ / "docs" / "presentacion"
    (destino / "presentacion.html").write_text(html, encoding="utf-8")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1920, "height": 1080})
        pg.goto((destino / "presentacion.html").as_uri())
        pg.pdf(path=str(destino / "presentacion.pdf"), width="1920px", height="1080px", print_background=True)
        b.close()
    print("diapositivas en", destino)


if __name__ == "__main__":
    main()
