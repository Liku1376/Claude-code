"use strict";
// Zodiac Studio front end: collects birth details, calls the JSON API and
// renders the results. No frameworks — plain DOM.

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const SIGN_GLYPHS = ["♈", "♉", "♊", "♋", "♌", "♍", "♎", "♏", "♐", "♑", "♒", "♓"];
const ELEMENT_COLORS = ["var(--fire)", "var(--earth)", "var(--air)", "var(--water)"];
let META = { cities: [], signs: [] };
let lastChart = null;

// ---------------------------------------------------------------- helpers
function toast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => t.classList.add("hidden"), 5000);
}

async function api(path, body) {
  const res = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Request failed");
  return data;
}

async function run(outId, fn) {
  const out = $(outId);
  out.innerHTML = '<p class="loading">Calculating…</p>';
  try {
    out.innerHTML = await fn();
  } catch (err) {
    out.innerHTML = "";
    toast(err.message);
  }
}

const today = () => {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
};
function shiftDate(iso, days, months = 0, years = 0) {
  const d = new Date(iso + "T12:00:00");
  d.setFullYear(d.getFullYear() + years, d.getMonth() + months, d.getDate() + days);
  return d.toISOString().slice(0, 10);
}
function browserTz() {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || ""; } catch (e) { return ""; }
}
const stars = (n) => `<span class="stars">${"★".repeat(n)}<span class="off">${"★".repeat(5 - n)}</span></span>`;
const ord = (n) => n + (n % 100 >= 11 && n % 100 <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th"));
const pill = (status) => `<span class="pill ${esc(status)}">${esc(status === "current" ? "now" : status)}</span>`;
const fmtDate = (iso) => new Date(iso.slice(0, 10) + "T12:00:00").toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });

// ---------------------------------------------------------------- profile
const FIELDS = ["name", "date", "time", "city", "lat", "lon", "tz"];
function saveProfile() {
  const data = {};
  for (const f of FIELDS) { data["p-" + f] = $("p-" + f).value; data["q-" + f] = $("q-" + f).value; }
  data["p-unknown"] = $("p-unknown").checked;
  try { localStorage.setItem("zodiac-profile", JSON.stringify(data)); } catch (e) { /* storage unavailable */ }
}
function loadProfile() {
  let data = {};
  try { data = JSON.parse(localStorage.getItem("zodiac-profile") || "{}"); } catch (e) { data = {}; }
  for (const [k, v] of Object.entries(data)) {
    const el = $(k);
    if (!el) continue;
    if (el.type === "checkbox") el.checked = !!v; else el.value = v;
  }
  if (!$("p-tz").value) $("p-tz").value = browserTz();
}
function bindCity(prefix) {
  $(prefix + "-city").addEventListener("change", () => {
    const c = META.cities.find((x) => x.name === $(prefix + "-city").value);
    if (c) {
      $(prefix + "-lat").value = c.lat;
      $(prefix + "-lon").value = c.lon;
      $(prefix + "-tz").value = c.tz;
      saveProfile();
    }
  });
}
function person(prefix = "p") {
  const date = $(prefix + "-date").value;
  if (!date) throw new Error(prefix === "p" ? "Please enter your date of birth." : "Please enter the partner's date of birth.");
  const unknown = prefix === "p" && $("p-unknown").checked;
  return {
    name: $(prefix + "-name").value,
    date,
    time: unknown ? "12:00" : ($(prefix + "-time").value || "12:00"),
    time_known: !unknown,
    lat: $(prefix + "-lat").value || 0,
    lon: $(prefix + "-lon").value || 0,
    tz: $(prefix + "-tz").value || browserTz() || "UTC",
  };
}

// ---------------------------------------------------------------- chart wheel
function wheelSvg(chart) {
  const S = 520, c = S / 2, R = 245, r1 = 205, r2 = 160, r3 = 92;
  const asc = chart.ascendant.lon;
  const ang = (lon) => (Math.PI / 180) * (180 + lon - asc);
  const pt = (lon, r) => [c + r * Math.cos(ang(lon)), c - r * Math.sin(ang(lon))];
  let svg = `<svg class="wheel" viewBox="-28 -12 ${S + 56} ${S + 24}" role="img" aria-label="Birth chart wheel">`;
  svg += `<circle cx="${c}" cy="${c}" r="${R}" fill="#151937" stroke="#2e356b"/>`;
  for (let i = 0; i < 12; i++) {
    const a0 = i * 30, a1 = a0 + 30;
    const [x0, y0] = pt(a0, R), [x1, y1] = pt(a1, R), [x2, y2] = pt(a1, r1), [x3, y3] = pt(a0, r1);
    svg += `<path d="M${x0},${y0} A${R},${R} 0 0 0 ${x1},${y1} L${x2},${y2} A${r1},${r1} 0 0 1 ${x3},${y3} Z" fill="${ELEMENT_COLORS[i % 4]}" fill-opacity=".16" stroke="#2e356b"/>`;
    const [tx, ty] = pt(a0 + 15, (R + r1) / 2);
    svg += `<text x="${tx}" y="${ty}" font-size="20" fill="${ELEMENT_COLORS[i % 4]}" text-anchor="middle" dominant-baseline="central">${SIGN_GLYPHS[i]}</text>`;
  }
  svg += `<circle cx="${c}" cy="${c}" r="${r1}" fill="none" stroke="#2e356b"/><circle cx="${c}" cy="${c}" r="${r3}" fill="#10142e" stroke="#2e356b"/>`;
  chart.cusps.forEach((cusp, i) => {
    const [x0, y0] = pt(cusp, r3), [x1, y1] = pt(cusp, r1);
    const strong = i % 3 === 0;
    svg += `<line x1="${x0}" y1="${y0}" x2="${x1}" y2="${y1}" stroke="${strong ? "#f5c26b" : "#3b4380"}" stroke-width="${strong ? 1.6 : 1}"/>`;
    const next = chart.cusps[(i + 1) % 12];
    const mid = cusp + (((next - cusp) % 360) + 360) % 360 / 2;
    const [hx, hy] = pt(mid, r3 + 12);
    svg += `<text x="${hx}" y="${hy}" font-size="10" fill="#a3a6c8" text-anchor="middle" dominant-baseline="central">${i + 1}</text>`;
  });
  // Aspect lines between planets inside the inner circle.
  const lonOf = Object.fromEntries(chart.planets.map((p) => [p.name, p.lon]));
  lonOf.Ascendant = chart.ascendant.lon; lonOf.Midheaven = chart.midheaven.lon;
  for (const a of chart.aspects) {
    if (a.aspect === "Conjunction" || !(a.a in lonOf) || !(a.b in lonOf)) continue;
    const [x0, y0] = pt(lonOf[a.a], r3 - 2), [x1, y1] = pt(lonOf[a.b], r3 - 2);
    const col = a.nature === "harmonious" ? "#6fd3a0" : "#ff8a8a";
    svg += `<line x1="${x0}" y1="${y0}" x2="${x1}" y2="${y1}" stroke="${col}" stroke-opacity=".55" stroke-width="1"/>`;
  }
  // Planet glyphs, spread apart when they crowd together.
  const placed = [...chart.planets].sort((a, b) => a.lon - b.lon).map((p) => ({ ...p, disp: p.lon }));
  for (let pass = 0; pass < 6; pass++) {
    for (let i = 1; i < placed.length; i++) {
      if (placed[i].disp - placed[i - 1].disp < 7) placed[i].disp = placed[i - 1].disp + 7;
    }
  }
  for (const p of placed) {
    const [mx, my] = pt(p.lon, r1), [mx2, my2] = pt(p.lon, r1 - 8);
    svg += `<line x1="${mx}" y1="${my}" x2="${mx2}" y2="${my2}" stroke="#e9e8f5"/>`;
    const [gx, gy] = pt(p.disp, r2 + 18);
    svg += `<text x="${gx}" y="${gy}" font-size="17" fill="#e9e8f5" text-anchor="middle" dominant-baseline="central"><title>${esc(p.name)} ${esc(p.position)}</title>${esc(p.glyph)}</text>`;
    const [dx, dy] = pt(p.disp, r2 - 6);
    svg += `<text x="${dx}" y="${dy}" font-size="9" fill="#a3a6c8" text-anchor="middle" dominant-baseline="central">${Math.floor(p.lon % 30)}°${p.retro ? "℞" : ""}</text>`;
  }
  const [ax, ay] = pt(asc, R + 2);
  svg += `<text x="${ax - 4}" y="${ay - 8}" font-size="11" fill="#f5c26b" text-anchor="end">ASC</text>`;
  const [mx, my] = pt(chart.midheaven.lon, R + 2);
  svg += `<text x="${mx}" y="${my - 6}" font-size="11" fill="#f5c26b" text-anchor="middle">MC</text>`;
  return svg + "</svg>";
}

// ---------------------------------------------------------------- renderers
function renderChart(d) {
  lastChart = d;
  const ch = d.chart, sun = d.sun_sign;
  const elems = Object.entries(ch.elements).map(([k, v]) => `<div class="stat"><b>${v}</b><span>${k}</span></div>`).join("");
  const mods = Object.entries(ch.modalities).map(([k, v]) => `<div class="stat"><b>${v}</b><span>${k}</span></div>`).join("");
  let html = `<div class="sign-card"><div class="big-glyph">${sun.symbol}</div><div>
    <h3>${esc(d.name || "Your")} ${d.name ? "— " : ""}${esc(sun.name)} Sun, ${esc(ch.planets[1].sign)} Moon, ${esc(ch.ascendant.sign)} Rising</h3>
    <div class="hint">${esc(ch.zodiac)} zodiac · ${esc(ch.house_system)} houses${ch.ayanamsa ? ` · ayanamsa ${ch.ayanamsa}°` : ""}${d.time_known ? "" : " · birth time unknown: Moon, Ascendant and houses are approximate"}</div></div></div>
    <p class="summary">${esc(ch.summary)}</p>
    <div class="cols"><div>${wheelSvg(ch)}</div><div>
      <h4>Element balance</h4><div class="stats">${elems}</div>
      <h4>Modality balance</h4><div class="stats">${mods}</div>
      <h4>Angles</h4><p>Ascendant: <b>${esc(ch.ascendant.position)}</b><br>Midheaven: <b>${esc(ch.midheaven.position)}</b></p>
      <h4>Moon phase at birth</h4><p>${esc(d.moon_phase.name)} (${d.moon_phase.illumination}% lit)</p>
    </div></div>
    <h4>Planets</h4><div class="scroll"><table><tr><th>Planet</th><th>Position</th><th>House</th><th>Meaning</th></tr>`;
  for (const p of ch.planets) {
    html += `<tr><td>${esc(p.glyph)} ${esc(p.name)}${p.retro ? ' <span title="retrograde">℞</span>' : ""}</td><td>${esc(p.position)}</td><td>${p.house}</td><td>${esc(p.text)}</td></tr>`;
  }
  html += `</table></div><h4>Aspects</h4><div class="scroll"><table><tr><th>Aspect</th><th>Orb</th><th>Meaning</th></tr>`;
  for (const a of ch.aspects) {
    html += `<tr><td class="${a.nature}">${esc(a.a)} ${a.symbol} ${esc(a.b)} <small>(${esc(a.aspect)})</small></td><td>${a.orb}°</td><td>${esc(a.text)}</td></tr>`;
  }
  html += `</table></div><h4>About ${esc(sun.name)}</h4>${signBlurb(sun)}`;
  return html;
}

function signBlurb(s) {
  return `<p><b>${esc(s.dates)}</b> · ${esc(s.element)} · ${esc(s.modality)} · ruled by ${esc(s.ruler)}</p>
    <p><b>Strengths:</b> ${esc(s.strengths)}<br><b>Challenges:</b> ${esc(s.challenges)}<br>
    <b>Most compatible:</b> ${esc(s.compatible.join(", "))}<br>
    <b>Lucky:</b> number ${s.lucky.number}, ${esc(s.lucky.color)}, ${esc(s.lucky.day)}, ${esc(s.lucky.stone)}</p>`;
}

const RASHI_SHORT = ["Mesha", "Vrishabha", "Mithuna", "Karka", "Simha", "Kanya", "Tula", "Vrishchika", "Dhanu", "Makara", "Kumbha", "Meena"];
const SI_LAYOUT = { 11: [1, 1], 0: [1, 2], 1: [1, 3], 2: [1, 4], 3: [2, 4], 4: [3, 4], 5: [4, 4], 6: [4, 3], 7: [4, 2], 8: [4, 1], 9: [3, 1], 10: [2, 1] };
function southIndian(k) {
  const bySign = Array.from({ length: 12 }, () => []);
  for (const g of k.grahas) bySign[g.sign].push(g.short + (g.retro ? "(R)" : ""));
  let html = '<div class="si-chart">';
  for (let s = 0; s < 12; s++) {
    const [row, col] = SI_LAYOUT[s];
    const isLagna = s === k.lagna.sign;
    html += `<div class="${isLagna ? "lagna" : ""}" style="grid-row:${row};grid-column:${col}">${isLagna ? "<b>Asc</b> " : ""}${bySign[s].join(" ")}<span class="rname">${RASHI_SHORT[s]}</span></div>`;
  }
  return html + `<div class="center">Rashi chart<br><small>Lagna ${esc(k.lagna.rashi)}</small></div></div>`;
}

function renderVedic(k) {
  let html = `<div class="cols"><div>${southIndian(k)}</div><div>
    <div class="stats">
      <div class="stat"><b>${esc(k.lagna.rashi)}</b><span>Lagna (ascendant), lord ${esc(k.lagna.lord)}</span></div>
      <div class="stat"><b>${esc(k.moon_sign.rashi)}</b><span>Rashi (Moon sign)</span></div>
      <div class="stat"><b>${esc(k.nakshatra.name)} ${k.nakshatra.pada}</b><span>Janma nakshatra · pada</span></div>
      <div class="stat"><b>${esc(k.sun_sign)}</b><span>Sidereal Sun sign</span></div>
    </div>
    <p>Nakshatra lord <b>${esc(k.nakshatra.lord)}</b>, deity <b>${esc(k.nakshatra.deity)}</b>, symbol <b>${esc(k.nakshatra.symbol)}</b>. Lahiri ayanamsa ${k.ayanamsa}°.</p>
    <h4>Mangal Dosha</h4><p class="${k.manglik.from_lagna ? "challenging" : "harmonious"}">${esc(k.manglik.text)}</p>
    <h4>Birth Panchang</h4><p>${esc(k.panchang_at_birth.vara)}, ${esc(k.panchang_at_birth.paksha)} ${esc(k.panchang_at_birth.tithi)}, yoga ${esc(k.panchang_at_birth.yoga)}, karana ${esc(k.panchang_at_birth.karana)}</p>
  </div></div>
  <h4>Grahas</h4><div class="scroll"><table><tr><th>Graha</th><th>Rashi</th><th>Degree</th><th>House</th><th>Nakshatra</th></tr>`;
  for (const g of k.grahas) {
    html += `<tr><td>${esc(g.name)}${g.retro ? " ℞" : ""}</td><td>${esc(g.rashi)}</td><td>${g.degree.toFixed(2)}°</td><td>${g.house}</td><td>${esc(g.nakshatra)} (pada ${g.pada})</td></tr>`;
  }
  html += `</table></div><h4>Vimshottari Dasha</h4><p class="summary">${esc(k.dasha.reading || "")}</p>
    <p class="hint">Born in ${esc(k.dasha.birth_nakshatra)} → first dasha ${esc(k.dasha.start_lord)}, ${k.dasha.balance_years} years remaining at birth. Click a period to see its sub-periods.</p>`;
  for (const p of k.dasha.periods) {
    html += `<details ${p.status === "current" ? "open" : ""}><summary class="dasha-row ${p.status}">${pill(p.status)} <b>${esc(p.lord)}</b> Mahadasha · ${fmtDate(p.start)} → ${fmtDate(p.end)} (${p.years} yrs)</summary>
      <p class="hint">${esc(p.theme)}</p><div class="scroll"><table>`;
    for (const s of p.antardashas || []) {
      html += `<tr class="${s.status === "current" ? "dasha-row current" : ""}"><td>${pill(s.status)}</td><td>${esc(p.lord)} / ${esc(s.lord)}</td><td>${fmtDate(s.start)} → ${fmtDate(s.end)}</td></tr>`;
    }
    html += "</table></div></details>";
  }
  const ss = k.sade_sati;
  html += `<h4>Sade Sati (Saturn over your Moon)</h4><p class="summary">${esc(ss.status_text)} Saturn is now in ${esc(ss.saturn_now)}.</p><p class="hint">${esc(ss.about)}</p><table>`;
  for (const p of ss.periods) html += `<tr><td>${pill(p.status)}</td><td>Sade Sati</td><td>${fmtDate(p.start)} → ${fmtDate(p.end)}${p.open_start ? " (already running at birth)" : ""}</td></tr>`;
  for (const p of ss.dhaiya) html += `<tr><td>${pill(p.status)}</td><td>${esc(p.kind)}</td><td>${fmtDate(p.start)} → ${fmtDate(p.end)}</td></tr>`;
  return html + "</table>";
}

function renderHoroscope(h) {
  const areas = ["love", "career", "money", "health"];
  let html = `<div class="sign-card"><div class="big-glyph">${h.symbol}</div><div><h3>${esc(h.sign)} — ${esc(h.period)} horoscope</h3>
    <div class="hint">${fmtDate(h.from)}${h.to !== h.from ? " → " + fmtDate(h.to) : ""}</div></div></div>
    <p class="summary">${esc(h.overall)}</p><div class="stats">`;
  for (const a of areas) html += `<div class="stat"><span>${a}</span><br>${stars(h.scores[a])}</div>`;
  html += `<div class="stat"><span>Lucky</span><br>#${h.lucky.number} · ${esc(h.lucky.color)} · ${esc(h.lucky.time)}</div></div>`;
  for (const a of areas) html += `<h4>${a[0].toUpperCase() + a.slice(1)}</h4><p>${esc(h[a])}</p>`;
  if (h.notes.length) html += `<h4>Planetary notes</h4><ul>${h.notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>`;
  html += `<details><summary>Planet positions used</summary><p>${Object.entries(h.planets).map(([k, v]) => `${esc(k)}: ${esc(v)}`).join(" · ")}</p></details>`;
  return html;
}

function renderForecast(f) {
  const t = f.transits;
  let html = `<h3>${fmtDate(f.date)} ${pill(f.when)} · age ${f.age}</h3><p class="summary">${esc(t.headline)}</p><div class="stats">`;
  for (const [k, v] of Object.entries(t.scores)) html += `<div class="stat"><span>${esc(k)}</span><br>${stars(v)}</div>`;
  html += `</div><div class="cols"><div>
    <h4>Vedic period</h4><p>${esc(f.dasha.reading || "")}</p><p>${esc(f.sade_sati)}</p>
    <h4>Numerology cycle</h4><p>Personal year <b>${f.numerology.personal_year.number}</b>: ${esc(f.numerology.personal_year.text)}.<br>
      Personal month <b>${f.numerology.personal_month.number}</b>: ${esc(f.numerology.personal_month.text)}.<br>
      Personal day <b>${f.numerology.personal_day.number}</b>: ${esc(f.numerology.personal_day.text)}.</p>
    <h4>Chinese year</h4><p><b>${esc(f.chinese.year_sign)}</b> (${esc(f.chinese.relation)}): ${esc(f.chinese.text)}</p>
  </div><div>
    <h4>Moon</h4><p>${esc(t.moon.phase.name)} (${t.moon.phase.illumination}% lit) at ${esc(t.moon.position)}, in your ${ord(t.moon.house)} house.</p>
    <h4>Panchang</h4><p>${esc(f.panchang.vara)} · ${esc(f.panchang.paksha)} ${esc(f.panchang.tithi)} · ${esc(f.panchang.nakshatra)} nakshatra · ${esc(f.panchang.yoga)} yoga</p>
    <h4>Where the planets are in your chart</h4><ul>${t.placements.map((p) => `<li>${esc(p.text)}${p.retro ? " (retrograde)" : ""}</li>`).join("")}</ul>
  </div></div><h4>Active transits</h4>`;
  if (!t.aspects.length) html += "<p>No close transits on this date.</p>";
  else {
    html += '<div class="scroll"><table><tr><th>Transit</th><th>Orb</th><th>Interpretation</th></tr>';
    for (const a of t.aspects) html += `<tr><td class="${a.nature}">${esc(a.transit)} ${a.symbol} natal ${esc(a.natal)}</td><td>${a.orb}°</td><td>${esc(a.text)}</td></tr>`;
    html += "</table></div>";
  }
  return html;
}

function renderTimeline(t, filter) {
  const events = t.events.filter((e) => filter === "all" || e.status === filter);
  let html = `<p class="hint">${t.events.length} life events over ${t.years} years. Gold dot = happening now, blue = still to come.</p><ul class="timeline">`;
  let markerShown = false;
  for (const e of events) {
    if (!markerShown && filter === "all" && e.date > t.today) {
      html += `<li class="now-marker">▶ Today — ${fmtDate(t.today)}</li>`;
      markerShown = true;
    }
    const passes = e.passes.length > 1 ? ` · exact ${e.passes.map(fmtDate).join(", ")}` : "";
    html += `<li class="${e.status}"><div class="when">${fmtDate(e.date)} · age ${e.age}${passes} ${pill(e.status)}</div>
      <b>${esc(e.title)}</b><div>${esc(e.text)}</div></li>`;
  }
  return html + "</ul>";
}

function renderCompat(c) {
  const g = c.guna_milan;
  let html = `<h3>${esc(c.names[0])} & ${esc(c.names[1])}</h3>
    <div class="stats"><div class="stat"><b>${c.overall}%</b><span>Overall harmony</span></div>
    <div class="stat"><b>${g.total}/36</b><span>Guna Milan · ${esc(g.verdict)}</span></div>
    <div class="stat"><b>${c.synastry.score}%</b><span>Synastry</span></div>
    <div class="stat"><b>${c.sun_signs.score}%</b><span>${esc(c.sun_signs.a)} + ${esc(c.sun_signs.b)}</span></div>
    <div class="stat"><b>${c.chinese.score}%</b><span>${esc(c.chinese.a)} + ${esc(c.chinese.b)}</span></div>
    <div class="stat"><b>${c.numerology.score}%</b><span>Life paths ${c.numerology.a} + ${c.numerology.b}</span></div></div>
    <div class="cols"><div><h4>Ashtakoota (Guna Milan)</h4><table><tr><th>Koota</th><th>Score</th><th>Detail</th></tr>`;
  for (const k of g.kootas) {
    html += `<tr><td>${esc(k.name)}<br><small class="hint">${esc(k.about)}</small></td><td>${k.score}/${k.max}<div class="bar"><i style="width:${(k.score / k.max) * 100}%"></i></div></td><td>${esc(k.detail)}</td></tr>`;
  }
  html += `</table>${g.doshas.length ? `<p class="challenging">Doshas: ${esc(g.doshas.join(", "))}</p>` : ""}</div><div>
    <h4>Sun signs</h4><p>${esc(c.sun_signs.elements[0])} meets ${esc(c.sun_signs.elements[1])}.</p>
    <h4>Chinese zodiac</h4><p><b>${esc(c.chinese.relation)}</b> — ${esc(c.chinese.text)}</p>
    <h4>Numerology</h4><p>${esc(c.numerology.text)}</p>
    <h4>Synastry aspects</h4><table>`;
  for (const a of c.synastry.aspects) html += `<tr><td class="${a.nature}">${esc(c.names[0])}'s ${esc(a.a)} ${a.symbol} ${esc(c.names[1])}'s ${esc(a.b)}</td><td>${a.orb}°</td></tr>`;
  return html + "</table></div></div>";
}

function renderPanchang(p) {
  const pc = p.panchang;
  let html = `<h3>Panchang · ${esc(p.moment.slice(0, 16).replace("T", " "))}</h3><div class="stats">
    <div class="stat"><b>${esc(pc.vara)}</b><span>Vara</span></div>
    <div class="stat"><b>${esc(pc.tithi)}</b><span>Tithi · ${esc(pc.paksha)} · ${pc.tithi_progress}% done</span></div>
    <div class="stat"><b>${esc(pc.nakshatra)} ${pc.nakshatra_pada}</b><span>Nakshatra (lord ${esc(pc.nakshatra_lord)})</span></div>
    <div class="stat"><b class="${pc.yoga_auspicious ? "harmonious" : "challenging"}">${esc(pc.yoga)}</b><span>Yoga</span></div>
    <div class="stat"><b class="${pc.karana_auspicious ? "harmonious" : "challenging"}">${esc(pc.karana)}</b><span>Karana</span></div>
    <div class="stat"><b>${esc(p.moon_phase.name)}</b><span>${p.moon_phase.illumination}% illuminated</span></div></div>
    <p>Moon in ${esc(pc.moon_rashi)}, Sun in ${esc(pc.sun_rashi)}. Rising sign: ${esc(p.lagna.tropical)} (tropical) / ${esc(p.lagna.sidereal)} (sidereal).</p>
    <div class="scroll"><table><tr><th>Planet</th><th>Tropical</th><th>Sidereal (Lahiri)</th></tr>`;
  for (const pl of p.planets) html += `<tr><td>${esc(pl.name)}${pl.retro ? " ℞" : ""}</td><td>${esc(pl.tropical)}</td><td>${esc(pl.sidereal)}</td></tr>`;
  return html + "</table></div>";
}

function renderSky(s) {
  let html = `<h3>Sky calendar ${s.year}</h3><p>Chinese New Year: <b>${fmtDate(s.lunar_new_year)}</b> — year of the ${esc(s.chinese_year)}.</p>
    <div class="toolbar"><label>Show <select id="sky-filter"><option value="all">All events</option><option value="lunation">Moons &amp; eclipses</option><option value="station">Retrogrades</option><option value="ingress">Sign changes</option></select></label></div>
    <div class="scroll"><table id="sky-table"><tr><th>Date</th><th>Time</th><th>Event</th><th>Detail</th></tr>`;
  for (const e of s.events) {
    html += `<tr data-kind="${e.kind}"><td>${fmtDate(e.date)}</td><td>${esc(e.time)}</td><td class="${e.eclipse ? "challenging" : ""}">${e.eclipse ? "<b>" : ""}${esc(e.title)}${e.eclipse ? "</b>" : ""}</td><td>${esc(e.detail)}</td></tr>`;
  }
  return html + "</table></div>";
}

function renderMore(d) {
  const c = d.chinese, n = d.numerology;
  const numRow = (label, x) => x ? `<tr><td>${label}</td><td><b>${x.number}</b></td><td><b>${esc(x.title)}</b> — ${esc(x.text)}</td></tr>` : "";
  return `<div class="cols"><div><h3>Chinese zodiac</h3><p class="summary">${esc(c.text)}</p>
    <p>Year pillar <b>${esc(c.stem_branch)}</b> · ${esc(c.polarity)} · Chinese year starting ${fmtDate(c.lunar_new_year)}</p>
    <p>Best matches: <b>${esc(c.best_matches.join(", "))}</b> · Clash: <b>${esc(c.clash)}</b></p></div>
    <div><h3>Numerology</h3><table>${numRow("Life Path", n.life_path)}${numRow("Birthday", n.birthday)}${numRow("Expression", n.expression)}${numRow("Soul Urge", n.soul_urge)}${numRow("Personality", n.personality)}</table>
    ${n.expression ? "" : '<p class="hint">Enter your full name above for Expression, Soul Urge and Personality numbers.</p>'}</div></div>`;
}

// ---------------------------------------------------------------- wiring
function showTab(name) {
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".tab").forEach((s) => s.classList.toggle("hidden", s.id !== "tab-" + name));
  try { localStorage.setItem("zodiac-tab", name); } catch (e) { /* ignore */ }
}

const actions = {
  chart: () => run("chart-out", async () => renderChart(await api("/api/chart", { person: person(), zodiac: $("c-zodiac").value, house_system: $("c-houses").value }))),
  vedic: () => run("vedic-out", async () => renderVedic(await api("/api/vedic", { person: person(), on: $("v-on").value }))),
  horoscope: () => run("horoscope-out", async () => {
    const body = { sign: $("h-sign").value, period: $("h-period").value, date: $("h-date").value, tz: $("p-tz").value || browserTz() };
    if (body.sign === "") {
      if (!$("p-date").value) throw new Error("Choose a sign or enter your date of birth.");
      body.birth_date = $("p-date").value;
    }
    return renderHoroscope(await api("/api/horoscope", body));
  }),
  forecast: () => run("forecast-out", async () => renderForecast(await api("/api/forecast", { person: person(), on: $("f-on").value }))),
  timeline: () => run("timeline-out", async () => {
    actions.timelineData = await api("/api/timeline", { person: person(), years: $("t-years").value });
    return renderTimeline(actions.timelineData, $("t-filter").value);
  }),
  compat: () => run("compat-out", async () => {
    const a = person("p"), b = person("q");
    const [x, y] = $("q-order").value === "ab" ? [a, b] : [b, a];
    return renderCompat(await api("/api/compatibility", { a: x, b: y }));
  }),
  panchang: () => run("sky-out", async () => renderPanchang(await api("/api/panchang", {
    date: $("s-date").value, time: $("s-time").value || "06:00", tz: $("p-tz").value || browserTz(),
    lat: $("p-lat").value || 0, lon: $("p-lon").value || 0,
  }))),
  sky: () => run("sky-out", async () => {
    const html = renderSky(await api("/api/sky", { year: $("s-year").value, tz: $("p-tz").value || browserTz() }));
    setTimeout(() => {
      const sel = $("sky-filter");
      if (sel) sel.addEventListener("change", () => {
        document.querySelectorAll("#sky-table tr[data-kind]").forEach((r) => {
          r.classList.toggle("hidden", sel.value !== "all" && r.dataset.kind !== sel.value);
        });
      });
    });
    return html;
  }),
  more: () => run("more-out", async () => renderMore(await api("/api/chart", { person: person() }))),
};

async function init() {
  try {
    META = await (await fetch("/api/meta")).json();
  } catch (e) {
    toast("Could not reach the Zodiac Studio server.");
  }
  $("cities").innerHTML = META.cities.map((c) => `<option value="${esc(c.name)}">`).join("");
  $("h-sign").innerHTML += META.signs.map((s) => `<option value="${s.index}">${s.symbol} ${esc(s.name)} (${esc(s.dates)})</option>`).join("");
  loadProfile();
  bindCity("p");
  bindCity("q");
  document.querySelectorAll("#profile input, #tab-compat .grid input").forEach((el) => el.addEventListener("change", saveProfile));

  const t = today();
  $("v-on").value = t; $("h-date").value = t; $("f-on").value = t; $("s-date").value = t;
  $("s-time").value = new Date().toTimeString().slice(0, 5);
  $("s-year").value = new Date().getFullYear();

  document.querySelectorAll("#tabs button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
  $("c-go").onclick = actions.chart;
  $("v-go").onclick = actions.vedic;
  $("h-go").onclick = actions.horoscope;
  $("f-go").onclick = actions.forecast;
  $("t-go").onclick = actions.timeline;
  $("q-go").onclick = actions.compat;
  $("s-go").onclick = actions.panchang;
  $("s-year-go").onclick = actions.sky;
  $("m-go").onclick = actions.more;
  $("t-filter").onchange = () => { if (actions.timelineData) $("timeline-out").innerHTML = renderTimeline(actions.timelineData, $("t-filter").value); };
  const step = (dir) => {
    const p = $("h-period").value;
    $("h-date").value = shiftDate($("h-date").value || t, p === "day" ? dir : p === "week" ? 7 * dir : 0, p === "month" ? dir : 0, p === "year" ? dir : 0);
    actions.horoscope();
  };
  $("h-prev").onclick = () => step(-1);
  $("h-next").onclick = () => step(1);
  $("f-prev").onclick = () => { $("f-on").value = shiftDate($("f-on").value || t, -1); actions.forecast(); };
  $("f-next").onclick = () => { $("f-on").value = shiftDate($("f-on").value || t, 1); actions.forecast(); };

  let tab = "chart";
  try { tab = localStorage.getItem("zodiac-tab") || "chart"; } catch (e) { /* ignore */ }
  showTab($("tab-" + tab) ? tab : "chart");
}

init();
