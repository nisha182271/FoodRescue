// FoodRescue frontend. Vanilla JS, no build step. All server text goes in via textContent.
const TOKEN_KEY = "fr_token";
const $ = (id) => document.getElementById(id);
const VIEWS = ["home", "donations", "login", "register", "dashboard", "impact", "safety", "admin"];
const state = { user: null, zones: {}, safety: null, donations: [], claimed: [] };

// Build an element. Strings become text nodes; null/false/undefined children and attributes are skipped.
function h(tag, props, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v === false || v === null || v === undefined) continue;
    if (k === "class") node.className = v;
    else node.setAttribute(k, v === true ? "" : String(v));
  }
  for (const c of children) if (c !== null && c !== undefined && c !== false) node.append(c);
  return node;
}

function toast(msg, kind = "success") {
  const el = $("toast");
  el.textContent = msg;
  el.className = "toast show " + kind;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.remove("show"), 3500);
}

function errorText(data, status) {
  const d = data && data.detail;
  if (Array.isArray(d)) return d.map((x) => x.msg || JSON.stringify(x)).join("; ");
  if (typeof d === "string") return d;
  return "Request failed (" + status + ")";
}

// JSON API helper. Adds the Bearer token when one is stored. Throws Error with .status on failure.
async function api(path, opts = {}) {
  const headers = {};
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) headers["Authorization"] = "Bearer " + token;
  let res;
  try {
    res = await fetch(path, {
      method: opts.method || (opts.body !== undefined ? "POST" : "GET"),
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    });
  } catch (e) {
    throw new Error("Network error: " + e.message);
  }
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch (e) { data = text; }
  if (!res.ok) {
    const err = new Error(errorText(data, res.status));
    err.status = res.status;
    throw err;
  }
  return data;
}

const fmtDate = (iso) => {
  const d = new Date(iso);
  return isNaN(d) ? "-" : d.toLocaleString();
};
const zoneName = (id) => state.zones[id] || ("Zone " + id);
const toIso = (v) => new Date(v).toISOString(); // datetime-local -> UTC ISO string ending in Z

function badge(status) {
  const label = String(status || "posted");
  return h("span", { class: "badge badge-" + label.replace(/[^a-z_-]/gi, "").toLowerCase() }, label);
}

function setUser(user) {
  state.user = user || null;
  $("btn-login-link").hidden = !!user;
  $("btn-register-link").hidden = !!user;
  $("btn-logout").hidden = !user;
  $("user-name").hidden = !user;
  $("user-name").textContent = user ? user.name : "";
}

function saveSession(data) {
  localStorage.setItem(TOKEN_KEY, data.access_token);
  setUser(data.user);
}

// ---- Navigation ----
function closeNav() {
  $("nav-links").classList.remove("open");
  $("nav-toggle").setAttribute("aria-expanded", "false");
}

function route() {
  let name = location.hash.slice(1);
  if (!VIEWS.includes(name)) name = "home";
  document.querySelectorAll(".view").forEach((v) => { v.hidden = v.dataset.view !== name; });
  document.querySelectorAll("[data-link]").forEach((a) => a.classList.toggle("active", a.dataset.link === name));
  closeNav();
  const loaders = {
    donations: loadDonations, dashboard: loadDashboard, impact: loadImpact,
    safety: loadSafety, admin: loadAdmin,
  };
  if (loaders[name]) loaders[name]();
}

// ---- Meta: zones and safety ----
async function loadZones() {
  try {
    const list = await api("api/meta/zones");
    const zones = Array.isArray(list) ? list : (list.zones || []);
    state.zones = {};
    zones.forEach((z) => { state.zones[z.id] = z.name || ("Zone " + z.id); });
    document.querySelectorAll(".zone-select").forEach((sel) => {
      const opts = [h("option", { value: "" }, "Select zone")];
      zones.forEach((z) => opts.push(h("option", { value: z.id }, zoneName(z.id))));
      sel.replaceChildren(...opts);
    });
    const filter = $("filter-zone");
    zones.forEach((z) => filter.append(h("option", { value: z.id }, zoneName(z.id))));
  } catch (err) {
    toast("Could not load zones: " + err.message, "error");
  }
}

async function loadSafetyInfo() {
  try {
    state.safety = await api("api/meta/safety");
    const types = state.safety.storage_types || [];
    const sel = document.querySelector('select[name="storage_type"]');
    if (types.length) {
      sel.replaceChildren(...types.map((t) => h("option", { value: t }, String(t).charAt(0).toUpperCase() + String(t).slice(1))));
    }
    $("disclaimer").textContent = state.safety.disclaimer || $("disclaimer").textContent;
  } catch (err) {
    // Safety info is optional; the footer keeps its default text.
  }
}

function loadSafety() {
  const s = state.safety || {};
  $("storage-list").replaceChildren(...(s.storage_types || []).map((t) => h("li", {}, String(t))));
  $("safety-text").textContent = s.disclaimer || "Safety information is currently unavailable.";
}

// ---- Session ----
async function restoreSession() {
  if (!localStorage.getItem(TOKEN_KEY)) return setUser(null);
  try {
    const me = await api("api/me");
    setUser(me.user || me);
  } catch (err) {
    if (err.status === 401) localStorage.removeItem(TOKEN_KEY);
    setUser(null);
  }
}

async function onLogin(e) {
  e.preventDefault();
  const fd = new FormData(e.target);
  try {
    const data = await api("api/auth/login", { body: { name: fd.get("name").trim(), password: fd.get("password") } });
    saveSession(data);
    toast("Welcome back, " + data.user.name);
    location.hash = "#dashboard";
  } catch (err) {
    toast(err.message, "error");
  }
}

async function onRegister(e) {
  e.preventDefault();
  const fd = new FormData(e.target);
  const body = { name: fd.get("name").trim(), password: fd.get("password"), role: fd.get("role") };
  const zone = fd.get("zone_id");
  if (zone) body.zone_id = Number(zone);
  try {
    const data = await api("api/auth/register", { body });
    saveSession(data);
    toast("Account created");
    location.hash = "#dashboard";
  } catch (err) {
    toast(err.message, "error");
  }
}

function onLogout() {
  localStorage.removeItem(TOKEN_KEY);
  state.claimed = [];
  setUser(null);
  toast("Logged out");
  location.hash = "#home";
}

// ---- Donations (public) ----
async function loadDonations() {
  const msg = $("donation-msg");
  const params = new URLSearchParams();
  const cat = $("filter-category").value;
  const zone = $("filter-zone").value;
  if (cat) params.set("category", cat);
  if (zone) params.set("zone_id", zone);
  const qs = params.toString();
  msg.hidden = false;
  msg.textContent = "Loading…";
  try {
    state.donations = await api("api/donations" + (qs ? "?" + qs : ""));
  } catch (err) {
    state.donations = [];
    msg.textContent = "Could not load donations.";
    toast(err.message, "error");
    $("donation-grid").replaceChildren();
    return;
  }
  const sel = $("filter-category");
  const have = new Set([...sel.options].map((o) => o.value));
  state.donations.forEach((d) => {
    if (d.category && !have.has(d.category)) {
      have.add(d.category);
      sel.append(h("option", { value: d.category }, d.category));
    }
  });
  renderDonations();
}

function donationCard(d) {
  const allergens = Array.isArray(d.allergens) && d.allergens.length ? d.allergens.join(", ") : "None listed";
  return h("article", { class: "card" },
    h("h3", {}, d.food_name),
    h("p", { class: "meta" }, "Category: " + d.category),
    h("p", { class: "meta" }, d.quantity_meals + " meals · " + d.quantity_kg + " kg"),
    h("p", { class: "meta" }, "Storage: " + d.storage_type + " · Zone: " + zoneName(d.zone_id)),
    h("p", { class: "meta" }, "Pickup by: " + fmtDate(d.pickup_by)),
    h("p", { class: "meta" }, "Allergens: " + allergens));
}

// Client-side text search over the server-filtered list.
function renderDonations() {
  const term = $("search").value.trim().toLowerCase();
  const list = state.donations.filter((d) => String(d.food_name || "").toLowerCase().includes(term));
  $("donation-grid").replaceChildren(...list.map(donationCard));
  const msg = $("donation-msg");
  msg.hidden = list.length > 0;
  msg.textContent = "No donations match your filters.";
}

// ---- Dashboard ----
function loadDashboard() {
  const u = state.user;
  $("dash-guest").hidden = !!u;
  $("dash-donor").hidden = !(u && u.role === "donor");
  $("dash-receiver").hidden = !(u && u.role === "receiver");
  if (!u) return;
  if (u.role === "donor") loadMine();
  if (u.role === "receiver") loadMatches();
  renderClaimed();
}

async function loadMine() {
  try {
    const items = await api("api/donations/mine");
    const rows = items.map((d) => h("tr", {},
      h("td", {}, d.food_name),
      h("td", {}, d.category),
      h("td", {}, String(d.quantity_meals)),
      h("td", {}, fmtDate(d.pickup_by)),
      h("td", {}, badge(d.status))));
    if (!rows.length) rows.push(h("tr", {}, h("td", { colspan: 5, class: "muted" }, "No donations posted yet.")));
    $("mine-body").replaceChildren(...rows);
  } catch (err) {
    toast("Could not load your donations: " + err.message, "error");
  }
}

async function onCreateDonation(e) {
  e.preventDefault();
  const form = e.target;
  const fd = new FormData(form);
  try {
    const body = {
      food_name: fd.get("food_name").trim(),
      category: fd.get("category").trim(),
      quantity_kg: Number(fd.get("quantity_kg")),
      quantity_meals: parseInt(fd.get("quantity_meals"), 10),
      prepared_at: toIso(fd.get("prepared_at")),
      pickup_by: toIso(fd.get("pickup_by")),
      storage_type: fd.get("storage_type"),
      zone_id: Number(fd.get("zone_id")),
      allergens: String(fd.get("allergens") || "").split(",").map((s) => s.trim()).filter(Boolean),
      notes: fd.get("notes").trim() || null,
    };
    await api("api/donations", { body });
    toast("Donation posted");
    form.reset();
    loadMine();
  } catch (err) {
    toast(err.message, "error");
  }
}

async function loadMatches() {
  const msg = $("matches-msg");
  msg.hidden = false;
  msg.textContent = "Loading…";
  try {
    const items = await api("api/matches");
    msg.hidden = items.length > 0;
    msg.textContent = "No matches yet.";
    $("matches-list").replaceChildren(...items.map(matchCard));
  } catch (err) {
    msg.textContent = "Could not load matches.";
    toast(err.message, "error");
  }
}

function matchCard(m) {
  const d = m.donation || {};
  const breakdown = m.breakdown || m.score_breakdown || {};
  const lines = Object.entries(breakdown).map(([k, v]) =>
    h("li", {}, k.replace(/_/g, " ") + ": " + (typeof v === "object" ? JSON.stringify(v) : String(v))));
  const btn = h("button", { class: "btn btn-primary btn-sm", type: "button" }, "Claim");
  btn.addEventListener("click", () => claim(d.id, d));
  return h("article", { class: "card" },
    h("h3", {}, d.food_name || "Donation"),
    h("p", { class: "meta" }, "Score: " + (m.score ?? "n/a")),
    lines.length ? h("ul", { class: "score-list" }, ...lines) : null,
    h("p", { class: "meta" }, (d.quantity_meals ?? "?") + " meals · " + (d.category || "")),
    h("p", { class: "meta" }, "Pickup by: " + fmtDate(d.pickup_by)),
    h("div", { class: "actions" }, btn));
}

async function claim(id, d) {
  try {
    await api("api/donations/" + id + "/claim", { method: "POST" });
    toast("Donation claimed");
    state.claimed = state.claimed.filter((c) => c.id !== id);
    state.claimed.push({ id, food_name: d.food_name || "Donation", status: "claimed" });
    loadMatches();
    renderClaimed();
  } catch (err) {
    toast(err.message, "error");
  }
}

async function updateStatus(item, to) {
  try {
    await api("api/donations/" + item.id + "/status", { body: { to_status: to } });
    item.status = to;
    toast("Status updated to " + to);
    renderClaimed();
  } catch (err) {
    toast(err.message, "error");
  }
}

function claimedCard(item) {
  const collect = h("button", { class: "btn btn-outline btn-sm", type: "button", disabled: item.status !== "claimed" }, "Mark collected");
  const deliver = h("button", { class: "btn btn-outline btn-sm", type: "button", disabled: item.status !== "collected" }, "Mark delivered");
  collect.addEventListener("click", () => updateStatus(item, "collected"));
  deliver.addEventListener("click", () => updateStatus(item, "delivered"));
  return h("article", { class: "card" }, h("h3", {}, item.food_name), badge(item.status),
    h("div", { class: "actions" }, collect, deliver));
}

function renderClaimed() {
  const cards = state.claimed.map(claimedCard);
  if (!cards.length) cards.push(h("p", { class: "muted" }, "Nothing claimed yet in this session."));
  $("claimed-list").replaceChildren(...cards);
}

// ---- Impact and admin ----
function renderStats(target, data) {
  const obj = data && typeof data === "object" ? data : {};
  target.replaceChildren(...Object.entries(obj).map(([k, v]) =>
    h("div", { class: "stat" },
      h("div", { class: "value" }, typeof v === "object" ? JSON.stringify(v) : String(v)),
      h("div", { class: "label" }, k.replace(/_/g, " ")))));
}

async function loadImpact() {
  try {
    renderStats($("impact-stats"), await api("api/impact"));
  } catch (err) {
    toast("Could not load impact: " + err.message, "error");
  }
}

async function loadAdmin() {
  try {
    const [impact, donations] = await Promise.all([api("api/impact"), api("api/donations")]);
    renderStats($("admin-stats"), Object.assign({}, impact, { posted_donations: Array.isArray(donations) ? donations.length : "n/a" }));
  } catch (err) {
    toast("Could not load admin stats: " + err.message, "error");
  }
}

// ---- Wiring ----
function bindEvents() {
  $("nav-toggle").addEventListener("click", () => {
    const open = $("nav-links").classList.toggle("open");
    $("nav-toggle").setAttribute("aria-expanded", String(open));
  });
  $("login-form").addEventListener("submit", onLogin);
  $("register-form").addEventListener("submit", onRegister);
  $("btn-logout").addEventListener("click", onLogout);
  $("donation-form").addEventListener("submit", onCreateDonation);
  $("filter-form").addEventListener("submit", (e) => e.preventDefault());
  $("filter-category").addEventListener("change", loadDonations);
  $("filter-zone").addEventListener("change", loadDonations);
  $("search").addEventListener("input", renderDonations);
}

async function init() {
  bindEvents();
  await Promise.all([loadZones(), loadSafetyInfo(), restoreSession()]);
  window.addEventListener("hashchange", route);
  route();
}

init();
