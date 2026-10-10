"use strict";
/* Volby Brno 2026 – projektorové a mobilní zobrazení průběžných výsledků.
 *
 * Zdroje dat (v tomto pořadí):
 *   1. živé XML z volby.gov.cz (povoluje CORS),
 *   2. záloha data/latest/<kod>.json, kterou ukládá GitHub Action.
 * Celky bez sečteného okrsku ukazují šedě výsledky 2022 (mock/2022/latest).
 *
 * Parametry URL: ?mock=2022 | ?mock=2022-prubeh  (testovací data)
 *                ?demo                             (vymyšlené hlasy 2026)
 *                ?interval=12                      (rotace v sekundách)
 */

const GREEN = "#0bd26f";
const GREY_ZELENI = "#8e8e8e";
const REFRESH_MS = 60_000;
const params = new URLSearchParams(location.search);
const MOCK = params.get("mock");
const DEMO = params.has("demo"); // vymyšlené hlasy pro letošní kandidátky (test barev a rozložení)
const YEAR = MOCK ? "2022" : "2026";

const S = {
  cfg: null, barvy: null, zkratky: {},
  units: [],          // konfigurace celků v pořadí rotace
  data: {},           // kod -> normalizovaná data
  ref: {},            // kod -> výsledky 2022 (pro celky bez dat)
  meta: {},           // kod -> {src, failed, lastOk}
  active: 0, elapsed: 0, intervalMs: 12000,
  view: "res", showAll: false,
  coal: load("vv-coal", {}),
  theme: document.documentElement.dataset.theme || "light",
};

function load(key, def) { try { return JSON.parse(localStorage.getItem(key)) ?? def; } catch (e) { return def; } }
function save(key, val) { try { localStorage.setItem(key, JSON.stringify(val)); } catch (e) {} }
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const num2 = v => v.toFixed(2).replace(".", ",");
const fmt = v => num2(v) + " %";
const pctHtml = v => `${num2(v)}<small>%</small>`;
// Ikona mandátu (postava) místo zkratky „mand.“
const SEAT = `<svg class="seat" viewBox="0 0 24 24" role="img" aria-label="mandátů"><circle cx="12" cy="7" r="4.5"/><path d="M3.5 22c0-5 3.8-8.5 8.5-8.5s8.5 3.5 8.5 8.5z"/></svg>`;
const seatsHtml = n => n > 0 ? `${n}${SEAT}` : "";
// Hlavní celek (Brno) má vlastní řádek nahoře a ukazuje všechny strany; stránka měst ho nemá.
const isMain = i => !!S.cfg.hlavni && i === 0;
const isMainKod = kod => !!S.cfg.hlavni && kod === S.units[0].kod;
// Hlavní celek ukazuje všechny strany (Brno); u Prahy s 24 kandidátkami jen nad 3 % jako ostatní.
const allForMain = () => S.cfg.hlavni_vsechny_strany !== false;
// Odkazy mezi stránkami – stejné na všech třech, aktuální zvýrazněná.
const PAGES = [
  { text: "Praha", href: "praha.html", config: "config-praha.json" },
  { text: "Brno", href: "./", config: "config.json" },
  { text: "Města 1", href: "mesta.html", config: "config-mesta.json" },
  { text: "Města 2", href: "mesta2.html", config: "config-mesta2.json" },
];
const pagesHtml = () => `<nav class="pages">${PAGES.map(pg => (document.body.dataset.config || "config.json") === pg.config
  ? `<span class="pill-small on" aria-current="page">${pg.text}</span>`
  : `<a class="pill-small" href="${pg.href}">${pg.text}</a>`).join("")}</nav>`;
const short = n => S.zkratky[n] || n;
const plMand = n => n === 1 ? "mandát" : n >= 2 && n <= 4 ? "mandáty" : "mandátů";

/* ---------------- data ---------------- */

function fromJson(d) {
  const u = d.ucast || {};
  return {
    kod: d.kod, voleno: d.voleno, spocteno: !!d.je_spocteno, generovano: d.generovano,
    zprac: u.okrsky_zprac || 0, celkem: u.okrsky_celkem || 0, ucast: u.ucast_proc || 0,
    strany: d.strany.map(s => ({ por: s.por, vstrana: s.vstrana, nazev: s.nazev, hlasy: s.hlasy, kandidatu: s.kandidatu, oficialni: s.zastupitele })),
  };
}

function fromXml(text) {
  const doc = new DOMParser().parseFromString(text, "application/xml");
  const obec = doc.getElementsByTagName("OBEC")[0];
  const ucast = obec && obec.getElementsByTagName("UCAST")[0];
  if (!obec || !ucast) throw new Error("XML bez výsledků");
  const n = (el, a) => Number(el.getAttribute(a) || 0);
  const vysledek = obec.getElementsByTagName("VYSLEDEK")[0];
  const strany = [...vysledek.children].filter(e => e.localName === "VOLEBNI_STRANA").map(s => ({
    por: n(s, "POR_STR_HLAS_LIST"), vstrana: n(s, "VSTRANA"), nazev: s.getAttribute("NAZEV_STRANY"),
    hlasy: n(s, "HLASY"), kandidatu: n(s, "KANDIDATU_POCET"), oficialni: n(s, "ZASTUPITELE_POCET"),
  }));
  return {
    kod: obec.getAttribute("KODZASTUP"), voleno: n(obec, "VOLENO_ZASTUP"),
    spocteno: ["1", "true"].includes(obec.getAttribute("JE_SPOCTENO")),
    generovano: doc.documentElement.getAttribute("DATUM_CAS_GENEROVANI"),
    zprac: n(ucast, "OKRSKY_ZPRAC"), celkem: n(ucast, "OKRSKY_CELKEM"), ucast: n(ucast, "UCAST_PROC"),
    strany,
  };
}

async function get(url, type, ms = 10000) {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), ms);
  try {
    const r = await fetch(url, { signal: ctl.signal, cache: "no-store" });
    if (!r.ok) throw new Error("HTTP " + r.status);
    return type === "json" ? await r.json() : await r.text();
  } finally { clearTimeout(t); }
}

async function loadUnit(u) {
  const m = S.meta[u.kod] || (S.meta[u.kod] = {});
  let d = null, src = null;
  if (!MOCK) {
    try {
      d = fromXml(await get(`https://volby.gov.cz/appdata/${S.cfg.volby}/${S.cfg.datum}/odata/zastup/vysledky_obec_${u.kod}.xml`, "text"));
      src = "živě";
    } catch (e) { /* zkusíme zálohu */ }
  }
  if (!d) {
    try {
      d = fromJson(await get(`${MOCK ? "mock/" + MOCK : "data"}/latest/${u.kod}.json?t=${Date.now()}`, "json"));
      src = MOCK ? "mock" : "záloha";
    } catch (e) { /* nic */ }
  }
  if (d && DEMO) d = demo(d);
  if (d && d.kod === u.kod) {
    S.data[u.kod] = d;
    Object.assign(m, { src, failed: !MOCK && src !== "živě", lastOk: Date.now() });
  } else {
    m.failed = true;
  }
}

async function refresh() {
  await Promise.all(S.units.map(loadUnit));
  render();
}

function demo(d) {
  let seed = Number(d.kod);
  const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  const zprac = d.kod === "551171" ? 0 : Math.max(1, Math.round(d.celkem * (0.3 + rnd() * 0.7)));
  const strany = d.strany.map(s => ({ ...s, hlasy: zprac ? Math.round(Math.pow(rnd(), 2) * 20000 + 300) : 0, oficialni: 0 }));
  return { ...d, zprac, spocteno: false, ucast: zprac ? 35 + rnd() * 15 : 0, generovano: d.generovano || "2026-10-10T21:14:00", strany };
}

/* ---------------- mandáty: § 45 zákona 491/2001 Sb. ---------------- */

function mandaty(strany, voleno) {
  const out = Object.fromEntries(strany.map(s => [s.por, 0]));
  const V = strany.reduce((a, s) => a + s.hlasy, 0);
  if (!V) return out;
  const sHlasy = strany.filter(s => s.hlasy > 0);
  // Uzavírací klauzule 5 %; strana s méně kandidáty než mandátů má základ úměrně snížený.
  const zaklad = s => V * Math.min(s.kandidatu || voleno, voleno) / voleno;
  let postup = sHlasy;
  for (const t of [5, 4, 3, 2, 1]) {
    const p = sHlasy.filter(s => s.hlasy * 100 >= t * zaklad(s));
    if (p.length >= 2) { postup = p; break; }
    if (t === 1) postup = sHlasy.length >= 2 ? sHlasy : p.length ? p : sHlasy;
  }
  // D'Hondt (dělitelé 1, 2, 3 …); strana nedostane víc mandátů, než má kandidátů.
  for (let i = 0; i < voleno; i++) {
    let best = null, bq = -1;
    for (const s of postup) {
      if (s.kandidatu && out[s.por] >= s.kandidatu) continue;
      const q = s.hlasy / (out[s.por] + 1);
      if (q > bq || (q === bq && (s.hlasy > best.hlasy || (s.hlasy === best.hlasy && s.por < best.por)))) { bq = q; best = s; }
    }
    if (!best) break;
    out[best.por]++;
  }
  return out;
}

/* Připravený pohled na celek: strany s %, mandáty a barvou. */
function view(u) {
  const live = S.data[u.kod];
  const hasLive = !!(live && live.zprac > 0);
  const d = hasLive ? live : S.ref[u.kod];
  const isRef = !hasLive && !!d;
  const nase = isRef ? u.nase["2022"] : u.nase[YEAR];
  if (!d) return { u, live, hasLive, isRef, d: null, parties: [], nase };
  const V = d.strany.reduce((a, s) => a + s.hlasy, 0);
  const official = d.spocteno;
  const est = official ? null : mandaty(d.strany, d.voleno);
  const parties = d.strany.map(s => ({
    ...s,
    pct: V ? s.hlasy / V * 100 : 0,
    seats: official ? s.oficialni : est[s.por],
    ours: s.por === nase,
    color: isRef ? "var(--grey)" : barva(u, s, nase),
  })).sort((a, b) => b.pct - a.pct || a.por - b.por);
  return { u, live, hasLive, isRef, d, parties, nase, official, voleno: d.voleno };
}

function barva(u, s, nase) {
  if (s.por === nase) return GREEN;
  const B = S.barvy;
  const g = B.vyjimky[`${u.kod}:${s.por}`] || B.vstrana[String(s.vstrana)] || B.vychozi;
  if (g === "zeleni") return GREY_ZELENI; // zelená patří jen naší kandidátce
  const sk = B.skupiny[g] || B.skupiny[B.vychozi];
  return (S.theme === "dark" && sk.barva_tmava) || sk.barva;
}

const shown = (v, all) => all ? v.parties : v.parties.filter(p => p.pct >= 3 || p.ours);

function textOn(c) {
  if (!c.startsWith("#")) return "var(--bg)";
  const n = parseInt(c.slice(1), 16);
  return (0.299 * (n >> 16) + 0.587 * (n >> 8 & 255) + 0.114 * (n & 255)) / 255 > 0.6 ? "#000" : "#fff";
}

function timeTxt(v) {
  if (!v.hasLive || !v.live.generovano) return "–";
  return v.live.generovano.slice(11, 16);
}
const warnHtml = v => S.meta[v.u.kod]?.failed ? `<span class="warn" title="volby.gov.cz neodpovídá – zobrazena poslední dostupná data">⚠</span>` : "";

/* Klíčované vykreslení: zachová prvky mezi aktualizacemi kvůli animacím. */
function keyed(parent, items, key, create, update, scope) {
  if (parent._scope !== scope) { parent.textContent = ""; parent._k = new Map(); parent._scope = scope; }
  const old = parent._k, next = new Map();
  items.forEach((it, i) => {
    const k = key(it);
    let el = old.get(k);
    if (!el) { el = create(it); parent.appendChild(el); void el.offsetHeight; }
    old.delete(k);
    update(el, it, i);
    el.style.order = i;
    next.set(k, el);
  });
  old.forEach(el => el.remove());
  parent._k = next;
}
const h = (html) => { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstChild; };

/* ---------------- projektor ---------------- */

function fit() {
  const s = Math.min(innerWidth / 1024, innerHeight / 768);
  $("stage").style.transform = `translate(${(innerWidth - 1024 * s) / 2}px, ${(innerHeight - 768 * s) / 2}px) scale(${s})`;
}

function renderBrnoRow() {
  const el = $("brnoRow");
  el.hidden = !S.cfg.hlavni || isMain(S.active);
  if (el.hidden) return;
  const v = view(S.units[0]);
  const d = v.live;
  const cells = shown(v, false);
  el.innerHTML = `
    <div class="brno-meta">
      <a href="${esc(v.u.odkaz)}" target="_blank" rel="noopener">${esc(v.u.zobrazit)} ↗</a>
      <div class="rows">
        <div>Okrsky <b>${d ? d.zprac + " / " + d.celkem : "–"}</b> ${d && d.celkem ? "(" + fmt(d.zprac / d.celkem * 100) + ")" : ""}</div>
        <div>Účast <b>${v.hasLive ? fmt(d.ucast) : "–"}</b></div>
        <div>Aktualizováno <b>${timeTxt(v)}</b>${warnHtml(v)}</div>
      </div>
    </div>
    <div class="cells">${cells.map(p => `
      <div class="cell${p.ours && !v.isRef ? " ours" : ""}" style="border-top-color:${p.color}" title="${esc(p.nazev)}">
        <div class="n"><span>${esc(short(p.nazev))}</span></div>
        <div class="p">${num2(p.pct)}</div>
        <div class="s">${seatsHtml(p.seats)}</div>
      </div>`).join("")}
    </div>`;
  if (v.isRef) el.querySelector(".brno-meta .rows").insertAdjacentHTML("beforeend", `<div>Zobrazen rok <b>2022</b></div>`);
}

function renderSide() {
  const el = $("side");
  el.hidden = isMain(S.active);
  if (el.hidden) return;
  el.innerHTML = `<div class="side-head"><div>${esc(S.cfg.nadpis || "Městská část")}</div><div>Naše</div></div>` + S.units.map((u, i) => {
    const d = S.data[u.kod];
    const v = d && d.zprac > 0 ? view(u) : null;
    const ours = v && v.parties.find(p => p.ours);
    const prog = d && d.celkem ? d.zprac / d.celkem * 100 : 0;
    return `<button type="button" class="side-row${i === S.active ? " on" : ""}" data-i="${i}">
      <span class="nm">${esc(u.kratky)}</span><span class="v">${ours ? fmt(ours.pct) : "–"}</span>
      <span class="prog" style="width:${prog}%"></span></button>`;
  }).join("");
}

const seatsTotal = v => (v.live || v.d)?.voleno || 0;

function headHtml(v) {
  const d = v.live;
  const cp = d && d.celkem ? d.zprac / d.celkem * 100 : 0;
  return `<div class="dhead">
    <div class="dtitle"><a class="dname" href="${esc(v.u.odkaz)}" target="_blank" rel="noopener">${esc(v.u.zobrazit)}<span>↗</span></a>
      ${seatsTotal(v) ? `<div class="dseats">${seatsTotal(v)} ${plMand(seatsTotal(v))} v zastupitelstvu</div>` : ""}</div>
    <div class="metrics">
      <div class="metric"><div class="lbl">Sečteno okrsků</div>
        <div class="row"><div class="val">${d ? d.zprac + " / " + d.celkem : "–"}</div><div class="sub">${d ? fmt(cp) : ""}</div></div>
        <div class="bar6"><div style="width:${cp}%"></div></div></div>
      <div class="metric"><div class="lbl">Účast</div><div class="val pad">${v.hasLive ? fmt(d.ucast) : "–"}</div></div>
      <div class="metric"><div class="lbl">Aktualizováno</div><div class="val pad">${timeTxt(v)}${warnHtml(v)}</div></div>
    </div></div>`;
}

function renderResults(v) {
  const det = $("detail");
  const scope = "res:" + v.u.kod + ":" + v.isRef;
  if (det._scope !== scope) {
    det._scope = scope;
    det.innerHTML = `<div id="dh"></div><div id="chartWrap" class="chart"></div>`;
  }
  $("dh").innerHTML = headHtml(v);
  const wrap = $("chartWrap");
  if (!v.d) {
    wrap.innerHTML = `<div class="empty"><b>Čekáme na data</b><span>Zatím nebyl sečten žádný okrsek</span></div>`;
    wrap._built = false;
    return;
  }
  if (!wrap._built) {
    wrap.innerHTML = `${v.isRef ? `<div class="ref-note"><b>Zobrazuji výsledky 2022</b>, zatím nebyl sečten žádný okrsek</div>` : ""}
      <div class="plot" id="plot"><div class="five" id="five"><span>5 %</span></div></div><div class="labels" id="labels"></div>`;
    wrap._built = true;
  }
  const bars = shown(v, (isMain(S.active) && allForMain()) || S.showAll);
  const dense = bars.length > 10;
  wrap.classList.toggle("dense", dense);
  const scale = Math.max(...bars.map(p => p.pct), 10) / 0.82;
  $("five").style.bottom = (5 / scale * 100) + "%";
  keyed($("plot"), bars, p => p.por,
    () => h(`<div class="col"><div class="pct"></div><div class="bar"></div></div>`),
    (el, p) => {
      el.firstChild.innerHTML = pctHtml(p.pct);
      el.lastChild.style.background = p.color;
      el.lastChild.style.height = (p.pct / scale * 100) + "%";
    }, scope);
  // „five“ musí v plotu zůstat – keyed ho při změně scope smaže, tak ho vrátíme
  if (!$("five")) { $("plot").prepend(h(`<div class="five" id="five"><span>5 %</span></div>`)); $("five").style.bottom = (5 / scale * 100) + "%"; }
  keyed($("labels"), bars, p => p.por,
    () => h(`<div class="lab"><div class="n"><span></span></div><div class="s"></div></div>`),
    (el, p) => {
      el.children[0].firstChild.textContent = short(p.nazev);
      el.title = p.nazev;
      el.children[0].className = "n" + (p.ours ? " ours" : "");
      el.children[1].innerHTML = seatsHtml(p.seats);
    }, scope);
}

/* Koalice – sdílené pro projektor i mobil. */
function renderCoal(container, v) {
  const kod = v.u.kod;
  const total = (v.live || v.d)?.voleno || 0;
  const maj = Math.floor(total / 2) + 1;
  const seated = v.hasLive ? v.parties.filter(p => p.seats > 0) : [];
  const sel = (S.coal[kod] || []).filter(por => seated.some(p => p.por === por));
  const chosen = sel.map(por => seated.find(p => p.por === por));
  const sum = chosen.reduce((a, p) => a + p.seats, 0);
  const miss = maj - sum;
  const status = !v.hasLive ? "Bez dat" : miss <= 0 ? (miss < 0 ? "Rezerva " + -miss : "Většina") : `Chybí ${miss} ${plMand(miss)}`;
  const scope = "coal:" + kod + ":" + v.hasLive;
  if (container._scope !== scope) {
    container._scope = scope;
    container.innerHTML = `<div class="coal">
      <div class="coal-head"><div><div class="lbl">Sestavit většinu</div><div class="nm">${esc(v.u.zobrazit)}</div></div>
        <div class="tot">${total ? total + " mandátů v zastupitelstvu" : ""}</div></div>
      <div>
        <div class="coal-sum"><span class="n" data-r="sum"></span><span class="of">/ ${maj} pro většinu</span>
          <span class="status" data-r="status"></span><button type="button" class="reset" data-act="reset">Vymazat výběr</button></div>
        <div class="coal-bar" style="margin-top:12px"><div data-r="segs" style="display:flex;width:100%;height:100%"></div>
          <div class="maj-line" style="left:${maj / (total || 1) * 100}%"></div>
          <div class="maj-lbl" style="left:${maj / (total || 1) * 100}%">většina ${maj}</div></div>
      </div>
      ${seated.length ? `<div class="cards" data-r="cards"></div>` : `<div class="empty"><b>Čekáme na data</b></div>`}
    </div>`;
  }
  const q = r => container.querySelector(`[data-r="${r}"]`);
  q("sum").textContent = sum;
  q("status").textContent = status;
  q("status").className = "status" + (v.hasLive && miss <= 0 ? " ok" : "");
  keyed(q("segs"), chosen, p => p.por, () => h(`<div class="seg-c"></div>`), (el, p) => {
    el.style.width = (p.seats / total * 100) + "%";
    el.style.background = p.color;
    el.style.color = textOn(p.color);
    el.textContent = p.seats;
  }, scope);
  if (q("cards")) keyed(q("cards"), seated, p => p.por,
    p => h(`<button type="button" class="card" data-por="${p.por}"><div class="top"></div><div class="n"></div><div class="r"><div class="s"></div><div class="a"></div></div></button>`),
    (el, p) => {
      const on = sel.includes(p.por);
      el.className = "card" + (on ? " on" : "") + (p.ours ? " ours" : "");
      el.querySelector(".top").style.background = p.color;
      el.querySelector(".n").textContent = short(p.nazev);
      el.title = p.nazev;
      el.querySelector(".s").innerHTML = `${p.seats}${SEAT}`;
      const a = el.querySelector(".a");
      a.textContent = on ? "Odebrat" : "+ Přidat";
      a.className = "a" + (!on && p.ours ? " add-ours" : "");
    }, scope);
  container.onclick = e => {
    const card = e.target.closest("[data-por]");
    if (card) {
      const por = Number(card.dataset.por);
      S.coal[kod] = sel.includes(por) ? sel.filter(x => x !== por) : sel.concat(por);
    } else if (e.target.closest('[data-act="reset"]')) S.coal[kod] = [];
    else return;
    save("vv-coal", S.coal);
    render();
  };
}

function renderStage() {
  const u = S.units[S.active];
  const v = view(u);
  renderBrnoRow();
  renderSide();
  $("allBtn").hidden = !(S.view === "res" && !(isMain(S.active) && allForMain()));
  $("allBtn").classList.toggle("on", S.showAll);
  document.querySelectorAll(".seg button").forEach(b => b.classList.toggle("on", b.dataset.view === S.view));
  if (S.view === "res") renderResults(v);
  else { $("detail")._scope = null; renderCoal($("detail"), v); }
  $("footLeft").innerHTML = S.view === "coal" ? `<b>Automatické přepínání pozastaveno</b>`
    : isMain(S.active) ? `<button type="button" class="pill-small fg" id="toDistricts">Městské části →</button>`
    : `Linka pod názvem = podíl sečtených okrsků`;
  $("footLeft").insertAdjacentHTML("beforeend", pagesHtml());
  $("seatNote").innerHTML = `${SEAT} = mandát · ` + (v.isRef ? "rok 2022, oficiální" : v.official ? "oficiální výsledek" : v.hasLive ? "přibližný výpočet dle současných výsledků" : "");
  $("themeBtn").textContent = S.theme === "dark" ? "Světlý režim" : "Tmavý režim";
  tick(0);
}

/* ---------------- mobil ---------------- */

function renderMobile() {
  $("mChips").innerHTML = S.units.map(u => `<a href="#u-${u.kod}">${esc(u.kratky)}</a>`).join("");
  $("mTheme").textContent = S.theme === "dark" ? "Světlý" : "Tmavý";
  const wrap = $("mUnits");
  keyed(wrap, S.units, u => u.kod, u => h(`<section class="m-unit" id="u-${u.kod}"></section>`), (el, u) => {
    const v = view(u);
    const d = v.live;
    const cp = d && d.celkem ? d.zprac / d.celkem * 100 : 0;
    const list = shown(v, (isMainKod(u.kod) && allForMain()) || S.showAll);
    const max = Math.max(...list.map(p => p.pct), 10);
    el.innerHTML = `
      <h2><a href="${esc(u.odkaz)}" target="_blank" rel="noopener">${esc(u.zobrazit)} <span>↗</span></a></h2>
      <div class="m-meta"><span>Okrsky <b>${d ? d.zprac + " / " + d.celkem : "–"}</b> ${d ? "(" + fmt(cp) + ")" : ""}</span>
        <span>Účast <b>${v.hasLive ? fmt(d.ucast) : "–"}</b></span><span>Mandátů <b>${seatsTotal(v) || "–"}</b></span><span>Aktualizováno <b>${timeTxt(v)}</b>${warnHtml(v)}</span></div>
      <div class="m-prog"><div style="width:${cp}%"></div></div>
      ${v.isRef ? `<div class="ref-note" style="margin-bottom:10px"><b>Zobrazuji výsledky 2022</b>, zatím nebyl sečten žádný okrsek</div>` : ""}
      ${v.d ? `<div class="hbars">${list.map(p => `
        <div class="hrow"><div class="n${p.ours ? " ours" : ""}">${esc(p.nazev)}</div>
          <div class="v">${fmt(p.pct)}<small>${seatsHtml(p.seats)}</small></div>
          <div class="track"><div style="width:${p.pct / max * 100}%;background:${p.color}"></div><span class="f5" style="left:${5 / max * 100}%"></span></div></div>`).join("")}</div>`
        : `<div class="m-empty"><b>Čekáme na data</b><span>Zatím nebyl sečten žádný okrsek</span></div>`}
      <div class="m-actions">
        ${v.hasLive ? `<button type="button" data-coal="${u.kod}">Sestavit koalici</button>` : ""}
        ${!(isMainKod(u.kod) && allForMain()) ? `<button type="button" class="sec" data-all>${S.showAll ? "Jen strany nad 3 %" : "Všechny strany"}</button>` : ""}
      </div>`;
  }, "m");
  $("mSeatNote").innerHTML = SEAT + " = mandát. Do sečtení všech okrsků jde o přibližný výpočet dle současných výsledků. Celky bez sečteného okrsku ukazují šedě výsledky 2022.";
  $("mSeatNote").insertAdjacentHTML("beforeend", pagesHtml());
  if (!$("mCoal").hidden) renderCoal($("mCoalBody"), view(S.units.find(u => u.kod === S.mCoalKod)));
}

/* ---------------- řízení ---------------- */

const isMobile = matchMedia("(max-width: 699px)");

function render() {
  if (isMobile.matches) renderMobile(); else renderStage();
}

function tick(dt) {
  if (S.view === "coal") { S.elapsed = 0; }
  else {
    S.elapsed += dt;
    if (S.elapsed >= S.intervalMs) { S.elapsed = 0; S.active = (S.active + 1) % S.units.length; render(); return; }
  }
  $("countdown").style.width = (S.view === "coal" ? 0 : S.elapsed / S.intervalMs * 100) + "%";
}

function select(i) { S.active = i; S.elapsed = 0; render(); }

function setTheme(t) {
  S.theme = t;
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem("vv-theme", t); } catch (e) {}
  $("detail")._scope = null; // barvy stran závisí na tématu
  render();
}

function bind() {
  $("side").addEventListener("click", e => { const r = e.target.closest("[data-i]"); if (r) select(Number(r.dataset.i)); });
  $("allBtn").onclick = () => { S.showAll = !S.showAll; render(); };
  document.querySelectorAll(".seg button").forEach(b => b.onclick = () => {
    if (S.view === b.dataset.view) return;
    S.view = b.dataset.view; S.elapsed = 0; render();
  });
  $("footLeft").addEventListener("click", e => { if (e.target.id === "toDistricts") select(1); });
  $("themeBtn").onclick = $("mTheme").onclick = () => setTheme(S.theme === "dark" ? "light" : "dark");
  $("mUnits").addEventListener("click", e => {
    const c = e.target.closest("[data-coal]");
    if (c) { S.mCoalKod = c.dataset.coal; $("mCoal").hidden = false; $("mCoalBody")._scope = null; render(); return; }
    if (e.target.closest("[data-all]")) { S.showAll = !S.showAll; render(); }
  });
  $("mCoalClose").onclick = () => { $("mCoal").hidden = true; };
  addEventListener("resize", () => { fit(); });
  isMobile.addEventListener("change", () => { $("detail")._scope = null; $("mUnits")._scope = null; render(); });
}

async function init() {
  const [cfg, barvy, zkratky] = await Promise.all([get(document.body.dataset.config || "config.json", "json"), get("barvy.json", "json"), get("zkratky.json", "json").catch(() => ({}))]);
  S.cfg = cfg; S.barvy = barvy; S.units = cfg.obce; S.zkratky = zkratky.nazvy || {};
  S.intervalMs = (Number(params.get("interval")) || cfg.interval_s || 12) * 1000;
  await Promise.all(S.units.map(async u => {
    try { S.ref[u.kod] = fromJson(await get(`mock/2022/latest/${u.kod}.json`, "json")); } catch (e) {}
  }));
  fit(); bind();
  render();
  await refresh();
  setInterval(refresh, REFRESH_MS);
  let last = performance.now();
  setInterval(() => { const now = performance.now(); if (!isMobile.matches) tick(now - last); last = now; }, 250);
}

init();
