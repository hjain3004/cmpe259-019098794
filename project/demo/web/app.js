"use strict";

const $ = id => document.getElementById(id);

const state = {
  meta: null,
  session: null,
  config: "C3",
  busy: false,
  turns: 0,
  lastQuestion: "",
  traces: [],
};

const RESPONSE_BADGES = {
  WARN: { text: "Heads up", cls: "warn" },
  CLARIFY: { text: "I need one detail", cls: "clarify" },
  ABSTAIN: { text: "I can't tell from your records", cls: "abstain" },
  ANSWER: null,
  ERROR: { text: "Could not answer", cls: "error" },
};

const STATUS_CLASSES = {
  "Paid": "status-paid",
  "Partly paid?": "status-partly",
  "Unpaid": "status-unpaid",
  "Overdue": "status-overdue",
  "Check before paying": "status-check",
};

const MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MONTH_INDEX = {
  january: 0, jan: 0, february: 1, feb: 1, march: 2, mar: 2, april: 3, apr: 3,
  may: 4, june: 5, jun: 5, july: 6, jul: 6, august: 7, aug: 7,
  september: 8, sep: 8, sept: 8, october: 9, oct: 9, november: 10, nov: 10, december: 11, dec: 11,
};

const TOOL_NAME_RE = /\b(?:list_open_bills|get_bill_status|match_payments|sum_amount_due|compare_vendor_payment_details|summarize_purchases|get_source_evidence)\b/g;
const EVIDENCE_ID_RE = /\b(?:span_(?:inv|cn|msg)_[A-Za-z0-9_-]+|vh_[A-Za-z0-9_-]+|txn_\d+|msg_[A-Za-z0-9_-]+)\b/g;

const viewer = {
  data: null, zoom: 1, baseW: 0, baseH: 0, panX: 0, panY: 0,
  dragging: false, moved: false, startX: 0, startY: 0, origPanX: 0, origPanY: 0, imgEl: null,
};

function element(tag, text, className) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (className) el.className = className;
  return el;
}

function formatOwnerMoneyAndDates(raw) {
  let out = String(raw || "");
  // Format "$1,073.25 USD" or "1073.25 USD" into "$1,073.25"
  out = out.replace(/\$(\d[\d,]*\.\d{2})\s+USD\b/g, "$$$1");
  out = out.replace(/(^|[^\w$])(\d+(?:\.\d{2}))\s+USD\b/g, (_, pre, num) => {
    const val = Number(num);
    if (!Number.isFinite(val)) return `${pre}${num}`;
    return `${pre}$${val.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  });
  // Format ISO dates 2026-10-01 -> "Oct 1"
  out = out.replace(/\b(20\d{2})-(\d{2})-(\d{2})\b/g, (_, _y, m, d) => {
    const mi = Number(m) - 1;
    const day = Number(d);
    if (mi >= 0 && mi < 12 && day >= 1 && day <= 31) return `${MONTHS_SHORT[mi]} ${day}`;
    return _;
  });
  // Format written dates like "October 1, 2026" or "September 12" -> "Oct 1", "Sep 12"
  out = out.replace(
    /\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:,\s*20\d{2})?\b/gi,
    (_, mon, day) => `${MONTHS_SHORT[MONTH_INDEX[mon.toLowerCase()]]} ${Number(day)}`
  );
  // Keep evidence IDs, raw JSON snippets, and tool names out of owner view
  out = out.replace(EVIDENCE_ID_RE, "").replace(TOOL_NAME_RE, "record lookup");
  out = out.replace(/\(\s*\)/g, "").replace(/\s{2,}/g, " ").trim();
  return out;
}

function richParagraph(value) {
  const p = element("p");
  const clean = formatOwnerMoneyAndDates(value);
  const parts = clean.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  for (const part of parts) {
    if (part.startsWith("**") && part.endsWith("**")) p.append(element("strong", part.slice(2, -2)));
    else if (part.startsWith("`") && part.endsWith("`")) p.append(document.createTextNode(part.slice(1, -1)));
    else p.append(document.createTextNode(part));
  }
  return p;
}

function setError(message = "") {
  $("page-error").textContent = message;
  $("page-error").hidden = !message;
}

async function api(path, body) {
  const options = body === undefined
    ? {}
    : {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CashBooks-Token": state.meta.token },
        body: JSON.stringify(body),
      };
  const response = await fetch(path, options);
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error("The local server is unavailable. Check that it is running, then reload this page.");
  }
  if (!response.ok) throw new Error(data.error || "The request could not be completed.");
  return data;
}

function setBusy(busy) {
  state.busy = busy;
  $("question").disabled = busy;
  $("send-button").disabled = busy || !$("question").value.trim();
  $("reset-button").disabled = busy;
  const sel = $("config-select");
  if (sel) sel.disabled = busy;
  document.querySelectorAll(".suggestion,.followup").forEach(b => { b.disabled = busy; });
}

function renderBehindTheScenesTrace() {
  const container = $("bts-trace");
  if (!state.traces.length) {
    container.replaceChildren(
      element("p", "Ask a question to inspect the tool trace, retrieval counts, and source evidence IDs.", "bts-empty")
    );
    return;
  }
  const list = element("div", undefined, "bts-trace-list");
  state.traces.forEach((entry, idx) => {
    const res = entry.result;
    const item = element("div", undefined, "bts-trace-item");
    const method = state.meta.configs.find(c => c.id === res.config);
    const head = element("strong", `Turn ${idx + 1} · ${res.config} (${method ? method.name : res.config}) · ${res.kind}`);
    item.append(head);
    if (res.latency_ms !== null) {
      item.append(element("p", `Latency: ${(res.latency_ms / 1000).toFixed(2)} s`));
    }
    if (res.tools && res.tools.length) {
      for (const call of res.tools) {
        const line = element("p");
        line.append(element("code", call.name), document.createTextNode(` — ${call.title}${call.details ? ` (${call.details})` : ""}`));
        if (call.failed) line.append(document.createTextNode(" [tool returned error]"));
        item.append(line);
      }
    } else if (res.retrieved_count) {
      item.append(element("p", `Supplied ${res.retrieved_count} retrieved context entries (${res.config}).`));
    } else {
      item.append(element("p", "No tool calls or retrieved chunks recorded for this turn."));
    }
    if (res.sources && res.sources.length) {
      const eids = res.sources.map(s => s.evidence_id).join(", ");
      item.append(element("div", `Evidence IDs: ${eids}`, "bts-eids"));
    }
    list.append(item);
  });
  container.replaceChildren(list);
}

async function newConversation(config = state.config) {
  setBusy(true);
  setError();
  try {
    const data = await api("/api/session", { config, previous: state.session });
    state.session = data.session;
    state.config = config;
    state.turns = 0;
    state.lastQuestion = "";
    state.traces = [];
    $("conversation").replaceChildren();
    $("question").value = "";
    const sel = $("config-select");
    if (sel) sel.value = config;
    const cfg = state.meta.configs.find(c => c.id === config);
    if (cfg) $("config-description").textContent = cfg.description;
    renderBehindTheScenesTrace();
  } catch (e) {
    setError(e.message);
  } finally {
    setBusy(false);
  }
}

function renderAttentionPanel(groups) {
  const wrap = $("attention-groups");
  wrap.replaceChildren();
  if (!groups || !groups.length) {
    wrap.append(element("p", "Everything looks up to date right now.", "section-sub"));
    return;
  }
  for (const grp of groups) {
    const section = element("section", undefined, "att-group");
    const head = element("div", undefined, "att-group-head");
    head.append(element("h2", grp.title), element("span", String(grp.cards.length), "att-count"));
    section.append(head);

    const cardsWrap = element("div", undefined, "att-cards");
    for (const card of grp.cards) {
      const art = element("article", undefined, "att-card");
      const top = element("div", undefined, "att-card-top");
      const who = element("div", undefined, "att-card-who");
      who.append(element("span", card.vendor, "att-vendor"), element("span", card.invoice, "att-invoice"));
      top.append(who, element("span", card.amount, "att-amount"));
      art.append(top);

      art.append(element("p", formatOwnerMoneyAndDates(card.summary), "att-summary"));

      const foot = element("div", undefined, "att-card-foot");
      const statusCls = STATUS_CLASSES[card.status] || "status-unpaid";
      foot.append(element("span", card.status, `status-pill ${statusCls}`));
      if (card.proof) {
        const proofBtn = element("button", "See proof", "proof-button");
        proofBtn.type = "button";
        proofBtn.addEventListener("click", () => openEvidenceViewer(card.proof));
        foot.append(proofBtn);
      }
      art.append(foot);
      cardsWrap.append(art);
    }
    section.append(cardsWrap);
    wrap.append(section);
  }
}

/* Evidence Viewer (preserved) */
function applyImageTransform() {
  if (!viewer.imgEl) return;
  viewer.imgEl.style.width = `${viewer.baseW}px`;
  viewer.imgEl.style.height = `${viewer.baseH}px`;
  viewer.imgEl.style.transform = `translate(${viewer.panX}px, ${viewer.panY}px) scale(${viewer.zoom})`;
  $("ev-zoom-readout").textContent = `${Math.round(viewer.zoom * 100)}%`;
  $("ev-stage").classList.toggle("is-pannable", viewer.zoom > 1.02);
}

function fitPdfToStage() {
  if (!viewer.data || viewer.data.kind !== "pdf_page" || !viewer.imgEl) return;
  const stage = $("ev-stage");
  const sw = Math.max(240, stage.clientWidth - 24);
  const sh = Math.max(240, stage.clientHeight - 24);
  const scale = Math.min(sw / viewer.data.width, sh / viewer.data.height);
  viewer.baseW = Math.round(viewer.data.width * scale);
  viewer.baseH = Math.round(viewer.data.height * scale);
  viewer.zoom = 1;
  viewer.panX = (stage.clientWidth - viewer.baseW) / 2;
  viewer.panY = Math.max(12, (stage.clientHeight - viewer.baseH) / 2);
  applyImageTransform();
}

function zoomAt(targetZoom, anchorX, anchorY) {
  if (!viewer.imgEl) return;
  const stage = $("ev-stage");
  const next = Math.min(6, Math.max(0.5, targetZoom));
  const cx = anchorX !== undefined ? anchorX : stage.clientWidth / 2;
  const cy = anchorY !== undefined ? anchorY : stage.clientHeight / 2;
  const imgX = (cx - viewer.panX) / viewer.zoom;
  const imgY = (cy - viewer.panY) / viewer.zoom;
  viewer.zoom = next;
  viewer.panX = cx - imgX * next;
  viewer.panY = cy - imgY * next;
  applyImageTransform();
}

function jumpToHighlight() {
  if (!viewer.data || !viewer.data.highlight || !viewer.imgEl) return;
  const stage = $("ev-stage");
  const h = viewer.data.highlight;
  const boxWFrac = Math.max(0.08, h.x1 - h.x0);
  const targetZoom = Math.min(4.0, Math.max(2.4, 0.52 / boxWFrac));
  const nx = (h.x0 + h.x1) / 2;
  const ny = (h.top + h.bottom) / 2;
  viewer.zoom = targetZoom;
  viewer.panX = stage.clientWidth / 2 - nx * viewer.baseW * targetZoom;
  viewer.panY = stage.clientHeight / 2 - ny * viewer.baseH * targetZoom;
  applyImageTransform();
}

function setFullscreen(on) {
  const dlg = $("evidence-dialog");
  dlg.classList.toggle("ev-dialog--fullscreen", on);
  $("ev-fullscreen").setAttribute("aria-pressed", String(on));
  $("ev-fullscreen").textContent = on ? "Exit full screen" : "Full screen";
  requestAnimationFrame(() => fitPdfToStage());
}

function renderPdfEvidence(data) {
  const stage = $("ev-stage");
  stage.classList.add("ev-stage--pdf");
  const img = document.createElement("img");
  img.id = "ev-page-img";
  img.className = "ev-page-img";
  img.alt = data.title;
  img.draggable = false;
  viewer.imgEl = img;
  img.addEventListener("load", () => fitPdfToStage());
  img.src = data.image_url;
  stage.replaceChildren(img);
}

function renderBankEvidence(data) {
  const stage = $("ev-stage");
  stage.classList.remove("ev-stage--pdf");
  const wrap = element("div", undefined, "ev-bank-wrap");
  const table = element("table", undefined, "ev-bank-table");
  const thead = document.createElement("thead");
  const hr = document.createElement("tr");
  for (const col of ["Date", "Reference", "Description", "Amount"]) hr.append(element("th", col));
  thead.append(hr);
  const tbody = document.createElement("tbody");
  for (const row of data.rows) {
    const tr = document.createElement("tr");
    if (row.highlighted) tr.className = "ev-row-highlighted";
    const amt = formatOwnerMoneyAndDates(`${row.amount} ${row.currency}`);
    tr.append(
      element("td", formatOwnerMoneyAndDates(row.posted_on)),
      element("td", row.txn_id),
      element("td", row.descriptor),
      element("td", amt, "ev-num")
    );
    tbody.append(tr);
  }
  table.append(thead, tbody);
  wrap.append(table);
  stage.replaceChildren(wrap);
}

function renderMessageEvidence(data) {
  const stage = $("ev-stage");
  stage.classList.remove("ev-stage--pdf");
  const card = element("div", undefined, "ev-message-card");
  const meta = element("dl", undefined, "ev-meta-grid");
  for (const [k, v] of [
    ["From", data.from],
    ["Date", formatOwnerMoneyAndDates(data.received_on)],
    ["Channel", (data.channel || "email").toUpperCase()],
    ["Subject", data.subject || "(no subject)"],
  ]) {
    meta.append(element("dt", k), element("dd", v));
  }
  const body = element("div", undefined, "ev-message-body");
  const s = Math.max(0, Math.min(data.body.length, data.highlight_start || 0));
  const e = Math.max(s, Math.min(data.body.length, data.highlight_end || 0));
  if (s > 0) body.append(document.createTextNode(data.body.slice(0, s)));
  if (e > s) body.append(element("mark", data.body.slice(s, e), "ev-highlight-mark"));
  if (e < data.body.length) body.append(document.createTextNode(data.body.slice(e)));
  card.append(meta, body);
  stage.replaceChildren(card);
}

function renderVendorEvidence(data) {
  const stage = $("ev-stage");
  stage.classList.remove("ev-stage--pdf");
  const card = element("div", undefined, "ev-vendor-card");
  const v = data.vendor;
  const rows = [
    ["canonical_name", "Vendor name", v.canonical_name],
    ["aliases", "Aliases", v.aliases && v.aliases.length ? v.aliases.join(", ") : "None"],
    ["bank_name", "Verified bank", v.bank_name || "—"],
    ["account", "Account number", v.account || "—"],
    ["routing", "Routing number", v.routing || "—"],
    ["verified_on", "Verified on", v.verified_on ? formatOwnerMoneyAndDates(v.verified_on) : "—"],
    ["trusted_contact", "Trusted contact", v.trusted_contact || "—"],
  ];
  for (const [key, label, val] of rows) {
    const row = element("div", undefined, key === data.highlighted_field ? "ev-vendor-row ev-field-highlighted" : "ev-vendor-row");
    row.append(element("span", label, "ev-vendor-key"), element("span", val, "ev-vendor-val"));
    card.append(row);
  }
  stage.replaceChildren(card);
}

async function openEvidenceViewer(citation) {
  const dlg = $("evidence-dialog");
  dlg.classList.remove("ev-dialog--fullscreen");
  $("ev-fullscreen").setAttribute("aria-pressed", "false");
  $("ev-fullscreen").textContent = "Full screen";
  viewer.data = null;
  viewer.imgEl = null;
  viewer.zoom = 1;
  $("evidence-title").textContent = citation.label || "Supporting proof";
  $("ev-stage").replaceChildren(element("p", "Loading document…", "ev-loading"));
  for (const id of ["ev-jump", "ev-zoom-out", "ev-zoom-readout", "ev-zoom-in", "ev-zoom-reset", "ev-fullscreen", "ev-hint"]) $(id).hidden = true;
  const cleanSupports = formatOwnerMoneyAndDates(citation.supports || "");
  $("ev-claim-text").textContent = cleanSupports;
  $("ev-claim").hidden = !cleanSupports;
  if (!dlg.open) dlg.showModal();
  try {
    const q = new URLSearchParams({ id: citation.evidence_id });
    if (state.session) q.set("session", state.session);
    if (citation.supports) q.set("supports", citation.supports);
    const data = await api(`/api/evidence?${q.toString()}`);
    viewer.data = data;
    $("evidence-title").textContent = data.title || citation.label || "Supporting proof";
    const claimText = formatOwnerMoneyAndDates(data.supports || citation.supports || "");
    $("ev-claim-text").textContent = claimText;
    $("ev-claim").hidden = !claimText;
    const isPdf = data.kind === "pdf_page";
    for (const id of ["ev-zoom-out", "ev-zoom-readout", "ev-zoom-in", "ev-zoom-reset", "ev-fullscreen", "ev-hint"]) $(id).hidden = !isPdf;
    $("ev-jump").hidden = !(isPdf && data.highlight);
    if (isPdf) renderPdfEvidence(data);
    else if (data.kind === "bank") renderBankEvidence(data);
    else if (data.kind === "message") renderMessageEvidence(data);
    else if (data.kind === "vendor") renderVendorEvidence(data);
  } catch (e) {
    $("ev-stage").replaceChildren(element("p", e.message || "Document could not be loaded.", "ev-error"));
  }
}

function renderReply(result) {
  state.traces.push({ result });
  renderBehindTheScenesTrace();

  const article = element("article", undefined, "message assistant-message");
  const heading = element("div", undefined, "assistant-heading");
  heading.append(element("span", "cb", "assistant-symbol"), element("span", "CashBooks", "assistant-name"));

  const badgeSpec = RESPONSE_BADGES[result.kind];
  if (badgeSpec) {
    heading.append(element("span", badgeSpec.text, `response-badge ${badgeSpec.cls}`));
  }

  const body = element("div", undefined, "assistant-body");
  for (const p of result.answer.split(/\n\s*\n/)) body.append(richParagraph(p));
  article.append(heading, body);

  if (result.clarifying_question) {
    const box = element("div", undefined, "clarification");
    box.append(element("strong", "I need one detail"), richParagraph(result.clarifying_question));
    article.append(box);
  }
  if (result.risks && result.risks.length) {
    const box = element("div", undefined, "warning-list");
    for (const risk of result.risks) box.append(richParagraph(risk));
    article.append(box);
  }
  if (result.calculation && result.calculation.steps && result.calculation.steps.length) {
    const box = element("div", undefined, "calculation");
    box.append(element("strong", "Calculation"));
    for (const st of result.calculation.steps) box.append(richParagraph(st));
    if (result.calculation.result) {
      box.append(element("strong", formatOwnerMoneyAndDates(result.calculation.result)));
    }
    article.append(box);
  }
  if (result.next_step) {
    const box = element("div", undefined, "next-step");
    box.append(element("strong", "Next step"), richParagraph(result.next_step));
    article.append(box);
  }

  if (result.sources && result.sources.length) {
    const sources = element("div", undefined, "source-details");
    const chipRow = element("div", undefined, "citation-chips");
    for (const c of result.sources) {
      const chip = element("button", undefined, "citation-chip");
      chip.type = "button";
      chip.append(
        element("span", `See proof · ${c.label}`, "citation-chip-pill"),
        element("span", formatOwnerMoneyAndDates(c.supports), "citation-chip-text")
      );
      chip.addEventListener("click", () => openEvidenceViewer(c));
      chipRow.append(chip);
    }
    sources.append(chipRow);
    article.append(sources);
  }

  const matchedCfgQ = (state.meta.questions || []).find(q => q.question === state.lastQuestion);
  if (matchedCfgQ && matchedCfgQ.followup) {
    const followups = element("div", undefined, "followups");
    const b = element("button", matchedCfgQ.followup, "followup");
    b.type = "button";
    b.addEventListener("click", () => fillQuestion(matchedCfgQ.followup));
    followups.append(b);
    article.append(followups);
  }

  $("conversation").append(article);
}

function fillQuestion(q) {
  if (state.busy) return;
  $("question").value = q;
  $("send-button").disabled = false;
  $("question").focus();
  $("question").scrollIntoView({ block: "center", behavior: "auto" });
}

async function submit(event) {
  event.preventDefault();
  const question = $("question").value.trim();
  if (!question || state.busy || !state.session) return;
  setError();
  setBusy(true);
  state.lastQuestion = question;
  state.turns += 1;
  document.querySelectorAll(".followups").forEach(e => e.remove());

  const user = element("article", undefined, "message user-message");
  user.append(element("p", question));
  $("conversation").append(user);
  $("question").value = "";
  $("pending").hidden = false;
  $("pending-text").textContent = state.meta.mode === "live"
    ? "Checking your records…"
    : "Running offline rehearsal…";
  $("pending").scrollIntoView({ block: "center", behavior: "auto" });

  try {
    renderReply(await api("/api/ask", { session: state.session, question }));
  } catch (e) {
    setError(e.message);
    $("question").value = question;
  } finally {
    $("pending").hidden = true;
    setBusy(false);
    $("question").focus();
  }
}

$("question-form").addEventListener("submit", submit);
$("question").addEventListener("input", () => {
  $("send-button").disabled = state.busy || !$("question").value.trim();
});
$("question").addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    $("question-form").requestSubmit();
  }
});
$("reset-button").addEventListener("click", () => newConversation());

const evDialog = $("evidence-dialog");
$("close-evidence").addEventListener("click", () => evDialog.close());
evDialog.addEventListener("close", () => { evDialog.returnValue = ""; });
if (!("closedBy" in HTMLDialogElement.prototype)) {
  const outside = (e, dlg) => {
    const r = dlg.getBoundingClientRect();
    return e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom;
  };
  let pressedOutside = false;
  evDialog.addEventListener("pointerdown", e => { pressedOutside = outside(e, evDialog); });
  evDialog.addEventListener("pointerup", e => { if (pressedOutside && outside(e, evDialog)) evDialog.close(); });
}

$("ev-zoom-in").addEventListener("click", () => zoomAt(viewer.zoom * 1.3));
$("ev-zoom-out").addEventListener("click", () => zoomAt(viewer.zoom / 1.3));
$("ev-zoom-reset").addEventListener("click", () => fitPdfToStage());
$("ev-jump").addEventListener("click", () => jumpToHighlight());
$("ev-fullscreen").addEventListener("click", () => setFullscreen(!evDialog.classList.contains("ev-dialog--fullscreen")));

$("ev-stage").addEventListener("wheel", e => {
  if (!viewer.data || viewer.data.kind !== "pdf_page" || !viewer.imgEl) return;
  e.preventDefault();
  const rect = $("ev-stage").getBoundingClientRect();
  const factor = e.ctrlKey ? Math.exp(-e.deltaY * 0.01) : (e.deltaY < 0 ? 1.15 : 1 / 1.15);
  zoomAt(viewer.zoom * factor, e.clientX - rect.left, e.clientY - rect.top);
}, { passive: false });

$("ev-stage").addEventListener("pointerdown", e => {
  if (!viewer.data || viewer.data.kind !== "pdf_page" || !viewer.imgEl) return;
  viewer.dragging = true;
  viewer.moved = false;
  viewer.startX = e.clientX;
  viewer.startY = e.clientY;
  viewer.origPanX = viewer.panX;
  viewer.origPanY = viewer.panY;
  $("ev-stage").classList.add("is-dragging");
  $("ev-stage").setPointerCapture(e.pointerId);
});
$("ev-stage").addEventListener("pointermove", e => {
  if (!viewer.dragging) return;
  const dx = e.clientX - viewer.startX;
  const dy = e.clientY - viewer.startY;
  if (Math.hypot(dx, dy) > 4) viewer.moved = true;
  viewer.panX = viewer.origPanX + dx;
  viewer.panY = viewer.origPanY + dy;
  applyImageTransform();
});
function endDrag(e) {
  if (!viewer.dragging) return;
  viewer.dragging = false;
  $("ev-stage").classList.remove("is-dragging");
  if ($("ev-stage").hasPointerCapture(e.pointerId)) $("ev-stage").releasePointerCapture(e.pointerId);
  if (!viewer.moved && e.type === "pointerup" && e.target === viewer.imgEl) {
    setFullscreen(!evDialog.classList.contains("ev-dialog--fullscreen"));
  }
}
$("ev-stage").addEventListener("pointerup", endDrag);
$("ev-stage").addEventListener("pointercancel", endDrag);
window.addEventListener("resize", () => {
  if (evDialog.open && viewer.data && viewer.data.kind === "pdf_page") fitPdfToStage();
});

(async () => {
  try {
    state.meta = await api("/api/meta");
    $("owner-clock").textContent = `${state.meta.business} · as of ${state.meta.as_of_display}`;
    const isRehearsal = state.meta.mode !== "live";
    $("rehearsal-banner").hidden = !isRehearsal;
    $("bts-mode").textContent = isRehearsal ? "Rehearsal (scripted, offline)" : "Live";
    $("bts-eval-date").textContent = state.meta.as_of;

    renderAttentionPanel(state.meta.attention);

    const select = $("config-select");
    select.replaceChildren();
    for (const c of state.meta.configs) {
      const opt = element("option", `${c.id} — ${c.name}`);
      opt.value = c.id;
      opt.selected = c.id === state.config;
      select.append(opt);
    }
    select.addEventListener("change", async () => {
      const chosen = select.value;
      await newConversation(chosen);
    });

    const sugWrap = $("suggestions");
    sugWrap.replaceChildren();
    for (const q of state.meta.questions) {
      const b = element("button", undefined, "suggestion");
      b.type = "button";
      b.append(element("strong", q.question));
      if (q.followup) b.append(element("span", `Then: "${q.followup}"`));
      b.addEventListener("click", () => fillQuestion(q.question));
      sugWrap.append(b);
    }

    await newConversation();
  } catch (e) {
    setError(e.message || "Start the local server and reload this page.");
  }
})();
