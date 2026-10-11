"""Standalone HTML report of a PowDroid session."""

import html
import json

from core import __version__, metrics

CHART_JS = "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PowDroid report – __TITLE__</title>
<script src="__CHART_JS__"></script>
<style>
  :root { --bg:#f7f7f8; --panel:#fff; --text:#1d1d1f; --muted:#6b6b72; --border:#e2e2e6; --accent:#5374C9; --warn:#B7791F; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#1d1d1d; --panel:#282828; --text:#e6e6e6; --muted:#a0a0a0; --border:#3c3c3c; --accent:#7d98e0; --warn:#E8B04B; }
  }
  * { box-sizing: border-box; }
  body { margin:0; padding:24px 16px; background:var(--bg); color:var(--text);
         font: 14px/1.45 -apple-system, "Segoe UI", Inter, Roboto, sans-serif; }
  main { max-width:1200px; margin:0 auto; display:flex; flex-direction:column; gap:16px; }
  h1 { margin:0; font-size:22px; } .muted { color:var(--muted); }
  .cards { display:grid; grid-template-columns:repeat(auto-fit, minmax(160px, 1fr)); gap:12px; }
  .card, .panel { background:var(--panel); border:1px solid var(--border); border-radius:8px; padding:14px; }
  .card .label { color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.04em; }
  .warnings { background:var(--panel); border:1px solid var(--warn); border-radius:8px; padding:10px 14px; color:var(--warn); }
  .warnings ul { margin:0; padding-left:18px; }
  .card .value { font-size:20px; font-weight:600; margin-top:4px; font-variant-numeric:tabular-nums; }
  .controls { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin-bottom:10px; }
  select, input { background:var(--bg); color:var(--text); border:1px solid var(--border);
                  border-radius:6px; padding:6px 8px; font:inherit; }
  .table-wrap { max-height:480px; overflow:auto; border:1px solid var(--border); border-radius:6px; }
  table { border-collapse:collapse; width:100%; font-variant-numeric:tabular-nums; }
  th, td { padding:6px 10px; border-bottom:1px solid var(--border); white-space:nowrap; text-align:left; }
  th { position:sticky; top:0; background:var(--panel); cursor:pointer; user-select:none; }
  th:hover { color:var(--accent); }
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
  <section class="panel">
    <div class="controls">
      <input id="search" type="search" placeholder="Filter rows (e.g. an app name)" size="32">
      <span id="count" class="muted"></span>
    </div>
    <div class="table-wrap"><table id="table"><thead></thead><tbody></tbody></table></div>
  </section>
</main>
<script>
const COLUMNS = __COLUMNS__;
const ROWS = __ROWS__;
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
const accent = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim();
let chart = null;
function draw() {
  const s = series[document.getElementById("view").value];
  if (typeof Chart === "undefined") return;
  if (chart) chart.destroy();
  chart = new Chart(document.getElementById("chart"), {
    type: "line",
    data: { datasets: [{ label: s.label, data: s.data, stepped: s.stepped, borderColor: accent,
            backgroundColor: accent + "33", fill: true, pointRadius: 0, borderWidth: 1.5 }] },
    options: { animation: false, parsing: false, interaction: { mode: "nearest", axis: "x", intersect: false },
               plugins: { tooltip: { callbacks: { title: items => clock(items[0].parsed.x) } } },
               scales: { x: { type: "linear", min: 0, max: ends.length ? ends[ends.length - 1] : 0,
                              ticks: { maxTicksLimit: 12, callback: clock },
                              title: { display: true, text: "Time since start (min:s)" } },
                         y: { beginAtZero: true, title: { display: true, text: s.label } } } },
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
const trs = ROWS.map(r => {
  const tr = document.createElement("tr");
  r.forEach(v => { tr.insertCell().textContent = v; });
  tr.dataset.text = r.join("\u0001").toLowerCase();
  return tr;
});
tbody.append(...trs);
let order = ROWS.map((_, i) => i), sortCol = -1, sortAsc = true;
function sortBy(col) {
  sortAsc = sortCol === col ? !sortAsc : true;
  sortCol = col;
  const num = v => (v === "" || isNaN(v)) ? null : Number(v);
  order.sort((a, b) => {
    const x = ROWS[a][col], y = ROWS[b][col], nx = num(x), ny = num(y);
    const cmp = (nx !== null && ny !== null) ? nx - ny : String(x).localeCompare(String(y));
    return sortAsc ? cmp : -cmp;
  });
  tbody.append(...order.map(i => trs[i]));
}
let filterTimer = null;
function filter() {
  const q = document.getElementById("search").value.toLowerCase();
  let shown = 0;
  for (const tr of trs) {
    tr.hidden = q !== "" && !tr.dataset.text.includes(q);
    if (!tr.hidden) shown++;
  }
  document.getElementById("count").textContent = shown + " / " + ROWS.length + " rows";
}
document.getElementById("search").addEventListener("input", () => {
  clearTimeout(filterTimer);
  filterTimer = setTimeout(filter, 150);
});
filter();
</script>
</body>
</html>
"""


def _script_json(value):
    # Prevent "</script>" (or similar) inside data from closing the script element.
    return json.dumps(value).replace("</", "<\\/")


def generate(result):
    """The HTML page of a session.Result."""
    cards_html = "".join(
        f'<div class="card"><div class="label">{html.escape(metrics.SUMMARY_LABELS[key])}</div>'
        f'<div class="value">{html.escape(value)}</div></div>'
        for key, value in metrics.summary_items(result.summary).items()
    )
    warnings_html = ('<section class="warnings"><ul>'
                     + "".join(f"<li>{html.escape(w)}</li>" for w in result.warnings)
                     + "</ul></section>") if result.warnings else ""
    return (
        TEMPLATE.replace("__CHART_JS__", CHART_JS)
        .replace("__TITLE__", html.escape(result.csv_path.stem))
        .replace("__VERSION__", html.escape(__version__))
        .replace("__WARNINGS__", warnings_html)
        .replace("__CARDS__", cards_html)
        .replace("__COLUMNS__", _script_json(metrics.COLUMNS))
        .replace("__ROWS__", _script_json([metrics.format_row(row) for row in result.rows]))
    )


def write(result):
    """Write the HTML page next to the session's CSV and return its path."""
    html_path = result.csv_path.with_suffix(".html")
    html_path.write_text(generate(result), encoding="utf-8")
    return html_path
