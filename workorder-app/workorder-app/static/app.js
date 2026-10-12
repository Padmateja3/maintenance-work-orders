// Minimal single-page UI. Plain JS, no build step.
// All dynamic content goes through h() / textContent, never innerHTML, so API data cannot inject markup.
"use strict";

const app = document.getElementById("app");
const PRIORITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];
const STATUSES = ["OPEN", "ASSIGNED", "IN_PROGRESS", "COMPLETED", "CANCELLED"];
const FLOW = ["OPEN", "ASSIGNED", "IN_PROGRESS", "COMPLETED"];
const PAGE_SIZE = 20;

// ---------------------------------------------------------------- helpers --
function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false || k === "value") continue;
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  if (attrs.value != null) el.value = attrs.value; // after children, so <select> options exist
  return el;
}

class ApiError extends Error {
  constructor(status, error) {
    super(error?.message || `Request failed (${status})`);
    this.status = status;
    this.details = error?.details || [];
  }
}

async function api(method, path, body) {
  let res;
  try {
    res = await fetch("/api" + path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, { message: "Cannot reach the server." });
  }
  let data = null;
  try { data = await res.json(); } catch { /* empty body */ }
  if (!res.ok) throw new ApiError(res.status, data?.error);
  return data;
}

const qs = (obj) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(obj)) if (v !== "" && v != null) p.set(k, v);
  const s = p.toString();
  return s ? "?" + s : "";
};

const label = (s) => (s || "").replaceAll("_", " ");
const badge = (cls, text) => h("span", { class: `badge ${cls}` }, label(text));
const priorityBadge = (p) => badge(`p-${p}`, p);
const statusBadge = (s) => badge(`s-${s}`, s);
const fmtDate = (iso) => (iso ? iso.slice(0, 10) : "–");
const fmtTime = (iso) => (iso ? iso.replace("T", " ").replace("Z", " UTC") : "–");
const todayLocal = () => { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 10); };
const option = (value, text, selected) => h("option", { value, selected: selected ? true : null }, text ?? value);

function errorBanner(err) {
  const items = (err.details || []).filter((d) => d.message && d.message !== err.message);
  return h("div", { class: "banner error", role: "alert" }, err.message,
    items.length ? h("ul", {}, items.map((d) => h("li", {}, d.field ? `${d.field}: ${d.message}` : d.message))) : null);
}
const okBanner = (text) => h("div", { class: "banner ok" }, text);

function setNav(name) {
  document.querySelectorAll("[data-nav]").forEach((a) => a.classList.toggle("active", a.dataset.nav === name));
}
function show(...nodes) { app.replaceChildren(...nodes.flat()); }

// ---------------------------------------------------------- screen 1: list --
const listState = { q: "", status: "", priority: "", offset: 0 };

async function renderList() {
  setNav("list");
  const results = h("div");
  const pager = h("div", { class: "pager" });
  let timer;

  const onFilter = (key) => (e) => { listState[key] = e.target.value; listState.offset = 0; load(); };
  const search = h("input", { type: "search", placeholder: "Search number, asset, description, technician…", value: listState.q, "aria-label": "Search", size: 38,
    oninput: (e) => { listState.q = e.target.value; listState.offset = 0; clearTimeout(timer); timer = setTimeout(load, 250); } });
  const status = h("select", { "aria-label": "Status", onchange: onFilter("status"), value: listState.status },
    option("", "All statuses"), STATUSES.map((s) => option(s, label(s))));
  const priority = h("select", { "aria-label": "Priority", onchange: onFilter("priority"), value: listState.priority },
    option("", "All priorities"), PRIORITIES.map((p) => option(p)));

  show(
    h("div", { class: "row spread" }, h("h1", {}, "Maintenance work orders"),
      h("a", { class: "btn primary", href: "#/new" }, "+ New")),
    h("div", { class: "row", style: "margin-bottom:14px" }, search, status, priority),
    results, pager);

  async function load() {
    try {
      const data = await api("GET", "/work-orders" + qs({ q: listState.q.trim(), status: listState.status,
        priority: listState.priority, limit: PAGE_SIZE, offset: listState.offset }));
      const rows = data.items.map((w) => h("tr", { class: "click", tabindex: 0,
        onclick: () => (location.hash = `#/work-orders/${w.id}`),
        onkeydown: (e) => e.key === "Enter" && (location.hash = `#/work-orders/${w.id}`) },
        h("td", {}, h("a", { href: `#/work-orders/${w.id}`, onclick: (e) => e.stopPropagation() }, w.work_order_number)),
        h("td", {}, w.asset.asset_id), h("td", {}, w.maintenance_type.name),
        h("td", {}, priorityBadge(w.priority)), h("td", {}, statusBadge(w.status)),
        h("td", {}, w.technician ? w.technician.name : h("span", { class: "muted" }, "Unassigned")),
        h("td", {}, w.scheduled_date)));
      results.replaceChildren(rows.length
        ? h("div", { class: "table-wrap" }, h("table", {},
            h("thead", {}, h("tr", {}, ["Work order", "Asset", "Type", "Priority", "Status", "Technician", "Scheduled"].map((c) => h("th", {}, c)))),
            h("tbody", {}, rows)))
        : h("p", { class: "muted" }, "No work orders match."));
      const from = data.total ? data.offset + 1 : 0;
      const to = data.offset + data.items.length;
      pager.replaceChildren(h("span", { class: "muted small" }, `${from}–${to} of ${data.total}`),
        h("button", { disabled: data.offset === 0, onclick: () => { listState.offset = Math.max(0, data.offset - PAGE_SIZE); load(); } }, "Previous"),
        h("button", { disabled: to >= data.total, onclick: () => { listState.offset = data.offset + PAGE_SIZE; load(); } }, "Next"));
    } catch (err) { results.replaceChildren(errorBanner(err)); }
  }
  load();
}

// --------------------------------------------------------- screen 2: create --
async function renderNew() {
  setNav("list");
  show(h("p", { class: "muted" }, "Loading…"));
  let assets, techs, types;
  try {
    [assets, techs, types] = await Promise.all([
      api("GET", "/assets?limit=200"), api("GET", "/technicians?status=ACTIVE&limit=200"), api("GET", "/maintenance-types")]);
  } catch (err) { return show(errorBanner(err)); }

  const banner = h("div");
  const f = {
    asset: h("select", { required: true }, option("", "Select an asset…"),
      assets.items.map((a) => option(a.id, `${a.asset_id} — ${a.manufacturer} ${a.model}${a.status === "OUT_OF_SERVICE" ? " (OUT OF SERVICE)" : ""}`))),
    type: h("select", { required: true }, option("", "Select a type…"),
      types.map((t) => option(t.id, t.name + (t.is_emergency ? " (emergency)" : "")))),
    priority: h("select", { required: true }, PRIORITIES.map((p) => option(p, p, p === "MEDIUM"))),
    tech: h("select", {}, option("", "— Unassigned —"), techs.items.map((t) => option(t.id, `${t.name} (${t.skill})`))),
    date: h("input", { type: "date", required: true, min: todayLocal(), value: todayLocal() }),
    number: h("input", { placeholder: "Leave blank to auto-generate", maxlength: 40 }),
    desc: h("textarea", { maxlength: 2000, placeholder: "What needs to be done?" }),
  };
  const critHint = h("span", { class: "hint" }, "");
  const syncHint = () => {
    critHint.textContent = f.priority.value === "CRITICAL" ? "CRITICAL work orders must have a technician." : "";
    f.tech.required = f.priority.value === "CRITICAL";
  };
  f.priority.addEventListener("change", syncHint);
  const oosHint = h("span", { class: "hint" }, "");
  const syncOos = () => {
    const a = assets.items.find((x) => String(x.id) === f.asset.value);
    const t = types.find((x) => String(x.id) === f.type.value);
    oosHint.textContent = a && a.status === "OUT_OF_SERVICE" && !(t && t.is_emergency)
      ? "This asset is out of service — only emergency maintenance types are accepted." : "";
  };
  f.asset.addEventListener("change", syncOos); f.type.addEventListener("change", syncOos);

  const submit = h("button", { class: "primary", type: "submit" }, "Create work order");
  const form = h("form", { class: "card grid", novalidate: false, onsubmit: async (e) => {
    e.preventDefault();
    submit.disabled = true; banner.replaceChildren();
    try {
      const wo = await api("POST", "/work-orders", {
        asset_id: Number(f.asset.value), maintenance_type_id: Number(f.type.value), priority: f.priority.value,
        technician_id: f.tech.value ? Number(f.tech.value) : null, scheduled_date: f.date.value,
        description: f.desc.value, work_order_number: f.number.value.trim() || null });
      location.hash = `#/work-orders/${wo.id}`;
    } catch (err) { banner.replaceChildren(errorBanner(err)); submit.disabled = false; window.scrollTo(0, 0); }
  } },
    h("label", {}, "Asset", f.asset, oosHint), h("label", {}, "Maintenance type", f.type),
    h("label", {}, "Priority", f.priority), h("label", {}, "Technician", f.tech, critHint),
    h("label", {}, "Scheduled date", f.date), h("label", {}, "Work order number", f.number),
    h("label", { class: "wide" }, "Description", f.desc),
    h("div", { class: "wide row" }, submit, h("a", { class: "btn", href: "#/" }, "Cancel")));
  show(h("h1", {}, "New work order"), banner, form);
}

// -------------------------------------------------------- screen 3: details --
async function renderDetail(id) {
  setNav("list");
  const banner = h("div");
  const box = h("div");
  show(h("p", {}, h("a", { href: "#/" }, "← All work orders")), banner, box);

  async function load(notice) {
    try {
      const [wo, events, techs] = await Promise.all([
        api("GET", `/work-orders/${id}`), api("GET", `/work-orders/${id}/events`),
        api("GET", "/technicians?status=ACTIVE&limit=200")]);
      draw(wo, events, techs.items, notice);
    } catch (err) { box.replaceChildren(errorBanner(err)); }
  }

  async function change(patch, notice) {
    banner.replaceChildren();
    try { await api("PUT", `/work-orders/${id}`, patch); await load(notice); }
    catch (err) { banner.replaceChildren(errorBanner(err)); window.scrollTo(0, 0); }
  }

  function draw(wo, events, techs, notice) {
    banner.replaceChildren(...(notice ? [okBanner(notice)] : []));
    const idx = FLOW.indexOf(wo.status);
    const stepper = h("div", { class: "stepper", "aria-label": "Progress" },
      FLOW.map((s, i) => h("span", { class: "step" + (s === wo.status ? " now" : i < idx ? " done" : "") }, label(s))),
      wo.status === "CANCELLED" ? h("span", { class: "step now" }, "CANCELLED") : null);

    const facts = h("dl", { class: "facts" },
      fact("Asset", h("span", {}, wo.asset.asset_id, " — ", wo.asset.manufacturer, " ", wo.asset.model, " ",
        wo.asset.status === "OUT_OF_SERVICE" ? badge("p-CRITICAL", "OUT OF SERVICE") : null,
        " ", h("a", { href: `#/assets/${wo.asset_id}` }, "history"))),
      fact("Maintenance type", wo.maintenance_type.name + (wo.maintenance_type.is_emergency ? " (emergency)" : "")),
      fact("Priority", priorityBadge(wo.priority)), fact("Status", statusBadge(wo.status)),
      fact("Technician", wo.technician ? `${wo.technician.name} (${wo.technician.skill})` : "Unassigned"),
      fact("Scheduled date", wo.scheduled_date), fact("Created", fmtTime(wo.created_at)),
      fact("Completed", fmtTime(wo.completed_at)),
      fact("Description", wo.description || h("span", { class: "muted" }, "—")));

    // Valid actions come from the server's allowed_transitions, so the UI never offers an illegal move.
    const actions = h("div", { class: "row" });
    if (wo.allowed_transitions.includes("ASSIGNED") || wo.status === "ASSIGNED") {
      const sel = h("select", { "aria-label": "Technician" }, option("", "Select technician…"),
        techs.map((t) => option(t.id, `${t.name} (${t.skill})`, wo.technician_id === t.id)));
      actions.append(sel, h("button", { class: "primary", onclick: () => sel.value
        ? change({ technician_id: Number(sel.value) }, wo.status === "OPEN" ? "Technician assigned." : "Technician changed.")
        : (banner.replaceChildren(errorBanner({ message: "Choose a technician first." }))) },
        wo.status === "OPEN" ? "Assign" : "Reassign"));
    }
    if (wo.allowed_transitions.includes("IN_PROGRESS"))
      actions.append(h("button", { class: "primary", onclick: () => change({ status: "IN_PROGRESS" }, "Work started.") }, "Start work"));
    if (wo.allowed_transitions.includes("COMPLETED"))
      actions.append(h("button", { class: "primary", onclick: () => change({ status: "COMPLETED" }, "Work order completed.") }, "Mark complete"));
    if (wo.allowed_transitions.includes("CANCELLED"))
      actions.append(h("button", { class: "danger", onclick: () => confirm("Cancel this work order? This cannot be undone.") && change({ status: "CANCELLED" }, "Work order cancelled.") }, "Cancel work order"));
    const terminal = !wo.allowed_transitions.length;

    box.replaceChildren(
      h("h1", {}, wo.work_order_number), stepper, h("div", { class: "card" }, facts),
      h("h2", {}, "Actions"),
      terminal ? h("p", { class: "muted" }, `This work order is ${label(wo.status).toLowerCase()} and can no longer be changed.`) : h("div", { class: "card" }, actions),
      h("h2", {}, "History"),
      h("div", { class: "card" }, h("ul", { class: "timeline" }, events.map(describeEvent))));
  }
  load();
}

const fact = (term, value) => h("div", {}, h("dt", {}, term), h("dd", {}, value));

function describeEvent(e) {
  const what = e.event_type === "CREATED" ? `Created (${label(e.to_status)})`
    : e.event_type === "STATUS_CHANGED" ? `${label(e.from_status)} → ${label(e.to_status)}`
    : e.event_type === "ASSIGNED" ? "Technician changed" : (e.note || "Updated");
  return h("li", {}, h("strong", {}, what), e.technician_name ? ` · ${e.technician_name}` : "",
    h("span", { class: "muted small" }, "  ", fmtTime(e.created_at)));
}

// ----------------------------------------------- registry (assets & techs) --
async function renderRegistry() {
  setNav("registry");
  const banner = h("div");
  const assetBox = h("div"), techBox = h("div");
  show(h("h1", {}, "Assets & technicians"), banner, h("h2", {}, "Assets"), assetFormCard(), assetBox,
    h("h2", {}, "Technicians"), techFormCard(), techBox);
  loadAssets(); loadTechs();

  const fail = (err) => { banner.replaceChildren(errorBanner(err)); window.scrollTo(0, 0); };

  async function loadAssets() {
    try {
      const { items } = await api("GET", "/assets?limit=200");
      assetBox.replaceChildren(items.length ? h("div", { class: "table-wrap" }, h("table", {},
        h("thead", {}, h("tr", {}, ["Asset ID", "Type", "Manufacturer / model", "Serial", "Hours", "Cycles", "Status", ""].map((c) => h("th", {}, c)))),
        h("tbody", {}, items.map((a) => h("tr", {},
          h("td", {}, a.asset_id), h("td", {}, a.asset_type), h("td", {}, `${a.manufacturer} ${a.model}`), h("td", {}, a.serial_number),
          h("td", {}, a.usage_hours), h("td", {}, a.usage_cycles),
          h("td", {}, h("select", { "aria-label": `Status of ${a.asset_id}`, value: a.status,
            onchange: async (e) => { banner.replaceChildren(); try { await api("PUT", `/assets/${a.id}`, { status: e.target.value }); banner.replaceChildren(okBanner(`${a.asset_id} is now ${label(e.target.value)}.`)); } catch (err) { fail(err); loadAssets(); } } },
            ["ACTIVE", "INACTIVE", "OUT_OF_SERVICE"].map((s) => option(s, label(s))))),
          h("td", {}, h("a", { href: `#/assets/${a.id}` }, "History"))))))) : h("p", { class: "muted" }, "No assets yet."));
    } catch (err) { fail(err); }
  }

  async function loadTechs() {
    try {
      const { items } = await api("GET", "/technicians?limit=200");
      techBox.replaceChildren(items.length ? h("div", { class: "table-wrap" }, h("table", {},
        h("thead", {}, h("tr", {}, ["Name", "Skill", "Status"].map((c) => h("th", {}, c)))),
        h("tbody", {}, items.map((t) => h("tr", {}, h("td", {}, t.name), h("td", {}, t.skill),
          h("td", {}, h("select", { "aria-label": `Status of ${t.name}`, value: t.status,
            onchange: async (e) => { banner.replaceChildren(); try { await api("PUT", `/technicians/${t.id}`, { status: e.target.value }); } catch (err) { fail(err); loadTechs(); } } },
            ["ACTIVE", "INACTIVE", "ON_LEAVE"].map((s) => option(s, label(s)))))))))) : h("p", { class: "muted" }, "No technicians yet."));
    } catch (err) { fail(err); }
  }

  function assetFormCard() {
    const v = {};
    const field = (key, text, attrs = {}) => h("label", {}, text, (v[key] = h("input", attrs)));
    const form = h("form", { class: "card grid", onsubmit: async (e) => {
      e.preventDefault(); banner.replaceChildren();
      try {
        const a = await api("POST", "/assets", { asset_id: v.asset_id.value, asset_type: v.asset_type.value, manufacturer: v.manufacturer.value,
          model: v.model.value, serial_number: v.serial_number.value, usage_hours: Number(v.usage_hours.value || 0),
          usage_cycles: Number(v.usage_cycles.value || 0), status: v.status.value });
        form.reset(); banner.replaceChildren(okBanner(`Asset ${a.asset_id} registered.`)); loadAssets();
      } catch (err) { fail(err); }
    } },
      field("asset_id", "Asset ID", { required: true, placeholder: "AST-1024" }), field("asset_type", "Asset type", { required: true, placeholder: "Pump" }),
      field("manufacturer", "Manufacturer", { required: true }), field("model", "Model", { required: true }),
      field("serial_number", "Serial number", { required: true }),
      field("usage_hours", "Usage hours", { type: "number", min: 0, step: "any", value: 0 }),
      field("usage_cycles", "Usage cycles", { type: "number", min: 0, step: 1, value: 0 }),
      h("label", {}, "Status", (v.status = h("select", {}, ["ACTIVE", "INACTIVE", "OUT_OF_SERVICE"].map((s) => option(s, label(s)))))),
      h("div", { class: "wide" }, h("button", { class: "primary", type: "submit" }, "Register asset")));
    return form;
  }

  function techFormCard() {
    const v = {};
    const form = h("form", { class: "card grid", onsubmit: async (e) => {
      e.preventDefault(); banner.replaceChildren();
      try {
        const t = await api("POST", "/technicians", { name: v.name.value, skill: v.skill.value, status: v.status.value });
        form.reset(); banner.replaceChildren(okBanner(`Technician ${t.name} registered.`)); loadTechs();
      } catch (err) { fail(err); }
    } },
      h("label", {}, "Name", (v.name = h("input", { required: true }))), h("label", {}, "Skill", (v.skill = h("input", { required: true, placeholder: "Electrical" }))),
      h("label", {}, "Status", (v.status = h("select", {}, ["ACTIVE", "INACTIVE", "ON_LEAVE"].map((s) => option(s, label(s)))))),
      h("div", { class: "wide" }, h("button", { class: "primary", type: "submit" }, "Register technician")));
    return form;
  }
}

// ------------------------------------------------------ asset history view --
async function renderAssetHistory(id) {
  setNav("registry");
  show(h("p", { class: "muted" }, "Loading…"));
  try {
    const data = await api("GET", `/assets/${id}/history?limit=200`);
    const a = data.asset, s = data.summary;
    show(h("p", {}, h("a", { href: "#/registry" }, "← Assets & technicians")),
      h("h1", {}, `Maintenance history — ${a.asset_id}`),
      h("div", { class: "card" }, h("dl", { class: "facts" },
        fact("Asset", `${a.asset_type} · ${a.manufacturer} ${a.model}`), fact("Serial number", a.serial_number),
        fact("Status", label(a.status)), fact("Usage", `${a.usage_hours} h · ${a.usage_cycles} cycles`),
        fact("Work orders", s.total), fact("Last completed", fmtTime(s.last_completed_at)),
        fact("By status", Object.entries(s.by_status).map(([k, n]) => `${label(k)}: ${n}`).join(" · ") || "–"))),
      data.items.length ? h("div", { class: "table-wrap" }, h("table", {},
        h("thead", {}, h("tr", {}, ["Work order", "Type", "Priority", "Status", "Technician", "Scheduled", "Completed"].map((c) => h("th", {}, c)))),
        h("tbody", {}, data.items.map((w) => h("tr", {},
          h("td", {}, h("a", { href: `#/work-orders/${w.id}` }, w.work_order_number)), h("td", {}, w.maintenance_type.name),
          h("td", {}, priorityBadge(w.priority)), h("td", {}, statusBadge(w.status)),
          h("td", {}, w.technician ? w.technician.name : "–"), h("td", {}, w.scheduled_date), h("td", {}, fmtDate(w.completed_at)))))))
        : h("p", { class: "muted" }, "No work orders for this asset yet."));
  } catch (err) { show(errorBanner(err)); }
}

// ------------------------------------------------------------------ router --
function route() {
  const hash = location.hash.replace(/^#/, "") || "/";
  let m;
  if (hash === "/") return renderList();
  if (hash === "/new") return renderNew();
  if (hash === "/registry") return renderRegistry();
  if ((m = hash.match(/^\/work-orders\/(\d+)$/))) return renderDetail(m[1]);
  if ((m = hash.match(/^\/assets\/(\d+)$/))) return renderAssetHistory(m[1]);
  show(h("h1", {}, "Page not found"), h("a", { href: "#/" }, "Back to work orders"));
}
window.addEventListener("hashchange", route);
route();
