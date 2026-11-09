"""Generate the judge-facing pitch deck for Smart Librarian.

Renders both
  - docs/JUDGES_PRESENTATION.html  (self-contained 16:9 deck)
  - docs/JUDGES_PRESENTATION.pptx  (editable PowerPoint, python-pptx)
The PDF is produced separately via a local browser print
(docs/JUDGES_PRESENTATION.pdf).

Run from the repo root:  python docs/build_pitch_slides.py
"""
import html
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches, Pt

FONT_BODY = "Trebuchet MS"
FONT_DISPLAY = "Georgia"

DOCS = Path(__file__).resolve().parent
HTML_OUT = DOCS / "JUDGES_PRESENTATION.html"
PPTX_OUT = DOCS / "JUDGES_PRESENTATION.pptx"

DIV_END = "</div>"

NAVY = "#17233f"
NAVY_SOFT = "#2c3a5e"
TEAL = "#0f766e"
TEAL_SOFT = "#d7ebe8"
CORAL = "#e76f51"
CORAL_SOFT = "#fbdfd4"
IVORY = "#f8f2e7"
PAPER = "#fdfaf3"
INK = "#232323"
MUTED = "#5c6577"
LINE = "#e3d9c6"

SLIDES = [
    {
        "layout": "title", "appendix": False,
        "kicker": "SINCE AI 2026 \u00b7 BAYER CHALLENGE",
        "title": "Build less.\nTrust what remains.",
        "product": "Smart Librarian",
        "subtitle": "From a business question to a governed report \u2014 "
                    "without creating the next duplicate.",
        "footer": "Working prototype \u00b7 Official synthetic builder pack \u00b7 "
                  "Not Bayer business data",
        "notes": "Open with the tension: AI makes analytics easier to create. "
                 "Our question is whether another report should exist at all. "
                 "Introduce Smart Librarian as a governance-first analytics "
                 "prototype.",
    },
    {
        "layout": "problem", "appendix": False,
        "kicker": "THE PROBLEM",
        "title": "AI can accelerate the wrong thing.",
        "stages": ["More requests", "More dashboards", "More duplicated logic"],
        "pains": ["Which KPI is right?", "Who owns this?",
                  "Can we safely retire it?"],
        "takeaway": "During a Tableau-to-Power BI migration, creation alone "
                    "is not the win.",
        "notes": "The challenge brief names dashboard sprawl, duplicate "
                 "logic, unclear ownership and technical debt. Do not claim "
                 "we measured these costs at Bayer.",
    },
    {
        "layout": "pillars", "appendix": False,
        "kicker": "OUR RESPONSE",
        "title": "Reuse before you create.",
        "pillars": ["Reuse exact approved scope", "Make ownership explicit",
                    "Keep evidence with the output"],
        "supporting": "AI proposes intent. People confirm responsibility. "
                      "Deterministic checks govern the result.",
        "notes": "Reuse here means an equivalent normalized confirmed "
                 "specification, owner and source fingerprint. It is not "
                 "general visual or semantic equivalence across arbitrary "
                 "dashboards.",
    },
    {
        "layout": "twocol", "appendix": False,
        "kicker": "MEANINGFUL AI, BOUNDED AUTHORITY",
        "title": "Let AI interpret. Never let it silently decide.",
        "left_head": "LLM proposes",
        "left_items": ["Products", "markets", "fields", "periods"],
        "right_head": "Governed workflow controls",
        "right_items": ["Validate choices", "confirm scope", "choose owner",
                        "separate approval"],
        "footer": "Snowflake Cortex for opt-in extraction. No LLM-calculated "
                  "business values.",
        "notes": "Show that the useful AI task is language-to-structured "
                 "intent, not unrestricted text-to-SQL. A provider outage is "
                 "shown as offline fallback, never as successful live "
                 "extraction. The roles and approval actors are simulated.",
    },
    {
        "layout": "demo", "appendix": False,
        "kicker": "LIVE DEMO",
        "title": "One question. An accountable answer.",
        "quote": "Show monthly Nubeqa net sales and sales forecast in "
                 "Germany for January through March 2026.",
        "journey": ["Ask", "Confirm scope + owner", "Create plan",
                    "Separate approval", "Freeze report", "Export"],
        "badge": "Commercial \u00b7 Nubeqa \u00b7 Germany \u00b7 Jan\u2013Mar 2026",
        "footer": "Synthetic source data \u00b7 Explicit owner: OWN-001",
        "notes": "Switch to the verified running Snowflake demo; use the "
                 "launcher-printed URL, not a hardcoded slide URL. Tick the "
                 "LLM opt-in and confirm last extraction is llm. Confirm both "
                 "fields, three months and OWN-001. Create pending plan, "
                 "approve via DEMO-CHALLENGE-APPROVER in the separate-actor "
                 "block without switching requester, render and record plan "
                 "ID. If this was already approved the request may reuse it: "
                 "prepare a fresh DB before presentation, not during it. Do "
                 "not show credentials.",
    },
    {
        "layout": "reveal", "appendix": False,
        "kicker": "THE REVEAL",
        "title": "The second request should not create a second report.",
        "emphasis": "REUSE",
        "supporting": "Same confirmed scope + same owner + same source "
                      "fingerprint \u2192 existing approved plan",
        "contrast": [("Reorder the same fields", "same plan"),
                     ("Remove a field", "different scope")],
        "footer": "Wording is not identity. The normalized specification is.",
        "notes": "Repeat the commercial request or reorder its two fields. "
                 "Show the original plan ID returned. Removing forecast must "
                 "not return the original two-field plan; it is pending or "
                 "reuses its own previously approved plan. An approved but "
                 "not rendered reused plan still needs rendering.",
    },
    {
        "layout": "pbi", "appendix": False,
        "kicker": "POWER BI HANDOFF",
        "title": "The report travels. Its evidence travels with it.",
        "workflow": ["PBIP ZIP", "Extract fully", "Open GovernedReport.pbip",
                     "Refresh"],
        "pages": ["Dashboard", "Source Evidence", "Ownership & Evidence"],
        "footer": "Packaged frozen snapshot \u2014 not a live Snowflake "
                  "connection.",
        "notes": "Show a prepared Power BI Desktop project. First Refresh "
                 "loads packaged frozen data. Inspect all three pages and "
                 "compare scope, values, units and owner to frozen "
                 "preview/CSV. ZIP download alone is not a Power BI pass. If "
                 "Desktop is unavailable, call this stage NOT RUN. No service "
                 "publishing or live Snowflake BI connection is implemented.",
    },
    {
        "layout": "domains", "appendix": False,
        "kicker": "ONE CONTROL PATTERN, FOUR DOMAINS",
        "title": "Different questions. The same discipline.",
        "domains": [
            ("Commercial", "Monthly", "Net sales + forecast"),
            ("Supply", "Snapshot", "OTIF + inventory + risk"),
            ("Market Access", "Snapshot", "Coverage + reimbursement"),
            ("Launch", "Events", "Milestones + status"),
        ],
        "footer": "Native units. Source-backed rows. No invented time trends "
                  "or readiness scores.",
        "notes": "Commercial is monthly, Supply and Market Access are "
                 "snapshots, Launch is event-grain. Launch milestone fields "
                 "are not a calculated readiness KPI. Use other domains as "
                 "breadth, not four full repeated live demos.",
    },
    {
        "layout": "estate", "appendix": False,
        "kicker": "BEYOND CREATION",
        "title": "An analytics estate needs an exit strategy.",
        "decisions": ["Review reuse candidates", "Propose migration",
                      "Propose consolidation or retirement"],
        "evidence": ["Owner", "KPI catalog", "Usage", "Dependencies",
                     "Governance signals"],
        "status": "Approved proposal \u2260 executed change",
        "footer": "Candidate similarity is context, not certified report "
                  "equivalence.",
        "notes": "Estate decisions combines source metadata and evidence for "
                 "a human proposal. Lifecycle actions do not modify the real "
                 "BI estate. KPI catalog metadata is not an executable "
                 "certified semantic model.",
    },
    {
        "layout": "evidence", "appendix": False,
        "kicker": "PROOF, NOT PROMISE",
        "title": "A working prototype. Clear evidence boundaries.",
        "tiles": [
            ("Prior local end-to-end checks",
             "Four-domain approval, frozen render, exports, REUSE and "
             "Power BI page checks."),
            ("Separate Snowflake checks",
             "Four-domain live intent extraction verified on "
             "7 November 2026."),
        ],
        "distinction": "The complete end-to-end checks used an earlier "
                       "provider. A complete Snowflake end-to-end pass is "
                       "not claimed by those checks.",
        "footer": "Today\u2019s live demo is evidence only for the steps "
                  "actually shown.",
        "notes": "Grounding: README.md Verified state and "
                 "docs/CHALLENGE_DEMO.md. Historical browser/Power BI "
                 "evidence under artifacts/downloads/"
                 "team_acceptance_20261107_072528 and artifacts/logs/"
                 "pbi-accept-gate.log; Snowflake evidence under "
                 "artifacts/logs/snowflake_live_20261107_170832_665939/"
                 "results.json and snowflake_ui_recheck_20261107_173007_"
                 "684893.json. Do not state tests were rerun today. Do not "
                 "convert historical results into a combined Snowflake e2e "
                 "claim. Evidence is local and git-ignored.",
    },
    {
        "layout": "roadmap", "appendix": False,
        "kicker": "PATH TO ENTERPRISE",
        "title": "Scale the control plane, not the dashboard count.",
        "current_head": "Working locally",
        "current": ["Confirmed specifications", "persisted plans",
                    "frozen exports", "audit events"],
        "next_head": "Next integrations",
        "next": ["Enterprise identity", "managed registry",
                 "approved BI deployment", "certified semantic bindings"],
        "footer": "Prototype limits: simulated authorization; no production "
                  "lifecycle execution or Power BI service publishing.",
        "notes": "These next integrations are proposed architecture, not "
                 "current features. The local app is loopback-only and "
                 "unauthenticated; do not propose exposing it publicly. An "
                 "enterprise pilot should validate reuse rate, review effort "
                 "and maintenance impact; no business improvement has been "
                 "measured here.",
    },
    {
        "layout": "closing", "appendix": False,
        "kicker": "SMART LIBRARIAN",
        "title": "The best new dashboard\nmight be the one we never create.",
        "anchors": ["Fewer duplicates", "Explicit ownership",
                    "Evidence that stays attached"],
        "qualifier": "The intended business outcome \u2014 not a measured "
                     "impact claim.",
        "close": "Build less. Build better. Govern by design.",
        "notes": "End on the business outcome and invite judges to inspect a "
                 "plan, its evidence and its reuse identity. Fewer "
                 "duplicates is a design goal demonstrated by exact-scope "
                 "reuse, not a measured enterprise reduction.",
    },
    {
        "layout": "arch", "appendix": True,
        "kicker": "APPENDIX \u00b7 ARCHITECTURE",
        "title": "A thin AI layer. An explicit governance spine.",
        "ui": "Streamlit UI",
        "api": "FastAPI workflow",
        "branch": "Opt-in Snowflake Cortex \u2192 validated intent",
        "spine": ["Confirmed spec", "SQLite plans + audit", "frozen report",
                  "HTML / CSV / ZIP / Power Query / PBIP"],
        "source": "Read-only synthetic workbook \u00b7 fingerprint-pinned",
        "footer": "The LLM interprets metadata choices; report values come "
                  "from source rows.",
        "notes": "Power BI imports the exported snapshot. There is no live "
                 "BI-to-Snowflake connection here. Identities are simulated. "
                 "Workbook and evidence inputs remain read-only.",
    },
    {
        "layout": "qa", "appendix": True,
        "kicker": "APPENDIX \u00b7 JUDGE Q&A",
        "title": "Where we draw the line.",
        "qa": [
            ("Does REUSE prove two dashboards are equivalent?",
             "No. It matches confirmed scope, owner and source fingerprint."),
            ("Are KPI definitions certified executable logic?",
             "No. Catalog context is distinct from semantic bindings."),
            ("Can AI approve or calculate the report?",
             "No. Separate simulated approval; deterministic source-row "
             "rendering."),
            ("Does a successful export prove Desktop works?",
             "No. Open, Refresh and inspect all three pages."),
        ],
        "notes": "Use these boundaries directly and confidently. Do not "
                 "imply implemented enterprise authentication, lifecycle "
                 "execution or service publication.",
    },
]

MAIN_COUNT = sum(1 for s in SLIDES if not s["appendix"])
TOTAL = len(SLIDES)

CSS = f"""
:root{{
  --ivory:{IVORY}; --paper:{PAPER}; --navy:{NAVY}; --navy-soft:{NAVY_SOFT};
  --teal:{TEAL}; --teal-soft:{TEAL_SOFT}; --coral:{CORAL};
  --coral-soft:{CORAL_SOFT}; --ink:{INK}; --muted:{MUTED}; --line:{LINE};
}}
*{{box-sizing:border-box}}
html,body{{margin:0;padding:0;height:100%;background:#10182e;color:var(--ink);
  font-family:"Trebuchet MS","Segoe UI",Arial,sans-serif;}}
h1,h2,h3{{font-family:Georgia,"Times New Roman",serif;font-weight:700;
  color:var(--navy);letter-spacing:.2px;}}
#deck{{height:calc(100vh - 48px);width:100vw;overflow:hidden;position:relative;}}
.slide{{position:absolute;width:1280px;height:720px;left:50%;top:50%;
  display:none;overflow:hidden;background:var(--paper);
  transform:translate(-50%,-50%) scale(var(--scale,1));
  transform-origin:center center;
  padding:54px 72px 64px;border-top:6px solid var(--accent,{NAVY});}}
.slide.active{{display:flex;flex-direction:column;animation:fadein .25s ease;}}
@media (prefers-reduced-motion:reduce){{.slide.active{{animation:none}}}}
@keyframes fadein{{from{{opacity:0}}to{{opacity:1}}}}
.slide.dark{{background:linear-gradient(135deg,var(--navy) 0%,#1e3050 60%,var(--teal) 140%);
  color:var(--ivory);border-top-color:var(--coral);}}
.slide.dark h1,.slide.dark h2{{color:var(--ivory);}}
.kicker{{color:var(--accent,{TEAL});text-transform:uppercase;
  letter-spacing:.22em;font-size:15px;font-weight:700;margin:0 0 10px;}}
.slide.dark .kicker{{color:#9fd4cd;}}
h2.title{{font-size:44px;line-height:1.12;margin:0 0 26px;}}
.slide.dark h2.title{{color:var(--ivory);}}
.ft{{position:absolute;left:72px;right:72px;bottom:20px;display:flex;
  justify-content:space-between;align-items:center;
  font-size:15px;color:var(--muted);
  border-top:1px solid var(--line);padding-top:10px;}}
.slide.dark .ft{{color:#9fb0d0;border-top-color:rgba(255,255,255,.18);}}
.ft .pg{{font-variant-numeric:tabular-nums;}}
.badge-apx{{display:inline-block;background:var(--coral);color:#fff;
  font-size:11px;font-weight:700;letter-spacing:.14em;border-radius:4px;
  padding:2px 8px;margin-left:10px;vertical-align:middle;}}
.flowrow{{display:flex;align-items:stretch;gap:14px;margin:8px 0;}}
.fnode{{flex:1;background:#fff;border:1px solid var(--line);border-radius:12px;
  padding:18px 16px;font-size:22px;font-weight:700;color:var(--navy);
  display:flex;align-items:center;justify-content:center;text-align:center;
  box-shadow:0 1px 4px rgba(23,35,63,.06);}}
.fnode.teal{{background:var(--teal);color:#fff;border-color:var(--teal);}}
.fnode.navy{{background:var(--navy);color:var(--ivory);border-color:var(--navy);}}
.farr{{align-self:center;color:var(--coral);font-size:30px;font-weight:700;}}
.pains{{display:flex;gap:14px;margin-top:22px;}}
.pain{{flex:1;background:var(--coral-soft);border-left:5px solid var(--coral);
  border-radius:10px;padding:16px 18px;font-size:21px;color:var(--navy);}}
.takeaway{{margin-top:auto;background:var(--navy);color:var(--ivory);
  border-radius:12px;padding:20px 26px;font-size:24px;
  font-family:Georgia,serif;}}
.pillarrow{{display:flex;gap:18px;margin-top:14px;}}
.pillar{{flex:1;background:#fff;border:1px solid var(--line);
  border-top:5px solid var(--teal);border-radius:12px;padding:26px 22px;
  font-size:26px;font-weight:700;color:var(--navy);line-height:1.25;
  box-shadow:0 1px 4px rgba(23,35,63,.06);}}
.pillar .num{{display:block;font-family:Georgia,serif;font-size:15px;
  color:var(--teal);font-weight:700;letter-spacing:.14em;margin-bottom:12px;}}
.support{{margin-top:auto;background:var(--teal-soft);
  border-left:5px solid var(--teal);border-radius:10px;
  padding:18px 24px;font-size:22px;color:var(--navy);}}
.cols{{display:flex;gap:22px;flex:1;}}
.col{{flex:1;border-radius:14px;padding:26px 30px;}}
.col h3{{margin:0 0 16px;font-size:17px;letter-spacing:.12em;
  text-transform:uppercase;font-family:"Trebuchet MS";}}
.col.ai{{background:var(--teal-soft);border:1px solid #b8d8d3;}}
.col.ai h3{{color:var(--teal);}}
.col.gov{{background:var(--navy);color:var(--ivory);}}
.col.gov h3{{color:#9fd4cd;}}
.col ul{{margin:0;padding-left:22px;font-size:26px;line-height:1.7;}}
.col.gov ul{{color:var(--ivory);}}
.quote{{font-family:Georgia,serif;font-size:34px;line-height:1.3;
  color:var(--navy);border-left:6px solid var(--coral);
  padding:6px 0 6px 26px;margin:4px 0 26px;max-width:1050px;}}
.badge{{display:inline-block;background:var(--teal);color:#fff;border-radius:999px;
  padding:8px 22px;font-size:18px;font-weight:700;margin-top:18px;}}
.bigreuse{{font-family:Georgia,serif;font-size:120px;font-weight:700;
  color:var(--teal);line-height:1;margin:2px 0 8px;letter-spacing:.04em;}}
.resupport{{font-size:24px;color:var(--navy);margin-bottom:20px;}}
.contrast{{display:flex;gap:16px;}}
.contrast div{{flex:1;background:#fff;border:1px solid var(--line);
  border-radius:10px;padding:14px 18px;font-size:21px;color:var(--ink);}}
.contrast b{{color:var(--coral);}}
.pages{{display:flex;gap:18px;margin-top:24px;flex:1;}}
.page{{flex:1;background:#fff;border:1px solid var(--line);border-radius:12px;
  padding:0;overflow:hidden;box-shadow:0 1px 4px rgba(23,35,63,.08);}}
.page .bar{{background:var(--navy-soft);color:#dfe5f2;font-size:14px;
  padding:8px 14px;letter-spacing:.08em;text-transform:uppercase;}}
.page .body{{padding:20px 16px;font-size:24px;font-weight:700;
  color:var(--navy);font-family:Georgia,serif;}}
.doms{{display:flex;gap:16px;flex:1;margin-top:8px;}}
.dom{{flex:1;background:#fff;border:1px solid var(--line);border-radius:12px;
  border-top:5px solid var(--teal);padding:22px 18px;
  box-shadow:0 1px 4px rgba(23,35,63,.06);}}
.dom h3{{margin:0 0 6px;font-size:26px;color:var(--navy);}}
.dom .grain{{display:inline-block;background:var(--teal-soft);color:var(--teal);
  font-size:15px;font-weight:700;border-radius:999px;padding:3px 12px;
  margin-bottom:14px;text-transform:uppercase;letter-spacing:.08em;}}
.dom .fields{{font-size:20px;color:var(--ink);line-height:1.35;}}
.estrow{{display:flex;gap:16px;margin-top:6px;}}
.estcard{{flex:1;background:#fff;border:1px solid var(--line);
  border-left:5px solid var(--teal);border-radius:10px;
  padding:18px 20px;font-size:23px;font-weight:700;color:var(--navy);}}
.estrip{{display:flex;gap:10px;margin-top:20px;flex-wrap:wrap;}}
.estrip span{{background:var(--teal-soft);color:var(--navy);border-radius:999px;
  padding:7px 18px;font-size:18px;font-weight:700;}}
.status{{margin-top:auto;background:var(--coral);color:#fff;border-radius:10px;
  padding:16px 24px;font-size:24px;font-weight:700;font-family:Georgia,serif;
  text-align:center;}}
.tiles{{display:flex;gap:20px;flex:1;}}
.tile{{flex:1;background:#fff;border:1px solid var(--line);border-radius:12px;
  border-top:5px solid var(--teal);padding:24px 26px;
  box-shadow:0 1px 4px rgba(23,35,63,.06);}}
.tile h3{{margin:0 0 12px;font-size:22px;color:var(--teal);
  font-family:"Trebuchet MS";}}
.tile p{{font-size:22px;line-height:1.4;color:var(--ink);margin:0;}}
.distinct{{margin-top:20px;background:var(--coral-soft);
  border-left:5px solid var(--coral);border-radius:10px;
  padding:16px 22px;font-size:21px;color:var(--navy);}}
.rmcols{{display:flex;gap:22px;flex:1;}}
.rmcol{{flex:1;border-radius:14px;padding:24px 30px;}}
.rmcol.now{{background:var(--teal-soft);border:1px solid #b8d8d3;}}
.rmcol.next{{background:#fff;border:2px dashed var(--navy-soft);}}
.rmcol h3{{margin:0 0 14px;font-size:17px;letter-spacing:.12em;
  text-transform:uppercase;font-family:"Trebuchet MS";}}
.rmcol.now h3{{color:var(--teal);}}
.rmcol.next h3{{color:var(--navy-soft);}}
.rmcol ul{{margin:0;padding-left:22px;font-size:24px;line-height:1.75;}}
.anchors{{display:flex;gap:18px;margin-top:34px;}}
.anchor{{flex:1;background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.22);
  border-radius:12px;padding:22px 20px;font-size:24px;font-weight:700;
  color:var(--ivory);text-align:center;}}
.qual{{margin-top:22px;font-size:17px;color:#9fb0d0;font-style:italic;}}
.close{{margin-top:auto;font-family:Georgia,serif;font-size:30px;
  color:#9fd4cd;font-weight:700;}}
.archwrap{{flex:1;display:flex;flex-direction:column;gap:14px;}}
.src{{background:var(--teal-soft);border:1px solid #b8d8d3;border-radius:10px;
  padding:12px 20px;font-size:19px;font-weight:700;color:var(--teal);
  text-align:center;}}
.archmid{{display:flex;gap:14px;align-items:stretch;}}
.archbox{{flex:1;background:#fff;border:1px solid var(--line);
  border-radius:10px;padding:16px;font-size:22px;font-weight:700;
  color:var(--navy);display:flex;align-items:center;justify-content:center;
  text-align:center;}}
.branch{{background:#fff;border:2px dashed var(--teal);border-radius:10px;
  padding:12px 20px;font-size:20px;color:var(--teal);font-weight:700;
  text-align:center;}}
.spine{{background:var(--navy);border-radius:12px;padding:16px 22px;}}
.spine .flowrow{{margin:0;}}
.spine .fnode{{background:rgba(255,255,255,.12);border-color:rgba(255,255,255,.25);
  color:var(--ivory);font-size:19px;padding:14px 12px;}}
.spine .farr{{color:var(--coral);}}
.qa{{display:flex;flex-direction:column;gap:14px;flex:1;
  justify-content:center;}}
.qa .pair{{background:#fff;border:1px solid var(--line);border-radius:10px;
  border-left:5px solid var(--teal);padding:14px 22px;}}
.qa .q{{font-size:21px;font-weight:700;color:var(--navy);margin-bottom:4px;}}
.qa .a{{font-size:20px;color:var(--ink);}}
#controls{{position:fixed;bottom:0;left:0;right:0;display:flex;gap:.4rem;
  align-items:center;justify-content:center;padding:.45rem .6rem;z-index:40;
  background:rgba(23,35,63,.92);backdrop-filter:blur(4px);}}
#controls button{{font-family:inherit;font-size:.85rem;border:none;
  border-radius:8px;padding:.45em .9em;cursor:pointer;
  background:var(--teal);color:#fff;}}
#controls button:hover{{background:#0c5f59;}}
#controls button.sec{{background:transparent;color:#cfd8ea;
  border:1px solid #46557a;}}
#controls button.sec:hover{{background:var(--navy-soft);}}
#counter{{color:#cfd8ea;font-size:.82rem;min-width:6em;text-align:center;}}
#progress{{position:fixed;bottom:0;left:0;height:4px;background:var(--coral);
  z-index:41;transition:width .2s;}}
@page{{size:13.333in 7.5in;margin:0;}}
@media print{{
  *{{-webkit-print-color-adjust:exact;print-color-adjust:exact;}}
  #controls,#progress{{display:none;}}
  html,body{{background:var(--paper);}}
  #deck{{height:auto;overflow:visible;}}
  .slide{{position:static;display:flex;transform:none;left:auto;top:auto;
    width:13.333in;height:7.5in;page-break-after:always;
    padding:.55in .75in .65in;animation:none;}}
}}
"""

JS = """
(function(){
  var slides = Array.prototype.slice.call(document.querySelectorAll('.slide'));
  var n = slides.length, cur = 0;
  var counter = document.getElementById('counter');
  var prog = document.getElementById('progress');
  function fit(){
    var s = Math.min(window.innerWidth/1280, (window.innerHeight-48)/720);
    document.documentElement.style.setProperty('--scale', s);
  }
  window.addEventListener('resize', fit); fit();
  function label(i){
    var apx = slides[i].dataset.apx === '1';
    return apx ? ('Appendix ' + (i+1) + ' / ' + n) : ((i+1) + ' / ' + n);
  }
  function go(i){
    cur = Math.max(0, Math.min(n-1, i));
    slides.forEach(function(s,j){s.classList.toggle('active', j===cur);});
    counter.textContent = label(cur);
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
  document.getElementById('nextBtn').addEventListener('click',function(){go(cur+1);});
  document.getElementById('prevBtn').addEventListener('click',function(){go(cur-1);});
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
  document.addEventListener('keydown',function(e){
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


def esc(t):
    return html.escape(t).replace("\n", "<br>")


def flow_html(nodes, cls=""):
    out = []
    for i, node in enumerate(nodes):
        if i:
            out.append('<span class="farr">&#8594;</span>')
        out.append(f'<div class="fnode {cls}">{esc(node)}</div>')
    return '<div class="flowrow">' + "".join(out) + DIV_END


def slide_body(s):
    L = s["layout"]
    if L == "title":
        t = esc(s["title"])
        return (
            '<div style="flex:1;display:flex;flex-direction:column;'
            'justify-content:center;">'
            f'<p class="kicker">{esc(s["kicker"])}</p>'
            f'<h2 class="title" style="font-size:64px;margin:0 0 18px;">{t}</h2>'
            f'<p style="font-size:22px;color:#9fd4cd;font-weight:700;'
            f'letter-spacing:.18em;text-transform:uppercase;margin:0 0 14px;">'
            f'{esc(s["product"])}</p>'
            f'<p style="font-size:26px;color:#dfe5f2;max-width:22em;margin:0;'
            f'line-height:1.35;">{esc(s["subtitle"])}</p>'
            + DIV_END)
    if L == "problem":
        return (flow_html(s["stages"])
                + '<div class="pains">'
                + "".join(f'<div class="pain">{esc(p)}</div>'
                          for p in s["pains"])
                + DIV_END
                + f'<div class="takeaway">{esc(s["takeaway"])}</div>')
    if L == "pillars":
        return ('<div class="pillarrow">'
                + "".join(
                    f'<div class="pillar"><span class="num">0{i+1}</span>'
                    f'{esc(p)}</div>' for i, p in enumerate(s["pillars"]))
                + DIV_END
                + f'<div class="support">{esc(s["supporting"])}</div>')
    if L == "twocol":
        def items(xs):
            return "<ul>" + "".join(f"<li>{esc(x)}</li>" for x in xs) + "</ul>"
        return ('<div class="cols">'
                f'<div class="col ai"><h3>{esc(s["left_head"])}</h3>'
                f'{items(s["left_items"])}</div>'
                f'<div class="col gov"><h3>{esc(s["right_head"])}</h3>'
                f'{items(s["right_items"])}</div>'
                + DIV_END)
    if L == "demo":
        return (f'<p class="quote">\u201c{esc(s["quote"])}\u201d</p>'
                + flow_html(s["journey"], "navy")
                + f'<div><span class="badge">{esc(s["badge"])}</span></div>')
    if L == "reveal":
        return (f'<div class="bigreuse">{esc(s["emphasis"])}</div>'
                f'<div class="resupport">{esc(s["supporting"])}</div>'
                '<div class="contrast">'
                + "".join(f'<div>{esc(a)} <b>\u2192 {esc(b)}</b></div>'
                          for a, b in s["contrast"])
                + DIV_END)
    if L == "pbi":
        return (flow_html(s["workflow"], "teal")
                + '<div class="pages">'
                + "".join(
                    f'<div class="page"><div class="bar">Report page '
                    f'{i+1}</div><div class="body">{esc(p)}</div></div>'
                    for i, p in enumerate(s["pages"]))
                + DIV_END)
    if L == "domains":
        return ('<div class="doms">'
                + "".join(
                    f'<div class="dom"><h3>{esc(d)}</h3>'
                    f'<span class="grain">{esc(g)}</span>'
                    f'<div class="fields">{esc(f)}</div></div>'
                    for d, g, f in s["domains"])
                + DIV_END)
    if L == "estate":
        return ('<div class="estrow">'
                + "".join(f'<div class="estcard">{esc(d)}</div>'
                          for d in s["decisions"])
                + DIV_END
                + '<div class="estrip">'
                + "".join(f"<span>{esc(e)}</span>" for e in s["evidence"])
                + DIV_END
                + f'<div class="status">{esc(s["status"])}</div>')
    if L == "evidence":
        return ('<div class="tiles">'
                + "".join(f'<div class="tile"><h3>{esc(h)}</h3>'
                          f"<p>{esc(b)}</p></div>" for h, b in s["tiles"])
                + DIV_END
                + f'<div class="distinct">{esc(s["distinction"])}</div>')
    if L == "roadmap":
        def items(xs):
            return "<ul>" + "".join(f"<li>{esc(x)}</li>" for x in xs) + "</ul>"
        return ('<div class="rmcols">'
                f'<div class="rmcol now"><h3>{esc(s["current_head"])}</h3>'
                f'{items(s["current"])}</div>'
                f'<div class="rmcol next"><h3>{esc(s["next_head"])}</h3>'
                f'{items(s["next"])}</div>'
                + DIV_END)
    if L == "closing":
        t = esc(s["title"])
        return (
            f'<h2 class="title" style="font-size:52px;margin:0;">{t}</h2>'
            '<div class="anchors">'
            + "".join(f'<div class="anchor">{esc(a)}</div>'
                      for a in s["anchors"])
            + DIV_END
            + f'<p class="qual">{esc(s["qualifier"])}</p>'
            f'<p class="close">{esc(s["close"])}</p>')
    if L == "arch":
        return ('<div class="archwrap">'
                f'<div class="src">{esc(s["source"])}</div>'
                '<div class="archmid">'
                f'<div class="archbox">{esc(s["ui"])}</div>'
                '<span class="farr">&#8594;</span>'
                f'<div class="archbox">{esc(s["api"])}</div>'
                + DIV_END
                + f'<div class="branch">{esc(s["branch"])}</div>'
                '<div class="spine">' + flow_html(s["spine"]) + DIV_END
                + DIV_END)
    if L == "qa":
        return ('<div class="qa">'
                + "".join(f'<div class="pair"><div class="q">{esc(q)}</div>'
                          f'<div class="a">{esc(a)}</div></div>'
                          for q, a in s["qa"])
                + DIV_END)
    raise ValueError(L)


def slide_html(s, idx):
    dark = s["layout"] in ("title", "closing")
    head = ""
    if s["layout"] not in ("title", "closing"):
        apx = ' <span class="badge-apx">APPENDIX</span>' if s["appendix"] else ""
        head = (f'<p class="kicker">{esc(s["kicker"])}{apx}</p>'
                f'<h2 class="title">{esc(s["title"])}</h2>')
    footer = ""
    if s.get("footer"):
        footer = (f'<div class="ft"><span>{esc(s["footer"])}</span>'
                  f'<span class="pg">{idx + 1} / {TOTAL}</span></div>')
    return (f'<section class="slide{" dark" if dark else ""}" '
            f'data-apx="{1 if s["appendix"] else 0}" '
            f'data-title="{esc(s["title"].replace(chr(10), " "))}">'
            f"{head}{slide_body(s)}{footer}</section>")


def render_html():
    slides = "\n".join(slide_html(s, i) for i, s in enumerate(SLIDES))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Smart Librarian \u2014 Judge Presentation</title>
<style>{CSS}</style>
</head>
<body>
<div id="deck">
{slides}
</div>
<div id="controls" role="toolbar" aria-label="Slide controls">
  <button id="prevBtn">&#8592; Prev</button>
  <span id="counter">1 / {TOTAL}</span>
  <button id="nextBtn">Next &#8594;</button>
  <button class="sec" id="fsBtn" title="Fullscreen">&#9974; Full</button>
  <button class="sec" id="printBtn">Print</button>
</div>
<div id="progress"></div>
<script>{JS}</script>
</body>
</html>
"""


def rgb_color(h):
    if isinstance(h, RGBColor):
        return h
    return RGBColor.from_string(h.lstrip("#"))


def box(slide, x, y, w, h, fill=None, line=None, dashed=False,
        shape=MSO_SHAPE.ROUNDED_RECTANGLE, line_w=0.75):
    sp = slide.shapes.add_shape(shape, x, y, w, h)
    if fill is None:
        sp.fill.background()
    else:
        sp.fill.solid()
        sp.fill.fore_color.rgb = rgb_color(fill)
    if line is None:
        sp.line.fill.background()
    else:
        sp.line.color.rgb = rgb_color(line)
        sp.line.width = Pt(line_w)
        if dashed:
            sp.line.dash_style = 4
    sp.shadow.inherit = False
    return sp


def txt(slide, x, y, w, h, text, size, color, bold=False, font=FONT_BODY,
        italic=False, align=None):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    lines = text.split("\n")
    for i, ln in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        if align:
            p.alignment = align
        r = p.add_run()
        r.text = ln
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.italic = italic
        r.font.name = font
        r.font.color.rgb = rgb_color(color)
    return tb


def shape_text(sp, lines, size, color, bold=False, heading=None,
               head_color=None, head_size=13):
    tf = sp.text_frame
    tf.word_wrap = True
    tf.margin_left = Inches(0.16)
    tf.margin_right = Inches(0.14)
    tf.margin_top = Inches(0.1)
    tf.margin_bottom = Inches(0.08)
    first = True
    if heading is not None:
        p = tf.paragraphs[0]
        first = False
        r = p.add_run()
        r.text = heading
        r.font.size = Pt(head_size)
        r.font.bold = True
        r.font.name = FONT_BODY
        r.font.color.rgb = rgb_color(head_color)
        p.space_after = Pt(8)
    for ln in lines:
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        r = p.add_run()
        r.text = ln
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.name = FONT_BODY
        r.font.color.rgb = rgb_color(color)
        p.space_after = Pt(4)


def chrome(slide, s, idx):
    box(slide, 0, 0, Inches(13.333), Pt(6), fill=NAVY,
              shape=MSO_SHAPE.RECTANGLE)
    txt(slide, Inches(0.75), Inches(0.28), Inches(11.5), Inches(0.35),
        s["kicker"] + ("   \u00b7 APPENDIX" if s["appendix"] else ""),
        12, CORAL if s["appendix"] else TEAL, bold=True)
    txt(slide, Inches(0.75), Inches(0.62), Inches(12.1), Inches(1.2),
        s["title"], 34, NAVY, bold=True, font=FONT_DISPLAY)
    if s.get("footer"):
        box(slide, Inches(0.75), Inches(7.02), Inches(11.85), Pt(1),
                 fill=LINE, shape=MSO_SHAPE.RECTANGLE)
        txt(slide, Inches(0.75), Inches(7.06), Inches(10.6), Inches(0.34),
            s["footer"], 11, MUTED)
    txt(slide, Inches(11.9), Inches(7.06), Inches(0.8), Inches(0.34),
        f"{idx + 1} / {TOTAL}", 11, MUTED)


def notes(slide, s):
    slide.notes_slide.notes_text_frame.text = s["notes"]


def p_title(prs, s, idx):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    box(slide, 0, 0, prs.slide_width, prs.slide_height, fill=NAVY,
        shape=MSO_SHAPE.RECTANGLE)
    box(slide, 0, 0, prs.slide_width, Pt(6), fill=CORAL,
        shape=MSO_SHAPE.RECTANGLE)
    txt(slide, Inches(0.9), Inches(1.35), Inches(11.5), Inches(0.4),
        s["kicker"], 14, rgb_color("9fd4cd"), bold=True)
    txt(slide, Inches(0.9), Inches(1.8), Inches(11.6), Inches(1.9),
        s["title"], 54, IVORY, bold=True, font=FONT_DISPLAY)
    txt(slide, Inches(0.9), Inches(3.95), Inches(11.5), Inches(0.4),
        s["product"].upper(), 16, rgb_color("9fd4cd"), bold=True)
    txt(slide, Inches(0.9), Inches(4.45), Inches(11.0), Inches(1.0),
        s["subtitle"], 22, rgb_color("dfe5f2"))
    txt(slide, Inches(0.9), Inches(6.85), Inches(11.6), Inches(0.35),
        s["footer"], 11, rgb_color("9fb0d0"))
    notes(slide, s)
    return slide


def p_problem(prs, s, idx):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    chrome(slide, s, idx)
    x = Inches(0.75)
    w = Inches(3.7)
    for i, st in enumerate(s["stages"]):
        card = box(slide, x, Inches(1.9), w, Inches(1.15), fill="ffffff",
                   line=LINE)
        shape_text(card, [st], 20, NAVY, bold=True)
        if i < 2:
            txt(slide, x + w, Inches(2.25), Inches(0.5), Inches(0.5), "\u2192",
                24, CORAL, bold=True)
        x = x + w + Inches(0.5)
    x = Inches(0.75)
    for p in s["pains"]:
        card = box(slide, x, Inches(3.35), w, Inches(0.9), fill=CORAL_SOFT)
        box(slide, x, Inches(3.35), Pt(4), Inches(0.9), fill=CORAL,
                   shape=MSO_SHAPE.RECTANGLE)
        shape_text(card, [p], 20, NAVY)
        x = x + w + Inches(0.5)
    strip = box(slide, Inches(0.75), Inches(4.7), Inches(11.85), Inches(1.1),
                fill=NAVY)
    shape_text(strip, [s["takeaway"]], 24, IVORY)
    notes(slide, s)
    return slide


def p_pillars(prs, s, idx):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    chrome(slide, s, idx)
    x = Inches(0.75)
    w = Inches(3.85)
    for i, pl in enumerate(s["pillars"]):
        card = box(slide, x, Inches(1.95), w, Inches(2.3), fill="ffffff",
                   line=LINE)
        box(slide, x, Inches(1.95), w, Pt(5), fill=TEAL,
            shape=MSO_SHAPE.RECTANGLE)
        shape_text(card, [f"0{i+1}", pl], 24, NAVY, bold=True,
                   heading=None)
        card.text_frame.paragraphs[0].runs[0].font.size = Pt(14)
        card.text_frame.paragraphs[0].runs[0].font.color.rgb = rgb_color(TEAL)
        x = x + w + Inches(0.25)
    strip = box(slide, Inches(0.75), Inches(4.7), Inches(11.85), Inches(1.1),
                fill=TEAL_SOFT)
    box(slide, Inches(0.75), Inches(4.7), Pt(4), Inches(1.1),
               fill=TEAL, shape=MSO_SHAPE.RECTANGLE)
    shape_text(strip, [s["supporting"]], 22, NAVY)
    notes(slide, s)
    return slide


def p_twocol(prs, s, idx):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    chrome(slide, s, idx)
    left = box(slide, Inches(0.75), Inches(1.9), Inches(5.8), Inches(4.7),
               fill=TEAL_SOFT, line="b8d8d3")
    right = box(slide, Inches(6.8), Inches(1.9), Inches(5.8), Inches(4.7),
                fill=NAVY)
    shape_text(left, ["\u2022 " + i for i in s["left_items"]], 24, NAVY,
               heading=s["left_head"].upper(), head_color=TEAL)
    shape_text(right, ["\u2022 " + i for i in s["right_items"]], 24, IVORY,
               heading=s["right_head"].upper(), head_color="9fd4cd")
    notes(slide, s)
    return slide


def p_demo(prs, s, idx):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    chrome(slide, s, idx)
    box(slide, Inches(0.75), Inches(1.9), Pt(6), Inches(1.3),
               fill=CORAL, shape=MSO_SHAPE.RECTANGLE)
    txt(slide, Inches(1.05), Inches(1.95), Inches(11.4), Inches(1.2),
        "\u201c" + s["quote"] + "\u201d", 26, NAVY, italic=True,
        font=FONT_DISPLAY)
    x = Inches(0.75)
    w = Inches(1.8)
    for i, step in enumerate(s["journey"]):
        card = box(slide, x, Inches(3.6), w, Inches(1.15), fill=NAVY)
        shape_text(card, [step], 20, IVORY, bold=True)
        if i < len(s["journey"]) - 1:
            txt(slide, x + w - Inches(0.06), Inches(3.95), Inches(0.4),
                Inches(0.5), "\u2192", 20, CORAL, bold=True)
        x = x + w + Inches(0.22)
    badge = box(slide, Inches(0.75), Inches(5.15), Inches(7.2), Inches(0.8),
                fill=TEAL)
    shape_text(badge, [s["badge"]], 20, "ffffff", bold=True)
    notes(slide, s)
    return slide


def p_reveal(prs, s, idx):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    chrome(slide, s, idx)
    txt(slide, Inches(0.75), Inches(1.75), Inches(8), Inches(1.6),
        s["emphasis"], 88, TEAL, bold=True, font=FONT_DISPLAY)
    txt(slide, Inches(0.75), Inches(3.5), Inches(11.9), Inches(0.9),
        s["supporting"], 24, NAVY)
    x = Inches(0.75)
    for a, b in s["contrast"]:
        card = box(slide, x, Inches(4.6), Inches(5.8), Inches(1.15),
                   fill="ffffff", line=LINE)
        shape_text(card, [f"{a}  \u2192  {b}"], 20, INK)
        x = x + Inches(6.05)
    notes(slide, s)
    return slide


def p_pbi(prs, s, idx):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    chrome(slide, s, idx)
    x = Inches(0.75)
    w = Inches(2.7)
    for i, step in enumerate(s["workflow"]):
        card = box(slide, x, Inches(1.9), w, Inches(1.0), fill=TEAL)
        shape_text(card, [step], 20, "ffffff", bold=True)
        if i < len(s["workflow"]) - 1:
            txt(slide, x + w, Inches(2.15), Inches(0.45), Inches(0.5),
                "\u2192", 22, CORAL, bold=True)
        x = x + w + Inches(0.45)
    x = Inches(0.75)
    w = Inches(3.85)
    for i, pg in enumerate(s["pages"]):
        card = box(slide, x, Inches(3.3), w, Inches(2.2), fill="ffffff",
                   line=LINE)
        bar = box(slide, x, Inches(3.3), w, Inches(0.45), fill=NAVY_SOFT,
                  shape=MSO_SHAPE.RECTANGLE)
        shape_text(bar, [f"REPORT PAGE {i+1}"], 12, "dfe5f2", bold=True)
        tf = card.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.space_before = Pt(60)
        r = p.add_run()
        r.text = pg
        r.font.size = Pt(24)
        r.font.bold = True
        r.font.name = FONT_DISPLAY
        r.font.color.rgb = rgb_color(NAVY)
        x = x + w + Inches(0.15)
    notes(slide, s)
    return slide


def p_domains(prs, s, idx):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    chrome(slide, s, idx)
    x = Inches(0.75)
    w = Inches(2.85)
    for name, grain, fields in s["domains"]:
        card = box(slide, x, Inches(1.95), w, Inches(3.9), fill="ffffff",
                   line=LINE)
        box(slide, x, Inches(1.95), w, Pt(5), fill=TEAL,
            shape=MSO_SHAPE.RECTANGLE)
        tf = card.text_frame
        tf.word_wrap = True
        tf.margin_top = Inches(0.22)
        p = tf.paragraphs[0]
        r = p.add_run(); r.text = name
        r.font.size = Pt(24); r.font.bold = True
        r.font.name = FONT_DISPLAY; r.font.color.rgb = rgb_color(NAVY)
        p2 = tf.add_paragraph(); p2.space_before = Pt(6)
        r = p2.add_run(); r.text = grain.upper()
        r.font.size = Pt(13); r.font.bold = True
        r.font.name = FONT_BODY; r.font.color.rgb = rgb_color(TEAL)
        p3 = tf.add_paragraph(); p3.space_before = Pt(14)
        r = p3.add_run(); r.text = fields
        r.font.size = Pt(20); r.font.name = FONT_BODY
        r.font.color.rgb = rgb_color(INK)
        x = x + w + Inches(0.15)
    notes(slide, s)
    return slide


def p_estate(prs, s, idx):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    chrome(slide, s, idx)
    x = Inches(0.75)
    w = Inches(3.85)
    for d in s["decisions"]:
        card = box(slide, x, Inches(1.9), w, Inches(1.2), fill="ffffff",
                   line=LINE)
        box(slide, x, Inches(1.9), Pt(4), Inches(1.2), fill=TEAL,
            shape=MSO_SHAPE.RECTANGLE)
        shape_text(card, [d], 20, NAVY, bold=True)
        x = x + w + Inches(0.15)
    x = Inches(0.75)
    for e in s["evidence"]:
        chip = box(slide, x, Inches(3.4), Inches(2.28), Inches(0.8),
                   fill=TEAL_SOFT)
        shape_text(chip, [e], 20, NAVY, bold=True)
        x = x + Inches(2.44)
    strip = box(slide, Inches(0.75), Inches(4.5), Inches(11.85), Inches(1.0),
                fill=CORAL)
    shape_text(strip, [s["status"]], 26, "ffffff", bold=True)
    strip.text_frame.paragraphs[0].runs[0].font.name = FONT_DISPLAY
    notes(slide, s)
    return slide


def p_evidence(prs, s, idx):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    chrome(slide, s, idx)
    x = Inches(0.75)
    for head, body in s["tiles"]:
        card = box(slide, x, Inches(1.9), Inches(5.8), Inches(2.6),
                   fill="ffffff", line=LINE)
        box(slide, x, Inches(1.9), Inches(5.8), Pt(5), fill=TEAL,
            shape=MSO_SHAPE.RECTANGLE)
        shape_text(card, [body], 21, INK, heading=head, head_color=TEAL,
                   head_size=18)
        x = x + Inches(6.05)
    strip = box(slide, Inches(0.75), Inches(4.85), Inches(11.85), Inches(1.3),
                fill=CORAL_SOFT)
    box(slide, Inches(0.75), Inches(4.85), Pt(4), Inches(1.3), fill=CORAL,
        shape=MSO_SHAPE.RECTANGLE)
    shape_text(strip, [s["distinction"]], 20, NAVY)
    notes(slide, s)
    return slide


def p_roadmap(prs, s, idx):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    chrome(slide, s, idx)
    left = box(slide, Inches(0.75), Inches(1.9), Inches(5.8), Inches(4.7),
               fill=TEAL_SOFT, line="b8d8d3")
    right = box(slide, Inches(6.8), Inches(1.9), Inches(5.8), Inches(4.7),
                fill="ffffff", line=NAVY_SOFT, dashed=True, line_w=1.5)
    shape_text(left, ["\u2022 " + i for i in s["current"]], 22, NAVY,
               heading=s["current_head"].upper(), head_color=TEAL)
    shape_text(right, ["\u2022 " + i for i in s["next"]], 22, INK,
               heading=s["next_head"].upper(), head_color=NAVY_SOFT)
    notes(slide, s)
    return slide


def p_closing(prs, s, idx):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    box(slide, 0, 0, prs.slide_width, prs.slide_height, fill=NAVY,
        shape=MSO_SHAPE.RECTANGLE)
    box(slide, 0, 0, prs.slide_width, Pt(6), fill=CORAL,
        shape=MSO_SHAPE.RECTANGLE)
    txt(slide, Inches(0.9), Inches(0.9), Inches(11.5), Inches(0.4),
        s["kicker"], 14, rgb_color("9fd4cd"), bold=True)
    txt(slide, Inches(0.9), Inches(1.45), Inches(11.6), Inches(1.9),
        s["title"], 44, IVORY, bold=True, font=FONT_DISPLAY)
    x = Inches(0.9)
    for a in s["anchors"]:
        card = box(slide, x, Inches(3.7), Inches(3.75), Inches(1.0),
                   fill=NAVY_SOFT, line="46557a")
        shape_text(card, [a], 20, IVORY, bold=True)
        x = x + Inches(3.95)
    txt(slide, Inches(0.9), Inches(4.95), Inches(11.5), Inches(0.4),
        s["qualifier"], 13, rgb_color("9fb0d0"), italic=True)
    txt(slide, Inches(0.9), Inches(5.9), Inches(11.6), Inches(0.7),
        s["close"], 28, rgb_color("9fd4cd"), bold=True, font=FONT_DISPLAY)
    notes(slide, s)
    return slide


def p_arch(prs, s, idx):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    chrome(slide, s, idx)
    src = box(slide, Inches(0.75), Inches(1.85), Inches(11.85), Inches(0.6),
              fill=TEAL_SOFT, line="b8d8d3")
    shape_text(src, [s["source"]], 20, TEAL, bold=True)
    ui = box(slide, Inches(0.75), Inches(2.7), Inches(5.6), Inches(0.85),
             fill="ffffff", line=LINE)
    shape_text(ui, [s["ui"]], 22, NAVY, bold=True)
    txt(slide, Inches(6.45), Inches(2.85), Inches(0.5), Inches(0.5),
        "\u2192", 24, CORAL, bold=True)
    api = box(slide, Inches(7.0), Inches(2.7), Inches(5.6), Inches(0.85),
              fill="ffffff", line=LINE)
    shape_text(api, [s["api"]], 22, NAVY, bold=True)
    br = box(slide, Inches(7.0), Inches(3.75), Inches(5.6), Inches(0.6),
             fill="ffffff", line=TEAL, dashed=True, line_w=1.5)
    shape_text(br, [s["branch"]], 20, TEAL, bold=True)
    box(slide, Inches(0.75), Inches(4.6), Inches(11.85), Inches(1.75),
                fill=NAVY)
    x = Inches(1.0)
    w = Inches(2.6)
    for i, st in enumerate(s["spine"]):
        node = box(slide, x, Inches(4.8), w, Inches(1.2), fill=NAVY_SOFT,
                   line="46557a")
        shape_text(node, [st], 20, IVORY, bold=True)
        if i < 3:
            txt(slide, x + w - Inches(0.04), Inches(5.15), Inches(0.35),
                Inches(0.5), "\u2192", 20, CORAL, bold=True)
        x = x + w + Inches(0.2)
    notes(slide, s)
    return slide


def p_qa(prs, s, idx):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    chrome(slide, s, idx)
    y = Inches(1.85)
    for q, a in s["qa"]:
        card = box(slide, Inches(0.75), y, Inches(11.85), Inches(1.12),
                   fill="ffffff", line=LINE)
        box(slide, Inches(0.75), y, Pt(4), Inches(1.12), fill=TEAL,
            shape=MSO_SHAPE.RECTANGLE)
        tf = card.text_frame
        tf.word_wrap = True
        tf.margin_left = Inches(0.18)
        tf.margin_top = Inches(0.07)
        p = tf.paragraphs[0]
        r = p.add_run(); r.text = q
        r.font.size = Pt(20); r.font.bold = True
        r.font.name = FONT_BODY; r.font.color.rgb = rgb_color(NAVY)
        p2 = tf.add_paragraph(); p2.space_before = Pt(2)
        r = p2.add_run(); r.text = a
        r.font.size = Pt(20); r.font.name = FONT_BODY
        r.font.color.rgb = rgb_color(INK)
        y = y + Inches(1.28)
    notes(slide, s)
    return slide


BUILDERS = {
    "title": p_title, "problem": p_problem, "pillars": p_pillars,
    "twocol": p_twocol, "demo": p_demo, "reveal": p_reveal, "pbi": p_pbi,
    "domains": p_domains, "estate": p_estate, "evidence": p_evidence,
    "roadmap": p_roadmap, "closing": p_closing, "arch": p_arch, "qa": p_qa,
}


def render_pptx():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    for i, s in enumerate(SLIDES):
        BUILDERS[s["layout"]](prs, s, i)
    prs.save(PPTX_OUT)


def main():
    HTML_OUT.write_text(render_html(), encoding="utf-8")
    render_pptx()
    print(f"{HTML_OUT.name}: {TOTAL} slides ({MAIN_COUNT} main + "
          f"{TOTAL - MAIN_COUNT} appendix)")
    print(f"{PPTX_OUT.name}: {TOTAL} slides")


if __name__ == "__main__":
    main()
