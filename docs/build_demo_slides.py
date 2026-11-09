"""Generate the easy team walkthrough deck from docs/DEMO_WALKTHROUGH.md.

The markdown is the single source of truth: every numbered `##` section
has exactly one `- Do:` / `- See:` / `- Proves:` / `- Remember:` bullet
plus optional fenced code blocks. This script renders both
  - docs/DEMO_SLIDES.html  (self-contained card-layout deck)
  - docs/DEMO_SLIDES.pptx  (editable PowerPoint, python-pptx)
The PDF is produced separately: open the HTML and Print -> Save as PDF.

Run from the repo root:  python docs/build_demo_slides.py
"""
import html
import math
import re
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Inches, Pt

FONT_BODY = "Trebuchet MS"
FONT_DISPLAY = "Georgia"
FONT_MONO = "Consolas"

DOCS = Path(__file__).resolve().parent
RUNBOOK = DOCS / "DEMO_WALKTHROUGH.md"
HTML_OUT = DOCS / "DEMO_SLIDES.html"
PPTX_OUT = DOCS / "DEMO_SLIDES.pptx"

# (section range, key, toc label, kicker label, accent color)
CHAPTERS = [
    (range(1, 8),   "setup",        "Setup",         "Setup",          "#17233f"),
    (range(8, 13),  "commercial",   "Commercial",    "Commercial",     "#0f766e"),
    (range(13, 18), "supply",       "Supply",        "Supply",         "#e76f51"),
    (range(18, 23), "marketaccess", "Market Access", "Market Access",  "#6d4a7f"),
    (range(23, 28), "launch",       "Launch",        "Launch",         "#b8860b"),
    (range(28, 45), "shared",       "Extra checks",  "Extra checks",   "#2c3a5e"),
]

GROUPS = {"do": "action", "see": "outcome", "proves": "proof",
          "remember": "remember"}
CARD_HEADINGS = {"action": "What to do", "outcome": "What you get",
                 "proof": "What this proves"}


def chapter_for(num):
    for rng, key, toc, kicker, color in CHAPTERS:
        if num in rng:
            return key, toc, kicker, color
    return "shared", "Extra checks", "Extra checks", "#2c3a5e"


def _handle_section_line(line, cur, in_code):
    """Fold one source line into the current section's blocks.
    Returns the updated in_code flag."""
    if line.strip().startswith("```"):
        if not in_code:
            cur["blocks"].append(("c", []))
        return not in_code
    if in_code:
        cur["blocks"][-1][1].append(line.rstrip())
    elif line.startswith("- "):
        cur["blocks"].append(("b", line[2:].rstrip()))
    elif line.strip():
        cur["blocks"].append(("p", line.rstrip()))
    return in_code


def parse_runbook(text):
    intro = []
    sections = []
    cur = None
    in_code = False
    for line in text.split("\n"):
        m = re.match(r"^## (\d+) \| (.+)$", line)
        if m:
            cur = {"num": int(m.group(1)), "title": m.group(2).strip(),
                   "blocks": []}
            sections.append(cur)
            in_code = False
            continue
        if cur is None:
            if line.strip() and not line.startswith("# "):
                intro.append(line.rstrip())
            continue
        in_code = _handle_section_line(line, cur, in_code)
    return intro, sections


def group_blocks(blocks):
    """Split labeled bullets into the four cards; code/prose follow the
    preceding bullet's group."""
    groups = {"action": [], "outcome": [], "proof": [], "remember": []}
    cur = "action"
    for kind, payload in blocks:
        if kind == "b":
            label, _, body = payload.partition(":")
            cur = GROUPS.get(label.strip().lower(), "action")
            groups[cur].append(("b", body.strip()))
        else:
            groups[cur].append((kind, payload))
    return groups


def md(text):
    esc = html.escape(text)
    esc = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc)
    esc = re.sub(r"`([^`]+)`", r"<code>\1</code>", esc)
    esc = re.sub(r"(https?://127\.0\.0\.1:\d+[\w/]*)",
                 r'<a href="\1">\1</a>', esc)
    return esc


# ---------------------------------------------------------------- HTML
CSS = """
:root{
  --ivory:#f8f2e7; --paper:#fdfaf3; --navy:#17233f; --navy-soft:#2c3a5e;
  --teal:#0f766e; --teal-soft:#d7ebe8; --coral:#e76f51; --coral-soft:#fbdfd4;
  --ink:#232323; --muted:#5c6577; --line:#e3d9c6; --accent:#17233f;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0;height:100%;background:var(--ivory);color:var(--ink);
  font-family:"Trebuchet MS","Segoe UI",Arial,sans-serif;font-size:16px;}
h1,h2,h3{font-family:Georgia,"Times New Roman",serif;font-weight:700;
  color:var(--navy);letter-spacing:.2px;}
code{font-family:Consolas,"Courier New",monospace;background:#efe7d6;
  padding:.08em .3em;border-radius:4px;font-size:.9em;color:var(--navy);}
pre{position:relative;background:var(--navy);color:#f3ead9;padding:.7em 1em;
  border-radius:10px;font-size:16px;line-height:1.45;overflow-x:auto;
  white-space:pre-wrap;overflow-wrap:break-word;margin:.6em 0;}
pre code{font:inherit;background:none;padding:0;color:inherit;}
.copybtn{position:absolute;top:.35em;right:.45em;font:600 .68rem "Trebuchet MS";
  background:var(--teal);border:none;color:#fff;border-radius:6px;
  padding:.22em .65em;cursor:pointer;opacity:.85;}
.copybtn:hover{opacity:1;}
#deck{height:100vh;width:100vw;overflow:hidden;position:relative;}
.slide{position:absolute;inset:0;display:none;overflow-y:auto;
  padding:3vh 4vw 7vh;background:var(--paper);
  border-top:6px solid var(--accent);}
.slide.active{display:block;animation:fadein .28s ease;}
@media (prefers-reduced-motion:reduce){.slide.active{animation:none}}
@keyframes fadein{from{opacity:0}to{opacity:1}}
.slide-inner{height:100%;display:flex;flex-direction:column;min-height:0;}
.kicker{color:var(--accent);text-transform:uppercase;letter-spacing:.2em;
  font-size:.78rem;font-weight:700;margin-bottom:.15rem;}
.slide h2{font-size:clamp(1.35rem,2.5vw,2rem);margin:.05em 0 .4em;
  border-bottom:3px solid var(--accent);padding-bottom:.18em;}
.slide h2 .secnum{color:var(--accent);font-family:Consolas,monospace;
  font-size:.62em;margin-right:.4em;}
.cards{flex:1;min-height:0;display:grid;grid-template-columns:3fr 2fr;
  gap:.9rem;}
.sidecol{display:flex;flex-direction:column;gap:.9rem;min-height:0;}
.card{background:#fff;border:1px solid var(--line);border-radius:12px;
  padding:.8em 1em;box-shadow:0 1px 4px rgba(23,35,63,.06);
  overflow-y:auto;min-height:0;}
.card h3{margin:0 0 .4em;font-size:clamp(.85rem,1.05vw,1rem);
  color:var(--accent);text-transform:uppercase;letter-spacing:.09em;
  font-family:"Trebuchet MS";}
.card p{margin:.4em 0;font-size:clamp(1.05rem,1.5vw,1.35rem);
  line-height:1.42;}
.card>:last-child{margin-bottom:0;}
.action-card{border-left:5px solid var(--accent);}
.outcome-card{border-left:5px solid var(--teal);flex:1;}
.proof-card{border-left:5px solid var(--coral);flex:1;}
.remember{margin:.7em 0 0;padding:.55em 1em;border-radius:10px;
  background:var(--teal-soft);border-left:5px solid var(--teal);
  font-size:clamp(.95rem,1.2vw,1.1rem);line-height:1.4;}
.remember b{color:var(--teal);text-transform:uppercase;font-size:.78em;
  letter-spacing:.08em;margin-right:.4em;}
.slide.title-slide{background:linear-gradient(135deg,var(--navy) 0%,#1e3050 55%,var(--teal) 130%);
  color:var(--ivory);border-top-color:var(--coral);}
.slide.title-slide h1{color:var(--ivory);border:none;}
.slide.title-slide .kicker{color:#9fd4cd;}
.slide.title-slide p{color:#dfe5f2;}
.q3{display:grid;grid-template-columns:repeat(3,1fr);gap:.8rem;margin:1em 0;}
.q3 div{background:rgba(255,255,255,.1);border-radius:10px;
  padding:.7em .9em;font-size:clamp(.9rem,1.2vw,1.05rem);line-height:1.35;}
.q3 b{display:block;color:#9fd4cd;font-size:.75rem;text-transform:uppercase;
  letter-spacing:.12em;margin-bottom:.25em;}
.flow{display:flex;align-items:center;gap:.45rem;flex-wrap:wrap;margin:1em 0;}
.flow .node{background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.25);
  border-radius:10px;padding:.45em .8em;font-size:clamp(.85rem,1.1vw,1rem);
  font-weight:700;}
.flow .arr{color:var(--coral);font-weight:700;}
.chips{display:flex;gap:.5rem;flex-wrap:wrap;margin-top:.8em;}
.chip{background:var(--teal);border-radius:999px;padding:.25em 1em;
  font-size:.82rem;font-weight:700;}
.chip.alt{background:var(--coral);}
.chip.dim{background:rgba(255,255,255,.16);color:#dfe5f2;}
.small{font-size:.8rem;color:#9fb0d0;}
#controls{position:fixed;bottom:0;left:0;right:0;display:flex;gap:.4rem;
  align-items:center;justify-content:center;padding:.45rem .6rem;z-index:40;
  background:rgba(23,35,63,.92);backdrop-filter:blur(4px);}
#controls button{font-family:inherit;font-size:.85rem;border:none;
  border-radius:8px;padding:.45em .9em;cursor:pointer;background:var(--teal);color:#fff;}
#controls button:hover{background:#0c5f59;}
#controls button.sec{background:transparent;color:#cfd8ea;border:1px solid #46557a;}
#controls button.sec:hover{background:#2c3a5e;}
#counter{color:#cfd8ea;font-size:.82rem;min-width:4.5em;text-align:center;}
#progress{position:fixed;bottom:0;left:0;height:4px;background:var(--coral);
  z-index:41;transition:width .2s;}
#toc{position:fixed;top:0;right:0;bottom:0;width:min(380px,92vw);z-index:60;
  background:var(--navy);color:var(--ivory);padding:1.2rem;overflow-y:auto;
  transform:translateX(105%);transition:transform .25s ease;
  box-shadow:-4px 0 18px rgba(0,0,0,.3);}
#toc.open{transform:none;}
#toc h3{color:#dfe5f2;margin:.8em 0 .3em;font-size:1rem;
  font-family:"Trebuchet MS";padding-left:.5em;}
#toc a{display:block;color:#cfd8ea;text-decoration:none;padding:.32em .3em;
  font-size:.82rem;border-bottom:1px solid #263353;}
#toc a:hover{color:#fff;background:#2c3a5e;}
#toc a .dot{width:.75em;height:.75em;border-radius:50%;display:inline-block;
  margin-right:.5em;}
#toc .closebtn{position:absolute;top:.6rem;right:.8rem;background:none;
  border:none;color:#cfd8ea;font-size:1.3rem;cursor:pointer;}
@media (max-width:700px){
  .slide{padding-bottom:100px;}
  .slide-inner{height:auto;min-height:100%;}
  .cards{flex:none;grid-template-columns:minmax(0,1fr);}
  .sidecol{min-height:auto;}
  .card{overflow:visible;min-width:0;}
  .outcome-card,.proof-card{flex:none;}
  .q3{grid-template-columns:1fr;}
  pre{font-size:14px;}
}
@page{size:13.333in 7.5in;margin:0;}
@media print{
  *{-webkit-print-color-adjust:exact;print-color-adjust:exact;}
  #controls,#progress,#toc,.copybtn{display:none;}
  #deck{height:auto;overflow:visible;}
  .slide{position:static;display:block;overflow:hidden;width:13.333in;
    height:7.5in;page-break-after:always;padding:.42in .5in;
    animation:none;}
  .slide-inner{height:100%;}
  .kicker{font-size:11pt;margin-bottom:.06in;}
  .slide h2{font-size:26pt;margin:0 0 .18in;padding-bottom:.08in;}
  .cards{gap:.22in;}
  .sidecol{gap:.22in;}
  .card{padding:.14in .18in;overflow:visible;}
  .card h3{font-size:12pt;margin-bottom:.1in;}
  .card p{font-size:16pt;line-height:1.32;margin:.28em 0;}
  pre{font-size:14pt;padding:.1in .12in;margin:.08in 0;}
  .remember{font-size:12pt;padding:.1in .16in;margin-top:.2in;}
  .slide.title-slide{padding:.6in;}
  .slide.title-slide h1{font-size:44pt;}
  .slide.title-slide p{font-size:15pt;}
  .slide.title-slide .small{font-size:11pt;}
  .q3 div{font-size:13pt;}
  .flow .node,.chip{font-size:12pt;}
}
"""

JS = """
(function(){
  var slides = Array.prototype.slice.call(document.querySelectorAll('.slide'));
  var n = slides.length, cur = 0;
  var counter = document.getElementById('counter');
  var prog = document.getElementById('progress');
  var toc = document.getElementById('toc');
  var tocBtn = document.getElementById('tocBtn');
  var tocClose = document.getElementById('tocClose');
  document.querySelectorAll('#tocList a').forEach(function(a){
    a.addEventListener('click',function(e){
      e.preventDefault();
      go(Number.parseInt(a.dataset.idx,10)); closeToc();
    });
  });
  function go(i){
    cur = Math.max(0, Math.min(n-1, i));
    slides.forEach(function(s,j){s.classList.toggle('active', j===cur);});
    counter.textContent = (cur+1)+' / '+n;
    prog.style.width = ((cur+1)/n*100)+'%';
    if (history.replaceState) history.replaceState(null,'','#slide-'+(cur+1));
  }
  function hashSlide(){
    var m = (location.hash||'').match(/^#slide-(\\d+)$/);
    return m ? Number.parseInt(m[1],10)-1 : null;
  }
  window.addEventListener('hashchange',function(){
    var i = hashSlide();
    if(i !== null && i !== cur) go(i);
  });
  function openToc(){toc.classList.add('open');toc.removeAttribute('inert');tocClose.focus();}
  function closeToc(){
    if(!toc.classList.contains('open')) return;
    toc.classList.remove('open');toc.setAttribute('inert','');tocBtn.focus();
  }
  document.getElementById('nextBtn').addEventListener('click',function(){go(cur+1);});
  document.getElementById('prevBtn').addEventListener('click',function(){go(cur-1);});
  tocBtn.addEventListener('click',function(){
    if(toc.classList.contains('open')) closeToc(); else openToc();
  });
  tocClose.addEventListener('click',closeToc);
  document.getElementById('printBtn').addEventListener('click',function(){window.print();});
  document.getElementById('fsBtn').addEventListener('click',function(){
    try{
      if(!document.fullscreenElement){
        var p = document.documentElement.requestFullscreen &&
                document.documentElement.requestFullscreen();
        if(p && p.catch) p.catch(function(){});
      } else { document.exitFullscreen(); }
    }catch(e){}
  });
  document.querySelectorAll('.copybtn').forEach(function(btn){
    btn.addEventListener('click',function(){
      var code = btn.parentElement.querySelector('code');
      var reset = function(t){btn.textContent=t;setTimeout(function(){btn.textContent='Copy';},1500);};
      var fallback = function(){
        try{
          var r = document.createRange(); r.selectNodeContents(code);
          var s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
        }catch(e){}
        reset('Select text to copy');
      };
      try{
        if(navigator.clipboard && navigator.clipboard.writeText){
          navigator.clipboard.writeText(code.innerText).then(function(){
            reset('Copied');
          },fallback);
        } else { fallback(); }
      }catch(e){ fallback(); }
    });
  });
  document.addEventListener('keydown',function(e){
    if(e.key==='Escape'){closeToc();return;}
    var t = e.target;
    if(t && (t.tagName==='INPUT'||t.tagName==='TEXTAREA'||t.tagName==='SELECT'||
        t.tagName==='BUTTON'||t.tagName==='A'||t.isContentEditable)) return;
    var sel = window.getSelection && window.getSelection();
    if(sel && String(sel).length) return;
    if(e.ctrlKey||e.metaKey||e.altKey) return;
    if(e.key==='ArrowRight'||e.key===' '||e.key==='PageDown'){e.preventDefault();go(cur+1);}
    else if(e.key==='ArrowLeft'||e.key==='PageUp'){e.preventDefault();go(cur-1);}
    else if(e.key==='Home'){e.preventDefault();go(0);}
    else if(e.key==='End'){e.preventDefault();go(n-1);}
  });
  var start = hashSlide();
  go(start === null ? 0 : start);
})();
"""


def group_html(items):
    parts = []
    for kind, payload in items:
        if kind == "c":
            code = html.escape("\n".join(payload))
            parts.append(
                f'<pre><button class="copybtn" type="button">Copy'
                f'</button><code>{code}</code></pre>')
        else:
            parts.append(f"<p>{md(payload)}</p>")
    return "".join(parts)


def _cover_html(intro):
    return (
        '<section class="slide title-slide" data-title="Title">'
        '<div class="slide-inner">'
        '<p class="kicker">Smart Librarian</p>'
        '<h1 style="font-size:clamp(2.1rem,4.8vw,3.6rem);margin:.15em 0;">'
        'Smart Librarian \u2014 Live Demo</h1>'
        f'<p style="font-size:1.02rem;max-width:46em;">{md(" ".join(intro))}</p>'
        '<div class="q3">'
        '<div><b>What to do</b>The exact clicks and commands</div>'
        '<div><b>What you get</b>What you should see on screen</div>'
        '<div><b>What this proves</b>Why the step matters</div>'
        '</div>'
        '<div class="flow">'
        '<span class="node">Ask</span><span class="arr">&#8594;</span>'
        '<span class="node">Confirm</span><span class="arr">&#8594;</span>'
        '<span class="node">Approve</span><span class="arr">&#8594;</span>'
        '<span class="node">Render</span><span class="arr">&#8594;</span>'
        '<span class="node">Download</span><span class="arr">&#8594;</span>'
        '<span class="node">REUSE</span>'
        '</div>'
        '<div class="chips">'
        '<span class="chip">Commercial</span><span class="chip">Supply</span>'
        '<span class="chip">Market Access</span><span class="chip">Launch</span>'
        '<span class="chip alt">Snowflake Cortex</span>'
        '<span class="chip dim">Synthetic data only</span>'
        '</div>'
        '<p class="small" style="margin-top:1.6em;">'
        '45 slides = cover + 44 test steps. Arrow keys / Space navigate; '
        'the Contents button jumps to any section; Print gives one '
        'landscape page per slide.</p>'
        '</div></section>'
    )


def _section_html(s, kicker, color):
    g = group_blocks(s["blocks"])
    remember = " ".join(
        md(pl) for kind, pl in g["remember"] if isinstance(pl, str))
    return (
        f'<section class="slide" data-title="{s["num"]:02d} | '
        f'{html.escape(s["title"])}" style="--accent:{color}">'
        '<div class="slide-inner">'
        f'<p class="kicker">{html.escape(kicker)}</p>'
        f'<h2><span class="secnum">{s["num"]:02d}</span>'
        f'{html.escape(s["title"])}</h2>'
        '<div class="cards">'
        f'<div class="card action-card"><h3>{CARD_HEADINGS["action"]}</h3>'
        f'{group_html(g["action"])}</div>'
        '<div class="sidecol">'
        f'<div class="card outcome-card"><h3>{CARD_HEADINGS["outcome"]}</h3>'
        f'{group_html(g["outcome"])}</div>'
        f'<div class="card proof-card"><h3>{CARD_HEADINGS["proof"]}</h3>'
        f'{group_html(g["proof"])}</div>'
        '</div></div>'
        f'<p class="remember"><b>Remember</b>{remember}</p>'
        '</div></section>'
    )


def _toc_html(toc_links):
    out = []
    for label, color, idx in toc_links:
        if idx is None:
            out.append(
                f'<h3 style="border-left:4px solid {color}">'
                f'{html.escape(label[3:])}</h3>')
        else:
            out.append(
                f'<a href="#" data-idx="{idx}"><i class="dot" '
                f'style="background:{color}"></i>{html.escape(label)}</a>')
    return "".join(out)


def render_html(intro, sections):
    slides_html = [_cover_html(intro)]
    toc_links = [("Cover", "#e76f51", 0)]
    last_chapter = None
    for s in sections:
        key, toc_label, kicker, color = chapter_for(s["num"])
        if key != last_chapter:
            toc_links.append(("CH:" + toc_label, color, None))
            last_chapter = key
        toc_links.append((f'{s["num"]:02d} {s["title"]}', color,
                          len(slides_html)))
        slides_html.append(_section_html(s, kicker, color))

    total = len(slides_html)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Smart Librarian \u2014 Live Demo</title>
<style>{CSS}</style>
</head>
<body>
<nav id="toc" aria-label="Table of contents" inert>
  <button class="closebtn" id="tocClose" aria-label="Close contents">&times;</button>
  <h3 style="margin-top:0;border:none">Contents</h3>
  <div id="tocList">{_toc_html(toc_links)}</div>
</nav>
<div id="deck">
{chr(10).join(slides_html)}
</div>
<div id="controls" role="toolbar" aria-label="Slide controls">
  <button class="sec" id="tocBtn">&#9776; Contents</button>
  <button id="prevBtn">&#8592; Prev</button>
  <span id="counter">1 / {total}</span>
  <button id="nextBtn">Next &#8594;</button>
  <button class="sec" id="fsBtn" title="Fullscreen">&#9974; Full</button>
  <button class="sec" id="printBtn">Print</button>
</div>
<div id="progress"></div>
<script>{JS}</script>
</body>
</html>
"""


# ---------------------------------------------------------------- PPTX
NAVY = RGBColor(0x17, 0x23, 0x3F)
INK = RGBColor(0x23, 0x23, 0x23)
IVORY = RGBColor(0xF8, 0xF2, 0xE7)
CARD_BG = RGBColor(0xFF, 0xFF, 0xFF)
REMEMBER_BG = RGBColor(0xD7, 0xEB, 0xE8)
LINE_C = RGBColor(0xE3, 0xD9, 0xC6)
SUBTLE = RGBColor(0x9F, 0xB0, 0xD0)


def hx(color):
    return RGBColor.from_string(color.lstrip("#"))


def est_lines(text, size, width_in, mono=False):
    cpl = max(20, int(width_in * 72 / (size * (0.60 if mono else 0.52))))
    return max(1, math.ceil(len(text) / cpl))


def group_lines(items, size, width_in):
    lines = 0
    for kind, payload in items:
        if kind == "c":
            lines += sum(est_lines(cl, size, width_in, mono=True)
                         for cl in payload) + 0.4
        elif isinstance(payload, str):
            lines += est_lines(payload, size, width_in) + 0.3
    return lines


def fit_size(items, width_in, height_in, start=18, floor=16):
    size = start
    while size > floor and group_lines(items, size, width_in) * (size * 1.32) > height_in * 72:
        size -= 1
    return size


def add_textbox(slide, x, y, w, h, text, size, color, bold=False,
                font=FONT_BODY):
    tb = slide.shapes.add_textbox(x, y, w, h)
    p = tb.text_frame.paragraphs[0]
    r = p.add_run(); r.text = text
    r.font.size = Pt(size); r.font.bold = bold
    r.font.name = font; r.font.color.rgb = color
    return tb


def _page_num(slide, i, total, color):
    tb = slide.shapes.add_textbox(Inches(12.45), Inches(7.08),
                                  Inches(0.85), Inches(0.35))
    p = tb.text_frame.paragraphs[0]
    r = p.add_run(); r.text = f"{i} / {total}"
    r.font.size = Pt(12); r.font.color.rgb = hx(color)


def add_card(slide, x, y, w, h, heading, items, accent, body_size):
    box = slide.shapes.add_shape(1, x, y, w, h)
    box.fill.solid(); box.fill.fore_color.rgb = CARD_BG
    box.line.color.rgb = LINE_C; box.line.width = Pt(0.75)
    edge = slide.shapes.add_shape(1, x, y, Pt(4), h)
    edge.fill.solid(); edge.fill.fore_color.rgb = accent
    edge.line.fill.background()

    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = Inches(0.18); tf.margin_right = Inches(0.14)
    tf.margin_top = Inches(0.1); tf.margin_bottom = Inches(0.08)
    p = tf.paragraphs[0]
    r = p.add_run(); r.text = heading.upper()
    r.font.size = Pt(12); r.font.bold = True
    r.font.name = FONT_BODY; r.font.color.rgb = accent
    p.space_after = Pt(6)
    for kind, payload in items:
        if kind == "c":
            for cl in payload:
                p = tf.add_paragraph(); p.space_after = Pt(1)
                r = p.add_run(); r.text = cl
                r.font.name = FONT_MONO; r.font.size = Pt(body_size)
                r.font.color.rgb = NAVY
        else:
            p = tf.add_paragraph(); p.space_after = Pt(4)
            r = p.add_run(); r.text = payload
            r.font.name = FONT_BODY; r.font.size = Pt(body_size)
            r.font.color.rgb = INK


def _pptx_cover(prs, intro, total):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg = slide.shapes.add_shape(1, 0, 0, prs.slide_width, prs.slide_height)
    bg.fill.solid(); bg.fill.fore_color.rgb = NAVY; bg.line.fill.background()
    band = slide.shapes.add_shape(1, 0, Inches(6.0), prs.slide_width, Pt(4))
    band.fill.solid(); band.fill.fore_color.rgb = hx("#e76f51")
    band.line.fill.background()
    add_textbox(slide, Inches(0.8), Inches(0.5), Inches(11.7), Inches(0.45),
                "SMART LIBRARIAN", 14, hx("#9fd4cd"), bold=True)
    add_textbox(slide, Inches(0.8), Inches(1.0), Inches(11.7), Inches(1.0),
                "Smart Librarian \u2014 Live Demo", 40, IVORY, bold=True,
                font=FONT_DISPLAY)
    tb = slide.shapes.add_textbox(Inches(0.8), Inches(1.95), Inches(11.6),
                                  Inches(1.3))
    tf = tb.text_frame; tf.word_wrap = True
    for i, line in enumerate(intro):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        r = p.add_run(); r.text = line.strip()
        r.font.size = Pt(16); r.font.name = FONT_BODY
        r.font.color.rgb = RGBColor(0xDF, 0xE5, 0xF2)
        p.space_after = Pt(5)
    q = ["What to do - the exact clicks and commands",
         "What you get - what you should see on screen",
         "What this proves - why the step matters"]
    for j, text in enumerate(q):
        card = slide.shapes.add_shape(1, Inches(0.8 + j * 4.05),
                                    Inches(3.3), Inches(3.85), Inches(0.95))
        card.fill.solid(); card.fill.fore_color.rgb = RGBColor(0x2C, 0x3A, 0x5E)
        card.line.fill.background()
        tfp = card.text_frame; tfp.word_wrap = True
        p = tfp.paragraphs[0]
        r = p.add_run(); r.text = text
        r.font.size = Pt(16); r.font.name = FONT_BODY
        r.font.color.rgb = IVORY
    add_textbox(slide, Inches(0.8), Inches(4.5), Inches(11.8), Inches(0.5),
                "Ask  ->  Confirm  ->  Approve  ->  Render  ->  Download"
                "  ->  REUSE", 20, IVORY, bold=True)
    add_textbox(slide, Inches(0.8), Inches(5.1), Inches(11.8), Inches(0.5),
                "Commercial   |   Supply   |   Market Access   |   Launch"
                "      [Snowflake Cortex]   [Synthetic data only]",
                16, hx("#9fd4cd"))
    add_textbox(slide, Inches(0.8), Inches(6.55), Inches(11.8), Inches(0.4),
                "45 slides = cover + 44 test steps. This is a guide to "
                "tests you will perform, not a claim of today's results.",
                12, SUBTLE)
    _page_num(slide, 1, total, "#e76f51")
    return slide


def _pptx_section(prs, s, kicker, color, idx, total):
    accent = hx(color)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bar = slide.shapes.add_shape(1, 0, 0, prs.slide_width, Pt(6))
    bar.fill.solid(); bar.fill.fore_color.rgb = accent
    bar.line.fill.background()
    add_textbox(slide, Inches(0.6), Inches(0.28), Inches(12), Inches(0.35),
                kicker.upper(), 12, accent, bold=True)
    add_textbox(slide, Inches(0.6), Inches(0.62), Inches(12.2), Inches(0.85),
                f'{s["num"]:02d} | {s["title"]}', 27, NAVY, bold=True,
                font=FONT_DISPLAY)
    ln = slide.shapes.add_shape(1, Inches(0.62), Inches(1.5),
                                Inches(2.2), Pt(3))
    ln.fill.solid(); ln.fill.fore_color.rgb = accent
    ln.line.fill.background()

    g = group_blocks(s["blocks"])
    a_size = fit_size(g["action"], 7.2, 4.3)
    add_card(slide, Inches(0.6), Inches(1.75), Inches(7.55), Inches(4.55),
             CARD_HEADINGS["action"], g["action"], accent, a_size)
    o_size = fit_size(g["outcome"], 4.05, 2.05)
    add_card(slide, Inches(8.35), Inches(1.75), Inches(4.4), Inches(2.2),
             CARD_HEADINGS["outcome"], g["outcome"], hx("#0f766e"), o_size)
    p_size = fit_size(g["proof"], 4.05, 2.1)
    add_card(slide, Inches(8.35), Inches(4.1), Inches(4.4), Inches(2.2),
             CARD_HEADINGS["proof"], g["proof"], hx("#e76f51"), p_size)

    strip = slide.shapes.add_shape(1, Inches(0.6), Inches(6.42),
                                   Inches(12.15), Inches(0.85))
    strip.fill.solid(); strip.fill.fore_color.rgb = REMEMBER_BG
    strip.line.fill.background()
    tf = strip.text_frame; tf.word_wrap = True
    tf.margin_left = Inches(0.15); tf.margin_top = Inches(0.05)
    p = tf.paragraphs[0]
    r = p.add_run(); r.text = "REMEMBER  "
    r.font.size = Pt(12); r.font.bold = True
    r.font.color.rgb = hx("#0f766e"); r.font.name = FONT_BODY
    remember_text = " ".join(
        pl for kind, pl in g["remember"] if isinstance(pl, str))
    r = p.add_run(); r.text = remember_text
    r.font.size = Pt(16); r.font.color.rgb = INK; r.font.name = FONT_BODY
    _page_num(slide, idx, total, color)
    return slide


def render_pptx(intro, sections):
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    total = len(sections) + 1
    _pptx_cover(prs, intro, total)
    for idx, s in enumerate(sections, start=2):
        key, toc_label, kicker, color = chapter_for(s["num"])
        _pptx_section(prs, s, kicker, color, idx, total)
    prs.save(PPTX_OUT)


def main():
    text = RUNBOOK.read_text(encoding="utf-8")
    intro, sections = parse_runbook(text)
    HTML_OUT.write_text(render_html(intro, sections), encoding="utf-8")
    render_pptx(intro, sections)
    print(f"{HTML_OUT.name}: {len(sections) + 1} slides "
          f"({len(sections)} sections + cover)")
    print(f"{PPTX_OUT.name}: {len(sections) + 1} slides")


if __name__ == "__main__":
    main()
