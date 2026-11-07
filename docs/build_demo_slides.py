"""Generate the team demo test deck from docs/TEAM_DEMO_TEST_RUNBOOK.md.

The markdown is the single source of truth: this script parses every
numbered `##` section and renders both
  - docs/DEMO_SLIDES.html  (self-contained illustrated deck)
  - docs/DEMO_SLIDES.pptx  (editable PowerPoint, python-pptx)

Run from the repo root:  python docs/build_demo_slides.py
"""
import html
import math
import re
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Inches, Pt

DOCS = Path(__file__).resolve().parent
RUNBOOK = DOCS / "TEAM_DEMO_TEST_RUNBOOK.md"
HTML_OUT = DOCS / "DEMO_SLIDES.html"
PPTX_OUT = DOCS / "DEMO_SLIDES.pptx"

FONT_BODY = "Trebuchet MS"
FONT_DISPLAY = "Georgia"
FONT_MONO = "Consolas"

CHAPTERS = [
    (range(1, 8),   "setup",        "Setup & ground rules", "#17233f"),
    (range(8, 13),  "commercial",   "Commercial C1-C5",     "#0f766e"),
    (range(13, 18), "supply",       "Supply S1-S5",         "#e76f51"),
    (range(18, 23), "marketaccess", "Market Access M1-M5",  "#6d4a7f"),
    (range(23, 28), "launch",       "Launch L1-L5",         "#b8860b"),
    (range(28, 45), "shared",       "Shared checks G1-G17", "#2c3a5e"),
]


def chapter_for(num):
    for rng, key, label, color in CHAPTERS:
        if num in rng:
            return key, label, color
    return "shared", "Shared checks G1-G17", "#2c3a5e"


def _handle_section_line(cur, line, in_code):
    """Handle one body line inside a numbered section.

    Mutates cur["blocks"]; returns the new in_code state.
    """
    if line.strip().startswith("```"):
        if not in_code:
            cur["blocks"].append(("c", []))
        return not in_code
    if in_code:
        cur["blocks"][-1][1].append(line.rstrip())
        return in_code
    if line.startswith("- "):
        cur["blocks"].append(("b", line[2:].rstrip()))
    elif line.strip():
        cur["blocks"].append(("p", line.rstrip()))
    return in_code


def parse_runbook(text):
    lines = text.split("\n")
    intro = []
    sections = []
    cur = None
    in_code = False
    for line in lines:
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
        in_code = _handle_section_line(cur, line, in_code)
    return intro, sections


def classify(bullet):
    if re.match(r"^Expected\b", bullet):
        return "exp"
    if re.match(r"^(Capture|Record|Save)\b", bullet):
        return "evi"
    return "act"


def inline_md(escaped):
    """Apply minimal inline markdown on already-escaped text."""
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"(https?://127\.0\.0\.1:\d+[\w/]*)",
                     r'<a href="\1">\1</a>', escaped)
    return escaped


def md(text):
    return inline_md(html.escape(text))


# ---------------------------------------------------------------- HTML
CSS = """
:root{
  --ivory:#f8f2e7; --paper:#fdfaf3; --navy:#17233f; --navy-soft:#2c3a5e;
  --teal:#0f766e; --teal-soft:#d7ebe8; --coral:#e76f51; --coral-soft:#fbdfd4;
  --ink:#232323; --muted:#5c6577; --line:#e3d9c6; --accent:#17233f;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0;height:100%;background:var(--ivory);color:var(--ink);
  font-family:"Trebuchet MS","Segoe UI",Arial,sans-serif;}
h1,h2,h3,.serif{font-family:Georgia,"Times New Roman",serif;font-weight:700;
  color:var(--navy);letter-spacing:.2px;}
code{font-family:Consolas,"Courier New",monospace;background:#efe7d6;
  padding:.08em .3em;border-radius:4px;font-size:.9em;color:var(--navy);}
pre{position:relative;background:var(--navy);color:#f3ead9;padding:.8em 1em;
  border-radius:10px;font-family:Consolas,"Courier New",monospace;
  font-size:.9em;line-height:1.45;overflow-x:auto;white-space:pre-wrap;
  overflow-wrap:anywhere;margin:.55em 0;}
pre code{background:none;padding:0;color:inherit;}
.copybtn{position:absolute;top:.4em;right:.5em;font:600 .7rem "Trebuchet MS";
  background:var(--teal);border:none;color:#fff;border-radius:6px;
  padding:.25em .7em;cursor:pointer;opacity:.85;}
.copybtn:hover{opacity:1;}
#deck{height:100vh;width:100vw;overflow:hidden;position:relative;}
.slide{position:absolute;inset:0;display:none;overflow-y:auto;
  padding:4.5vh 6vw 9vh;background:var(--paper);border-top:6px solid var(--accent);}
.slide.active{display:block;animation:fadein .28s ease;}
@media (prefers-reduced-motion:reduce){.slide.active{animation:none}}
@keyframes fadein{from{opacity:0}to{opacity:1}}
.kicker{color:var(--accent);text-transform:uppercase;letter-spacing:.2em;
  font-size:.78rem;font-weight:700;margin-bottom:.3rem;}
.slide h2{font-size:clamp(1.35rem,2.6vw,2rem);margin:.1em 0 .55em;
  border-bottom:3px solid var(--accent);padding-bottom:.22em;}
.slide h2 .secnum{color:var(--accent);font-family:Consolas,monospace;
  font-size:.65em;margin-right:.4em;}
ul.steps{list-style:none;margin:.4em 0;padding:0;}
ul.steps li{margin:.5em 0;padding-left:1.15em;position:relative;
  font-size:clamp(.9rem,1.35vw,1.02rem);line-height:1.42;}
ul.steps li::before{content:"";position:absolute;left:0;top:.5em;
  width:.55em;height:.55em;border-radius:50%;background:var(--accent);}
ul.steps li.exp{background:var(--coral-soft);border-left:4px solid var(--coral);
  border-radius:0 8px 8px 0;padding:.45em .7em .45em 1.25em;}
ul.steps li.exp::before{background:var(--coral);left:.45em;}
ul.steps li.evi{background:var(--teal-soft);border-left:4px solid var(--teal);
  border-radius:0 8px 8px 0;padding:.45em .7em .45em 1.25em;}
ul.steps li.evi::before{background:var(--teal);left:.45em;}
ul.steps li .lbl{font-weight:700;text-transform:uppercase;font-size:.72em;
  letter-spacing:.08em;display:block;color:var(--navy);}
.slide.title-slide{background:linear-gradient(135deg,var(--navy) 0%,#1e3050 55%,var(--teal) 130%);
  color:var(--ivory);border-top-color:var(--coral);}
.slide.title-slide h1{color:var(--ivory);border:none;}
.slide.title-slide .kicker{color:#9fd4cd;}
.tag{display:inline-block;background:rgba(255,255,255,.14);color:#dfe5f2;
  border-radius:999px;padding:.15em .8em;font-size:.78rem;font-weight:700;
  letter-spacing:.05em;margin:.15em .25em .15em 0;}
.tag.solid{background:var(--teal-soft);color:var(--teal);}
.small{font-size:.82rem;color:var(--muted);}
.legend{display:flex;gap:1.2rem;flex-wrap:wrap;margin:.9em 0;font-size:.8rem;}
.legend span{display:inline-flex;align-items:center;gap:.35em;}
.dot{width:.8em;height:.8em;border-radius:50%;display:inline-block;}
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
#toc h3{color:var(--ivory);margin:.8em 0 .3em;font-size:1rem;}
#toc a{display:block;color:#cfd8ea;text-decoration:none;padding:.32em .3em;
  font-size:.82rem;border-bottom:1px solid #263353;}
#toc a:hover{color:#fff;background:#2c3a5e;}
#toc a .dot{margin-right:.5em;}
#toc .closebtn{position:absolute;top:.6rem;right:.8rem;background:none;
  border:none;color:#cfd8ea;font-size:1.3rem;cursor:pointer;}
@page{size:13.333in 7.5in;margin:0;}
@media print{
  *{-webkit-print-color-adjust:exact;print-color-adjust:exact;}
  #controls,#progress,#toc,.copybtn{display:none;}
  #deck{height:auto;overflow:visible;}
  #deck .slide{position:static;display:block;overflow:visible;
    page-break-after:always;min-height:auto;padding:.7cm 1cm;animation:none;}
  .slide h2{font-size:15pt;margin-bottom:.3em;}
  body{font-size:8.8pt;}
  pre{font-size:7.6pt;padding:.5em .7em;}
  ul.steps li{margin:.3em 0;font-size:8.8pt;}
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
        reset('Select text to copy'); // honest: clipboard unavailable
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
  var m = location.hash.match(/slide-(\\d+)/);
  go(m ? Number.parseInt(m[1],10)-1 : 0);
})();
"""


def _title_slide_html(intro):
    title_intro = " ".join(intro)
    return (
        '<section class="slide title-slide" data-title="Title" '
        'style="--accent:#e76f51">'
        '<div class="slide-inner">'
        '<p class="kicker">Smart Librarian - complete team demo test deck</p>'
        '<h1 style="font-size:clamp(2rem,4.6vw,3.4rem);margin:.2em 0;">'
        'Full four-dataset<br>live-LLM test run</h1>'
        '<p style="font-size:1.05rem;max-width:44em;color:#dfe5f2;">'
        f'{md(title_intro)}</p>'
        '<div style="margin-top:1.2em;">'
        '<span class="tag">44 test sections</span>'
        '<span class="tag">4 datasets x 5 steps + shared checks</span>'
        '<span class="tag">Manual test plan - not today\'s results</span>'
        '</div>'
        '<p class="small" style="margin-top:2em;color:#9fb0d0;">'
        'Arrow keys / Space navigate. The Contents button jumps to any '
        'section. Print produces one landscape page per section.</p>'
        '<div class="legend">'
        '<span><i class="dot" style="background:#e76f51"></i>'
        'Orange = expected result</span>'
        '<span><i class="dot" style="background:#0f766e"></i>'
        'Teal = evidence to record</span>'
        '<span><i class="dot" style="background:#17233f"></i>'
        'Dot = action / instruction</span>'
        '</div></div></section>')


def _bullet_html(payload):
    cls = classify(payload)
    lbl = {"exp": '<span class="lbl">Expected</span>',
           "evi": '<span class="lbl">Evidence</span>'}.get(cls, "")
    return f'<li class="{cls}">{lbl}{md(payload)}</li>'


def _section_body_html(blocks):
    parts = []
    in_list = False
    for kind, payload in blocks:
        if kind == "b":
            if not in_list:
                parts.append('<ul class="steps">')
                in_list = True
            parts.append(_bullet_html(payload))
        else:
            if in_list:
                parts.append('</ul>')
                in_list = False
            if kind == "c":
                code = html.escape("\n".join(payload))
                parts.append(
                    '<pre><button class="copybtn" type="button">Copy'
                    f'</button><code>{code}</code></pre>')
            else:
                parts.append(f'<p>{md(payload)}</p>')
    if in_list:
        parts.append('</ul>')
    return "".join(parts)


def _section_slide_html(s, label, color):
    head = (f'<section class="slide" data-title="{s["num"]:02d} | '
            f'{html.escape(s["title"])}" style="--accent:{color}">'
            '<div class="slide-inner">'
            f'<p class="kicker">{html.escape(label)}</p>'
            f'<h2><span class="secnum">{s["num"]:02d}</span>'
            f'{html.escape(s["title"])}</h2>')
    return head + _section_body_html(s["blocks"]) + '</div></section>'


def _toc_links_html(toc_links):
    toc_html = []
    for label, color, idx in toc_links:
        if idx is None:
            toc_html.append(
                f'<h3 style="color:#dfe5f2;border-left:4px solid {color};'
                f'padding-left:.5em">{html.escape(label[3:])}</h3>')
        else:
            toc_html.append(
                f'<a href="#" data-idx="{idx}"><i class="dot" '
                f'style="background:{color}"></i>{html.escape(label)}</a>')
    return "".join(toc_html)


def render_html(intro, sections):
    slides_html = [_title_slide_html(intro)]
    toc_links = [('Title', '#e76f51', 0)]

    last_chapter = None
    for s in sections:
        key, label, color = chapter_for(s["num"])
        if key != last_chapter:
            toc_links.append(("CH:" + label, color, None))
            last_chapter = key
        toc_links.append((f'{s["num"]:02d} {s["title"]}', color,
                          len(slides_html)))
        slides_html.append(_section_slide_html(s, label, color))

    total = len(slides_html)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Smart Librarian - Team Demo Test Deck</title>
<style>{CSS}</style>
</head>
<body>
<nav id="toc" aria-label="Table of contents" inert>
  <button class="closebtn" id="tocClose" aria-label="Close contents">&times;</button>
  <h3 style="margin-top:0">Contents</h3>
  <div id="tocList">{_toc_links_html(toc_links)}</div>
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
CORAL = RGBColor(0xB8, 0x4A, 0x2E)
TEAL = RGBColor(0x0F, 0x76, 0x6E)
MUTED = RGBColor(0x5C, 0x65, 0x77)
IVORY = RGBColor(0xF8, 0xF2, 0xE7)


def hx(color):
    return RGBColor.from_string(color.lstrip("#"))


def est_lines(text, size, width_in=11.9):
    cpl = max(20, int(width_in * 96 / (size * 0.52)))
    return max(1, math.ceil(len(text) / cpl))


def _pptx_title_slide(prs, intro, total):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg = slide.shapes.add_shape(1, 0, 0, prs.slide_width, prs.slide_height)
    bg.fill.solid(); bg.fill.fore_color.rgb = NAVY; bg.line.fill.background()
    band = slide.shapes.add_shape(1, 0, Inches(5.9),
                                  prs.slide_width, Inches(0.06))
    band.fill.solid(); band.fill.fore_color.rgb = hx("#e76f51")
    band.line.fill.background()

    tb = slide.shapes.add_textbox(Inches(0.8), Inches(0.7),
                                  Inches(11.7), Inches(0.5))
    p = tb.text_frame.paragraphs[0]
    r = p.add_run(); r.text = "SMART LIBRARIAN - COMPLETE TEAM DEMO TEST DECK"
    r.font.size = Pt(13); r.font.bold = True; r.font.color.rgb = hx("#9fd4cd")

    tb = slide.shapes.add_textbox(Inches(0.8), Inches(1.25),
                                  Inches(11.7), Inches(1.8))
    p = tb.text_frame.paragraphs[0]
    r = p.add_run(); r.text = "Full four-dataset live-LLM test run"
    r.font.size = Pt(44); r.font.bold = True
    r.font.name = FONT_DISPLAY; r.font.color.rgb = IVORY

    tb = slide.shapes.add_textbox(Inches(0.8), Inches(3.0),
                                  Inches(11.5), Inches(2.6))
    tf = tb.text_frame; tf.word_wrap = True
    for i, line in enumerate(intro):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        r = p.add_run(); r.text = line.strip()
        r.font.size = Pt(15); r.font.name = FONT_BODY
        r.font.color.rgb = RGBColor(0xDF, 0xE5, 0xF2)
        p.space_after = Pt(5)
    p = tf.add_paragraph()
    r = p.add_run()
    r.text = ("Legend: bullet = action; orange text = expected result; "
              "teal text = evidence to record; Consolas = copyable command.")
    r.font.size = Pt(13); r.font.italic = True
    r.font.color.rgb = hx("#9fd4cd")
    _page_num(slide, 1, total, "#e76f51")


def _fit_font_size(blocks):
    """Pick the largest body font size (15 down to 11) that fits."""
    size = 15
    while size > 11:
        lines = sum(
            est_lines(pl if isinstance(pl, str) else " ".join(pl), size)
            for _, pl in blocks)
        if lines * (size * 1.35) <= 5.1 * 72:
            break
        size -= 1
    return size


def _body_runs(blocks):
    """Yield (text, font, size_delta, color, space_after) per body line."""
    for kind, payload in blocks:
        if kind == "b":
            color = {"exp": CORAL, "evi": TEAL}.get(classify(payload), INK)
            yield "- " + payload, FONT_BODY, 0, color, 4
        elif kind == "c":
            for cl in payload:
                yield cl, FONT_MONO, 1, NAVY, 2
        else:
            yield payload, FONT_BODY, 1, MUTED, 4


def _add_body(tf, blocks, size):
    first = True
    for text, font, delta, color, space in _body_runs(blocks):
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p.space_after = Pt(space)
        r = p.add_run(); r.text = text
        r.font.name = font; r.font.size = Pt(size - delta)
        r.font.color.rgb = color


def _pptx_section_slide(prs, s, idx, total):
    _key, label, color = chapter_for(s["num"])
    accent = hx(color)
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    bar = slide.shapes.add_shape(1, 0, 0, prs.slide_width, Pt(6))
    bar.fill.solid(); bar.fill.fore_color.rgb = accent
    bar.line.fill.background()

    tb = slide.shapes.add_textbox(Inches(0.6), Inches(0.32),
                                  Inches(12), Inches(0.4))
    p = tb.text_frame.paragraphs[0]
    r = p.add_run(); r.text = label.upper()
    r.font.size = Pt(12); r.font.bold = True; r.font.color.rgb = accent

    tb = slide.shapes.add_textbox(Inches(0.6), Inches(0.72),
                                  Inches(12), Inches(0.95))
    p = tb.text_frame.paragraphs[0]
    r = p.add_run(); r.text = f'{s["num"]:02d} | {s["title"]}'
    r.font.size = Pt(28); r.font.bold = True
    r.font.name = FONT_DISPLAY; r.font.color.rgb = NAVY

    ln = slide.shapes.add_shape(1, Inches(0.62), Inches(1.55),
                                Inches(2.2), Pt(3))
    ln.fill.solid(); ln.fill.fore_color.rgb = accent
    ln.line.fill.background()

    body = slide.shapes.add_textbox(Inches(0.7), Inches(1.8),
                                    Inches(11.9), Inches(5.3))
    tf = body.text_frame; tf.word_wrap = True
    _add_body(tf, s["blocks"], _fit_font_size(s["blocks"]))

    _page_num(slide, idx, total, color)


def render_pptx(intro, sections):
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    total = len(sections) + 1

    _pptx_title_slide(prs, intro, total)
    for idx, s in enumerate(sections, start=2):
        _pptx_section_slide(prs, s, idx, total)

    prs.save(PPTX_OUT)


def _page_num(slide, i, total, color):
    tb = slide.shapes.add_textbox(Inches(12.2), Inches(6.95),
                                  Inches(1.0), Inches(0.4))
    p = tb.text_frame.paragraphs[0]
    r = p.add_run(); r.text = f"{i} / {total}"
    r.font.size = Pt(11); r.font.color.rgb = hx(color)


def main():
    text = RUNBOOK.read_text(encoding="utf-8")
    intro, sections = parse_runbook(text)
    HTML_OUT.write_text(render_html(intro, sections), encoding="utf-8")
    render_pptx(intro, sections)
    print(f"{HTML_OUT.name}: {len(sections) + 1} slides "
          f"({len(sections)} sections + title)")
    print(f"{PPTX_OUT.name}: {len(sections) + 1} slides")


if __name__ == "__main__":
    main()
