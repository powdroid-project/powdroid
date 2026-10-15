"""Standalone HTML report of a PowDroid session.

The page is self-contained: Chart.js (MIT license, powdroid/core/vendor) is inlined, so it
opens offline and fetches nothing.
"""

import html
import json
import re
from pathlib import Path

from powdroid.core import __version__, metrics

CHART_JS = Path(__file__).resolve().parent / "vendor" / "chart.umd.min.js"
TABLE_PAGE = 500  # rows added to the table at a time: building every row of a long session is slow

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PowDroid report – __TITLE__</title>
<script>__CHART_JS__</script>
<style>
  :root { --bg:#f7f7f8; --panel:#fff; --text:#1d1d1f; --muted:#6b6b72; --border:#e2e2e6;
          --accent:#5374C9; --warn:#B7791F; --marker:#C53030; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#1d1d1d; --panel:#282828; --text:#e6e6e6; --muted:#a0a0a0; --border:#3c3c3c;
            --accent:#7d98e0; --warn:#E8B04B; --marker:#FF6B6B; }
  }
  * { box-sizing: border-box; }
  body { margin:0; padding:24px 16px; background:var(--bg); color:var(--text);
         font: 14px/1.45 -apple-system, "Segoe UI", Inter, Roboto, sans-serif; }
  main { max-width:1200px; margin:0 auto; display:flex; flex-direction:column; gap:16px; }
  h1 { margin:0; font-size:22px; } h2 { margin:0 0 8px; font-size:16px; } .muted { color:var(--muted); }
  .cards { display:grid; grid-template-columns:repeat(auto-fit, minmax(160px, 1fr)); gap:12px; }
  .card, .panel { background:var(--panel); border:1px solid var(--border); border-radius:8px; padding:14px;
                  min-width:0; }
  .card .label { color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.04em; }
  .warnings { background:var(--panel); border:1px solid var(--warn); border-radius:8px; padding:10px 14px;
              color:var(--warn); }
  .warnings ul { margin:0; padding-left:18px; }
  .card .value { font-size:20px; font-weight:600; margin-top:4px; font-variant-numeric:tabular-nums; }
  .controls { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin-bottom:10px; }
  select, input, button { background:var(--bg); color:var(--text); border:1px solid var(--border);
                          border-radius:6px; padding:6px 8px; font:inherit; }
  button { cursor:pointer; } button:hover { border-color:var(--accent); }
  .table-wrap { max-height:480px; overflow:auto; border:1px solid var(--border); border-radius:6px; }
  table { border-collapse:collapse; width:100%; font-variant-numeric:tabular-nums; }
  th, td { padding:6px 10px; border-bottom:1px solid var(--border); white-space:nowrap; text-align:left; }
  #table th { position:sticky; top:0; background:var(--panel); cursor:pointer; user-select:none; }
  #table th:hover { color:var(--accent); }
  .details td:first-child { color:var(--muted); }
</style>
</head>
<body>
<main>
  <header>
    <h1>PowDroid energy report</h1>
    <div class="muted">__TITLE__ · PowDroid __VERSION__</div>
  </header>
  __WARNINGS__
  <section class="cards">__CARDS__</section>
  <section class="panel">
    <div class="controls">
      <label>View <select id="view">
        <option value="power">Power (W)</option>
        <option value="cumulative">Cumulative energy (J)</option>
      </select></label>
    </div>
    <canvas id="chart" height="110"></canvas>
  </section>
  __DETAILS__
  <section class="panel">
    <div class="controls">
      <input id="search" type="search" placeholder="Filter rows (e.g. an app name)" size="32">
      <span id="count" class="muted"></span>
      <button id="more" hidden></button>
    </div>
    <div class="table-wrap"><table id="table"><thead></thead><tbody></tbody></table></div>
  </section>
</main>
<script>
const COLUMNS = __COLUMNS__;
const ROWS = __ROWS__;
const MARKERS = __MARKERS__;  // [{x: seconds since the start, label}]
const PAGE = __PAGE__;
const col = name => COLUMNS.indexOf(name);
// Empty cells (unknown, e.g. while plugged in) are gaps, not zeros.
const num = v => (v === "" ? null : Number(v));
// x is the time since the session start, in seconds, so the axis is proportional to time.
const starts = ROWS.map(r => Number(r[col("elapsed_s")]));
const ends = ROWS.map((r, i) => starts[i] + Number(r[col("duration_ms")]) / 1000);
const power = ROWS.map((r, i) => ({ x: starts[i], y: num(r[col("power_w")]) }));
if (ROWS.length) power.push({ x: ends[ends.length - 1], y: power[power.length - 1].y });
let acc = 0;
const cumulative = [{ x: 0, y: 0 }, ...ROWS.map((r, i) => ({ x: ends[i], y: (acc += num(r[col("energy_j")]) || 0) }))];
const series = {
  power: { label: "Power (W)", data: power, stepped: "after" },
  cumulative: { label: "Cumulative energy (J)", data: cumulative, stepped: false },
};
const clock = s => Math.floor(s / 60) + ":" + String(Math.floor(s % 60)).padStart(2, "0");
const style = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const accent = style("--accent");
// Draws the markers as labelled vertical lines.
const markerLines = {
  id: "markers",
  afterDatasetsDraw(chart) {
    const { ctx, chartArea: area, scales: { x } } = chart;
    ctx.save();
    ctx.strokeStyle = ctx.fillStyle = style("--marker");
    ctx.setLineDash([4, 3]);
    ctx.font = "12px sans-serif";
    for (const m of MARKERS) {
      const px = x.getPixelForValue(m.x);
      if (px < area.left || px > area.right) continue;
      ctx.beginPath(); ctx.moveTo(px, area.top); ctx.lineTo(px, area.bottom); ctx.stroke();
      ctx.fillText(m.label, px + 4, area.top + 12);
    }
    ctx.restore();
  },
};
let chart = null;
function draw() {
  const s = series[document.getElementById("view").value];
  if (typeof Chart === "undefined") return;
  if (chart) chart.destroy();
  chart = new Chart(document.getElementById("chart"), {
    type: "line",
    data: { datasets: [{ label: s.label, data: s.data, stepped: s.stepped, borderColor: accent,
            backgroundColor: accent + "33", fill: true, pointRadius: 0, borderWidth: 1.5 }] },
    options: { animation: false, parsing: false, normalized: true,
               interaction: { mode: "nearest", axis: "x", intersect: false },
               plugins: { decimation: { enabled: true, algorithm: "min-max" },
                          tooltip: { callbacks: { title: items => clock(items[0].parsed.x) } } },
               scales: { x: { type: "linear", min: 0, max: ends.length ? ends[ends.length - 1] : 0,
                              ticks: { maxTicksLimit: 12, callback: clock },
                              title: { display: true, text: "Time since start (min:s)" } },
                         y: { beginAtZero: true, title: { display: true, text: s.label } } } },
    plugins: [markerLines],
  });
}
document.getElementById("view").addEventListener("change", draw);
draw();

const thead = document.querySelector("#table thead"), tbody = document.querySelector("#table tbody");
const headRow = thead.insertRow();
COLUMNS.forEach((c, i) => {
  const th = document.createElement("th");
  th.textContent = c;
  th.addEventListener("click", () => sortBy(i));
  headRow.appendChild(th);
});
const text = ROWS.map(r => r.join("\\u0001").toLowerCase());
let order = ROWS.map((_, i) => i), sortCol = -1, sortAsc = true, shown = [], limit = PAGE;
function row(i) {
  const tr = document.createElement("tr");
  ROWS[i].forEach(v => { tr.insertCell().textContent = v; });
  return tr;
}
// The table only holds the first `limit` matching rows: "Show more" adds a page.
function render() {
  const q = document.getElementById("search").value.toLowerCase();
  shown = q === "" ? order : order.filter(i => text[i].includes(q));
  tbody.replaceChildren(...shown.slice(0, limit).map(row));
  document.getElementById("count").textContent = shown.length + " / " + ROWS.length + " rows";
  updateMore();
}
function updateMore() {
  const more = document.getElementById("more");
  more.hidden = shown.length <= limit;
  more.textContent = "Show " + Math.min(PAGE, shown.length - limit) + " more";
}
function sortBy(c) {
  sortAsc = sortCol === c ? !sortAsc : true;
  sortCol = c;
  const value = v => (v === "" || isNaN(v)) ? null : Number(v);
  order.sort((a, b) => {
    const x = ROWS[a][c], y = ROWS[b][c], nx = value(x), ny = value(y);
    const cmp = (nx !== null && ny !== null) ? nx - ny : String(x).localeCompare(String(y));
    return sortAsc ? cmp : -cmp;
  });
  render();
}
let filterTimer = null;
document.getElementById("search").addEventListener("input", () => {
  clearTimeout(filterTimer);
  filterTimer = setTimeout(() => { limit = PAGE; render(); }, 150);
});
document.getElementById("more").addEventListener("click", () => {  // only the new page is built
  tbody.append(...shown.slice(limit, limit + PAGE).map(row));
  limit += PAGE;
  updateMore();
});
render();
</script>
</body>
</html>
"""


def _script_json(value):
    """JSON safe inside a <script> element, whatever its strings contain (app names come from the phone)."""
    text = json.dumps(value)
    for char, escaped in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026"),
                          (" ", "\\u2028"), (" ", "\\u2029")):
        text = text.replace(char, escaped)
    return text


def _chart_js():
    """The Chart.js bundle, without its source map comment (the map is not shipped)."""
    code = CHART_JS.read_text(encoding="utf-8")
    return "\n".join(line for line in code.splitlines() if not line.startswith("//# sourceMappingURL"))


def _table(headers, rows):
    head = "".join(f"<th>{html.escape(h)}</th>" for h in headers or [])
    head = f"<thead><tr>{head}</tr></thead>" if head else ""
    body = "".join("<tr>" + "".join(f"<td>{html.escape(str(cell))}</td>" for cell in row) + "</tr>" for row in rows)
    return f'<div class="table-wrap"><table>{head}<tbody>{body}</tbody></table></div>'


def details_sections(result):
    """(kind, title, headers, rows) of the measurement details of a session.Result, for the HTML and GUI reports.

    kind is "phases", "rails" or "measurement": (label, value) rows, without headers (None).
    """
    sections = []
    phases = metrics.phase_rows(result.phases)
    if phases:
        sections.append(("phases", "Phases (between markers)", metrics.PHASE_HEADERS, phases))
    rails = metrics.rail_rows(result.details.get("power_rails") or [])
    if rails:
        sections.append(("rails", "Power rails (on-device power monitors)", metrics.RAIL_HEADERS, rails))
    lines = metrics.measurement_lines(result.summary, result.details)
    if lines:
        sections.append(("measurement", "Measurement", None, lines))
    return sections


def generate(result):
    """The HTML page of a session.Result."""
    columns = metrics.columns(result.rows)
    format_row = metrics.row_formatter(columns)
    cards_html = "".join(
        f'<div class="card"><div class="label">{html.escape(metrics.SUMMARY_LABELS[key])}</div>'
        f'<div class="value">{html.escape(value)}</div></div>'
        for key, value in metrics.summary_items(result.summary).items()
    )
    warnings_html = ('<section class="warnings"><ul>'
                     + "".join(f"<li>{html.escape(w)}</li>" for w in result.warnings)
                     + "</ul></section>") if result.warnings else ""
    details_html = "".join(f'<section class="panel{" details" if kind == "measurement" else ""}">'
                           f"<h2>{html.escape(title)}</h2>{_table(headers, rows)}</section>"
                           for kind, title, headers, rows in details_sections(result))
    start_ms = result.rows[0]["start_ms"] if result.rows else 0
    markers = [{"x": (m["time_ms"] - start_ms) / 1000, "label": m["label"]} for m in result.markers]
    values = {
        "CHART_JS": _chart_js(),
        "TITLE": html.escape(result.csv_path.stem),
        "VERSION": html.escape(__version__),
        "WARNINGS": warnings_html,
        "CARDS": cards_html,
        "DETAILS": details_html,
        "PAGE": str(TABLE_PAGE),
        "MARKERS": _script_json(markers),
        "COLUMNS": _script_json(columns),
        "ROWS": _script_json([format_row(row) for row in result.rows]),
    }
    # In one pass, so that inserted text (e.g. an app named __ROWS__) is never replaced in turn.
    return re.sub(r"__([A-Z_]+)__", lambda m: values.get(m.group(1), m.group(0)), TEMPLATE)


def write(result):
    """Write the HTML page next to the session's CSV and return its path."""
    html_path = result.csv_path.with_suffix(".html")
    html_path.write_text(generate(result), encoding="utf-8")
    return html_path
