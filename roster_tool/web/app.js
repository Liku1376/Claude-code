"use strict";
// Roster Creator - single-page front end. All roster logic lives on the
// Python server; this file renders the pages and calls the JSON API.

const $ = (sel, root = document) => root.querySelector(sel);
const state = { meta: null, inputs: null, roster: null, published: null, publishedAt: "", analysis: null, page: 0 };

const SUMMARY = ["M", "E", "N", "CO", "L", "LL", "Primary", "Secondary"];
const ONCALL_LABEL = { primary: "Primary on-call", secondary: "Secondary on-call" };
const MONTHS = ["", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

// ---- helpers ---------------------------------------------------------------
function el(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") n.className = v;
    else if (k === "html") n.innerHTML = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) n.setAttribute(k, v);
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined) n.append(kid.nodeType ? kid : document.createTextNode(kid));
  return n;
}
function toast(msg) { $("#toast").textContent = msg; }
async function api(path, body) {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || ("Error " + r.status));
  return data;
}
async function apiGet(path) { const r = await fetch(path); if (!r.ok) throw new Error("Error " + r.status); return r.json(); }
async function downloadExport(fmt) {
  const r = await fetch("/api/export/" + fmt, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ inputs: state.inputs, roster: state.roster, shiftTimes: state.inputs.shift_times }),
  });
  if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.error || "Export failed"); }
  const blob = await r.blob();
  const name = (r.headers.get("Content-Disposition") || "").match(/filename="(.+?)"/);
  saveBlob(blob, name ? name[1] : "roster." + fmt);
}
function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = el("a", { href: url, download: filename });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function pickFile() {
  return new Promise((resolve) => {
    const inp = $("#filepick");
    inp.value = "";
    inp.onchange = () => {
      const f = inp.files[0]; if (!f) return resolve(null);
      const fr = new FileReader();
      fr.onload = () => { try { resolve(JSON.parse(fr.result)); } catch (e) { alert("That file is not valid JSON."); resolve(null); } };
      fr.readAsText(f);
    };
    inp.click();
  });
}
function engineers() { return state.inputs.engineers || []; }
function names(sme) { return engineers().filter(e => sme === undefined || !!truthy(e.sme) === sme).map(e => e.name); }
function truthy(v) { return v === true || v === "true" || v === 1 || v === "1" || v === "yes" || v === "Yes" || v === "sme"; }

// ---- pages -----------------------------------------------------------------
const PAGES = [
  { id: "team", nav: "Team", build: buildTeam },
  { id: "calendar", nav: "Calendar", build: buildCalendar },
  { id: "leave", nav: "Leave", build: buildLeave },
  { id: "longleave", nav: "Long Leave", build: buildLongLeave },
  { id: "req", nav: "Shift Requirements", build: buildReq },
  { id: "oncall", nav: "On-Call", build: buildOncall },
  { id: "rules", nav: "Rules", build: buildRules },
  { id: "roster", nav: "Roster", build: buildRoster },
];

function renderShell() {
  const steps = $("#steps");
  steps.innerHTML = "";
  PAGES.forEach((p, i) => {
    const badge = el("span", { class: "badge" });
    const step = el("div", { class: "step" + (i === state.page ? " active" : ""), onclick: () => goto(i) },
      el("span", { class: "num" }, String(i + 1)), el("span", { class: "name" }, p.nav), badge);
    step._badge = badge;
    steps.append(step);
  });
  updateBadges();
  renderPage();
}
function goto(i) { state.page = i; renderShell(); }
function renderPage() {
  const main = $("#main");
  main.innerHTML = "";
  PAGES[state.page].build(main);
  updateHeader();
}
function updateHeader() {
  const n = engineers().length, sme = engineers().filter(e => truthy(e.sme)).length;
  const m = state.inputs.month, y = state.inputs.year;
  $("#headerCtx").textContent = `${MONTHS[m] || ""} ${y || ""}   ·   ${n} engineers (${sme} SME)`;
}
function updateBadges() {
  const counts = { team: engineers().length, calendar: (state.inputs.holidays || []).length + (state.inputs.freeze_periods || []).length,
    leave: (state.inputs.leaves || []).length, longleave: (state.inputs.long_leaves || []).length,
    req: (state.inputs.requirements || []).length, oncall: (state.inputs.oncall || []).length };
  $("#steps").querySelectorAll(".step").forEach((s, i) => { const c = counts[PAGES[i].id]; s._badge.textContent = c ? c : ""; });
}

// ---- record editor ---------------------------------------------------------
// fields: [{key,label,type,options?}]  type: text|date|check|select
function recordEditor(container, opts) {
  const { title, hint, fields, listKey, noun } = opts;
  const rows = () => state.inputs[listKey] || (state.inputs[listKey] = []);
  let selected = -1;
  const inputs = {};

  const form = el("div", { class: "form-row" });
  for (const f of fields) {
    let control;
    if (f.type === "check") control = el("input", { type: "checkbox" });
    else if (f.type === "date") control = el("input", { type: "date" });
    else if (f.type === "select") { control = el("select"); refreshSelect(control, f); }
    else control = el("input", { type: "text", size: 16 });
    inputs[f.key] = control;
    form.append(el("label", { class: "field" }, el("span", {}, f.label), control));
  }
  const tableWrap = el("div");

  function refreshSelect(sel, f) {
    const cur = sel.value;
    sel.innerHTML = "";
    for (const o of (typeof f.options === "function" ? f.options() : f.options)) sel.append(el("option", { value: o }, o || "—"));
    if ([...sel.options].some(o => o.value === cur)) sel.value = cur;
  }
  function readForm() {
    const row = {};
    for (const f of fields) row[f.key] = f.type === "check" ? inputs[f.key].checked : inputs[f.key].value.trim();
    if (!row[fields[0].key]) { alert(fields[0].label + " is required."); return null; }
    return row;
  }
  function clearForm() { for (const f of fields) { if (f.type === "check") inputs[f.key].checked = false; else inputs[f.key].value = ""; } selected = -1; draw(); }
  function draw() {
    for (const f of fields) if (f.type === "select") refreshSelect(inputs[f.key], f);
    tableWrap.innerHTML = "";
    tableWrap.append(el("div", { class: "count-line" },
      el("span", {}, rows().length + " " + noun + (rows().length === 1 ? "" : "s")),
      el("span", { class: "r" }, "Click a row to edit it")));
    const tbl = el("table", { class: "records" });
    const head = el("tr");
    for (const f of fields) head.append(el("th", {}, f.label));
    tbl.append(el("thead", {}, head));
    const tb = el("tbody");
    rows().forEach((row, i) => {
      const tr = el("tr", { class: i === selected ? "sel" : "", onclick: () => { selected = i; for (const f of fields) { if (f.type === "check") inputs[f.key].checked = truthy(row[f.key]); else inputs[f.key].value = row[f.key] || ""; } draw(); } });
      for (const f of fields) tr.append(el("td", {}, f.type === "check" ? (truthy(row[f.key]) ? "✓ Yes" : "—") : (row[f.key] || "")));
      tb.append(tr);
    });
    tbl.append(tb);
    tableWrap.append(tbl);
    if (!rows().length) tableWrap.append(el("div", { class: "empty" }, "No " + noun + "s yet — fill in the form and press Add."));
  }
  function changed() { draw(); updateBadges(); updateHeader(); if (opts.onChange) opts.onChange(); }

  const card = el("div", { class: "card" }, el("h3", {}, title), hint ? el("div", { class: "hint" }, hint) : null, form,
    el("div", { class: "btns" },
      el("button", { class: "btn accent", onclick: () => { const r = readForm(); if (r) { rows().push(r); changed(); clearForm(); } } }, "＋ Add"),
      el("button", { class: "btn", onclick: () => { if (selected < 0) return alert("Select a row first."); const r = readForm(); if (r) { rows()[selected] = r; changed(); } } }, "Update"),
      el("button", { class: "btn danger", onclick: () => { if (selected < 0) return; rows().splice(selected, 1); selected = -1; changed(); } }, "Delete"),
      el("button", { class: "btn", onclick: clearForm }, "Clear")));
  container.append(card, tableWrap);
  draw();
}

function pageHeader(main, title, lead) {
  main.append(el("h2", {}, title), el("div", { class: "lead" }, lead));
}

function buildTeam(main) {
  pageHeader(main, "Team", "Who is on the roster. SMEs cover secondary on-call; everyone else covers primary on-call.");
  recordEditor(main, { title: "Add an engineer", listKey: "engineers", noun: "engineer",
    hint: "Tick SME for subject-matter experts (eligible for secondary on-call).",
    fields: [{ key: "name", label: "Name", type: "text" }, { key: "designation", label: "Designation", type: "select", options: () => ["", ...state.meta.designations] }, { key: "sme", label: "SME", type: "check" }] });
}
function buildCalendar(main) {
  pageHeader(main, "Month & Calendar", "Pick the roster month and mark weekends, holidays and freeze periods.");
  const monthSel = el("select"); MONTHS.slice(1).forEach((m, i) => monthSel.append(el("option", { value: i + 1 }, m)));
  monthSel.value = state.inputs.month; monthSel.onchange = () => { state.inputs.month = +monthSel.value; updateHeader(); };
  const yearInp = el("input", { type: "number", min: 2000, max: 2100, value: state.inputs.year, style: "width:80px" });
  yearInp.onchange = () => { state.inputs.year = +yearInp.value; updateHeader(); };
  const wd = el("div", { class: "form-row" });
  state.meta.weekdays.forEach((name, i) => {
    const cb = el("input", { type: "checkbox" }); cb.checked = (state.inputs.weekend_days || []).includes(i);
    cb.onchange = () => { const s = new Set(state.inputs.weekend_days || []); cb.checked ? s.add(i) : s.delete(i); state.inputs.weekend_days = [...s].sort(); };
    wd.append(el("label", { class: "field", style: "margin-right:10px" }, el("span", {}, name), cb));
  });
  main.append(el("div", { class: "card" }, el("h3", {}, "Roster month"),
    el("div", { class: "form-row" },
      el("label", { class: "field" }, el("span", {}, "Month"), monthSel),
      el("label", { class: "field" }, el("span", {}, "Year"), yearInp),
      el("label", { class: "field" }, el("span", {}, "Weekend days"), wd))));
  const grid = el("div", { class: "grid2" });
  main.append(grid);
  const left = el("div"), right = el("div"); grid.append(left, right);
  recordEditor(left, { title: "Holiday", listKey: "holidays", noun: "holiday",
    fields: [{ key: "date", label: "Date", type: "date" }, { key: "name", label: "Name", type: "text" }] });
  recordEditor(right, { title: "Freeze period", listKey: "freeze_periods", noun: "freeze period",
    hint: "Freeze days are exempt from the minimum Morning/Night rule.",
    fields: [{ key: "start", label: "Start", type: "date" }, { key: "end", label: "End", type: "date" }, { key: "note", label: "Note", type: "text" }] });
}
const leaveFields = () => [{ key: "engineer", label: "Engineer", type: "select", options: () => ["", ...names()] },
  { key: "start", label: "Start", type: "date" }, { key: "end", label: "End (optional)", type: "date" }, { key: "note", label: "Note", type: "text" }];
function buildLeave(main) { pageHeader(main, "Leave", "Planned days off. Leave the end empty for a single day. Shown as L."); recordEditor(main, { title: "Add leave", listKey: "leaves", noun: "leave request", fields: leaveFields() }); }
function buildLongLeave(main) { pageHeader(main, "Long Leave", "Extended absences such as vacations. Shown as LL."); recordEditor(main, { title: "Add long leave", listKey: "long_leaves", noun: "long leave", fields: leaveFields() }); }
function buildReq(main) {
  pageHeader(main, "Shift Requirements", "Pin an engineer to a shift, give them a preferred shift, or keep them off one.");
  recordEditor(main, { title: "Add a shift requirement", listKey: "requirements", noun: "requirement",
    hint: "Must = always this shift.  Prefer = this shift when the rules allow.  Avoid = never this shift.",
    fields: [{ key: "engineer", label: "Engineer", type: "select", options: () => ["", ...names()] },
      { key: "shift", label: "Shift", type: "select", options: () => state.meta.shifts.map(s => s.name) },
      { key: "start", label: "Start", type: "date" }, { key: "end", label: "End (optional)", type: "date" },
      { key: "mode", label: "Type", type: "select", options: ["Must", "Prefer", "Avoid"] }, { key: "note", label: "Note", type: "text" }] });
}
function buildOncall(main) {
  pageHeader(main, "On-Call", "Optionally fix who is on call for specific days. Other days are rotated automatically.");
  recordEditor(main, { title: "Set on-call for a day", listKey: "oncall", noun: "on-call override",
    hint: "Secondary on-call is not required on weekends and holidays.",
    fields: [{ key: "date", label: "Date", type: "date" }, { key: "primary", label: "Primary (non-SME)", type: "select", options: () => ["", ...names(false)] },
      { key: "secondary", label: "Secondary (SME)", type: "select", options: () => ["", ...names(true)] }] });
}
function buildRules(main) {
  pageHeader(main, "Rules", "Coverage minimums, shift timings, carry-over and generator settings.");
  const grid = el("div", { class: "grid2" }); main.append(grid);
  // minimums
  const minCard = el("div", { class: "card" }, el("h3", {}, "Minimum engineers per shift"), el("div", { class: "hint" }, "Default: at least 1 on Morning and Night on working days only."));
  const mt = el("table", { class: "mins" });
  const hr = el("tr"); hr.append(el("th", {}, "Day type")); state.meta.shifts.forEach(s => hr.append(el("th", {}, s.name))); mt.append(hr);
  state.meta.dayTypes.forEach(dt => {
    const tr = el("tr"); tr.append(el("td", {}, dt));
    state.meta.shifts.forEach(s => {
      const v = ((state.inputs.min_coverage || {})[dt] || {})[s.name] ?? 0;
      const inp = el("input", { type: "number", min: 0, max: 20, value: v });
      inp.onchange = () => { state.inputs.min_coverage[dt] = state.inputs.min_coverage[dt] || {}; state.inputs.min_coverage[dt][s.name] = +inp.value; };
      tr.append(el("td", {}, inp));
    });
    mt.append(tr);
  });
  minCard.append(mt); grid.append(minCard);
  // generator
  const attempts = el("input", { type: "number", min: 1, max: 5000, value: state.inputs.attempts, style: "width:90px" });
  attempts.onchange = () => state.inputs.attempts = +attempts.value;
  const seed = el("input", { type: "text", value: state.inputs.seed || "", style: "width:90px" });
  seed.onchange = () => state.inputs.seed = seed.value.trim();
  grid.append(el("div", { class: "card" }, el("h3", {}, "Generator"), el("div", { class: "hint" }, "More attempts give a fairer roster but take longer."),
    el("div", { class: "form-row" }, el("label", { class: "field" }, el("span", {}, "Attempts"), attempts), el("label", { class: "field" }, el("span", {}, "Random seed (optional)"), seed))));
  // shift timings + carry over
  const grid2 = el("div", { class: "grid2" }); main.append(grid2);
  const tt = el("table", { class: "mins" });
  tt.append(el("tr", {}, el("th", {}, "Shift"), el("th", {}, "Start"), el("th", {}, "End")));
  state.meta.shifts.forEach(s => {
    const t = (state.inputs.shift_times || {})[s.name] || { start: "", end: "" };
    const a = el("input", { type: "time", value: t.start }), b = el("input", { type: "time", value: t.end });
    a.onchange = () => { state.inputs.shift_times[s.name] = state.inputs.shift_times[s.name] || {}; state.inputs.shift_times[s.name].start = a.value; };
    b.onchange = () => { state.inputs.shift_times[s.name] = state.inputs.shift_times[s.name] || {}; state.inputs.shift_times[s.name].end = b.value; };
    tt.append(el("tr", {}, el("td", {}, s.name), el("td", {}, a), el("td", {}, b)));
  });
  grid2.append(el("div", { class: "card" }, el("h3", {}, "Shift timings"), el("div", { class: "hint" }, "Used for calendar invites (.ics). A night ending earlier than it starts ends next morning."), tt));
  const carry = el("div", { class: "card" }, el("h3", {}, "Carry-over from previous month"), el("div", { class: "hint" }, "Keeps comp offs and fairness going from one month to the next."));
  const co = state.inputs.carry_over || {};
  carry.append(el("div", {}, co.source ? `Imported from ${co.source}. Pending comp offs: ${(co.nights || []).map(n => n.engineer + " (" + n.date + ")").join(", ") || "none"}.` : "Nothing imported."));
  carry.append(el("div", { class: "btns" },
    el("button", { class: "btn accent", onclick: importPrevious }, "Import previous month's roster…"),
    el("button", { class: "btn", onclick: () => { state.inputs.carry_over = {}; renderPage(); } }, "Clear")));
  grid2.append(carry);
  // rules list
  const rules = el("div", { class: "card" }, el("h3", {}, "Mandatory rules applied"));
  [["Coverage", "At least 1 engineer on Morning and Night on working days (freeze, weekends and holidays excluded)."],
   ["Comp off", "Every night shift earns a comp off (CO) on the next working day — never on a weekend or holiday."],
   ["Primary on-call", "Every day — a non-SME engineer not on Morning or Night that day."],
   ["Secondary on-call", "An SME engineer — not required on weekends and holidays."],
   ["Requests", "Leave, long leave and shift requirements are honoured; anything unmet is reported."]].forEach(([h, t]) =>
    rules.append(el("div", { style: "margin:4px 0" }, el("strong", {}, "✓ " + h + "  "), el("span", { style: "color:var(--muted)" }, t))));
  main.append(rules);
}

// ---- roster page -----------------------------------------------------------
function buildRoster(main) {
  pageHeader(main, "Roster", "Click a cell to change, lock or swap it. Locked cells stay put when you regenerate.");
  const bar = el("div", { class: "toolbar" },
    el("button", { class: "btn accent big", onclick: generate }, "Generate roster ▶"),
    el("button", { class: "btn", onclick: () => openSwap() }, "⇄ Swap shifts…"),
    el("button", { class: "btn", onclick: markPublished }, "✓ Mark as published"),
    el("button", { class: "btn", onclick: clearLocks }, "Clear locks"),
    el("span", { class: "spacer" }),
    el("button", { class: "btn", onclick: save }, "Save roster"),
    el("button", { class: "btn", onclick: () => exportFmt("xlsx") }, "Excel"),
    el("button", { class: "btn", onclick: () => exportFmt("csv") }, "CSV"),
    el("button", { class: "btn", onclick: () => exportFmt("ics") }, "Calendar (.ics)"));
  main.append(bar);
  if (!state.roster) { main.append(el("div", { class: "card", style: "text-align:center;color:var(--muted);padding:40px" }, "No roster yet. Press ", el("strong", {}, "Generate roster"), " to build one.")); return; }
  main.append(buildTiles());
  main.append(buildLegend());
  main.append(el("div", { class: "grid-wrap" }, buildGrid()));
  main.append(buildBottom());
}
function codeMeta(code) { return state.meta.codes.find(c => c.code === code); }
function buildTiles() {
  const a = state.analysis, r = state.roster;
  const nights = names().map(n => r.counts[n].N || 0);
  const totalsN = names().map(n => (r.totals[n] || {}).N || 0);
  const nsub = state.inputs.carry_over && state.inputs.carry_over.source ? `incl. previous: ${Math.min(...totalsN)}–${Math.max(...totalsN)}` : `avg ${(nights.reduce((x, y) => x + y, 0) / (nights.length || 1)).toFixed(1)}`;
  const locks = r.locks.cells.length + Object.keys(r.locks.primary).length + Object.keys(r.locks.secondary).length;
  const tile = (cap, val, sub, cls) => el("div", { class: "tile" }, el("div", { class: "cap" }, cap), el("div", { class: "val", style: cls || "" }, val), el("div", { class: "sub" }, sub));
  return el("div", { class: "tiles" },
    a.errors === 0 ? tile("Status", "✓ Rules met", "ready to share", "color:var(--success)") : tile("Status", "✗ Fix rules", "see checks", "color:var(--danger)"),
    tile("Rule violations", a.errors, "mandatory rules", a.errors ? "color:var(--danger)" : ""),
    tile("Warnings", a.warnings, "requests not met", a.warnings ? "color:var(--warning)" : ""),
    tile("Nights / person", nights.length ? `${Math.min(...nights)}–${Math.max(...nights)}` : "—", nsub),
    tile("Preferences met", a.preferences.requested ? `${a.preferences.met}/${a.preferences.requested}` : "—", a.preferences.requested ? "preferred shifts" : "none set"),
    state.published ? tile("Changes", a.changes.length, `since published · ${locks} locked`, a.changes.length ? "color:var(--changed)" : "") : tile("Changes", "—", `not published · ${locks} locked`));
}
function buildLegend() {
  const lg = el("div", { class: "legend" });
  state.meta.codes.forEach(c => { lg.append(el("span", { class: "chip", style: `background:#${c.color};color:#${c.text}` }, c.code)); lg.append(el("span", {}, c.description.split(" (")[0])); });
  lg.append(el("span", { class: "dot", style: "background:var(--primary)" }), el("span", {}, "Primary"));
  lg.append(el("span", { class: "dot", style: "background:var(--teal)" }), el("span", {}, "Secondary"));
  lg.append(el("span", { class: "mk" }), el("span", {}, "Changed"));
  lg.append(el("span", {}, "🔒 Locked"));
  return lg;
}
function dayInfo(iso) { return state.analysis.days.find(d => d.iso === iso); }
function buildGrid() {
  const r = state.roster, a = state.analysis;
  const errDays = new Set(a.errorDays);
  const changed = new Set(a.changes.map(c => c.who + "|" + c.date));
  const smeSet = new Set(names(true));
  const tbl = el("table", { class: "roster" });
  // header
  const thead = el("thead"), hr = el("tr");
  hr.append(el("th", { class: "rowhead" }, MONTHS[r.month] + " " + r.year));
  a.days.forEach(d => {
    const th = el("th", { class: "col-" + d.type },
      el("div", { class: "wd" }, d.weekday.toUpperCase()), el("div", { class: "daynum" }, d.day),
      errDays.has(d.iso) ? el("div", { class: "errdot" }) : null);
    hr.append(th);
  });
  SUMMARY.forEach(s => hr.append(el("th", {}, ({ Primary: "PRI", Secondary: "SEC" })[s] || s)));
  thead.append(hr); tbl.append(thead);
  // engineer rows
  const tb = el("tbody");
  engineers().forEach(e => {
    const tr = el("tr");
    tr.append(el("td", { class: "rowhead" }, el("strong", {}, e.name), truthy(e.sme) ? el("span", { class: "sme-tag" }, "SME") : null, e.designation ? el("span", { class: "desig" }, e.designation) : null));
    a.days.forEach(d => {
      const code = (r.grid[e.name] || {})[d.iso] || "";
      const cm = codeMeta(code);
      const locked = r.locks.cells.some(c => c.engineer === e.name && c.date === d.iso);
      const td = el("td", { class: "cell col-" + d.type + (changed.has(e.name + "|" + d.iso) ? " changed" : "") });
      const pill = el("div", { class: "pill", style: cm ? `background:#${cm.color};color:#${cm.text}` : "background:#fff", onclick: (ev) => cellMenu(ev, e.name, d.iso) }, code);
      if (locked) pill.append(el("span", { class: "lock" }, "🔒"));
      if (r.primary[d.iso] === e.name) pill.append(el("span", { class: "oncall-dot p" }));
      if (r.secondary[d.iso] === e.name) pill.append(el("span", { class: "oncall-dot s" }));
      td.append(pill); tr.append(td);
    });
    SUMMARY.forEach(s => tr.append(el("td", { class: "sumcol" }, String(r.counts[e.name][s] || 0))));
    tb.append(tr);
  });
  // on-call rows
  ["primary", "secondary"].forEach(kind => {
    const tr = el("tr", { class: "oncall-row" });
    tr.append(el("td", { class: "rowhead" }, ONCALL_LABEL[kind]));
    const table = kind === "primary" ? r.primary : r.secondary;
    const locks = kind === "primary" ? r.locks.primary : r.locks.secondary;
    a.days.forEach(d => {
      const who = table[d.iso] || "";
      const td = el("td", { class: "cell oncall col-" + d.type + (kind === "secondary" ? " sec" : "") + (changed.has(ONCALL_LABEL[kind] + "|" + d.iso) ? " changed" : "") });
      const pill = el("div", { class: "pill", onclick: (ev) => oncallMenu(ev, kind, d.iso) }, who ? who.slice(0, 5) : "·");
      if (d.iso in locks) pill.append(el("span", { class: "lock" }, "🔒"));
      td.append(pill); tr.append(td);
    });
    SUMMARY.forEach(() => tr.append(el("td", {})));
    tb.append(tr);
  });
  tbl.append(tb);
  return tbl;
}
function buildBottom() {
  const wrap = el("div", { class: "bottom" });
  const tabs = el("div", { class: "tabs" });
  const t1 = el("div", { class: "tab active", onclick: () => switchTab(0) }, "Checks");
  const nch = state.analysis.changes.length;
  const t2 = el("div", { class: "tab", onclick: () => switchTab(1) }, "Changes since published" + (nch ? ` (${nch})` : ""));
  tabs.append(t1, t2);
  const p1 = el("div", { class: "tabpanel active" }), p2 = el("div", { class: "tabpanel" });
  // checks
  const it = el("table", { class: "issues" });
  if (state.analysis.errors === 0) it.append(el("tr", { class: "ok" }, el("td", { class: "sev" }, "✓ OK"), el("td", { class: "dt" }, ""), el("td", {}, "All mandatory rules are satisfied")));
  state.analysis.issues.forEach(i => it.append(el("tr", { class: i.severity }, el("td", { class: "sev" }, i.severity), el("td", { class: "dt" }, i.date ? fmtDate(i.date) : ""), el("td", {}, i.message))));
  p1.append(it);
  // changes
  const pub = el("div", { class: "pubbar" },
    el("span", {}, state.published ? `Published ${state.publishedAt}. ${nch} change(s) since then.` : "Not published yet. Click 'Mark as published' to start tracking changes."),
    el("button", { class: "btn", onclick: copyChanges }, "Copy list"));
  p2.append(pub);
  const ct = el("table", { class: "issues" });
  ct.append(el("tr", {}, el("th", {}, "Date"), el("th", {}, "Who"), el("th", {}, "Before"), el("th", {}, "After")));
  state.analysis.changes.forEach(c => ct.append(el("tr", { class: "Warning" }, el("td", { class: "dt" }, fmtDate(c.date)), el("td", {}, c.who), el("td", {}, c.old || "-"), el("td", {}, c.new || "-"))));
  p2.append(ct);
  wrap._panels = [p1, p2]; wrap._tabs = [t1, t2];
  wrap.append(tabs, p1, p2);
  wrap.switchTab = switchTab;
  window._bottom = wrap;
  return wrap;
  function switchTab(i) { wrap._tabs.forEach((t, k) => t.classList.toggle("active", k === i)); wrap._panels.forEach((p, k) => p.classList.toggle("active", k === i)); }
}
function switchTab(i) { if (window._bottom) window._bottom.switchTab(i); }
function fmtDate(iso) { const d = new Date(iso + "T00:00:00"); return d.toLocaleDateString(undefined, { weekday: "short", day: "2-digit", month: "short" }); }

// ---- cell menus & edits ----------------------------------------------------
function showMenu(ev, items) {
  ev.stopPropagation();
  closeMenu();
  const menu = el("div", { class: "menu" });
  items.forEach(it => {
    if (it.sep) { menu.append(el("div", { class: "sep" })); return; }
    const row = el("div", { class: "item" + (it.disabled ? " disabled" : "") + (it.sub ? " sub" : "") }, it.label);
    if (it.sub) row.onmouseenter = (e) => openSub(e, row, it.sub);
    else if (!it.disabled) row.onclick = () => { closeMenu(); it.onClick(); };
    menu.append(row);
  });
  document.body.append(menu);
  const x = Math.min(ev.clientX, window.innerWidth - menu.offsetWidth - 8);
  const y = Math.min(ev.clientY, window.innerHeight - menu.offsetHeight - 8);
  menu.style.left = x + "px"; menu.style.top = y + "px";
  window._menu = menu;
  setTimeout(() => document.addEventListener("click", closeMenu, { once: true }), 0);
}
function openSub(ev, row, items) {
  document.querySelectorAll(".menu.sub-open").forEach(m => m.remove());
  const menu = el("div", { class: "menu sub-open" });
  items.forEach(it => { const r = el("div", { class: "item" }, it.label); r.onclick = () => { closeMenu(); it.onClick(); }; menu.append(r); });
  document.body.append(menu);
  const rect = row.getBoundingClientRect();
  menu.style.left = Math.min(rect.right, window.innerWidth - menu.offsetWidth - 8) + "px";
  menu.style.top = Math.min(rect.top, window.innerHeight - menu.offsetHeight - 8) + "px";
}
function closeMenu() { document.querySelectorAll(".menu").forEach(m => m.remove()); window._menu = null; }

function cellMenu(ev, name, iso) {
  const r = state.roster;
  const locked = r.locks.cells.some(c => c.engineer === name && c.date === iso);
  const items = [{ label: `${name} · ${fmtDate(iso)}`, disabled: true }];
  state.meta.codes.forEach(c => items.push({ label: `${c.code}  ${c.description}`, onClick: () => setCell(name, iso, c.code) }));
  items.push({ sep: true });
  items.push({ label: "Swap with…", sub: engineers().filter(e => e.name !== name).map(e => ({ label: `${e.name} (${(r.grid[e.name] || {})[iso] || "-"})`, onClick: () => openSwap(name, e.name, iso) })) });
  items.push(locked ? { label: "Unlock", onClick: () => lockCell(name, iso, false) } : { label: "Lock (keep when regenerating)", onClick: () => lockCell(name, iso, true) });
  showMenu(ev, items);
}
function oncallMenu(ev, kind, iso) {
  const r = state.roster, wantSme = kind === "secondary";
  const locks = kind === "primary" ? r.locks.primary : r.locks.secondary;
  const items = [{ label: `${ONCALL_LABEL[kind]} · ${fmtDate(iso)}`, disabled: true },
    { label: "(none)", onClick: () => setOncall(kind, iso, "") }];
  engineers().filter(e => truthy(e.sme) === wantSme).forEach(e => items.push({ label: e.name, onClick: () => setOncall(kind, iso, e.name) }));
  items.push({ sep: true });
  items.push(iso in locks ? { label: "Unlock", onClick: () => lockOncall(kind, iso, false) } : { label: "Lock", onClick: () => lockOncall(kind, iso, true) });
  showMenu(ev, items);
}
function setCell(name, iso, code) {
  state.roster.grid[name] = state.roster.grid[name] || {}; state.roster.grid[name][iso] = code;
  setLockCell(name, iso, code); // hand edits are kept on regenerate
  revalidate();
}
function lockCell(name, iso, on) { if (on) setLockCell(name, iso, (state.roster.grid[name] || {})[iso] || ""); else removeLockCell(name, iso); revalidate(); }
function setLockCell(name, iso, code) { const cells = state.roster.locks.cells; const ex = cells.find(c => c.engineer === name && c.date === iso); if (ex) ex.code = code; else cells.push({ engineer: name, date: iso, code }); }
function removeLockCell(name, iso) { state.roster.locks.cells = state.roster.locks.cells.filter(c => !(c.engineer === name && c.date === iso)); }
function setOncall(kind, iso, name) { const t = kind === "primary" ? state.roster.primary : state.roster.secondary; if (name) t[iso] = name; else delete t[iso]; (kind === "primary" ? state.roster.locks.primary : state.roster.locks.secondary)[iso] = name; revalidate(); }
function lockOncall(kind, iso, on) { const locks = kind === "primary" ? state.roster.locks.primary : state.roster.locks.secondary; const t = kind === "primary" ? state.roster.primary : state.roster.secondary; if (on) locks[iso] = t[iso] || ""; else delete locks[iso]; revalidate(); }

async function revalidate() {
  try {
    const res = await api("/api/validate", { inputs: state.inputs, roster: state.roster, baseline: sameMonthPublished() });
    state.roster = res.roster; state.analysis = res.analysis; renderPage();
  } catch (e) { alert(e.message); }
}
function sameMonthPublished() {
  if (!state.published || !state.roster) return null;
  return state.published.year === state.roster.year && state.published.month === state.roster.month ? state.published : null;
}

// ---- generate / publish / locks --------------------------------------------
async function generate() {
  if (!engineers().length) { alert("Add at least one engineer on the Team page first."); goto(0); return; }
  toast("Checking staffing…");
  let locks = state.roster && state.roster.year === state.inputs.year && state.roster.month === state.inputs.month ? state.roster.locks : null;
  try {
    const pre = await api("/api/precheck", { inputs: state.inputs, locks });
    if (pre.issues.length) {
      const lines = pre.issues.slice(0, 8).map(i => "• " + (i.date ? fmtDate(i.date) + ": " : "") + i.message).join("\n");
      const more = pre.issues.length > 8 ? `\n…and ${pre.issues.length - 8} more` : "";
      if (!confirm("Not enough people on some days:\n\n" + lines + more + "\n\nGenerate anyway?")) { toast("Cancelled"); return; }
    }
    toast("Generating…");
    const baseline = sameMonthPublished();
    const res = await api("/api/generate", { inputs: state.inputs, locks, baseline });
    state.roster = res.roster; state.analysis = res.analysis;
    if (state.published && (state.published.year !== state.roster.year || state.published.month !== state.roster.month)) { state.published = null; state.publishedAt = ""; }
    goto(PAGES.length - 1);
    toast(locks ? `Regenerated — kept locked cells, ${state.analysis.changes.length} change(s) from published` : "Roster ready");
  } catch (e) { alert(e.message); toast("Error"); }
}
function markPublished() {
  if (!state.roster) return;
  state.published = JSON.parse(JSON.stringify(state.roster));
  state.publishedAt = new Date().toLocaleString();
  revalidate(); toast("Marked as published — later changes will be highlighted");
}
function clearLocks() {
  if (!state.roster) return;
  const n = state.roster.locks.cells.length + Object.keys(state.roster.locks.primary).length + Object.keys(state.roster.locks.secondary).length;
  if (n && confirm(`Unlock all ${n} locked cell(s)? The roster itself is not changed.`)) { state.roster.locks = { cells: [], primary: {}, secondary: {} }; revalidate(); }
}
function copyChanges() {
  if (!state.analysis.changes.length) { alert("No changes since the roster was published."); return; }
  const text = "Roster changes since " + (state.publishedAt || "publishing") + ":\n" +
    state.analysis.changes.map(c => `- ${fmtDate(c.date)}  ${c.who}: ${c.old || "-"} -> ${c.new || "-"}`).join("\n");
  navigator.clipboard.writeText(text).then(() => toast(`Copied ${state.analysis.changes.length} change(s)`), () => alert(text));
}

// ---- swap modal ------------------------------------------------------------
function openSwap(a = "", b = "", iso = "") {
  if (!state.roster) { alert("Generate a roster first."); return; }
  const nm = names();
  const aSel = el("select"), bSel = el("select");
  [aSel, bSel].forEach(s => nm.forEach(n => s.append(el("option", { value: n }, n))));
  aSel.value = a || nm[0]; bSel.value = b || nm[1] || nm[0];
  const dInp = el("input", { type: "date", value: iso || state.analysis.days[0].iso });
  const preview = el("div", { class: "preview" }), check = el("div", { class: "checkline" });
  const okBtn = el("button", { class: "btn accent", onclick: apply }, "Swap");
  let result = null;
  async function refresh() {
    result = null; okBtn.disabled = true;
    if (aSel.value === bSel.value) { preview.textContent = "Pick two different engineers."; check.textContent = ""; return; }
    try {
      const res = await api("/api/swap", { inputs: state.inputs, roster: state.roster, a: aSel.value, b: bSel.value, day: dInp.value });
      result = res.roster;
      let last = null; const lines = [];
      res.preview.forEach(c => { if (c.date !== last) { lines.push(fmtDate(c.date) + (last ? "   (comp off moves with the night)" : "")); last = c.date; } lines.push(`   ${c.who}:  ${c.old || "-"}  →  ${c.new || "-"}`); });
      preview.textContent = lines.join("\n") || "Nothing changes.";
      if (res.newErrors.length) { check.style.color = "var(--danger)"; check.textContent = "This swap would break: " + res.newErrors.join("; "); okBtn.textContent = "Swap anyway"; }
      else { check.style.color = "var(--success)"; check.textContent = "✓ No new rule problems."; okBtn.textContent = "Swap"; }
      okBtn.disabled = false;
    } catch (e) { preview.textContent = e.message; }
  }
  function apply() { if (result) { state.roster = result; overlay.remove(); revalidate(); toast(`Swapped ${aSel.value} and ${bSel.value}`); } }
  [aSel, bSel, dInp].forEach(x => x.onchange = refresh);
  const modal = el("div", { class: "modal" },
    el("h3", {}, "Swap shifts"), el("div", { class: "sub" }, "The two engineers exchange their shift and on-call duty. A swapped night takes its comp off along. Swapped cells are locked."),
    el("div", { class: "form-row" }, el("label", { class: "field" }, el("span", {}, "Engineer"), aSel), el("label", { class: "field" }, el("span", {}, "Swaps with"), bSel), el("label", { class: "field" }, el("span", {}, "Date"), dInp)),
    el("div", { style: "margin-top:12px" }, preview), check,
    el("div", { class: "actions" }, el("button", { class: "btn", onclick: () => overlay.remove() }, "Cancel"), okBtn));
  const overlay = el("div", { class: "overlay", onclick: (e) => { if (e.target === overlay) overlay.remove(); } }, modal);
  document.body.append(overlay);
  refresh();
}

// ---- file operations -------------------------------------------------------
async function exportFmt(fmt) { try { toast("Exporting…"); await downloadExport(fmt); toast("Exported " + fmt.toUpperCase()); } catch (e) { alert(e.message); } }
async function save() {
  try {
    const res = await api("/api/save", { inputs: state.inputs, roster: state.roster, published: sameMonthPublished(), publishedAt: state.publishedAt });
    saveBlob(new Blob([JSON.stringify(res.file, null, 2)], { type: "application/json" }), `roster_${state.inputs.year}_${String(state.inputs.month).padStart(2, "0")}.json`);
    toast("Roster file downloaded");
  } catch (e) { alert(e.message); }
}
async function openAny() {
  const data = await pickFile(); if (!data) return;
  try {
    if (data.format === "roster-creator/roster") {
      const res = await api("/api/open", { file: data });
      state.inputs = res.inputs; state.roster = res.roster; state.published = res.published; state.publishedAt = res.publishedAt || "";
      state.analysis = (await api("/api/validate", { inputs: state.inputs, roster: state.roster, baseline: state.published })).analysis;
      state.page = PAGES.length - 1;
    } else { state.inputs = normaliseInputs(data); state.roster = null; state.published = null; state.page = 0; }
    renderShell(); toast("Opened file");
  } catch (e) { alert(e.message); }
}
async function importPrevious() {
  const data = await pickFile(); if (!data) return;
  if (data.format !== "roster-creator/roster") { alert("Pick a roster file saved with 'Save roster'."); return; }
  try {
    const res = await api("/api/carry-over", { file: data });
    if ((state.inputs.year !== res.nextYear || state.inputs.month !== res.nextMonth) &&
        confirm(`That roster is for ${MONTHS[data.inputs.month]} ${data.inputs.year}. Set this roster's month to ${MONTHS[res.nextMonth]} ${res.nextYear}?`)) {
      state.inputs.year = res.nextYear; state.inputs.month = res.nextMonth;
    }
    if (!engineers().length && confirm("Your team is empty. Copy the team, weekend days, rules and shift timings from that roster?")) {
      ["engineers", "weekend_days", "min_coverage", "shift_times", "attempts"].forEach(k => { if (res.prevInputs[k] !== undefined) state.inputs[k] = JSON.parse(JSON.stringify(res.prevInputs[k])); });
    }
    state.inputs.carry_over = res.carryOver;
    renderShell(); toast("Imported carry-over from " + res.carryOver.source);
  } catch (e) { alert(e.message); }
}
function normaliseInputs(data) { const base = JSON.parse(JSON.stringify(state.meta.empty)); return Object.assign(base, data); }

// ---- boot ------------------------------------------------------------------
async function loadSample() { const res = await apiGet("/api/sample"); state.inputs = normaliseInputs(res.inputs); state.roster = null; state.published = null; state.page = 0; renderShell(); toast("Loaded sample data"); }
function newConfig() { if (confirm("Clear all inputs and the current roster?")) { state.inputs = normaliseInputs({}); state.roster = null; state.published = null; state.page = 0; renderShell(); } }

async function boot() {
  state.meta = await apiGet("/api/meta");
  state.inputs = normaliseInputs({});
  $("#genTop").onclick = generate;
  $("#mOpen").onclick = openAny;
  $("#mSave").onclick = () => state.roster ? save() : alert("Generate a roster first.");
  $("#mSample").onclick = loadSample;
  $("#mNew").onclick = newConfig;
  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey && e.key === "g") { e.preventDefault(); generate(); }
    if (e.ctrlKey && e.key === "s") { e.preventDefault(); if (state.roster) save(); }
    if (e.ctrlKey && e.key === "o") { e.preventDefault(); openAny(); }
    if (e.key === "Escape") { closeMenu(); document.querySelectorAll(".overlay").forEach(o => o.remove()); }
  });
  renderShell();
  toast("Ready — add your team, or use File → Load sample.");
}
boot();
