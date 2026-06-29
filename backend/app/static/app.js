"use strict";

const CATS = ["overview", "engineering", "hiring", "market", "traction"];
const $ = (id) => document.getElementById(id);

let es = null;
let tps = [];                 // tokens/sec history for the sparkline
const factsByCat = {};        // category -> [fact]

document.getElementById("screen-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const url = $("url").value.trim();
  if (url) start("/screen/stream?url=" + encodeURIComponent(url));
});

// Allow ?replay=events-host.jsonl on the page URL to drive a recorded demo.
const pageReplay = new URLSearchParams(location.search).get("replay");
if (pageReplay) start("/screen/stream?replay=" + encodeURIComponent(pageReplay));

function start(streamUrl) {
  if (es) es.close();
  resetUI();
  $("go").disabled = true;
  $("status").textContent = "screening…";
  es = new EventSource(streamUrl);
  es.onmessage = (m) => handle(JSON.parse(m.data));
  es.onerror = () => { $("status").textContent = "stream closed"; $("go").disabled = false; if (es) es.close(); };
}

function resetUI() {
  tps = [];
  for (const k of Object.keys(factsByCat)) delete factsByCat[k];
  document.querySelectorAll(".stage").forEach((s) => { s.className = "stage"; });
  $("c-collect").textContent = ""; $("c-extract").textContent = "";
  setText("frontier-usd", "$0.0000"); setText("amd-usd", "$0.0000");
  setText("savings", "—"); setText("gpu-util", "—"); setText("tps", "—");
  $("memo").hidden = true; $("verdict").innerHTML = ""; $("sections").innerHTML = ""; $("risk").innerHTML = "";
  drawGauge(0, false); drawSpark();
}

function handle(ev) {
  switch (ev.type) {
    case "stage": return onStage(ev);
    case "fact": return onFact(ev);
    case "metric": return onMetric(ev);
    case "cost": return onCost(ev);
    case "memo": return onMemo(ev);
    case "done": $("status").textContent = "done"; $("go").disabled = false; if (es) es.close(); return;
    case "error": $("status").textContent = "error: " + ev.message; $("go").disabled = false; if (es) es.close(); return;
  }
}

function onStage(ev) {
  const el = document.querySelector(`.stage[data-stage="${ev.stage}"]`);
  if (!el) return;
  el.classList.add(ev.status === "done" ? "done" : "active");
  if (ev.status === "done") el.classList.remove("active");
  if (ev.stage === "collect" && ev.sources != null) $("c-collect").textContent = ev.sources;
  if (ev.stage === "extract" && ev.facts != null) $("c-extract").textContent = ev.facts;
}

function onFact(ev) {
  (factsByCat[ev.category] ||= []).push(ev);
  const n = Object.values(factsByCat).reduce((a, b) => a + b.length, 0);
  $("c-extract").textContent = n;
}

function onMetric(ev) {
  if (ev.gpu_util != null) { setText("gpu-util", Math.round(ev.gpu_util * 100) + "%"); drawGauge(ev.gpu_util, true); }
  else { setText("gpu-util", "n/a"); drawGauge(0.0, false); }
  if (ev.tokens_per_sec != null) {
    setText("tps", Math.round(ev.tokens_per_sec));
    tps.push(ev.tokens_per_sec); if (tps.length > 60) tps.shift(); drawSpark();
  }
}

function onCost(ev) {
  tween("frontier-usd", ev.frontier_usd, (v) => "$" + v.toFixed(4));
  tween("amd-usd", ev.amd_usd, (v) => "$" + v.toFixed(4));
  if (ev.savings_x) setText("savings", ev.savings_x + "×");
}

function onMemo(ev) {
  $("memo").hidden = false;
  if (ev.verdict) {
    $("verdict").innerHTML =
      `<div class="rec">${esc(ev.verdict.recommendation)} — ${ev.verdict.score}/100`
      + ` <small style="color:var(--muted)">confidence ${ev.confidence}</small></div>`
      + `<div class="bb"><b>Bull:</b> ${esc(ev.verdict.bull)}</div>`
      + `<div class="bb"><b>Bear:</b> ${esc(ev.verdict.bear)}</div>`;
  }
  const summaries = ev.section_summaries || {};
  const out = [];
  for (const cat of CATS) {
    const facts = factsByCat[cat] || [];
    if (!facts.length && !summaries[cat]) continue;
    const rows = facts.map((f) =>
      `<div class="fact"><span class="conf">${f.confidence.toFixed(2)}</span>`
      + `<a href="${esc(f.source_url)}" target="_blank" rel="noopener">${esc(f.claim)} ↗</a></div>`).join("");
    out.push(`<div class="sec ${cat === "market" ? "market" : ""}"><h3>${cat}</h3>`
      + (summaries[cat] ? `<div class="summary">${esc(summaries[cat])}</div>` : "") + rows + `</div>`);
  }
  $("sections").innerHTML = out.join("");
  $("risk").innerHTML = (ev.risk_matrix || [])
    .map((r) => `<div class="riskchip">${esc(r.category)} <b>${r.score}/10</b></div>`).join("");
}

/* ---------- helpers ---------- */
function setText(id, t) { $(id).textContent = t; }
function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

const tweens = {};
function tween(id, target, fmt) {
  const el = $(id);
  const from = tweens[id] ?? 0;
  const t0 = performance.now(), dur = 400;
  function step(now) {
    const p = Math.min((now - t0) / dur, 1);
    const v = from + (target - from) * p;
    el.textContent = fmt(v);
    if (p < 1) requestAnimationFrame(step);
    else tweens[id] = target;
  }
  requestAnimationFrame(step);
}

function drawGauge(frac, live) {
  const c = $("gauge"), x = c.getContext("2d"), R = 50, cx = 60, cy = 60;
  x.clearRect(0, 0, 120, 120);
  x.lineWidth = 12; x.lineCap = "round";
  x.strokeStyle = "#232b3b"; x.beginPath(); x.arc(cx, cy, R, 0.75 * Math.PI, 2.25 * Math.PI); x.stroke();
  if (live) {
    x.strokeStyle = frac > 0.7 ? "#ff4d4d" : "#ffb020";
    x.beginPath(); x.arc(cx, cy, R, 0.75 * Math.PI, (0.75 + 1.5 * frac) * Math.PI); x.stroke();
  }
  x.fillStyle = "#e6edf6"; x.font = "700 20px ui-sans-serif"; x.textAlign = "center";
  x.fillText(live ? Math.round(frac * 100) + "%" : "—", cx, cy + 7);
}

function drawSpark() {
  const c = $("spark"), x = c.getContext("2d"), W = 280, H = 70;
  x.clearRect(0, 0, W, H);
  if (tps.length < 2) return;
  const max = Math.max(...tps, 1);
  x.strokeStyle = "#38d39f"; x.lineWidth = 2; x.beginPath();
  tps.forEach((v, i) => {
    const px = (i / (tps.length - 1)) * W, py = H - (v / max) * (H - 8) - 4;
    i ? x.lineTo(px, py) : x.moveTo(px, py);
  });
  x.stroke();
}
