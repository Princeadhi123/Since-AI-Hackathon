SCHEMA_ROOT = "https://developer.microsoft.com/json-schemas/fabric/"
TITLES = {
    "commercial": "Commercial / Finance",
    "market_access": "Market Access",
    "supply": "Supply / Logistics",
    "launch": "Launch Planning",
}
ROW_SCOPE = "__ReportScope"
ROW_LABEL = "__ReportRow"
EVENT_MARKER = "__EventMarker"


def _literal(value):
    text = str(value).replace("'", "''")
    return {"expr": {"Literal": {"Value": f"'{text}'"}}}


def _field(name, measure=False):
    return {
        "Measure" if measure else "Column": {
            "Expression": {"SourceRef": {"Entity": "FrozenReport"}},
            "Property": name,
        }
    }


def _projection(name, measure=False, label=None):
    return {
        "field": _field(name, measure),
        "queryRef": "FrozenReport." + name,
        "nativeQueryRef": name,
        "displayName": label or name,
    }


def metric_measure_name(metric):
    return "__RowValue_" + metric


def model_presentation(report, names, types):
    if ROW_SCOPE in names or ROW_LABEL in names or EVENT_MARKER in names:
        raise ValueError("Frozen columns collide with dashboard presentation columns")
    if not {"product_name", "market_name"}.issubset(names):
        raise ValueError("Dashboard requires product and market labels")
    scope = "'FrozenReport'[product_name] & \" / \" & 'FrozenReport'[market_name]"
    time = next((n for n in ("month", "milestone_date") if n in names), None)
    label = f"'FrozenReport'[{ROW_SCOPE}]"
    if time:
        label += f' & " / " & LEFT(\'FrozenReport\'[{time}], 10)'
    label += ' & " / source #" & FORMAT(\'FrozenReport\'[_source_row], "0")'
    columns = [
        {"name": ROW_SCOPE, "dataType": "string", "type": "calculated",
         "expression": scope, "summarizeBy": "none"},
        {"name": ROW_LABEL, "dataType": "string", "type": "calculated",
         "expression": label, "summarizeBy": "none"},
    ]
    measures = []
    selected = set(report["spec"]["intent"]["metric_ids"])
    fields = [
        f for f in report["spec"].get("fields", [])
        if f["metric_id"] in selected
        and f["metric_id"] in types
        and types[f["metric_id"]][0] in ("int64", "double")
        and f["unit"] not in ("category", "identifier")
    ]
    for field in fields:
        metric = field["metric_id"]
        escaped = metric.replace("]", "]]")
        measures.append({
            "name": metric_measure_name(metric),
            "expression": (
                "IF(COUNTROWS('FrozenReport') = 1, "
                f"SELECTEDVALUE('FrozenReport'[{escaped}]), BLANK())"
            ),
            "formatString": '0.0" %"' if field["unit"] == "%" else "#,0.00",
            "description": (
                f"Native source value in {field['unit']}. Blank unless exactly "
                "one frozen source row is in context; never a sum or average."
            ),
        })
    if report["spec"]["domain_id"] == "launch":
        measures.append({
            "name": EVENT_MARKER,
            "expression": "IF(COUNTROWS('FrozenReport') = 1, 1, BLANK())",
            "description": "Visual event marker only, not a KPI, count or progress measure.",
            "formatString": "0",
        })
    return columns, measures, fields


def _visual(name, kind, query, x, y, width, height, title):
    return {
        "$schema": SCHEMA_ROOT + "item/report/definition/visualContainer/2.1.0/schema.json",
        "name": name,
        "position": {"x": x, "y": y, "z": 0, "width": width,
                     "height": height, "tabOrder": 0},
        "visual": {
            "visualType": kind,
            "query": {"queryState": query},
            "visualContainerObjects": {
                "title": [{"properties": {
                    "show": {"expr": {"Literal": {"Value": "true"}}},
                    "text": _literal(title),
                }}],
            },
        },
    }


def _textbox(name, text, y, height, size=14):
    result = _visual(name, "textbox", {}, 32, y, 1376, height, "")
    result["visual"].pop("query")
    result["visual"]["visualContainerObjects"] = {}
    result["visual"]["objects"] = {
        "general": [{"properties": {"paragraphs": [{
            "textRuns": [{"value": text, "textStyle": {
                "fontSize": f"{size}pt", "fontFamily": "Segoe UI",
                "color": "#143B4A",
            }}],
        }]}}],
    }
    return result


def _table(name, names, display, y, height):
    result = _visual(name, "tableEx", {
        "Values": {"projections": [
            _projection(n, label=display.get(n, n)) for n in names
        ]},
    }, 32, y, 1376, height, "Frozen evidence | native units | no totals")
    result["visual"]["objects"] = {
        "total": [{"properties": {
            "totals": {"expr": {"Literal": {"Value": "false"}}},
        }}],
    }
    return result


def build_dashboard_files(report, names, fields):
    spec = report["spec"]
    domain = spec["domain_id"]
    title = TITLES.get(domain, domain)
    display = {f["metric_id"]: f"{f['name']} ({f['unit']})"
               for f in spec.get("fields", [])}
    panels = [(field["unit"], [field]) for field in fields]
    if domain == "launch":
        panels = [("Event markers, not a KPI", [])]
    pages = {}
    order = []

    def add_page(key, label):
        order.append(key)
        prefix = f"GovernedReport.Report/definition/pages/{key}/"
        pages[prefix + "page.json"] = {
            "$schema": SCHEMA_ROOT + "item/report/definition/page/2.0.0/schema.json",
            "name": key, "displayName": label, "displayOption": "FitToPage",
            "width": 1440, "height": 960,
        }
        header = (
            f"{title.upper()}  /  SYNTHETIC BUILDER PACK\n"
            f"Owner: {spec['owner_id']}  |  Source: {spec['source_sheet']}  |  "
            f"Grain: {spec['intent']['grain']}  |  Native values; no aggregation"
        )
        pages[prefix + "visuals/Header/visual.json"] = _textbox(
            key + "Header", header, 20, 110, 20)
        return prefix

    for start in range(0, max(len(panels), 1), 2):
        key = "Overview" if start == 0 else f"Metrics{start // 2 + 1}"
        prefix = add_page(key, "Dashboard" if start == 0 else f"Metrics {start // 2 + 1}")
        chosen = panels[start:start + 2]
        if not chosen:
            pages[prefix + "visuals/NoNumeric/visual.json"] = _textbox(
                key + "NoNumeric",
                "No numeric fields selected. The approved categorical source "
                "values are shown below; no KPI has been invented.", 180, 130, 20)
        for index, (unit, metrics) in enumerate(chosen):
            event = domain == "launch"
            monthly = spec["intent"]["grain"] == "month"
            category = "milestone_date" if event else "month" if monthly else ROW_LABEL
            query = {
                "Category": {"projections": [_projection(category)]},
                "Y": {"projections": (
                    [_projection(EVENT_MARKER, True, "Milestone event")]
                    if event else [
                        _projection(metric_measure_name(f["metric_id"]), True, f["name"])
                        for f in metrics
                    ]
                )},
            }
            if event or monthly:
                query["Series"] = {"projections": [
                    _projection(ROW_LABEL if event else ROW_SCOPE)
                ]}
            width = 1376 if len(chosen) == 1 else 672
            chart = _visual(
                key + f"Metric{index}", "lineChart" if event or monthly else "clusteredBarChart",
                query, 32 + index * 704, 156, width, 440,
                "Milestone event timeline | markers, not counts"
                if event else f"{metrics[0]['name']} | {unit}",
            )
            chart["visual"]["query"]["sortDefinition"] = {
                "sort": [{"field": _field(category), "direction": "Ascending"}],
            }
            chart["visual"]["objects"] = {
                "valueAxis": [{"properties": {
                    "showAxisTitle": {"expr": {"Literal": {"Value": "true"}}},
                    "axisTitle": _literal(unit),
                }}],
                "lineStyles": [{"properties": {
                    "showMarker": {"expr": {"Literal": {"Value": "true"}}},
                }}],
            }
            pages[prefix + f"visuals/Metric{index}/visual.json"] = chart
        pages[prefix + "visuals/SourceRows/visual.json"] = _table(
            "SourceRows" if start == 0 else key + "SourceRows", names, display, 632, 230)
        pages[prefix + "visuals/Footer/visual.json"] = _textbox(
            key + "Footer",
            "Synthetic, not actual Bayer performance. Charts show only the "
            "approved frozen scope. Multiple source rows in a chart point "
            "produce BLANK, never an implicit total. Full evidence and "
            "governance are on separate tabs.", 880, 65, 12)
    evidence = add_page("Evidence", "Source Evidence")
    pages[evidence + "visuals/EvidenceRows/visual.json"] = _table(
        "EvidenceRows", names, display, 160, 720)
    governance = add_page("Governance", "Ownership & Evidence")
    months = ", ".join(spec["intent"].get("months", [])) or "Undated snapshot"
    text = (
        f"ACCOUNTABILITY\nOwner: {spec['owner_id']}\n"
        f"Requester: {report.get('requester', 'Recorded in local plan audit')}\n"
        f"Plan: {report.get('plan_id', 'See exported approved plan')}\n\n"
        f"CONFIRMED SCOPE\nProducts: {', '.join(spec['intent']['product_ids'])}\n"
        f"Markets: {', '.join(spec['intent']['market_ids'])}\nPeriods: {months}\n\n"
        f"PROVENANCE\nSource: {spec['source_file']}\n"
        f"Workbook SHA256: {spec['source_sha256']}\n"
        f"Specification SHA256: {report['spec_hash']}\n\n"
        "CONTROLS & HANDOFF\nIdentities and approvals are local simulations. "
        "KPI references are context, not certified executable bindings.\n"
        "Desktop Refresh loads the embedded frozen rows; it does not fetch "
        "new business data. No service publishing or live refresh connection.\n"
        "After extraction, open GovernedReport.pbip and click Refresh now. "
        "Keep Report and SemanticModel folders beside the project."
    )
    pages[governance + "visuals/GovernanceText/visual.json"] = _textbox(
        "GovernanceText", text, 150, 750, 16)
    pages["GovernedReport.Report/definition/pages/pages.json"] = {
        "$schema": SCHEMA_ROOT + "item/report/definition/pagesMetadata/1.0.0/schema.json",
        "pageOrder": order, "activePageName": "Overview",
    }
    return pages
