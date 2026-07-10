"use strict";

const CATS = ["overview", "engineering", "hiring", "market", "traction"];
const $ = (id) => document.getElementById(id);

let es = null;
const factsByCat = {};        // category -> [fact]

document.getElementById("screen-form").addEventListener("submit", (e) => {
  e.preventDefault();
  let url = $("url").value.trim();
  if (url && !/^https?:\/\//i.test(url)) url = "https://" + url;  // bare domains work too
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
  es.onerror = () => {
    if ($("memo").hidden) showError("Connection to the server dropped mid-screen — try again.");
    $("status").textContent = "stream closed"; $("go").disabled = false; if (es) es.close();
  };
}

function resetUI() {
  for (const k of Object.keys(factsByCat)) delete factsByCat[k];
  document.querySelectorAll(".stage").forEach((s) => { s.className = "stage"; });
  $("c-collect").textContent = ""; $("c-extract").textContent = "";
  setText("naive-usd", "$0.0000"); setText("routed-usd", "$0.0000");
  setText("savings", "—"); setText("tok", "0");
  $("memo").hidden = true; $("verdict").innerHTML = ""; $("verdict").classList.remove("error");
  $("sections").innerHTML = ""; $("risk").innerHTML = "";
}

function showError(message) {
  const friendly = /RateLimit|429/i.test(message)
    ? "The model provider is rate-limiting us right now — wait a minute and try again."
    : "The screen could not finish — try again.";
  $("memo").hidden = false;
  $("verdict").classList.add("error");
  $("verdict").innerHTML = `<div class="error-banner"><b>Screen failed.</b> ${esc(friendly)}`
    + `<div class="error-detail">${esc(message)}</div></div>`;
}

function handle(ev) {
  switch (ev.type) {
    case "stage": return onStage(ev);
    case "fact": return onFact(ev);
    case "cost": return onCost(ev);
    case "memo": return onMemo(ev);
    case "done": $("status").textContent = "done"; $("go").disabled = false; if (es) es.close(); return;
    case "error":
      showError(ev.message);
      $("status").textContent = "error: " + ev.message; $("go").disabled = false; if (es) es.close(); return;
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

function onCost(ev) {
  tween("naive-usd", ev.naive_usd, (v) => "$" + v.toFixed(4));
  tween("routed-usd", ev.routed_usd, (v) => "$" + v.toFixed(4));
  if (ev.savings_x) setText("savings", ev.savings_x + "×");
  if (ev.tokens != null) setText("tok", ev.tokens.toLocaleString());
}

function onMemo(ev) {
  $("memo").hidden = false;
  if (ev.verdict) {
    const fb = ev.synth_fallback_model
      ? `<div class="fallback-note">premium model was rate-limited — synthesized on ${esc(String(ev.synth_fallback_model).split("/").pop())}</div>`
      : "";
    $("verdict").innerHTML =
      `<div class="rec">${esc(ev.verdict.recommendation)} — ${ev.verdict.score}/100`
      + ` <small style="color:var(--muted)">confidence ${ev.confidence}</small></div>`
      + `<div class="bb"><b>Bull:</b> ${esc(ev.verdict.bull)}</div>`
      + `<div class="bb"><b>Bear:</b> ${esc(ev.verdict.bear)}</div>` + fb;
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

/* ---------- example screens (in-page gallery) ---------- */
function recClass(r) {
  const s = (r || "").toLowerCase();
  if (s.includes("call")) return "rec-call";
  if (s.includes("pass")) return "rec-pass";
  return "rec-border";
}

function loadExamples() {
  const wrap = $("example-cards");
  if (!wrap) return;
  fetch("/api/screens").then((r) => r.json()).then((list) => {
    wrap.innerHTML = list.map((s) => `
      <button class="card" data-replay="${esc(s.name)}">
        <div class="host">${esc(s.host)}</div>
        <span class="rec ${recClass(s.recommendation)}">${esc(s.recommendation)} — ${s.score}/100</span>
        <div class="meta">
          <span><b>${s.facts}</b> facts</span>
          <span><b>${s.confidence}</b> conf</span>
          ${s.savings_x ? `<span><b>${s.savings_x}×</b> cheaper</span>` : ""}
        </div>
      </button>`).join("");
    wrap.querySelectorAll(".card").forEach((c) => c.addEventListener("click", () => {
      start("/screen/stream?replay=" + encodeURIComponent(c.dataset.replay));
      window.scrollTo({ top: 0, behavior: "smooth" });
    }));
  }).catch(() => {});
}

loadExamples();
