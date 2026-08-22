"use strict";
/* Worldwalker RPG — frontend engine: API glue, rendering, animation, sound. */

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------
async function api(path, opts) {
  const res = await fetch(path, opts);
  let data = {};
  try { data = await res.json(); } catch (e) { /* empty body */ }
  if (!res.ok) throw new Error(data.error || res.statusText || "Request failed");
  return data;
}
const apiGet = (path) => api(path);
const apiPost = (path, body) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
const apiForm = (path, body) => api(path, { method: "POST", body });

// Phone-host helper and future hosted-PWA support. API calls remain network
// only, so a phone never continues an outdated simulation while disconnected.
function initPhoneMode() {
  const params = new URLSearchParams(window.location.search);
  const phoneUrl = params.get("lan_url");
  if (params.get("phone_host") === "1" && phoneUrl) {
    document.body.classList.add("phone-hosting");
    $("#phone-host-url").textContent = phoneUrl;
    $("#phone-host-banner").hidden = false;
    $("#btn-copy-phone-url").addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(phoneUrl); showToast("Phone address copied.", "notify"); }
      catch (_) { window.prompt("Copy this address:", phoneUrl); }
    });
  }
  if ("serviceWorker" in navigator && window.isSecureContext) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }
}
initPhoneMode();

// ---------------------------------------------------------------------------
// Global app state
// ---------------------------------------------------------------------------
const APP = {
  worldsMeta: null,
  state: null,
  campaignActive: false,
  busy: false,
  soundEnabled: true,
  musicEnabled: true,
  animationsEnabled: true,
  music: { world: "", tracks: [], index: 0, userStarted: false },
  musicVolume: 0.35,
  activeChatThread: null,
  pendingLethal: null,   // {kind:'action'|'timeskip', action, assessment, timeskip:{...}}
  pendingAdvance: null,
  pendingManualRoll: null,
  pendingIntervention: null,
  pendingDifficulty: null,
  challenge: null,
  pendingCampaign: null,
  journalTab: "party",
  portraitAttempted: new Set(),
  portraitInFlight: false,
  deferPortraitGeneration: false,
  lastChapterCount: null,
  statusWindowOpen: false,
  lastLocation: null,
};

// ---------------------------------------------------------------------------
// Sound
// ---------------------------------------------------------------------------
function playSfx(name) {
  if (!APP.soundEnabled) return;
  const el = document.getElementById("snd-" + name);
  if (!el) return;
  try { el.currentTime = 0; el.play().catch(() => {}); } catch (e) {}
}

// ---------------------------------------------------------------------------
// Portable world music — files live beside the EXE under music/<World>.
// ---------------------------------------------------------------------------
function musicPlayer() { return $("#music-player"); }

// Smooth fades instead of hard cuts when a track changes or the world's
// music context switches. `el._fadeTimer` lets a new fade cancel one already
// in flight instead of fighting over the volume value.
function fadeAudioTo(el, target, duration = 450) {
  clearInterval(el._fadeTimer);
  const start = el.volume;
  const delta = target - start;
  if (Math.abs(delta) < 0.005 || duration <= 0) { el.volume = Math.max(0, Math.min(1, target)); return; }
  const steps = Math.max(1, Math.round(duration / 30));
  let i = 0;
  el._fadeTimer = setInterval(() => {
    i += 1;
    el.volume = Math.max(0, Math.min(1, start + delta * (i / steps)));
    if (i >= steps) clearInterval(el._fadeTimer);
  }, duration / steps);
}

function renderMusicStatus(folder) {
  const current = APP.music.tracks[APP.music.index];
  $("#music-title").textContent = current ? `${current.name}${current.source === "Shared" ? " · Shared" : ""}` : "No music found";
  $("#music-help").textContent = current ? `${APP.music.index + 1} of ${APP.music.tracks.length} · ${APP.music.world}` : `Drop MP3/MP4 files into ${folder || `music/${APP.music.world}`}`;
  $("#btn-music-play").textContent = !musicPlayer().paused && current ? "❚❚" : "▶";
}

function loadMusicTrack(index, playNow = false) {
  if (!APP.music.tracks.length) { renderMusicStatus(); return; }
  APP.music.index = (index + APP.music.tracks.length) % APP.music.tracks.length;
  const track = APP.music.tracks[APP.music.index];
  const player = musicPlayer();
  const targetVolume = APP.musicVolume ?? player.volume ?? 0.35;
  const switchingTrack = player.getAttribute("src") !== track.url;
  const swap = () => {
    if (switchingTrack) { player.src = track.url; player.load(); }
    renderMusicStatus();
    if (playNow && APP.musicEnabled) {
      player.volume = 0;
      player.play().then(() => { fadeAudioTo(player, targetVolume, 500); renderMusicStatus(); })
        .catch(() => { $("#music-help").textContent = "Press Play to start music."; });
    } else {
      fadeAudioTo(player, targetVolume, 350);
    }
  };
  if (switchingTrack && !player.paused) { fadeAudioTo(player, 0, 260); setTimeout(swap, 270); }
  else swap();
}

async function refreshMusic(world, keepPlaying = false) {
  const selectedWorld = world || APP.state?.world || "Custom World";
  const wasPlaying = !musicPlayer().paused || APP.music.userStarted;
  try {
    const data = await apiGet(`/api/music?world=${encodeURIComponent(selectedWorld)}`);
    const oldUrl = APP.music.tracks[APP.music.index]?.url;
    APP.music.world = data.world;
    APP.music.tracks = data.tracks || [];
    const sameIndex = APP.music.tracks.findIndex((track) => track.url === oldUrl);
    APP.music.index = sameIndex >= 0 ? sameIndex : 0;
    if (APP.music.tracks.length) loadMusicTrack(APP.music.index, keepPlaying && wasPlaying);
    else { musicPlayer().pause(); musicPlayer().removeAttribute("src"); renderMusicStatus(data.folder); }
  } catch (error) { $("#music-help").textContent = "Music folder could not be scanned."; }
}

async function openMusicFolder() {
  const result = await apiPost("/api/music/open_folder", { world: APP.state?.world || "Custom World" });
  showToast(`Opened music folder: ${result.folder}`, "system");
}

// ---------------------------------------------------------------------------
// Toasts + cinematic banner + screen fx
// ---------------------------------------------------------------------------
function showToast(message, tag) {
  const stack = $("#toast-stack");
  const el = document.createElement("div");
  el.className = "toast " + (tag || "system");
  el.textContent = message;
  stack.appendChild(el);
  setTimeout(() => el.remove(), 5100);
}

const CINEMATIC_ICON = { level_up: "🎉", xp: "✦", notify: "★", danger: "⚠", message: "✉", world: "🌍", time: "⏳", damage: "💥", position: "👑", achievement: "🏆" };
function showCinematic(type, message) {
  const banner = $("#cinematic-banner");
  const icon = CINEMATIC_ICON[type] || "★";
  banner.innerHTML = `<div class="banner-card ${type === "danger" || type === "damage" ? "danger" : type === "achievement" ? "achievement" : ""}"><span class="banner-icon">${icon}</span><span>${escapeHtml(message)}</span></div>`;
  banner.classList.add("show");
  clearTimeout(banner._t);
  banner._t = setTimeout(() => banner.classList.remove("show"), 3200);
}

function flashScreen(kind) {
  const fx = $("#fx-layer");
  fx.classList.remove("flash-danger", "flash-success");
  void fx.offsetWidth;
  fx.classList.add(kind === "danger" ? "flash-danger" : "flash-success");
}

function shakeApp() {
  const shell = $(".app-shell");
  shell.classList.remove("shake");
  void shell.offsetWidth;
  shell.classList.add("shake");
}

function handleNotifications(notifications) {
  (notifications || []).forEach((n) => {
    // Reserve the large cinematic interruption for genuinely major changes.
    // Routine stat, XP, and quest updates remain readable in the Chronicle.
    const majorCinematics = new Set(["level_up", "position", "danger", "damage", "achievement"]);
    const toastCinematics = new Set([...majorCinematics, "notify"]);
    if (toastCinematics.has(n.cinematic)) showToast(n.message, n.cinematic || n.tag);
    if (majorCinematics.has(n.cinematic)) {
      showCinematic(n.cinematic, n.message);
      if (n.cinematic === "level_up") playSfx("level_up");
      else if (n.cinematic === "position") playSfx("level_up");
      else if (n.cinematic === "achievement") playSfx("achievement");
      else if (n.cinematic === "xp") playSfx("xp");
      else if (n.cinematic === "danger") { playSfx("danger"); flashScreen("danger"); shakeApp(); }
      else if (n.cinematic === "damage") { playSfx("hit"); flashScreen("danger"); shakeApp(); }
      else playSfx("notify");
    }
  });
}

// ---------------------------------------------------------------------------
// Chronicle — story beats are grouped and labelled instead of appearing as
// an undifferentiated stack of prose, rolls, and system boxes.
// ---------------------------------------------------------------------------
function storyEntryParts(entry) {
  const tag = entry.tag || "narrative";
  const raw = String(entry.text || "").trim();
  const lines = raw.split("\n");
  const bracket = lines[0]?.match(/^\[([^\]]+)\]\s*$/);
  const labelByTag = { narrative: "Story", player: "Your action", system: "Notice", danger: "Urgent", roll: "Check", growth: "Growth" };
  const label = bracket ? bracket[1].replace(/[_-]+/g, " ") : (labelByTag[tag] || "Story");
  const body = bracket ? lines.slice(1).join("\n").trim() : raw.replace(/^>\s*/, "");
  return { tag, label, body: body || raw };
}

function storyBeatLabel(entries) {
  const tags = new Set((entries || []).map((entry) => entry.tag || "narrative"));
  if (tags.has("danger")) return "Critical development";
  if (tags.has("player")) return "Player decision";
  if (tags.has("narrative")) return "Story beat";
  return "World update";
}

// Names/factions/locations the GM bolds are frequently the exact things a
// player doesn't yet know the meaning of ("Nen", "Haki", a faction name) —
// when a bolded term matches something already in the Codex, tie it back to
// that entry right where it's read instead of leaving the Codex as a
// separate tab the player has to remember to go check.
function codexLookup() {
  const codex = (APP.state && Array.isArray(APP.state.codex)) ? APP.state.codex : [];
  const map = new Map();
  codex.forEach((c) => { if (c && c.name) map.set(escapeHtml(String(c.name)).toLowerCase(), c); });
  return map;
}

// Bold a narrative's own proper nouns (the GM wraps them in **stars**, same
// convention as the update schema) — text is escaped first, so this can
// never introduce real markup, only <strong> around already-safe text.
function renderBoldedText(el, text) {
  const lookup = codexLookup();
  const escaped = escapeHtml(text).replace(/\*\*(.+?)\*\*/g, (whole, name) => {
    const entry = lookup.get(name.toLowerCase());
    if (!entry) return `<strong>${name}</strong>`;
    const hint = escapeHtml(String(entry.notes || entry.type || "No further detail recorded yet.")).slice(0, 220);
    return `<strong class="codex-term" data-codex-name="${escapeHtml(entry.name)}" title="${hint}">${name}</strong>`;
  });
  el.innerHTML = escaped;
}

// Hover already shows the native tooltip; a tap/click (phones have no
// hover) surfaces the same note as a toast and jumps straight to the full
// Codex entry for anyone who wants more than one line.
document.addEventListener("click", (e) => {
  const term = e.target.closest(".codex-term");
  if (!term) return;
  const name = term.getAttribute("data-codex-name") || "";
  const entry = ((APP.state && APP.state.codex) || []).find((c) => c && c.name === name);
  if (!entry) return;
  showToast(`${entry.name}${entry.type ? ` (${entry.type})` : ""}: ${entry.notes || "No further detail recorded yet."}`, "notify");
  APP.journalTab = "codex";
});

function dayLabel(canonDay) {
  const n = Number(canonDay);
  return Number.isFinite(n) ? `Canon Day ${n >= 0 ? "+" : ""}${n}` : "";
}

function appendStoryEntries(entries) {
  const feed = $("#story-feed");
  const cleanEntries = (entries || []).filter((entry) => entry && String(entry.text || "").trim());
  if (!cleanEntries.length) return;
  // A multi-day skip returns entries stamped with different canon_day
  // values — split those into separate dated cards (like a history feed)
  // instead of lumping a whole week under one header. Entries without a
  // canon_day (ordinary single-action turns) merge into the current run.
  const runs = [];
  cleanEntries.forEach((entry) => {
    const day = entry.canon_day;
    const current = runs[runs.length - 1];
    if (current && (day === undefined || day === null || day === current.day)) { current.entries.push(entry); return; }
    runs.push({ day, entries: [entry] });
  });
  runs.forEach((run) => {
    const beat = document.createElement("section");
    beat.className = "story-beat";
    const firstTime = run.entries.find((entry) => entry.time)?.time;
    const clockLabel = firstTime ? new Date(firstTime).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : "";
    const dateText = dayLabel(run.day);
    beat.innerHTML = `<header class="story-beat-head"><span>${escapeHtml(dateText || storyBeatLabel(run.entries))}</span>${clockLabel ? `<time>${escapeHtml(clockLabel)}</time>` : ""}</header>`;
    const entriesWrap = document.createElement("div");
    entriesWrap.className = "story-beat-entries";
    beat.appendChild(entriesWrap);
    let lastRow = null;
    run.entries.forEach((entry) => {
      const part = storyEntryParts(entry);
      // A roll's numbers belong right next to the action they resolved, not
      // as their own separate row — attach as a compact inline pill onto
      // whatever action line immediately preceded it in this beat.
      if (part.tag === "roll" && lastRow) {
        const pill = document.createElement("span");
        const positive = /SUCCESS|BREAKTHROUGH/.test(part.body);
        pill.className = "story-roll-pill " + (positive ? "hit" : "miss");
        pill.textContent = part.body;
        if (entry.detail) pill.title = entry.detail;
        lastRow.querySelector(".story-entry-copy")?.appendChild(pill);
        return;
      }
      const div = document.createElement("div");
      div.className = "story-entry " + part.tag;
      const label = document.createElement("div");
      label.className = "story-entry-label";
      label.textContent = part.label;
      const body = document.createElement("div");
      body.className = "story-entry-copy";
      div.append(label, body);
      entriesWrap.appendChild(div);
      if (part.tag === "narrative" && APP.animationsEnabled) {
        typeText(body, part.body);
      } else if (part.tag === "narrative" || part.tag === "system") {
        renderBoldedText(body, part.body);
      } else {
        body.textContent = part.body;
      }
      lastRow = div;
    });
    feed.appendChild(beat);
  });
  feed.scrollTop = feed.scrollHeight + 400;
}

function typeText(el, text) {
  const caret = document.createElement("span");
  caret.className = "typing-caret";
  let i = 0;
  const speed = text.length > 900 ? 2 : text.length > 400 ? 3 : 6; // chars per tick
  function tick() {
    i += speed;
    renderBoldedText(el, text.slice(0, i));
    el.appendChild(caret);
    const feed = $("#story-feed");
    feed.scrollTop = feed.scrollHeight;
    if (i < text.length) requestAnimationFrame(tick);
    else caret.remove();
  }
  requestAnimationFrame(tick);
}

$("#btn-story-latest").addEventListener("click", () => {
  const feed = $("#story-feed");
  feed.scrollTo({ top: feed.scrollHeight, behavior: APP.animationsEnabled ? "smooth" : "auto" });
});

// ---------------------------------------------------------------------------
// State rendering
// ---------------------------------------------------------------------------
function setWidth(el, pct) { el.style.width = Math.max(0, Math.min(100, pct)) + "%"; }

function textList(value) {
  if (Array.isArray(value)) return value.map((x) => typeof x === "object" ? (x.text || x.name || JSON.stringify(x)) : String(x)).filter(Boolean);
  if (value && typeof value === "object") return Object.entries(value).map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`);
  return value ? [String(value)] : [];
}

function questView(q, index = 0) {
  if (typeof q !== "object" || q === null) {
    return { name: String(q || `Quest ${index + 1}`), status: "Active", explanation: "No additional explanation has been discovered yet.", knowledge: [], conditions: [], objectives: [], branchState: {}, giver: "", locations: [], risks: [], firstStep: "", deadline: "", rewards: [] };
  }
  return {
    name: q.name || q.title || `Quest ${index + 1}`,
    status: q.status || q.stage || "Active",
    explanation: q.explanation || q.description || q.notes || q.summary || "No additional explanation has been discovered yet.",
    knowledge: textList(q.current_knowledge || q.knowledge || q.clues || q.known_facts),
    conditions: textList(q.clear_conditions || q.completion_conditions || q.conditions || q.objectives || q.objective),
    objectives: Array.isArray(q.objectives) ? q.objectives : [],
    branchState: q.branch_state && typeof q.branch_state === "object" ? q.branch_state : {},
    giver: q.giver || q.cause || q.employer || "",
    locations: textList(q.locations || q.location),
    risks: textList(q.risks || q.known_risks || q.consequences),
    firstStep: q.first_step || q.next_step || "",
    deadline: q.deadline || "",
    rewards: textList(q.rewards || q.reward),
  };
}

function humanLabel(value) {
  return String(value || "Detail").replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function compactReadable(value) {
  if (value === null || value === undefined || value === "") return "";
  if (Array.isArray(value)) return value.map(compactReadable).filter(Boolean).join("; ");
  if (typeof value === "object") return "";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value).trim();
}

function renderSkillCard(name, rawDetail) {
  if (rawDetail === null || rawDetail === undefined) rawDetail = {};
  if (typeof rawDetail !== "object" || Array.isArray(rawDetail)) {
    return `<article class="skill-journal-card"><h3>✦ ${escapeHtml(name)}</h3><p>${escapeHtml(compactReadable(rawDetail) || "This skill has not been described yet.")}</p></article>`;
  }
  const detail = rawDetail;
  const rank = compactReadable(detail.rank ?? detail.tier ?? detail.level);
  const bonus = Number.isFinite(Number(detail.bonus)) ? Number(detail.bonus) : null;
  const summary = compactReadable(detail.effect || detail.description || detail.summary) || "The exact practical effect has not been recorded yet.";
  const rows = [
    ["How it works", detail.use || detail.activation || detail.usage || detail.requirements],
    ["Origin", detail.origin],
    ["Cost / limits", detail.limitation || detail.limitations || detail.cost || detail.drawback],
    ["How to improve", detail.growth_path || detail.growth || detail.next_steps],
  ].map(([label, value]) => [label, compactReadable(value)]).filter(([, value]) => value);
  const chips = [rank ? `<span>${escapeHtml(rank)}</span>` : "", bonus !== null ? `<span>${bonus >= 0 ? "+" : ""}${escapeHtml(bonus)} check bonus</span>` : ""].filter(Boolean).join("");
  return `<article class="skill-journal-card"><header><h3>✦ ${escapeHtml(name)}</h3>${chips ? `<div class="skill-chips">${chips}</div>` : ""}</header><p class="skill-summary">${escapeHtml(summary)}</p>${rows.map(([label, value]) => `<div class="skill-detail"><b>${escapeHtml(label)}</b><span>${escapeHtml(value)}</span></div>`).join("")}</article>`;
}

function loadPortraitImage(url) {
  const img = $("#portrait-img");
  if (!url || img.getAttribute("data-src") === url) return;
  img.classList.remove("loaded");
  const pre = new Image();
  pre.onload = () => {
    img.src = url;
    img.setAttribute("data-src", url);
    requestAnimationFrame(() => img.classList.add("loaded"));
  };
  pre.onerror = () => {
    $("#portrait-status").textContent = "PORTRAIT COULD NOT LOAD";
  };
  pre.src = url;
}

function renderAiPortrait(s) {
  const img = $("#portrait-img");
  const hasRealPortrait = !!((s._portrait_generated || s._portrait_reference) && s._portrait_image);
  if (hasRealPortrait) {
    loadPortraitImage(s._portrait_image);
  } else {
    // No generated art yet — the frame just stays blank instead of falling
    // back to a procedural sprite.
    img.classList.remove("loaded");
    img.removeAttribute("data-src");
    img.removeAttribute("src");
  }
  const status = $("#portrait-status");
  status.classList.toggle("generated", !!s._portrait_generated);
  if (s._portrait_generated) status.textContent = "AI PORTRAIT · CACHED";
  else if (!s._portrait_generation_enabled) status.textContent = "PORTRAITS OFF";
  else if (!s._portrait_generation_ready) status.textContent = "SET UP IMAGE AI FOR ART";
  else status.textContent = "AI PORTRAIT QUEUED";
  $("#btn-portrait-regenerate").disabled = APP.portraitInFlight || !APP.campaignActive;
  if (!APP.deferPortraitGeneration) ensureAiPortrait(s);
}

async function ensureAiPortrait(s, force = false) {
  if (!s || !APP.campaignActive || !s._portrait_generation_enabled || !s._portrait_generation_ready) return;
  const signature = s._portrait_signature;
  if (!signature || APP.portraitInFlight || (!force && (s._portrait_generated || APP.portraitAttempted.has(signature)))) return;
  APP.portraitAttempted.add(signature);
  APP.portraitInFlight = true;
  const loading = $("#portrait-loading"), button = $("#btn-portrait-regenerate"), status = $("#portrait-status");
  loading.hidden = false; button.disabled = true; status.textContent = force ? "REGENERATING AI PORTRAIT" : "CREATING AI PORTRAIT";
  try {
    const result = await apiPost("/api/portrait/generate", { force });
    if (APP.state && APP.state._portrait_signature === result.signature) {
      APP.state._portrait_image = result.image_url + `?v=${Date.now()}`;
      APP.state._portrait_generated = true;
      loadPortraitImage(APP.state._portrait_image);
      status.classList.add("generated");
      status.textContent = result.cached ? "AI PORTRAIT · CACHED" : "AI PORTRAIT · UPDATED";
    }
  } catch (err) {
    status.classList.remove("generated");
    status.textContent = "WORLD PORTRAIT · GENERATION UNAVAILABLE";
    showToast(err.message || "AI portrait generation failed.", "danger");
  } finally {
    APP.portraitInFlight = false; loading.hidden = true; button.disabled = !APP.campaignActive;
  }
}

// A small shared line-icon set (Feather-style: 24x24 grid, 2px stroke,
// round caps/joins) standing in for the old emoji glyphs — consistent
// weight and color (currentColor) instead of whatever font the OS
// happens to render emoji in.
const SVG_ICON_ATTRS = 'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"';
const ICONS = {
  sword: `<svg ${SVG_ICON_ATTRS}><line x1="20.5" y1="3.5" x2="9" y2="15"/><path d="M14.5 8 18 11.5"/><path d="M9 15 4 20"/><path d="M4 20l-1 1"/><path d="M6.5 17.5 4 15l-1 3 3 3 3-1z"/></svg>`,
  zap: `<svg ${SVG_ICON_ATTRS}><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>`,
  shield: `<svg ${SVG_ICON_ATTRS}><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>`,
  bookOpen: `<svg ${SVG_ICON_ATTRS}><path d="M2 4h6a4 4 0 0 1 4 4v13a3 3 0 0 0-3-3H2z"/><path d="M22 4h-6a4 4 0 0 0-4 4v13a3 3 0 0 1 3-3h7z"/></svg>`,
  eye: `<svg ${SVG_ICON_ATTRS}><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>`,
  star: `<svg ${SVG_ICON_ATTRS}><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>`,
  fileText: `<svg ${SVG_ICON_ATTRS}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="14" y2="17"/></svg>`,
  activity: `<svg ${SVG_ICON_ATTRS}><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>`,
  box: `<svg ${SVG_ICON_ATTRS}><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>`,
  award: `<svg ${SVG_ICON_ATTRS}><circle cx="12" cy="8" r="7"/><polyline points="8.21 13.89 7 23 12 20 17 23 15.79 13.88"/></svg>`,
  mail: `<svg ${SVG_ICON_ATTRS}><path d="M4 4h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"/><polyline points="22 6 12 13 2 6"/></svg>`,
  clock: `<svg ${SVG_ICON_ATTRS}><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`,
  compass: `<svg ${SVG_ICON_ATTRS}><circle cx="12" cy="12" r="10"/><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/></svg>`,
  edit: `<svg ${SVG_ICON_ATTRS}><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg>`,
};

// Keyword-matched icon per ability name — every world's ability set is
// different (Taijutsu vs Strength vs Aura Control), so this matches on
// meaning rather than a fixed per-world lookup table.
const ABILITY_ICON_RULES = [
  [/strength|taijutsu|power|brawn/i, ICONS.sword],
  [/dexterity|agility|ninjutsu/i, ICONS.zap],
  [/constitution|endurance|vitality/i, ICONS.shield],
  [/intelligence|intellect|genjutsu|cunning/i, ICONS.bookOpen],
  [/wisdom|willpower|instinct|chakra/i, ICONS.eye],
  [/charisma|luck|aura|fortune/i, ICONS.star],
];
function abilityIcon(name) {
  for (const [re, icon] of ABILITY_ICON_RULES) if (re.test(name)) return icon;
  return ICONS.star;
}

function renderState(state) {
  APP.state = state;
  const s = state;
  document.body.setAttribute("data-world", s.world || "Custom World");

  $("#hdr-world").textContent = s.world || "Custom World";
  $("#hdr-location").textContent = s.location || "Unknown";
  $("#hdr-turn").textContent = "Turn " + (s.turn || 0);
  const saved = s._last_autosave || s.last_autosave || "";
  $("#hdr-autosave").textContent = saved ? `Saved ${String(saved).replace("T", " ").slice(0, 16)}` : "Not saved";
  renderQueuedActions(s.queued_actions || []);

  // Generated portraits are keyed by visually relevant state and update only
  // when appearance, form, or visible equipment actually changes.
  renderAiPortrait(s);
  $("#portrait-name").textContent = s.name || "Traveler";
  $("#portrait-class").textContent = (s.special && s.special.Archetype) || "Adventurer";
  const posBadge = $("#position-badge");
  if (s.position && s.position.trim()) { posBadge.textContent = "★ " + s.position; posBadge.style.display = ""; }
  else posBadge.style.display = "none";

  // scene
  updateScene(s);

  // stat summary
  $("#stat-level").textContent = "Level " + (s.level ?? 1);
  $("#stat-xp").textContent = `XP ${s.xp ?? 0} / ${s.xp_next ?? 100}`;
  setWidth($("#bar-hp"), 100 * (s.hp ?? 0) / Math.max(1, s.hp_max ?? 100));
  $("#bar-hp-text").textContent = `${s.hp ?? 0} / ${s.hp_max ?? 100}`;
  setWidth($("#bar-resource"), 100 * (s.resource ?? 0) / Math.max(1, s.resource_max ?? 100));
  $("#bar-resource-text").textContent = `${s.resource ?? 0} / ${s.resource_max ?? 100}`;
  $("#resource-label").textContent = s.resource_name || "Energy";
  setWidth($("#bar-xp"), 100 * (s.xp ?? 0) / Math.max(1, s.xp_next ?? 100));
  $("#level-summary").style.display = s._uses_xp ? "" : "none";
  $("#xp-summary").style.display = s._uses_xp ? "" : "none";
  const hasRace = !!(s.race && String(s.race).trim());
  $("#stat-race-label").hidden = !hasRace;
  $("#stat-race").hidden = !hasRace;
  if (hasRace) $("#stat-race").textContent = s.race;
  $("#stat-age").textContent = s.age ? String(s.age) : "Unknown";
  $("#stat-status").textContent = (s.status && s.status.length) ? s.status.join(", ") : "Normal";
  $("#stat-time").textContent = s.world_time || "Day 1 — Morning";
  const currency = s.currency || {};
  $("#stat-currency-label").textContent = currency.name || "Currency";
  $("#stat-currency").textContent = currency.amount !== undefined ? Number(currency.amount).toLocaleString() : "0";
  $("#stat-summary-body").classList.toggle("narrative-progression", !s._uses_xp);

  // attributes — dynamic per world (see backend worlds.WORLD_ABILITIES)
  const attrs = s.stats || {};
  const attrKeys = Object.keys(attrs);
  $("#attributes-grid").innerHTML = attrKeys.map((k) => {
    const v = attrs[k] ?? 1;
    return `<div class="attr-cell"><div class="attr-name"><i class="a-icon">${abilityIcon(k)}</i>${escapeHtml(k)}</div><div class="attr-right"><span class="attr-val">${escapeHtml(v)}</span></div></div>`;
  }).join("");

  const isFullSheet = s._stat_style === "full_sheet";
  const hiddenWrap = $("#hidden-stats-wrap");
  if (isFullSheet) {
    const revealed = s.hidden_stats || {};
    // Skip any placeholder that collides with a visible core ability name
    // (e.g. Overgeared/Solo Max-Level Newbie already use "Luck" as a core stat).
    const placeholders = ["Fortune", "Hidden Class", "Talent"].filter((k) => !(k in revealed) && !attrKeys.includes(k));
    const cells = [
      ...Object.entries(revealed).map(([k, v]) => `<div class="attr-cell revealed"><div class="attr-name"><i class="a-icon">${abilityIcon(k)}</i>${escapeHtml(k)}</div><div class="attr-right"><span class="attr-val">${escapeHtml(v)}</span></div></div>`),
      ...placeholders.map((k) => `<div class="attr-cell locked"><div class="attr-name"><i class="a-icon">${abilityIcon(k)}</i>${escapeHtml(k)}</div><div class="attr-right"><span class="attr-val">???</span></div></div>`),
    ];
    $("#hidden-stats-grid").innerHTML = cells.join("");
    hiddenWrap.style.display = "";
  } else {
    hiddenWrap.style.display = "none";
  }

  // gear — worlds where itemization matters show the full equipped set,
  // others (per user request) only surface the signature weapon/held item.
  renderGearPanel(s);

  // skills & titles
  const skillItems = Object.keys(s.skills || {}).map((k) => `✦ ${escapeHtml(k)}`);
  const titleItems = (s.titles || []).map((t) => `🏅 ${escapeHtml(t)}`);
  renderTagListHtml("#skills-list", [...titleItems, ...skillItems], "None");

  // affiliations — formal membership + rank in any group/kingdom/hierarchy,
  // distinct from general faction reputation. Panel stays hidden until the
  // player actually belongs to something.
  const affiliations = (s.affiliations || []).filter((a) => a && a.faction);
  const affPanel = $("#affiliations-panel");
  affPanel.style.display = affiliations.length ? "" : "none";
  if (affiliations.length) {
    renderTagListHtml("#affiliations-list", affiliations.map((a) =>
      `🛡 <b>${escapeHtml(a.rank || "Member")}</b> — ${escapeHtml(a.faction)}${a.status && a.status !== "active" ? ` <small>(${escapeHtml(a.status)})</small>` : ""}`
    ), "None");
  }

  // The left rail keeps quests and world events compact; either button opens
  // the complete journal view.
  const questPreview = $("#active-quest-preview");
  const activeQuests = s.quests || [];
  if (activeQuests.length) {
    const q = questView(activeQuests[0]);
    questPreview.classList.remove("empty");
    questPreview.innerHTML = `<span>Active Quest</span><small>${escapeHtml(q.name)}</small>`;
  } else {
    questPreview.classList.add("empty");
    questPreview.innerHTML = `<span>Active Quest</span><small>No active quest</small>`;
  }

  const feedItems = [...(s.world_events || []), ...(s.timeline || []).slice(-5)].slice(-8).map((e) => escapeHtml(typeof e === "object" ? (e.text || JSON.stringify(e)) : e));
  const worldFeedNav = $("#world-feed-nav");
  worldFeedNav.innerHTML = `<span>World Feed</span><small>${feedItems.length ? escapeHtml(String(feedItems.length) + " recent updates") : "No updates yet"}</small>`;

  // messages
  renderMessagesPanel(s);

  // time mode + world systems icons
  $("#time-mode-label").textContent = "Time mode: " + (s.time_mode || "moment");
  updateWorldSystemIcons(s);

  // suggested actions
  const sugg = $("#suggested-actions");
  sugg.innerHTML = "";
  (s.suggested_actions || []).forEach((a) => {
    const btn = document.createElement("button");
    btn.textContent = a;
    btn.addEventListener("click", () => {
      const input = $("#action-input");
      const current = input.value.trim();
      input.value = current ? `${current}\n${a}` : a;
      input.focus();
      input.setSelectionRange(input.value.length, input.value.length);
      showToast("Suggested action added to the chat. Edit it or press Add Action.", "system");
    });
    sugg.appendChild(btn);
  });
  if (APP.music.world !== (s.world || "Custom World")) refreshMusic(s.world, APP.music.userStarted);
  renderCombatPanel(s);
  if (s.status_window_due && !APP.statusWindowOpen) { APP.statusWindowOpen = true; renderStatusWindow(s); openModal("modal-status-window"); }
  const chapters = Array.isArray(s.chapter_summaries) ? s.chapter_summaries : [];
  if (APP.lastChapterCount === null) {
    APP.lastChapterCount = chapters.length;
  } else if (chapters.length > APP.lastChapterCount) {
    renderChapterRecap(chapters[chapters.length - 1], s);
    openModal("modal-chapter-recap");
    APP.lastChapterCount = chapters.length;
  }
}

// A chapter break already gets a quiet Chronicle note; this turns the same
// already-generated chapter_summaries entry into an actual "previously, on…"
// moment instead of something only visible if you go dig through the Journal.
function renderChapterRecap(chapter, s) {
  $("#recap-world").textContent = s.world || "Worldwalker";
  $("#recap-title").textContent = chapter.title || `Chapter ${chapter.number || ""}`;
  const turns = chapter.turns || [];
  $("#recap-timespan").textContent = [chapter.time_span, turns.length ? `Turns ${turns[0]}–${turns[1]}` : ""].filter(Boolean).join(" · ");
  $("#recap-summary").textContent = chapter.summary || "The story moved forward.";
  $("#recap-decisions").innerHTML = (chapter.key_decisions || []).slice(0, 8).map((d) => `<li>${escapeHtml(d)}</li>`).join("");
  $("#recap-changes").innerHTML = (chapter.lasting_changes || []).slice(0, 8).map((c) => `<li>${escapeHtml(c)}</li>`).join("");
}
$("#btn-recap-continue").addEventListener("click", () => { closeModal("modal-chapter-recap"); playSfx("notify"); });

// ---------------------------------------------------------------------------
// Status window — a periodic full-stats popup every ~3 in-game months,
// styled like an RPG character sheet rather than another plain modal.
// ---------------------------------------------------------------------------
function renderStatusWindow(s) {
  $("#sw-name").textContent = s.name || "Traveler";
  $("#sw-class").textContent = (s.special && s.special.Archetype) || "Adventurer";
  $("#sw-meta").textContent = `${s.world_time || "Day 1"} · ${s.location || "Unknown"}`;
  setWidth($("#sw-bar-hp"), 100 * (s.hp ?? 0) / Math.max(1, s.hp_max ?? 100));
  $("#sw-hp-text").textContent = `${s.hp ?? 0} / ${s.hp_max ?? 100}`;
  setWidth($("#sw-bar-resource"), 100 * (s.resource ?? 0) / Math.max(1, s.resource_max ?? 100));
  $("#sw-resource-text").textContent = `${s.resource ?? 0} / ${s.resource_max ?? 100}`;
  $("#sw-resource-label").textContent = s.resource_name || "Energy";
  $("#sw-xp-row").style.display = s._uses_xp ? "" : "none";
  if (s._uses_xp) {
    setWidth($("#sw-bar-xp"), 100 * (s.xp ?? 0) / Math.max(1, s.xp_next ?? 100));
    $("#sw-xp-text").textContent = `Level ${s.level ?? 1} · ${s.xp ?? 0} / ${s.xp_next ?? 100}`;
  }
  const attrs = s.stats || {};
  $("#sw-attributes").innerHTML = Object.entries(attrs).map(([k, v]) =>
    `<div class="status-window-attr"><i class="a-icon">${abilityIcon(k)}</i><span>${escapeHtml(k)}</span><b>${escapeHtml(v)}</b></div>`
  ).join("") || '<div class="hint">None recorded.</div>';
  const skillItems = Object.keys(s.skills || {}).map((k) => `<li>✦ ${escapeHtml(k)}</li>`);
  const titleItems = (s.titles || []).map((t) => `<li>🏅 ${escapeHtml(t)}</li>`);
  $("#sw-skills").innerHTML = [...titleItems, ...skillItems].join("") || '<li class="hint">None yet.</li>';
  const currency = s.currency || {};
  const misc = [
    currency.name ? `<div><b>${escapeHtml(currency.amount ?? 0)}</b> ${escapeHtml(currency.name)}</div>` : "",
    `<div>Turn ${escapeHtml(s.turn ?? 0)}</div>`,
    (s.affiliations || []).length ? `<div>${escapeHtml((s.affiliations[0] || {}).rank || "Member")} — ${escapeHtml((s.affiliations[0] || {}).faction || "")}</div>` : "",
  ].filter(Boolean).join("");
  $("#sw-misc").innerHTML = misc || '<div class="hint">Unaffiliated.</div>';
}
$("#btn-status-window-ok").addEventListener("click", async () => {
  closeModal("modal-status-window");
  APP.statusWindowOpen = false;
  try { await apiPost("/api/status_window/dismiss", {}); } catch (e) { /* best effort */ }
});

function renderQueuedActions(actions) {
  const box = $("#queued-actions");
  if (!box) return;
  if (!actions.length) {
    box.innerHTML = '<p class="hint">No actions queued. Add as many as you want, in order.</p>';
    return;
  }
  box.innerHTML = actions.map((action, index) => `<div class="queued-action"><span class="queue-index">${index + 1}</span><span>${escapeHtml(action)}</span><button type="button" data-remove-action="${index}" title="Remove queued action">✕</button></div>`).join("");
}

$("#btn-music-play").addEventListener("click", async () => {
  if (!APP.music.tracks.length) await refreshMusic(APP.state?.world);
  const player = musicPlayer();
  if (!APP.music.tracks.length) { showToast("No music files found for this world or Shared.", "system"); return; }
  APP.music.userStarted = true;
  if (player.paused) { APP.musicEnabled = true; player.play().then(renderMusicStatus).catch(() => showToast("This file's audio codec is not supported. MP3 is recommended.", "danger")); }
  else { player.pause(); renderMusicStatus(); }
});
$("#btn-music-prev").addEventListener("click", () => { APP.music.userStarted = true; APP.musicEnabled = true; loadMusicTrack(APP.music.index - 1, true); });
$("#btn-music-next").addEventListener("click", () => { APP.music.userStarted = true; APP.musicEnabled = true; loadMusicTrack(APP.music.index + 1, true); });
$("#btn-music-refresh").addEventListener("click", () => refreshMusic(APP.state?.world, APP.music.userStarted));
$("#btn-music-folder").addEventListener("click", () => openMusicFolder().catch((e) => showToast(e.message, "danger")));
musicPlayer().addEventListener("ended", () => loadMusicTrack(APP.music.index + 1, true));
musicPlayer().addEventListener("play", renderMusicStatus);
musicPlayer().addEventListener("pause", renderMusicStatus);

$("#queued-actions").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-remove-action]");
  if (!button || APP.busy) return;
  try {
    const result = await apiPost("/api/actions/remove", { index: Number(button.getAttribute("data-remove-action")) });
    APP.state.queued_actions = result.queued_actions || [];
    renderQueuedActions(APP.state.queued_actions);
  } catch (error) { showToast(error.message, "danger"); }
});

const WEAPON_KEY_RE = /weapon|sword|blade|staff|bow|spear|gun|dagger|fist|knife|axe|hammer|held/i;
function isWeaponSlot(key) { return WEAPON_KEY_RE.test(key); }

// ---------------------------------------------------------------------------
// Equipment mannequin — hover a body zone to see what's equipped there and
// its effect. Only shown for "full" gear-style worlds (Overgeared, Solo
// Max-Level Newbie, Custom World) where itemization actually matters.
// ---------------------------------------------------------------------------
const MANNEQUIN_ZONES = [
  { key: "head", label: "Head", re: /head|helm|hat|crown|circlet/i, cx: 150, cy: 30, r: 22 },
  { key: "chest", label: "Chest", re: /chest|armor|robe|vest|body|breastplate/i, cx: 150, cy: 109, rw: 36, rh: 52 },
  { key: "weapon", label: "Weapon", re: WEAPON_KEY_RE, cx: 90, cy: 130, r: 19 },
  { key: "offhand", label: "Off-Hand", re: /shield|off.?hand/i, cx: 210, cy: 130, r: 19 },
  { key: "legs", label: "Legs", re: /legs|pants|greaves|trousers/i, cx: 150, cy: 207, rw: 36, rh: 26 },
  { key: "feet", label: "Feet", re: /feet|boots|shoes|sandals/i, cx: 150, cy: 240, rw: 34, rh: 11 },
  { key: "accessory", label: "Accessory", re: /ring|necklace|amulet|accessory|bracelet|earring|belt/i, cx: 150, cy: 70, r: 11 },
];

function buildMannequinHtml(eq) {
  const entries = Object.entries(eq);
  const matched = new Set();
  const zoneItems = MANNEQUIN_ZONES.map((z) => {
    const hit = entries.find(([k]) => z.re.test(k));
    if (hit) matched.add(hit[0]);
    return { ...z, item: hit ? hit[1] : null, itemKey: hit ? hit[0] : null };
  });
  const leftover = entries.filter(([k]) => !matched.has(k));

  const shapes = zoneItems.map((z) => {
    const filled = z.item ? "filled" : "";
    const shape = z.rw
      ? `<rect class="mq-zone ${filled}" data-tip="${escapeHtml(z.label)}: ${escapeHtml(z.item || "empty")}" x="${z.cx - z.rw}" y="${z.cy - z.rh}" width="${z.rw * 2}" height="${z.rh * 2}" rx="10"/>`
      : `<circle class="mq-zone ${filled}" data-tip="${escapeHtml(z.label)}: ${escapeHtml(z.item || "empty")}" cx="${z.cx}" cy="${z.cy}" r="${z.r}"/>`;
    return shape;
  }).join("");

  // A proper front-facing humanoid outline (head, neck, shoulders, arms
  // bending in at the waist, hips, two separate legs, two feet) instead of
  // the old ellipse-plus-two-rects blob. Interactive mq-zone shapes above
  // overlay this at the matching body position.
  const svg = `<svg class="mannequin-svg" viewBox="0 0 300 260" xmlns="http://www.w3.org/2000/svg">
    <ellipse cx="150" cy="204" rx="58" ry="14" class="mq-shadow"/>
    <circle cx="150" cy="30" r="19" class="mq-silhouette"/>
    <circle cx="143" cy="27" r="2.2" class="mq-face"/>
    <circle cx="157" cy="27" r="2.2" class="mq-face"/>
    <rect x="142" y="46" width="16" height="12" class="mq-silhouette"/>
    <path class="mq-silhouette" d="M150,55
      C121,55 109,61 101,77
      C95,89 91,104 87,121
      C85,129 89,133 95,131
      C101,129 104,117 108,103
      C111,93 115,85 121,79
      L123,129
      C119,139 117,149 117,159
      L183,159
      C183,149 181,139 177,129
      L179,79
      C185,85 189,93 192,103
      C196,117 199,129 205,131
      C211,133 215,129 213,121
      C209,104 205,89 199,77
      C191,61 179,55 150,55 Z"/>
    <path class="mq-silhouette" d="M117,159 L183,159 L179,181 L121,181 Z"/>
    <path class="mq-silhouette" d="M121,181 L148,181 L145,231 L127,231 Z"/>
    <path class="mq-silhouette" d="M152,181 L179,181 L173,231 L155,231 Z"/>
    <ellipse cx="133" cy="239" rx="15" ry="8" class="mq-silhouette"/>
    <ellipse cx="167" cy="239" rx="15" ry="8" class="mq-silhouette"/>
    ${shapes}
  </svg>`;

  return `<div class="mannequin-wrap"><div class="mannequin-tooltip" id="mannequin-tip" style="display:none"></div>${svg}</div>` +
    (leftover.length ? `<div class="jrow"><b>Other Equipped</b><br/>${leftover.map(([k, v]) => `${escapeHtml(k)}: ${escapeHtml(v)}`).join("<br/>")}</div>` : "");
}

function wireMannequinTooltips() {
  const tip = $("#mannequin-tip");
  $$(".mq-zone").forEach((el) => {
    el.addEventListener("mouseenter", () => { tip.textContent = el.getAttribute("data-tip"); tip.style.display = "block"; });
    el.addEventListener("mouseleave", () => { tip.style.display = "none"; });
  });
}

function renderGearPanel(s) {
  const eq = s.equipment || {};
  const keys = Object.keys(eq);
  const panel = $("#gear-panel");
  const full = s._gear_style === "full";
  const shown = full ? keys : keys.filter(isWeaponSlot).length ? keys.filter(isWeaponSlot) : keys.slice(0, 1);
  $("#gear-panel-title").textContent = full ? "Gear" : "Weapon";
  if (!shown.length) { panel.style.display = "none"; return; }
  panel.style.display = "";
  $("#gear-list").classList.remove("empty");
  $("#gear-list").innerHTML = shown.map((k) => `<li><b>${escapeHtml(k)}</b>: ${escapeHtml(eq[k])}</li>`).join("");
}

function renderTagList(sel, arr, fmt, emptyText) {
  const el = $(sel);
  if (!arr.length) { el.classList.add("empty"); el.textContent = emptyText; return; }
  el.classList.remove("empty");
  el.innerHTML = arr.map((x) => `<li>${fmt(x)}</li>`).join("");
}
function renderTagListHtml(sel, htmlItems, emptyText) {
  const el = $(sel);
  if (!htmlItems.length) { el.classList.add("empty"); el.textContent = emptyText; return; }
  el.classList.remove("empty");
  el.innerHTML = htmlItems.map((h) => `<li>${h}</li>`).join("");
}

function renderMessagesPanel(s) {
  const threads = s.chat_threads || {};
  const unread = s.unread_chats || [];
  const rows = [];
  Object.entries(threads).forEach(([name, msgs]) => {
    if (!msgs.length) return;
    const last = msgs[msgs.length - 1];
    const isUnread = unread.some((u) => u.thread === name);
    rows.push({ name, last, isUnread, time: last.turn || 0 });
  });
  rows.sort((a, b) => b.time - a.time);
  const items = rows.slice(0, 6).map((r) => `<b>${escapeHtml(r.name)}</b>${r.isUnread ? '<span class="unread-badge">•</span>' : ""}: ${escapeHtml((r.last.text || "").slice(0, 60))}`);
  renderTagListHtml("#messages-list", items, "No messages yet.");
}

const SCENE_ICON = { town_square: "sun", kingdom: "sun", indoor_grandhall: "sun", merchant_shop:"fire", tavern_inn:"fire", academy_classroom:"sun", ship_deck:"wind", arena_floor:"sun", harbor_port: "sun", forest_path: "wind", mountain_castle: "wind", starry_sky: "moon", night_wilderness: "moon", battlefield_dusk: "fire", monster_battlefield: "fire", duel: "wind", monster_lair: "fire", dungeon_cave: "cloud", tower_hub: "cloud" };
function updateWorldSystemIcons(s) {
  const cat = s._scene_category || "starry_sky";
  const active = SCENE_ICON[cat] || "sun";
  ["sun", "fire", "cloud", "wind", "moon"].forEach((k) => $("#sys-" + k).classList.toggle("active", k === active));
}

// ---------------------------------------------------------------------------
// Scene image + ambient FX
// ---------------------------------------------------------------------------
let sceneFx = { mode: null, particles: [], glows: [], raf: null, canvas: null, ctx: null, w: 0, h: 0 };
let scenePaint = { canvas: null, ctx: null, w: 0, h: 0, lastKey: null };

// Weather is tracked in state but was never actually shown anywhere — a
// light CSS overlay on the scene box is enough to make it register without
// touching the (already complex, per-category) procedural scene painter.
function weatherClassFor(weather) {
  const w = String(weather || "").toLowerCase();
  if (/storm|thunder|typhoon|hurricane/.test(w)) return "storm";
  if (/rain|drizzle|monsoon/.test(w)) return "rain";
  if (/snow|blizzard|sleet/.test(w)) return "snow";
  if (/fog|mist|haze/.test(w)) return "fog";
  return "";
}

function updateScene(s) {
  const url = s._scene_image;
  const cat = s._scene_category || "starry_sky";
  const img = $("#scene-img");
  document.body.setAttribute("data-scene", cat);
  $("#scene-category-badge").textContent = cat.replace(/_/g, " ").toUpperCase();
  $("#scene-location").textContent = s.location || "Unknown";
  $("#scene-world").textContent = s.world || "Custom World";

  const weatherCls = weatherClassFor(s.weather);
  const weatherEl = $("#scene-weather");
  weatherEl.className = "scene-weather" + (weatherCls ? " active " + weatherCls : "");

  // A location change gets a quick cut-to-black-and-back in the scene box
  // only — deliberately not anywhere else in the UI — so travel reads as a
  // moment instead of the background image just silently swapping.
  if (APP.lastLocation === null) {
    APP.lastLocation = s.location;
  } else if (s.location && s.location !== APP.lastLocation) {
    APP.lastLocation = s.location;
    if (APP.animationsEnabled) {
      const t = $("#scene-transition");
      t.classList.remove("playing");
      void t.offsetWidth;
      t.classList.add("playing");
    }
  }

  if (url) {
    if (img.getAttribute("data-src") !== url) {
      img.setAttribute("data-src", url);
      img.classList.remove("loaded");
      const pre = new Image();
      pre.onload = () => { img.src = url; requestAnimationFrame(() => img.classList.add("loaded")); };
      pre.src = url;
    }
  } else {
    img.removeAttribute("src");
    img.removeAttribute("data-src");
    img.classList.remove("loaded");
  }
  startSceneFx(cat);
  paintScene(cat, s.world || "Custom World");
  startCharacterAmbient(cat);
}

// ---- Ambient particles behind the character card --------------------------
// A much lighter echo of the scene particle system (seedParticles/tickSceneFx
// below) so the character card feels like it shares the same atmosphere as
// the scene, instead of being a static island next to a moving one.
let charAmbient = { mode: null, motes: [], canvas: null, ctx: null, w: 0, h: 0, raf: null, t: 0 };
const AMBIENT_COLOR_BY_MODE = {
  battlefield_dusk: "#ff8a4c", monster_battlefield: "#ff6a52", monster_lair: "#c95a3a",
  forest_path: "#8fce6a", dungeon_cave: "#6e8ca6", starry_sky: "#eef4ff", night_wilderness: "#cfe0ff",
  harbor_port: "#8bdde0", ship_deck: "#8bdde0", tower_hub: "#63e0f5", tavern_inn: "#f2b25a",
  merchant_shop: "#f2b25a", academy_classroom: "#e6c877", arena_floor: "#f2b25a",
};
function resizeCharAmbient() {
  const c = charAmbient.canvas;
  if (!c) return;
  const rect = c.parentElement.getBoundingClientRect();
  charAmbient.w = c.width = rect.width;
  charAmbient.h = c.height = rect.height;
}
window.addEventListener("resize", () => { if (APP.animationsEnabled) resizeCharAmbient(); });
function startCharacterAmbient(mode) {
  if (!charAmbient.canvas) {
    charAmbient.canvas = $("#character-ambient");
    charAmbient.ctx = charAmbient.canvas.getContext("2d");
  }
  if (charAmbient.mode === mode) return;
  charAmbient.mode = mode;
  resizeCharAmbient();
  const { w, h } = charAmbient;
  charAmbient.motes = Array.from({ length: 16 }, () => ({
    x: rand(0, w), y: rand(0, h), r: rand(.8, 2.6), phase: rand(0, Math.PI * 2), speed: rand(.01, .03),
  }));
  if (!charAmbient.raf) charAmbient.raf = requestAnimationFrame(tickCharAmbient);
}
function tickCharAmbient() {
  charAmbient.raf = requestAnimationFrame(tickCharAmbient);
  const { ctx, w, h, motes, mode } = charAmbient;
  if (!ctx || !w || !h) return;
  ctx.clearRect(0, 0, w, h);
  if (!APP.animationsEnabled) return;
  charAmbient.t += 0.016;
  const color = AMBIENT_COLOR_BY_MODE[mode] || "#c7a15c";
  motes.forEach((m) => {
    const y = m.y - ((charAmbient.t * m.speed * 260) % (h + 20));
    const x = m.x + Math.sin(charAmbient.t * .6 + m.phase) * 8;
    const yy = ((y % (h + 20)) + (h + 20)) % (h + 20) - 10;
    ctx.globalAlpha = .35 + .35 * Math.sin(charAmbient.t * 1.3 + m.phase);
    ctx.fillStyle = color;
    ctx.beginPath(); ctx.arc(x, yy, m.r, 0, Math.PI * 2); ctx.fill();
  });
  ctx.globalAlpha = 1;
}

// ---- Procedural scene fallback ------------------------------------------
// Generated environment art is the primary scene layer. This painter remains
// underneath it as an instant-loading fallback and preserves world tinting if
// a custom scene asset is absent. The particle canvas supplies subtle motion.
const SKY_BY_CATEGORY = {
  town_square: ["#3a6b8a", "#e8b774"], kingdom: ["#2c5678", "#e0a45f"], indoor_grandhall: ["#241a12", "#4a3420"],
  harbor_port: ["#2f7896", "#bfe6dc"], forest_path: ["#1f4a3a", "#5c9468"], mountain_castle: ["#233a55", "#8fa8c2"],
  battlefield_dusk: ["#2a1418", "#a3452f"], monster_lair: ["#0a0a10", "#241826"], dungeon_cave: ["#08090d", "#1c222c"],
  starry_sky: ["#040814", "#152238"], night_wilderness: ["#050a12", "#16233a"], tower_hub: ["#04060f", "#0e1a2e"],
  duel: ["#182238", "#b45d3d"], monster_battlefield: ["#16080c", "#6e1d1a"],
};

function resizeScenePaint() {
  const c = scenePaint.canvas;
  if (!c) return;
  const rect = c.parentElement.getBoundingClientRect();
  scenePaint.w = c.width = rect.width;
  scenePaint.h = c.height = rect.height;
}
window.addEventListener("resize", () => { resizeScenePaint(); if (scenePaint.lastKey) { const [cat, world] = scenePaint.lastKey.split("::"); drawScene(cat, world); } });

function paintScene(cat, world) {
  if (!scenePaint.canvas) {
    scenePaint.canvas = $("#scene-paint");
    scenePaint.ctx = scenePaint.canvas.getContext("2d");
  }
  const key = cat + "::" + world;
  resizeScenePaint();
  drawScene(cat, world);
  scenePaint.lastKey = key;
  requestAnimationFrame(() => scenePaint.canvas.classList.add("loaded"));
}

function hexToRgb(hex) {
  const h = hex.replace("#", "");
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}
function rgba(hex, a) { const [r, g, b] = hexToRgb(hex); return `rgba(${r},${g},${b},${a})`; }

function drawScene(cat, world) {
  const ctx = scenePaint.ctx, w = scenePaint.w, h = scenePaint.h;
  if (!ctx || !w || !h) return;
  ctx.clearRect(0, 0, w, h);
  const cs = getComputedStyle(document.body);
  const accent = (cs.getPropertyValue("--accent") || "#c7a15c").trim();
  const accent2 = (cs.getPropertyValue("--accent2") || "#75b6c8").trim();
  const sky = SKY_BY_CATEGORY[cat] || SKY_BY_CATEGORY.starry_sky;

  const grad = ctx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, sky[0]);
  grad.addColorStop(0.55, mixHex(sky[0], sky[1], 0.5));
  grad.addColorStop(1, mixHex(sky[1], accent, 0.28));
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, w, h);

  // soft horizon glow
  const glow = ctx.createRadialGradient(w * 0.5, h * 0.72, 10, w * 0.5, h * 0.72, w * 0.6);
  glow.addColorStop(0, rgba(accent2, 0.16));
  glow.addColorStop(1, rgba(accent2, 0));
  ctx.fillStyle = glow; ctx.fillRect(0, 0, w, h);

  // soft nebula/cloud wash for night-flavored categories — breaks up the flat gradient
  if (["starry_sky", "night_wilderness", "tower_hub", "monster_lair", "dungeon_cave"].includes(cat)) {
    for (let i = 0; i < 3; i++) {
      const nx = w * rand(0.1, 0.9), ny = h * rand(0.05, 0.5), nr = w * rand(0.18, 0.34);
      const neb = ctx.createRadialGradient(nx, ny, 0, nx, ny, nr);
      neb.addColorStop(0, rgba(i % 2 ? accent2 : accent, 0.10));
      neb.addColorStop(1, rgba(accent2, 0));
      ctx.fillStyle = neb; ctx.fillRect(0, 0, w, h);
    }
  }

  const drawSkyline = (baseY, count, minH, maxH, color, alpha) => {
    ctx.fillStyle = rgba(color, alpha);
    let x = -20;
    while (x < w + 20) {
      const bw = rand(w / count * 0.5, w / count * 1.1);
      const bh = rand(minH, maxH);
      ctx.fillRect(x, baseY - bh, bw, bh + 40);
      if (Math.random() > 0.5) { ctx.beginPath(); ctx.moveTo(x, baseY - bh); ctx.lineTo(x + bw / 2, baseY - bh - rand(10, 26)); ctx.lineTo(x + bw, baseY - bh); ctx.closePath(); ctx.fill(); }
      x += bw + rand(2, 10);
    }
  };
  const drawMountains = (baseY, amp, color, alpha, seedOffset) => {
    ctx.fillStyle = rgba(color, alpha);
    ctx.beginPath(); ctx.moveTo(0, h);
    for (let x = 0; x <= w; x += w / 14) ctx.lineTo(x, baseY - Math.abs(Math.sin(x * 0.01 + seedOffset)) * amp - rand(0, amp * 0.3));
    ctx.lineTo(w, h); ctx.closePath(); ctx.fill();
  };
  const drawTrees = (baseY, count, color, alpha) => {
    ctx.fillStyle = rgba(color, alpha);
    for (let i = 0; i < count; i++) {
      const x = (w / count) * i + rand(-10, 10);
      const th = rand(h * 0.12, h * 0.3);
      ctx.beginPath(); ctx.moveTo(x, baseY); ctx.lineTo(x + th * 0.32, baseY); ctx.lineTo(x + th * 0.16, baseY - th); ctx.closePath(); ctx.fill();
    }
  };

  if (cat === "town_square" || cat === "kingdom" || cat === "indoor_grandhall") {
    drawMountains(h * 0.62, h * 0.1, accent2, 0.14, 1);
    drawSkyline(h * 0.78, 16, h * 0.08, h * 0.24, "#000000", 0.38);
    drawSkyline(h * 0.86, 22, h * 0.05, h * 0.16, "#000000", 0.55);
    if (cat === "kingdom") {
      ctx.fillStyle = rgba(accent, 0.75);
      ctx.beginPath(); ctx.moveTo(w * 0.44, h * 0.72); ctx.lineTo(w * 0.48, h * 0.5); ctx.lineTo(w * 0.5, h * 0.6); ctx.lineTo(w * 0.52, h * 0.46); ctx.lineTo(w * 0.56, h * 0.72); ctx.closePath(); ctx.fill();
    }
  } else if (cat === "harbor_port") {
    ctx.fillStyle = rgba("#0a2230", 0.5);
    ctx.fillRect(0, h * 0.74, w, h * 0.3);
    for (let i = 0; i < 4; i++) {
      const x = w * (0.15 + i * 0.22);
      ctx.strokeStyle = rgba("#000000", 0.5); ctx.lineWidth = 3;
      ctx.beginPath(); ctx.moveTo(x, h * 0.55); ctx.lineTo(x, h * 0.78); ctx.stroke();
      ctx.fillStyle = rgba(accent, 0.6);
      ctx.beginPath(); ctx.moveTo(x, h * 0.55); ctx.lineTo(x + 26, h * 0.63); ctx.lineTo(x, h * 0.7); ctx.closePath(); ctx.fill();
    }
    drawSkyline(h * 0.82, 20, h * 0.03, h * 0.08, "#000000", 0.4);
  } else if (cat === "forest_path") {
    drawMountains(h * 0.5, h * 0.08, accent2, 0.1, 2);
    drawTrees(h * 0.86, 9, "#04140c", 0.5);
    drawTrees(h * 0.95, 13, "#020c07", 0.72);
  } else if (cat === "mountain_castle") {
    drawMountains(h * 0.55, h * 0.28, accent2, 0.28, 0.5);
    drawMountains(h * 0.68, h * 0.2, "#0c1420", 0.6, 2.2);
    ctx.fillStyle = rgba(accent, 0.7);
    ctx.fillRect(w * 0.46, h * 0.34, w * 0.03, h * 0.16);
    ctx.beginPath(); ctx.moveTo(w * 0.44, h * 0.34); ctx.lineTo(w * 0.475, h * 0.26); ctx.lineTo(w * 0.51, h * 0.34); ctx.closePath(); ctx.fill();
  } else if (cat === "duel") {
    drawMountains(h * 0.66, h * 0.12, accent2, 0.18, 1.8);
    ctx.fillStyle = rgba("#08080b", 0.72); ctx.fillRect(0, h * 0.78, w, h * 0.22);
    // Two readable fighting silhouettes, separated so the scene immediately
    // reads as a one-on-one confrontation rather than a generic battlefield.
    const fighter = (x, facing) => {
      ctx.save(); ctx.translate(x, h * 0.74); ctx.scale(facing, 1);
      ctx.fillStyle = rgba("#030305", 0.92);
      ctx.beginPath(); ctx.arc(0, -56, 12, 0, 7); ctx.fill();
      ctx.fillRect(-10, -45, 22, 39); ctx.fillRect(-8, -8, 8, 35); ctx.fillRect(6, -8, 8, 35);
      ctx.save(); ctx.translate(8, -36); ctx.rotate(-0.7); ctx.fillRect(0, -4, 48, 8); ctx.restore();
      ctx.strokeStyle = rgba(accent, 0.9); ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(46, -73); ctx.lineTo(12, -34); ctx.stroke();
      ctx.restore();
    };
    fighter(w * 0.32, 1); fighter(w * 0.68, -1);
  } else if (cat === "battlefield_dusk" || cat === "monster_battlefield") {
    ctx.fillStyle = rgba("#1a0a08", 0.6);
    ctx.fillRect(0, h * 0.78, w, h * 0.22);
    for (let i = 0; i < 10; i++) {
      const x = rand(0, w);
      ctx.strokeStyle = rgba("#050505", 0.6); ctx.lineWidth = 3;
      ctx.beginPath(); ctx.moveTo(x, h * 0.8); ctx.lineTo(x + rand(-14, 14), h * 0.8 - rand(20, 60)); ctx.stroke();
    }
    if (cat === "monster_battlefield") {
      for (let i = 0; i < 11; i++) {
        const x = w * (0.04 + i * 0.09), y = h * rand(0.64, 0.79), size = rand(9, 18);
        ctx.fillStyle = rgba("#020203", 0.82);
        ctx.beginPath(); ctx.arc(x, y - size, size, Math.PI, 0); ctx.lineTo(x + size, y); ctx.lineTo(x - size, y); ctx.closePath(); ctx.fill();
        ctx.fillStyle = rgba(i % 2 ? accent : accent2, 0.8); ctx.fillRect(x - size * .45, y - size * 1.15, 2, 2); ctx.fillRect(x + size * .3, y - size * 1.15, 2, 2);
      }
    }
  } else if (cat === "monster_lair" || cat === "dungeon_cave") {
    ctx.fillStyle = "#000000";
    for (let i = 0; i < 8; i++) { const x = (w / 8) * i + rand(-10, 10); const dh = rand(h * 0.08, h * 0.32); ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x + 30, 0); ctx.lineTo(x + 15, dh); ctx.closePath(); ctx.fill(); }
    for (let i = 0; i < 8; i++) { const x = (w / 8) * i + rand(-10, 10); const dh = rand(h * 0.1, h * 0.34); ctx.beginPath(); ctx.moveTo(x, h); ctx.lineTo(x + 34, h); ctx.lineTo(x + 17, h - dh); ctx.closePath(); ctx.fill(); }
    const vign = ctx.createRadialGradient(w / 2, h / 2, h * 0.15, w / 2, h / 2, h * 0.9);
    vign.addColorStop(0, "rgba(0,0,0,0)"); vign.addColorStop(1, "rgba(0,0,0,.75)");
    ctx.fillStyle = vign; ctx.fillRect(0, 0, w, h);
    if (cat === "monster_lair") { ctx.fillStyle = rgba(accent2, 0.5); ctx.beginPath(); ctx.arc(w * 0.5, h * 0.6, 5, 0, 7); ctx.arc(w * 0.54, h * 0.6, 5, 0, 7); ctx.fill(); }
  } else if (cat === "starry_sky" || cat === "night_wilderness") {
    const moonX = w * 0.8, moonY = h * 0.22;
    const bloom = ctx.createRadialGradient(moonX, moonY, 4, moonX, moonY, 70);
    bloom.addColorStop(0, rgba(accent2, 0.45)); bloom.addColorStop(0.4, rgba(accent2, 0.14)); bloom.addColorStop(1, rgba(accent2, 0));
    ctx.fillStyle = bloom; ctx.fillRect(0, 0, w, h);
    const moonBody = ctx.createRadialGradient(moonX - 6, moonY - 6, 2, moonX, moonY, 22);
    moonBody.addColorStop(0, "#ffffff"); moonBody.addColorStop(1, mixHex("#ffffff", accent2, 0.5));
    ctx.fillStyle = moonBody;
    ctx.beginPath(); ctx.arc(moonX, moonY, 20, 0, 7); ctx.fill();
    drawMountains(h * 0.78, h * 0.12, "#03060c", 0.85, 1.4);
  } else if (cat === "tower_hub") {
    for (let i = 0; i < 6; i++) {
      const x = (w / 6) * i + w / 12;
      const beamGrad = ctx.createLinearGradient(x, 0, x, h);
      beamGrad.addColorStop(0, rgba(accent, 0.0)); beamGrad.addColorStop(0.5, rgba(accent, 0.16)); beamGrad.addColorStop(1, rgba(accent, 0.0));
      ctx.fillStyle = beamGrad; ctx.fillRect(x - 1, 0, 2, h);
    }
    drawSkyline(h * 0.86, 12, h * 0.1, h * 0.3, "#000000", 0.65);
  }

  // gentle top vignette to blend into panel
  const top = ctx.createLinearGradient(0, 0, 0, h * 0.3);
  top.addColorStop(0, "rgba(0,0,0,.25)"); top.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = top; ctx.fillRect(0, 0, w, h * 0.3);
}

function mixHex(hexA, hexB, t) {
  const a = hexToRgb(hexA), b = hexToRgb(hexB);
  const r = Math.round(a[0] + (b[0] - a[0]) * t), g = Math.round(a[1] + (b[1] - a[1]) * t), bl = Math.round(a[2] + (b[2] - a[2]) * t);
  return `rgb(${r},${g},${bl})`;
}

function startSceneFx(mode) {
  if (!sceneFx.canvas) {
    sceneFx.canvas = $("#scene-fx");
    sceneFx.ctx = sceneFx.canvas.getContext("2d");
  }
  if (sceneFx.mode === mode) return;
  sceneFx.mode = mode;
  sceneFx.particles = [];
  sceneFx.glows = [];
  resizeSceneFx();
  seedParticles(mode);
  seedSceneGlows(mode);
  if (!sceneFx.raf) sceneFx.raf = requestAnimationFrame(tickSceneFx);
}

function resizeSceneFx() {
  const c = sceneFx.canvas;
  if (!c) return;
  const rect = c.parentElement.getBoundingClientRect();
  sceneFx.w = c.width = rect.width;
  sceneFx.h = c.height = rect.height;
}
window.addEventListener("resize", () => { if (APP.animationsEnabled) resizeSceneFx(); });

function rand(a, b) { return a + Math.random() * (b - a); }

function seedParticles(mode) {
  const { w, h } = sceneFx;
  const p = sceneFx.particles;
  if (mode === "town_square" || mode === "kingdom" || mode === "arena_floor") {
    for (let i = 0; i < 18; i++) p.push({ x: rand(0, w), y: rand(h * .7, h * .92), phase: rand(0, 6), speed: rand(.012, .035), scale: rand(.6, 1.15), hue: rand(0, 1) });
  } else if (mode === "duel") {
    for (let i = 0; i < 24; i++) p.push({ x: w / 2, y: h * .55, vx: rand(-1.6, 1.6), vy: rand(-1.1, 1.1), r: rand(.8, 2.2), life: rand(25, 80), age: rand(0, 60) });
  } else if (mode === "forest_path") {
    for (let i = 0; i < 26; i++) p.push({ x: rand(0, w), y: rand(0, h), vx: rand(-0.3, -1.1), vy: rand(0.3, 0.9), r: rand(2, 4), rot: rand(0, 6), vr: rand(-0.03, 0.03), a: rand(.4, .9) });
  } else if (mode === "starry_sky") {
    for (let i = 0; i < 60; i++) p.push({ x: rand(0, w), y: rand(0, h * 0.65), r: rand(0.5, 1.8), tw: rand(0, Math.PI * 2), speed: rand(.02, .06) });
  } else if (mode === "night_wilderness" || mode === "merchant_shop" || mode === "tavern_inn" || mode === "academy_classroom") {
    for (let i = 0; i < 28; i++) p.push({ x: rand(0, w), y: rand(h * .35, h * .9), vx: rand(-.18, .18), vy: rand(-.12, .12), r: rand(.7, 1.8), tw: rand(0, Math.PI * 2), speed: rand(.025, .07) });
  } else if (mode === "battlefield_dusk" || mode === "monster_battlefield" || mode === "monster_lair") {
    for (let i = 0; i < 34; i++) p.push({ x: rand(0, w), y: rand(h * 0.5, h), vx: rand(-0.3, 0.3), vy: rand(-1.4, -0.5), r: rand(1.5, 3.5), a: rand(.3, .8), life: rand(60, 160), age: 0 });
  } else if (mode === "harbor_port" || mode === "ship_deck") {
    for (let i = 0; i < 5; i++) p.push({ y: rand(h * 0.55, h * 0.9), amp: rand(2, 6), speed: rand(.01, .03), phase: rand(0, 6), width: w });
  } else if (mode === "dungeon_cave") {
    for (let i = 0; i < 16; i++) p.push({ x: rand(0, w), y: rand(-40, 0), vy: rand(1.2, 2.6), life: rand(40, 140), age: 0 });
  } else if (mode === "tower_hub") {
    for (let i = 0; i < 10; i++) p.push({ x: rand(0, w), y: rand(0, h), r: rand(1, 2.4), phase: rand(0, 6), speed: rand(.02, .05) });
  }
}

function seedSceneGlows(mode) {
  const glowMap = {
    indoor_grandhall: [[.13, .38, 30], [.87, .38, 30], [.31, .56, 20], [.69, .56, 20], [.50, .17, 20]],
    dungeon_cave: [[.12, .44, 27], [.83, .49, 25], [.37, .58, 16]],
    monster_lair: [[.08, .64, 23], [.89, .64, 23]],
    battlefield_dusk: [[.28, .73, 14], [.66, .68, 12]],
    monster_battlefield: [[.25, .76, 13], [.72, .71, 14]],
    merchant_shop: [[.36, .28, 18], [.62, .30, 14]],
    tavern_inn: [[.12, .48, 30], [.84, .31, 15], [.55, .24, 12]],
    arena_floor: [[.08, .67, 13], [.92, .67, 13]],
  };
  sceneFx.glows = (glowMap[mode] || []).map(([x, y, r]) => ({ x, y, r, phase: rand(0, Math.PI * 2), speed: rand(.045, .085) }));
}

function tickSceneFx() {
  sceneFx.raf = requestAnimationFrame(tickSceneFx);
  const { ctx, w, h, mode, particles, glows } = sceneFx;
  if (!ctx || !w || !h) return;
  ctx.clearRect(0, 0, w, h);
  if (!APP.animationsEnabled) return;

  glows.forEach((g) => {
    g.phase += g.speed;
    const flicker = .86 + Math.sin(g.phase) * .09 + Math.sin(g.phase * 2.7) * .05;
    const x = g.x * w, y = g.y * h, radius = g.r * flicker;
    const halo = ctx.createRadialGradient(x, y, 0, x, y, radius * 3.2);
    halo.addColorStop(0, "rgba(255,232,145,.55)");
    halo.addColorStop(.23, "rgba(255,145,48,.28)");
    halo.addColorStop(1, "rgba(255,85,18,0)");
    ctx.fillStyle = halo; ctx.fillRect(x - radius * 3.2, y - radius * 3.2, radius * 6.4, radius * 6.4);
    ctx.fillStyle = "rgba(255,226,133,.78)";
    ctx.beginPath(); ctx.ellipse(x, y, Math.max(1.5, radius * .09), Math.max(4, radius * .26), Math.sin(g.phase) * .08, 0, Math.PI * 2); ctx.fill();
  });

  if (mode === "town_square" || mode === "kingdom" || mode === "arena_floor") {
    particles.forEach((p) => {
      p.phase += p.speed; const bob = Math.sin(p.phase) * 2; const s = p.scale;
      ctx.fillStyle = p.hue > .5 ? "rgba(10,10,14,.52)" : "rgba(35,20,16,.48)";
      ctx.fillRect(Math.round(p.x - 3 * s), Math.round(p.y + bob), Math.round(6 * s), Math.round(14 * s));
      ctx.beginPath(); ctx.arc(Math.round(p.x), Math.round(p.y - 4 * s + bob), 4 * s, 0, 7); ctx.fill();
      p.x += Math.sin(p.phase * .4) * .08;
    });
  } else if (mode === "duel") {
    particles.forEach((p) => {
      p.x += p.vx; p.y += p.vy; p.age++;
      if (p.age > p.life) { p.x = w / 2 + rand(-20, 20); p.y = h * .55; p.age = 0; }
      ctx.globalAlpha = 1 - p.age / p.life; ctx.fillStyle = "#ffd36a"; ctx.fillRect(p.x, p.y, p.r * 2, p.r);
    }); ctx.globalAlpha = 1;
  } else if (mode === "forest_path") {
    ctx.save();
    particles.forEach((p) => {
      p.x += p.vx; p.y += p.vy; p.rot += p.vr;
      if (p.y > h + 10 || p.x < -10) { p.x = rand(0, w); p.y = -10; }
      ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.rot); ctx.globalAlpha = p.a;
      ctx.fillStyle = "#b98a3f"; ctx.beginPath(); ctx.ellipse(0, 0, p.r, p.r * 0.5, 0, 0, 7); ctx.fill(); ctx.restore();
    });
    ctx.restore();
  } else if (mode === "starry_sky") {
    particles.forEach((p) => {
      p.tw += p.speed;
      const a = 0.4 + Math.abs(Math.sin(p.tw)) * 0.6;
      ctx.globalAlpha = a; ctx.fillStyle = "#fff"; ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, 7); ctx.fill();
    });
    ctx.globalAlpha = 1;
  } else if (mode === "night_wilderness" || mode === "merchant_shop" || mode === "tavern_inn" || mode === "academy_classroom") {
    particles.forEach((p) => {
      p.tw += p.speed; p.x += p.vx + Math.sin(p.tw) * .08; p.y += p.vy + Math.cos(p.tw * .7) * .05;
      if (p.x < -5) p.x = w + 5; if (p.x > w + 5) p.x = -5;
      if (p.y < h * .3) p.y = h * .9; if (p.y > h * .94) p.y = h * .35;
      const a = .15 + Math.pow(Math.abs(Math.sin(p.tw)), 3) * .8;
      ctx.globalAlpha = a; ctx.fillStyle = mode === "night_wilderness" ? "#dfff8a" : "#ffe3a2"; ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, 7); ctx.fill();
    });
    ctx.globalAlpha = 1;
  } else if (mode === "battlefield_dusk" || mode === "monster_battlefield" || mode === "monster_lair") {
    particles.forEach((p) => {
      p.x += p.vx; p.y += p.vy; p.age++;
      if (p.age > p.life) { p.x = rand(0, w); p.y = rand(h * 0.6, h); p.age = 0; }
      const fade = 1 - p.age / p.life;
      ctx.globalAlpha = p.a * fade;
      ctx.fillStyle = mode === "battlefield_dusk" ? "#ff8a3d" : "#7fffb0";
      ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, 7); ctx.fill();
    });
    ctx.globalAlpha = 1;
  } else if (mode === "harbor_port" || mode === "ship_deck") {
    ctx.strokeStyle = "rgba(180,220,235,.35)"; ctx.lineWidth = 1;
    particles.forEach((p) => {
      p.phase += p.speed; ctx.beginPath();
      for (let x = 0; x <= p.width; x += 8) ctx.lineTo(x, p.y + Math.sin(x * 0.03 + p.phase) * p.amp);
      ctx.stroke();
    });
  } else if (mode === "dungeon_cave") {
    ctx.fillStyle = "rgba(180,220,255,.5)";
    particles.forEach((p) => {
      p.y += p.vy; p.age++;
      if (p.age > p.life) { p.y = rand(-40, 0); p.x = rand(0, w); p.age = 0; }
      ctx.fillRect(p.x, p.y, 1.4, 6);
    });
  } else if (mode === "tower_hub") {
    ctx.strokeStyle = "rgba(120,220,255,.5)";
    particles.forEach((p) => {
      p.phase += p.speed;
      const a = 0.3 + Math.abs(Math.sin(p.phase)) * 0.7;
      ctx.globalAlpha = a; ctx.beginPath(); ctx.arc(p.x, p.y, p.r * 4, 0, 7); ctx.stroke();
    });
    ctx.globalAlpha = 1;
  }
}

// ---------------------------------------------------------------------------
// Modals
// ---------------------------------------------------------------------------
function openModal(id) {
  $("#" + id).classList.add("open");
  if (id === "modal-journal") $$("[data-journal]").forEach((b) => b.classList.toggle("nav-open", b.getAttribute("data-journal") === APP.journalTab));
}
function closeModal(id) {
  $("#" + id).classList.remove("open");
  if (id === "modal-journal") $$("[data-journal]").forEach((b) => b.classList.remove("nav-open"));
}
$$(".modal-close").forEach((b) => b.addEventListener("click", () => closeModal(b.getAttribute("data-close"))));
$$(".modal-backdrop").forEach((m) => m.addEventListener("click", (e) => {
  const locked = new Set(["modal-welcome", "modal-difficult-check", "modal-timing-challenge", "modal-tactical-challenge", "modal-major-roll", "modal-lethal"]);
  if (e.target === m && !locked.has(m.id)) closeModal(m.id);
}));

// ---------------------------------------------------------------------------
// Turn submission
// ---------------------------------------------------------------------------
function setBusy(b) {
  APP.busy = b;
  const pill = $("#hdr-ai");
  $("#btn-send").disabled = b;
  if (b) { pill.textContent = "AI: GENERATING..."; pill.classList.add("busy"); }
  else { pill.textContent = "AI: READY"; pill.classList.remove("busy"); }
}

async function submitAction(text) {
  if (APP.busy || !text) return;
  if (!APP.campaignActive) { showToast("Start a campaign first.", "system"); openModal("modal-campaign"); return; }
  playSfx("ui_click");
  try {
    const result = await apiPost("/api/actions/queue", { action: text });
    $("#action-input").value = "";
    APP.state.queued_actions = result.queued_actions || [];
    renderQueuedActions(APP.state.queued_actions);
  } catch (e) {
    showToast(e.message, "danger"); playSfx("error");
  }
}

async function handleTurnResult(result, action) {
  if (result.status === "lethal_confirm_required") {
    APP.pendingLethal = { kind: "action", action };
    $("#lethal-warning").textContent = result.assessment.lethal_warning || "Failure could kill your character.";
    $("#lethal-risk").textContent = "Risk: " + (result.assessment.lethal_risk || "high").toUpperCase();
    APP.pendingLethal.assessment = result.assessment;
    openModal("modal-lethal");
    return;
  }
  if (result.status === "impossible") {
    appendStoryEntries([{ text: "[ACTION NOT POSSIBLE]\n" + result.reason, tag: "system" }]);
    return;
  }
  appendStoryEntries(result.story);
  if (result.roll) {
    playSfx("dice");
    if (result.roll.breakthrough) flashScreen("success");
    if (!result.roll.success) { flashScreen("danger"); shakeApp(); }
  }
  renderState(result.state);
  handleNotifications(result.notifications);
  if (result.died) {
    playSfx("danger"); shakeApp();
    openModal("modal-death");
  }
  refreshUsagePill();
}

// ---------------------------------------------------------------------------
// Combat — every round here is resolved entirely locally by the backend (the
// same d100-vs-difficulty math as a normal check, reusing real stats/skills),
// so clicking Attack/Defend/Flee is instant and free. The only AI call in
// this whole flow is the single narrate_combat() request once the fight
// ends, which turns the mechanical log into prose and applies loot/injury
// consequences exactly like any other resolved turn.
// ---------------------------------------------------------------------------
function combatLogLine(e) {
  const swingNote = e.extra_swing ? " [bonus swing — faster]" : "";
  if (e.actor === "player" && e.action === "defend") return { text: "You brace for the enemy's attack.", cls: "player" };
  if (e.actor === "player" && e.action === "flee") return { text: e.success ? "You break away from the fight." : "You try to flee — it fails.", cls: e.success ? "player" : "miss" };
  if (e.actor === "player" && e.action === "overwhelm") {
    const label = e.ability && e.ability !== "Overwhelm" ? e.ability : "an overwhelming personal ability";
    return e.success
      ? { text: `You end the fight outright with ${label}!`, cls: "hit" }
      : { text: `You try to end the fight with ${label} — it doesn't land this time.`, cls: "miss" };
  }
  if (e.actor === "player" && e.action === "heal") {
    const label = e.ability && e.ability !== "Attack" ? e.ability : "a plain effort";
    const costNote = e.resource_cost ? ` (-${e.resource_cost} ${APP.state?.resource_name || "Energy"})` : "";
    return e.success
      ? { text: `You use ${label} and recover ${e.healed ?? 0} HP${swingNote}${costNote}.`, cls: "player" }
      : { text: `You try to use ${label} — it fizzles${swingNote}${costNote}.`, cls: "miss" };
  }
  if (e.actor === "player" && e.action === "debuff") {
    const label = e.ability && e.ability !== "Attack" ? e.ability : "an effect";
    const costNote = e.resource_cost ? ` (-${e.resource_cost} ${APP.state?.resource_name || "Energy"})` : "";
    return e.applied
      ? { text: `You use ${label} on ${e.target || "the enemy"} — it takes hold, weakening them${swingNote}${costNote}.`, cls: "player" }
      : { text: `You try ${label} on ${e.target || "the enemy"} — it doesn't take hold${swingNote}${costNote}.`, cls: "miss" };
  }
  if (e.actor === "player") {
    const label = e.ability && e.ability !== "Attack" ? e.ability : "a plain attack";
    const costNote = e.resource_cost ? ` (-${e.resource_cost} ${APP.state?.resource_name || "Energy"})` : "";
    if (e.shrugged) return { text: `${e.target || "The enemy"} completely shrugs off your ${label}${swingNote}${costNote}.`, cls: "miss" };
    return e.success
      ? { text: `You hit ${e.target || "the enemy"} with ${label} for ${e.damage ?? 0} dmg${e.massive ? " — MASSIVE" : ""}${e.breakthrough ? " — BREAKTHROUGH" : ""}${swingNote}${costNote}.`, cls: "hit" }
      : { text: `You try ${label} on ${e.target || "the enemy"} — it misses${swingNote}${costNote}.`, cls: "miss" };
  }
  if (e.actor === "enemy") {
    if (e.shrugged) return { text: `You completely shrug off ${e.name || "the enemy"}'s attack${swingNote}.`, cls: "player" };
    return e.success
      ? { text: `${e.name || "The enemy"} hits you for ${e.damage ?? 0} dmg${e.massive ? " — MASSIVE" : ""}${swingNote}.`, cls: "hit" }
      : { text: `${e.name || "The enemy"}'s attack misses${swingNote}.`, cls: "miss" };
  }
  return { text: "Something happens.", cls: "" };
}

const COMBAT_EFFECT_ICON = { heal: "🩹 ", debuff: "☠ ", damage: "" };
function combatAbilityEffectType(s, name) {
  const detail = (s.skills || {})[name];
  const t = (detail && typeof detail === "object" ? detail.effect_type : "") || "";
  return ["damage", "heal", "debuff"].includes(t) ? t : "damage";
}
function populateCombatAbilitySelect(s) {
  const combat = s.combat || {};
  const cooldowns = combat.cooldowns || {};
  const abilitySel = $("#combat-ability");
  const skills = Object.keys(s.skills || {});
  const priorAbility = abilitySel.value;
  abilitySel.innerHTML = `<option value="">Plain Attack</option>` + skills.map((name) => {
    const readyAt = cooldowns[name] || 0;
    const remaining = readyAt - (combat.round || 1);
    const locked = remaining > 0;
    const icon = COMBAT_EFFECT_ICON[combatAbilityEffectType(s, name)];
    const label = locked ? `${icon}${name} (recovering, ${remaining} rd)` : `${icon}${name}`;
    return `<option value="${escapeHtml(name)}"${locked ? " disabled" : ""}>${escapeHtml(label)}</option>`;
  }).join("");
  if (skills.includes(priorAbility) && !$(`#combat-ability option[value="${CSS.escape(priorAbility)}"]`)?.disabled) abilitySel.value = priorAbility;
  updateCombatAttackButtonLabel(s);
}

const COMBAT_ACTION_ICON = {
  damage: ICONS.sword,
  heal: `<svg ${SVG_ICON_ATTRS}><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>`,
  debuff: `<svg ${SVG_ICON_ATTRS}><circle cx="12" cy="12" r="10"/><line x1="8" y1="12" x2="16" y2="12"/></svg>`,
};
const COMBAT_ACTION_LABEL = { damage: "ATTACK", heal: "HEAL", debuff: "DEBUFF" };
function updateCombatAttackButtonLabel(s) {
  const selected = $("#combat-ability").value;
  const effectType = selected ? combatAbilityEffectType(s, selected) : "damage";
  $("#btn-combat-attack").innerHTML = `<i class="btn-icon-svg">${COMBAT_ACTION_ICON[effectType]}</i>${COMBAT_ACTION_LABEL[effectType]}`;
}
$("#combat-ability").addEventListener("change", () => { if (APP.state) updateCombatAttackButtonLabel(APP.state); });

// Small, purely cosmetic combat feedback — a floating number and a quick
// bar-flash — so a hit registers as an event, not just a number changing in
// place. No shake here by design; screen-shake is reserved for the moments
// that already used it (deaths, lethal danger) and isn't being added to.
function spawnFloatingCombatNumber(targetSelector, amount, kind) {
  const target = $(targetSelector);
  if (!target || !amount) return;
  const rect = target.getBoundingClientRect();
  const el = document.createElement("span");
  el.className = "floating-combat-number " + kind;
  el.textContent = (kind === "heal" ? "+" : "-") + Math.round(Math.abs(amount));
  el.style.left = (rect.left + rect.width / 2) + "px";
  el.style.top = rect.top + "px";
  document.body.appendChild(el);
  el.addEventListener("animationend", () => el.remove());
  setTimeout(() => el.remove(), 1200);
}

function flashCombatBar(targetSelector) {
  const target = $(targetSelector);
  if (!target) return;
  target.classList.remove("bar-flash");
  void target.offsetWidth;
  target.classList.add("bar-flash");
}

function renderCombatPanel(s) {
  const panel = $("#combat-panel");
  const combat = s.combat || {};
  if (!combat.active) { panel.hidden = true; return; }
  panel.hidden = false;
  $("#combat-round").textContent = combat.round ?? 1;
  const e = combat.enemy || {};
  const dead = e.alive === false || Number(e.hp) <= 0;
  const pct = 100 * (Number(e.hp) || 0) / Math.max(1, Number(e.hp_max) || 1);
  const enemyBox = $("#combat-enemy");
  enemyBox.classList.toggle("dead", dead);
  const groupNote = e.is_group ? `<div class="combat-enemy-sub">Fighting as a group${e.group_size ? ` — roughly ${escapeHtml(e.group_size)} strong` : ""}</div>` : "";
  enemyBox.innerHTML = `<div class="combat-enemy-head"><b>${escapeHtml(e.name || "Enemy")}</b><span>${dead ? "DEFEATED" : `${escapeHtml(e.hp)} / ${escapeHtml(e.hp_max)}`}</span></div>${groupNote}<div class="bar-track"><div class="bar-fill" style="width:${Math.max(0, Math.min(100, pct))}%"></div></div>`;
  const resourceRow = $("#combat-resource-row");
  if (s.resource_max) resourceRow.innerHTML = `<span>${escapeHtml(s.resource_name || "Energy")}</span><b>${escapeHtml(s.resource ?? 0)} / ${escapeHtml(s.resource_max)}</b>`;
  else resourceRow.innerHTML = "";
  populateCombatAbilitySelect(s);
}

function appendCombatLogEntries(entries) {
  const log = $("#combat-log");
  (entries || []).forEach((e) => {
    const { text, cls } = combatLogLine(e);
    const row = document.createElement("div");
    row.className = "combat-log-row " + cls;
    row.textContent = text;
    log.appendChild(row);
  });
  log.scrollTop = log.scrollHeight;
  // Mirror the same lines into the main Chronicle, styled like a dice check,
  // so combat rounds are visible where the player is already looking —
  // purely a local render, no server round trip or AI cost involved.
  const chronicleLines = (entries || []).map((e) => combatLogLine(e).text).join("\n");
  if (chronicleLines) appendStoryEntries([{ text: "[COMBAT]\n" + chronicleLines, tag: "roll" }]);
}

let combatRoundBusy = false;
function setCombatButtonsDisabled(disabled) {
  $("#btn-combat-attack").disabled = $("#btn-combat-defend").disabled = $("#btn-combat-flee").disabled = $("#btn-combat-overwhelm").disabled = disabled;
}
async function submitCombatAction(action) {
  // Deliberately does NOT go through setBusy()/the "AI: GENERATING..." pill —
  // this round is resolved entirely locally and returns near-instantly, so
  // showing an AI-busy state here would misrepresent what's actually free.
  if (combatRoundBusy || APP.busy || !APP.state?.combat?.active) return;
  combatRoundBusy = true;
  setCombatButtonsDisabled(true);
  try {
    const payload = { action };
    if ((action === "attack" || action === "overwhelm") && $("#combat-ability").value) payload.ability = $("#combat-ability").value;
    const priorEnemyHp = Number(APP.state?.combat?.enemy?.hp ?? NaN);
    const priorPlayerHp = Number(APP.state?.hp ?? NaN);
    const result = await apiPost("/api/combat/action", payload);
    appendCombatLogEntries(result.log_tail);
    playSfx("dice");
    if (result.hp !== undefined) { APP.state.hp = result.hp; APP.state.hp_max = result.hp_max; }
    if (result.resource !== undefined) { APP.state.resource = result.resource; APP.state.resource_max = result.resource_max; }
    APP.state.combat = result.combat;
    renderState(APP.state);
    const newEnemyHp = Number(result.combat?.enemy?.hp ?? NaN);
    if (Number.isFinite(priorEnemyHp) && Number.isFinite(newEnemyHp) && newEnemyHp < priorEnemyHp) {
      spawnFloatingCombatNumber("#combat-enemy .bar-track", priorEnemyHp - newEnemyHp, "damage");
      flashCombatBar("#combat-enemy .bar-fill");
      playSfx("hit");
    }
    if (Number.isFinite(priorPlayerHp) && result.hp !== undefined && Number(result.hp) < priorPlayerHp) {
      spawnFloatingCombatNumber("#bar-hp", priorPlayerHp - Number(result.hp), "damage");
    } else if (Number.isFinite(priorPlayerHp) && result.hp !== undefined && Number(result.hp) > priorPlayerHp) {
      spawnFloatingCombatNumber("#bar-hp", Number(result.hp) - priorPlayerHp, "heal");
    }
    if (!result.combat?.active) {
      shakeApp();
      setBusy(true);
      try {
        const narrated = await apiPost("/api/combat/narrate", {});
        await handleTurnResult(narrated);
      } finally { setBusy(false); }
    } else if (result.player_died) {
      playSfx("danger"); shakeApp();
    }
  } catch (e) { showToast(e.message, "danger"); }
  finally { combatRoundBusy = false; setCombatButtonsDisabled(false); }
}
$("#btn-combat-attack").addEventListener("click", () => submitCombatAction("attack"));
$("#btn-combat-defend").addEventListener("click", () => submitCombatAction("defend"));
$("#btn-combat-flee").addEventListener("click", () => submitCombatAction("flee"));
$("#btn-combat-overwhelm").addEventListener("click", () => submitCombatAction("overwhelm"));

$("#btn-lethal-confirm").addEventListener("click", async () => {
  closeModal("modal-lethal");
  const pending = APP.pendingLethal;
  if (!pending) return;
  setBusy(true);
  try {
    if (pending.kind === "action") {
      appendStoryEntries([{ text: "> " + pending.action, tag: "player" }]);
      const result = await apiPost("/api/action/submit", { action: pending.action, confirmed_lethal: true, assessment: pending.assessment });
      await handleTurnResult(result, pending.action);
    } else if (pending.kind === "timeskip") {
      const payload = { ...pending.timeskip, confirmed_lethal: true };
      const result = await apiPost("/api/time/resolve", payload);
      await processTimeSkipResolution(result, payload);
    }
  } catch (e) { showToast(e.message, "danger"); playSfx("error"); }
  finally { setBusy(false); APP.pendingLethal = null; runBackgroundCheck(); }
});
$("#btn-lethal-cancel").addEventListener("click", () => {
  closeModal("modal-lethal");
  appendStoryEntries([{ text: "[ACTION REVERTED]\nYou stop before committing to the lethal decision.", tag: "danger" }]);
  APP.pendingLethal = null;
});

$("#btn-death-rewind").addEventListener("click", async () => {
  closeModal("modal-death");
  try {
    const result = await apiPost("/api/action/rewind_death", {});
    appendStoryEntries(result.story);
    renderState(result.state);
  } catch (e) { showToast(e.message, "danger"); }
});
$("#btn-death-keep").addEventListener("click", () => closeModal("modal-death"));

$("#btn-send").addEventListener("click", () => submitAction($("#action-input").value.trim()));
$("#action-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submitAction($("#action-input").value.trim()); }
});

$("#btn-retry-opening").addEventListener("click", async () => {
  if (!APP.campaignActive) { openModal("modal-campaign"); return; }
  setBusy(true);
  try {
    const result = await apiPost("/api/campaign/opening", {});
    appendStoryEntries(result.story);
    renderState(result.state);
  } catch (e) { showToast(e.message, "danger"); appendStoryEntries([{ text: "[AI SETUP REQUIRED]\n" + e.message, tag: "danger" }]); }
  finally { setBusy(false); }
});

// ---------------------------------------------------------------------------
// Background world simulation polling
// ---------------------------------------------------------------------------
let bgPollTimer = null;
async function runBackgroundCheck() {
  try {
    const r = await apiPost("/api/background/run", {});
    if (r.started) setTimeout(pollBackground, 1500);
  } catch (e) {}
}
async function pollBackground() {
  try {
    const r = await apiGet("/api/background/poll");
    (r.events || []).forEach((ev) => {
      if (ev.type === "chat") {
        showToast(`${ev.sender}: ${ev.message}`, "message"); playSfx("message");
        appendStoryEntries([{ text: `[MESSAGE REACTION — ${ev.sender}]\n${ev.message}`, tag: "system" }]);
        if (ev.state) renderState(ev.state);
      } else if (ev.type === "world_event") {
        showToast(ev.message, "world"); playSfx("world_event");
        appendStoryEntries([{ text: `[WORLD REACTION]\n${ev.message}`, tag: "system" }]);
        if (ev.state) renderState(ev.state);
      }
    });
  } catch (e) {}
}
// World simulation is intentionally advanced only after the player confirms
// an Advance plan. This prevents unsolicited GM/world responses while the
// player is still queuing actions.

// ---------------------------------------------------------------------------
// Time control
// ---------------------------------------------------------------------------
function syncTimeControl(unitSelector, amountSelector, amountFieldSelector, momentLabelSelector, helpSelector) {
  const unit = $(unitSelector).value;
  const isMoment = unit === "moment";
  const isEvent = unit === "next_event";
  const isEventDriven = isMoment || isEvent;
  const amount = $(amountSelector);
  amount.hidden = isEventDriven;
  amount.disabled = isEventDriven;
  if (isEventDriven) amount.value = "1";
  if (amountFieldSelector) $(amountFieldSelector).hidden = isEventDriven;
  if (momentLabelSelector) {
    $(momentLabelSelector).hidden = !isEventDriven;
    $(momentLabelSelector).textContent = isEvent ? "MAJOR EVENT" : "NEXT BEAT";
  }
  if (helpSelector) {
    $(helpSelector).textContent = isEvent
      ? "Continues through routine updates and stops naturally at the next major personal or canon event."
      : isMoment ? "Moment resolves exactly one contextual story beat, never more than 24 hours."
      : "Long skips simulate the full period and may stop early for goals or major events.";
  }
}

$("#time-unit").addEventListener("change", () => syncTimeControl("#time-unit", "#time-amount", null, null, "#time-control-help"));
$("#td-unit").addEventListener("change", () => syncTimeControl("#td-unit", "#td-amount", "#td-amount-field"));
syncTimeControl("#time-unit", "#time-amount", null, null, "#time-control-help");
syncTimeControl("#td-unit", "#td-amount", "#td-amount-field");

$("#btn-advance").addEventListener("click", async () => {
  if (APP.busy || !APP.campaignActive) return;
  const draft = $("#action-input").value.trim();
  if (draft) await submitAction(draft);
  const unit = $("#time-unit").value;
  const amount = ["moment", "next_event"].includes(unit) ? 1 : parseInt($("#time-amount").value || "1", 10);
  await beginTimeSkip(amount, unit, $("#time-plan").value, "normal");
});
$("#btn-detailed-time").addEventListener("click", () => {
  $("#td-amount").value = $("#time-amount").value;
  $("#td-unit").value = $("#time-unit").value;
  syncTimeControl("#td-unit", "#td-amount", "#td-amount-field");
  $("#td-orders").value = $("#time-plan").value;
  openModal("modal-time-detail");
});
$("#btn-begin-timeskip").addEventListener("click", async () => {
  const unit = $("#td-unit").value;
  const amount = ["moment", "next_event"].includes(unit) ? 1 : parseInt($("#td-amount").value || "1", 10);
  const orders = $("#td-orders").value;
  const intensity = $("#td-intensity").value;
  closeModal("modal-time-detail");
  await beginTimeSkip(amount, unit, orders, intensity);
});

async function beginTimeSkip(amount, unit, orders, intensity) {
  if (!APP.campaignActive) { showToast("Start a campaign first.", "system"); return; }
  setBusy(true);
  try {
    const assessData = await apiPost("/api/time/assess", { amount, unit, orders, intensity });
    const payload = { amount: assessData.amount, unit: assessData.unit, orders: assessData.orders, intensity: assessData.intensity, assessment: assessData.assessment };
    APP.pendingAdvance = payload;
    const difficult = payload.assessment?.difficult_checks || [];
    if (difficult.length) {
      APP.pendingDifficulty = { payload, checks: difficult };
      renderDifficultyGate(difficult);
      openModal("modal-difficult-check");
      return;
    }
    // Not risky enough to stop and ask, but still worth a quick heads-up
    // before committing — the same odds math just renders as a toast
    // instead of a blocking gate.
    const previews = payload.assessment?.check_previews || [];
    previews.slice(0, 2).forEach((p) => {
      const breakdown = formatBreakdownText(p.bonus_breakdown);
      showToast(`${p.action || p.reason}: about ${p.odds_percent ?? "?"}% odds${breakdown ? ` (${breakdown})` : ""}`, "system");
    });
    await resolveAssessedTimeSkip(payload);
  } catch (e) { renderQueuedActions(APP.state?.queued_actions || []); showToast(e.message, "danger"); playSfx("error"); }
  finally { setBusy(false); }
}

async function resolveAssessedTimeSkip(payload) {
  setBusy(true);
  try {
    $("#action-input").value = "";
    $("#time-plan").value = "";
    renderQueuedActions([]);
    playSfx("time_skip");
    const result = await apiPost("/api/time/resolve", payload);
    await processTimeSkipResolution(result, payload);
  } catch (error) {
    renderQueuedActions(APP.state?.queued_actions || []);
    showToast(error.message, "danger"); playSfx("error");
  } finally { setBusy(false); }
}

function formatBreakdownText(parts) {
  if (!Array.isArray(parts) || !parts.length) return "";
  return parts.map((p) => `${p.label} ${Number(p.value) >= 0 ? "+" : ""}${p.value}`).join(" · ");
}

function renderDifficultyGate(checks) {
  $("#difficult-check-list").innerHTML = checks.map((check) => {
    const range = check.difficulty_range || ["?", "?"];
    const bonus = Number(check.known_bonus || 0);
    const breakdown = formatBreakdownText(check.bonus_breakdown);
    return `<article class="difficult-check-row"><header><b>${escapeHtml(check.action || check.reason)}</b><span>${escapeHtml(check.risk || "none")} risk</span></header><div><strong>Needed total ${escapeHtml(range[0])}–${escapeHtml(range[1])}</strong><span>Expected raw roll: about ${escapeHtml(check.expected_raw_needed)}/100 (~${escapeHtml(check.odds_percent ?? "?")}% odds)</span><span>${escapeHtml(check.ability)}${check.skill ? ` · ${escapeHtml(check.skill)}` : ""} · total bonus ${bonus >= 0 ? "+" : ""}${escapeHtml(bonus)}</span>${breakdown ? `<span class="difficult-check-breakdown">${escapeHtml(breakdown)}</span>` : ""}</div></article>`;
  }).join("");
}

$("#btn-difficult-roll").addEventListener("click", async () => {
  const pending = APP.pendingDifficulty;
  if (!pending) return;
  closeModal("modal-difficult-check");
  APP.pendingDifficulty = null;
  await resolveAssessedTimeSkip(pending.payload);
});

$("#btn-difficult-cancel").addEventListener("click", () => {
  closeModal("modal-difficult-check");
  APP.pendingDifficulty = null;
  APP.pendingAdvance = null;
  renderQueuedActions(APP.state?.queued_actions || []);
  showToast("Advance canceled. Your queued actions are unchanged.", "system");
  $("#action-input").focus();
});

$("#btn-difficult-timing").addEventListener("click", () => startChallenge("timing"));
$("#btn-difficult-tactical").addEventListener("click", () => startChallenge("tactical"));

const TACTICAL_STAGES = [
  { title: "Stage 1 — Read the situation", help: "Choose how to create an opening.", options: [
    { label: "Study the opening", detail: "Steady information, modest payoff.", points: 18, volatility: 3 },
    { label: "Exploit the environment", detail: "Better payoff if circumstances cooperate.", points: 22, volatility: 8 },
    { label: "Seize the initiative", detail: "High reward with a serious swing.", points: 27, volatility: 17 },
  ]},
  { title: "Stage 2 — Execute", help: "Choose how to commit your technique.", options: [
    { label: "Precise technique", detail: "Reliable and resource-conscious.", points: 20, volatility: 4 },
    { label: "Adaptive feint", detail: "Strong but dependent on reading the opposition.", points: 24, volatility: 10 },
    { label: "Maximum output", detail: "Powerful, costly, and unstable.", points: 29, volatility: 19 },
  ]},
  { title: "Stage 3 — Finish", help: "Decide how much certainty to trade for impact.", options: [
    { label: "Secure the result", detail: "Protect what you have gained.", points: 17, volatility: 2 },
    { label: "Press the advantage", detail: "Balanced risk and reward.", points: 23, volatility: 9 },
    { label: "All or nothing", detail: "The largest possible swing.", points: 31, volatility: 24 },
  ]},
];

function startChallenge(mode) {
  const pending = APP.pendingDifficulty;
  if (!pending) return;
  closeModal("modal-difficult-check");
  APP.challenge = { mode, payload: pending.payload, checks: pending.checks, index: 0, scores: {}, modes: {}, attempts: [], stage: 0, tacticalPoints: 10 };
  APP.pendingDifficulty = null;
  if (mode === "timing") showTimingCheck(); else showTacticalCheck();
}

function currentChallengeCheck() { return APP.challenge?.checks?.[APP.challenge.index]; }

function finishChallengeCheck(score) {
  const challenge = APP.challenge;
  const check = currentChallengeCheck();
  challenge.scores[check.id] = Math.max(1, Math.min(100, Math.round(score)));
  challenge.modes[check.id] = challenge.mode;
  challenge.index += 1;
  challenge.attempts = []; challenge.stage = 0; challenge.tacticalPoints = 10;
  if (challenge.index < challenge.checks.length) {
    if (challenge.mode === "timing") showTimingCheck(); else showTacticalCheck();
    return;
  }
  const payload = { ...challenge.payload, manual_rolls: { ...(challenge.payload.manual_rolls || {}), ...challenge.scores }, challenge_modes: challenge.modes };
  closeModal(challenge.mode === "timing" ? "modal-timing-challenge" : "modal-tactical-challenge");
  APP.challenge = null;
  resolveAssessedTimeSkip(payload);
}

let timingAnimation = 0;
let timingPosition = 0;
function animateTimingNeedle(startTime, speed) {
  const elapsed = performance.now() - startTime;
  const phase = (elapsed % speed) / speed;
  timingPosition = phase <= .5 ? phase * 200 : (1 - phase) * 200;
  $("#timing-needle").style.left = timingPosition + "%";
  timingAnimation = requestAnimationFrame(() => animateTimingNeedle(startTime, speed));
}

function beginTimingAttempt() {
  cancelAnimationFrame(timingAnimation);
  const check = currentChallengeCheck();
  const speed = Math.max(700, 1450 - Number(check?.expected_raw_needed || 65) * 6);
  animateTimingNeedle(performance.now(), speed);
  $("#btn-timing-lock").disabled = false;
  $("#btn-timing-lock").textContent = "LOCK TIMING";
}

function showTimingCheck() {
  const challenge = APP.challenge, check = currentChallengeCheck();
  $("#timing-check-count").textContent = `CHECK ${challenge.index + 1} OF ${challenge.checks.length}`;
  $("#timing-check-title").textContent = check.action || check.reason;
  $("#timing-check-info").textContent = `${check.ability} · expected raw requirement about ${check.expected_raw_needed}/100 · known bonus ${Number(check.known_bonus || 0) >= 0 ? "+" : ""}${check.known_bonus || 0}`;
  $("#timing-attempts").textContent = "Attempt 1 of 3";
  openModal("modal-timing-challenge");
  beginTimingAttempt();
}

$("#btn-timing-lock").addEventListener("click", () => {
  const challenge = APP.challenge;
  if (!challenge || challenge.mode !== "timing") return;
  cancelAnimationFrame(timingAnimation);
  const score = Math.max(1, Math.round(100 - Math.abs(timingPosition - 50) * 2));
  challenge.attempts.push(score);
  $("#btn-timing-lock").disabled = true;
  $("#btn-timing-lock").textContent = `SCORE ${score}/100`;
  $("#timing-attempts").textContent = challenge.attempts.map((value, index) => `Attempt ${index + 1}: ${value}`).join(" · ");
  if (challenge.attempts.length >= 3) {
    setTimeout(() => finishChallengeCheck(challenge.attempts.reduce((a, b) => a + b, 0) / 3), 450);
  } else {
    setTimeout(() => { $("#timing-attempts").textContent += ` · Next: ${challenge.attempts.length + 1} of 3`; beginTimingAttempt(); }, 450);
  }
});

function showTacticalCheck() {
  const challenge = APP.challenge, check = currentChallengeCheck();
  $("#tactical-check-count").textContent = `CHECK ${challenge.index + 1} OF ${challenge.checks.length}`;
  $("#tactical-check-title").textContent = check.action || check.reason;
  $("#tactical-check-info").textContent = `${check.ability} · expected raw requirement about ${check.expected_raw_needed}/100 · known bonus ${Number(check.known_bonus || 0) >= 0 ? "+" : ""}${check.known_bonus || 0}`;
  openModal("modal-tactical-challenge");
  renderTacticalStage();
}

function renderTacticalStage() {
  const challenge = APP.challenge, stage = TACTICAL_STAGES[challenge.stage];
  $("#tactical-stage-title").textContent = stage.title;
  $("#tactical-stage-help").textContent = stage.help;
  $("#tactical-progress").textContent = `Approach score so far: ${challenge.tacticalPoints}`;
  $("#tactical-options").innerHTML = stage.options.map((option, index) => `<button type="button" data-tactical-option="${index}"><b>${escapeHtml(option.label)}</b><span>${escapeHtml(option.detail)}</span><small>Base +${option.points} · uncertainty ±${option.volatility}</small></button>`).join("");
}

$("#tactical-options").addEventListener("click", (event) => {
  const button = event.target.closest("[data-tactical-option]");
  const challenge = APP.challenge;
  if (!button || !challenge || challenge.mode !== "tactical") return;
  const option = TACTICAL_STAGES[challenge.stage].options[Number(button.getAttribute("data-tactical-option"))];
  const random = new Uint32Array(1); crypto.getRandomValues(random);
  const swing = (random[0] % (option.volatility * 2 + 1)) - option.volatility;
  challenge.tacticalPoints += option.points + swing;
  challenge.stage += 1;
  if (challenge.stage >= TACTICAL_STAGES.length) finishChallengeCheck(challenge.tacticalPoints);
  else renderTacticalStage();
});

function abortChallenge() {
  cancelAnimationFrame(timingAnimation);
  closeModal("modal-timing-challenge"); closeModal("modal-tactical-challenge");
  APP.challenge = null; APP.pendingAdvance = null;
  renderQueuedActions(APP.state?.queued_actions || []);
  showToast("Challenge canceled. Your queued actions are unchanged.", "system");
}
$("#btn-timing-abort").addEventListener("click", abortChallenge);
$("#btn-tactical-abort").addEventListener("click", abortChallenge);

async function processTimeSkipResolution(result, payload) {
  if (result.status === "lethal_confirm_required") {
    APP.pendingLethal = { kind: "timeskip", timeskip: payload };
    $("#lethal-warning").textContent = result.check.lethal_warning || "This plan could kill your character.";
    $("#lethal-risk").textContent = "Risk: " + (result.check.lethal_risk || "high").toUpperCase();
    openModal("modal-lethal");
    return;
  }
  if (result.status === "manual_roll_required") {
    APP.pendingManualRoll = { payload, checkId: result.check_id, check: result.check };
    $("#major-roll-reason").textContent = result.check.major_reason || result.check.reason || "A major turning point hangs in the balance.";
    $("#major-roll-details").textContent = "Roll 1–100. The game adds all relevant stat, skill, title, and situation bonuses, then compares the total with the required number.";
    $("#d100-value").textContent = "?";
    $("#d100-orb").classList.remove("rolling", "revealed");
    $("#btn-major-roll").disabled = false;
    openModal("modal-major-roll");
    return;
  }
  handleTimeSkipResult(result, payload);
  APP.pendingAdvance = null;
  APP.pendingManualRoll = null;
  $("#time-plan").value = "";
  runBackgroundCheck();
}

$("#btn-major-roll").addEventListener("click", async () => {
  const pending = APP.pendingManualRoll;
  if (!pending) return;
  const button = $("#btn-major-roll");
  button.disabled = true;
  $("#d100-orb").classList.add("rolling");
  const ticker = setInterval(() => { $("#d100-value").textContent = String(1 + Math.floor(Math.random() * 100)); }, 55);
  try {
    const rolled = await apiPost("/api/dice/d100", {});
    await new Promise((resolve) => setTimeout(resolve, APP.animationsEnabled ? 1150 : 80));
    clearInterval(ticker);
    $("#d100-value").textContent = rolled.roll;
    $("#d100-orb").classList.remove("rolling"); $("#d100-orb").classList.add("revealed");
    playSfx("dice");
    await new Promise((resolve) => setTimeout(resolve, APP.animationsEnabled ? 650 : 40));
    closeModal("modal-major-roll");
    const payload = { ...pending.payload, manual_rolls: { ...(pending.payload.manual_rolls || {}), [pending.checkId]: rolled.roll } };
    APP.pendingAdvance = payload;
    const result = await apiPost("/api/time/resolve", payload);
    await processTimeSkipResolution(result, payload);
  } catch (error) { clearInterval(ticker); showToast(error.message, "danger"); button.disabled = false; }
});

function clientDurationMinutes(amount, unit) {
  const multiplier = { moment: 1, minutes: 1, hours: 60, days: 1440, weeks: 10080, months: 43200 }[unit] || 1;
  return Math.max(0, Number(amount || 0) * multiplier);
}

function handleTimeSkipResult(result, payload) {
  appendStoryEntries(result.story);
  renderState(result.state);
  handleNotifications(result.notifications);
  if (result.major_event_reached) {
    showToast(`Major event reached: ${result.major_event_title || "campaign turning point"}.`, "world");
  }
  const majorStop = ["canon_event", "danger", "world_event"].includes(result.interruption_kind);
  if (result.interrupted && majorStop && (result.intervention_prompt || result.interruption_kind === "canon_event")) {
    const isDanger = result.interruption_kind === "danger";
    $("#canon-event-heading").textContent = result.interruption_kind === "canon_event" ? "MAJOR CANON EVENT" : isDanger ? "DANGER AHEAD" : "IMPORTANT WORLD EVENT";
    $("#canon-intervention-text").textContent = result.interruption_reason;
    $("#canon-event-context").textContent = result.interruption_context || result.narrative || "The simulation stopped at the moment your decision became necessary.";
    $("#canon-intervention-question").textContent = result.intervention_prompt || `Will ${APP.state?.name || "the player"} intervene?`;
    $("#btn-canon-intervene").textContent = isDanger ? "TAKE CONTROL — HANDLE IT MYSELF" : "YES — STOP HERE";
    $("#btn-canon-later").textContent = isDanger ? "LET IT PLAY OUT — DECIDE BY ROLL" : "NO — KEEP SIMULATING";
    APP.pendingIntervention = { result, payload };
    $("#intervention-bar").hidden = false;
  } else if (result.interrupted && result.interruption_reason) {
    showToast(result.interruption_reason, result.interruption_kind === "goal_complete" ? "notify" : "system");
  }
}

$("#btn-canon-intervene").addEventListener("click", () => {
  $("#intervention-bar").hidden = true;
  APP.pendingIntervention = null;
  $("#time-unit").value = "moment";
  syncTimeControl("#time-unit", "#time-amount", null, null, "#time-control-help");
  $("#action-input").focus();
  $("#action-input").placeholder = "Describe how you intervene, add the action, then Advance the next beat.";
});
$("#btn-canon-later").addEventListener("click", async () => {
  const pending = APP.pendingIntervention;
  if (!pending || APP.busy) return;
  $("#intervention-bar").hidden = true;
  APP.pendingIntervention = null;
  const payload = pending.payload || {};
  // Declining a flagged danger doesn't just narrate past it — it still has
  // to be decided by an actual roll, the same as any other action. Resolve
  // it as one normal "moment" beat (the same pipeline every single action
  // already goes through) before continuing the rest of the skip.
  if (pending.result?.interruption_kind === "danger") {
    await beginTimeSkip(1, "moment", pending.result.interruption_reason || "Face the danger without personally taking control", payload.intensity || "normal");
    if (!APP.campaignActive || APP.state?.alive === false) return; // death or campaign end already handled by the moment resolution
  }
  if (payload.unit === "moment") {
    await beginTimeSkip(1, "moment", "", payload.intensity || "normal");
    return;
  }
  const requested = clientDurationMinutes(payload.amount, payload.unit);
  const elapsed = clientDurationMinutes(pending.result?.elapsed?.amount, pending.result?.elapsed?.unit);
  const remaining = Math.max(0, Math.round(requested - elapsed));
  if (remaining > 0) await beginTimeSkip(remaining, "minutes", "", payload.intensity || "normal");
  else showToast("The requested time period had already ended at this event.", "system");
});

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------
$("#btn-open-chat").addEventListener("click", async () => { await refreshChat(); openModal("modal-chat"); });

async function refreshChat() {
  const data = await apiGet("/api/chats");
  const list = $("#chat-contacts");
  const names = Array.from(new Set([...Object.keys(data.contacts || {}), ...Object.keys(data.chat_threads || {})])).sort();
  list.innerHTML = "";
  if (!names.length) { list.innerHTML = '<p class="hint">No contacts yet. Meet recurring characters in the story to unlock chats.</p>'; return; }
  names.forEach((name) => {
    const unread = (data.unread || []).filter((u) => u.thread === name).length;
    const div = document.createElement("div");
    div.className = "contact-item" + (name === APP.activeChatThread ? " active" : "");
    div.innerHTML = `${escapeHtml(name)}${unread ? `<span class="unread-badge">${unread}</span>` : ""}`;
    div.addEventListener("click", () => renderChatThread(name, data));
    list.appendChild(div);
  });
  if (!APP.activeChatThread && names.length) renderChatThread(names[0], data);
  else if (APP.activeChatThread) renderChatThread(APP.activeChatThread, data);
}

function renderChatThread(name, data) {
  APP.activeChatThread = name;
  $$(".chat-contacts .contact-item").forEach((el) => el.classList.toggle("active", el.textContent.startsWith(name)));
  const msgs = (data.chat_threads || {})[name] || [];
  const box = $("#chat-messages");
  box.innerHTML = msgs.map((m) => `<div class="chat-msg ${m.direction}"><div class="meta">${escapeHtml(m.direction === "outgoing" ? "You" : m.sender)} · ${escapeHtml(m.time || "")}</div>${escapeHtml(m.text)}</div>`).join("");
  box.scrollTop = box.scrollHeight;
  apiPost("/api/chats/read", { thread: name }).catch(() => {});
}

$("#btn-chat-send").addEventListener("click", async () => {
  const text = $("#chat-input").value.trim();
  const thread = APP.activeChatThread;
  if (!text || !thread) return;
  const btn = $("#btn-chat-send"), input = $("#chat-input");
  btn.disabled = true; input.disabled = true;
  const originalLabel = btn.textContent;
  btn.textContent = "…";
  // Show the player's own line immediately — the actual reply is a real AI
  // call and can take a few seconds, so the conversation shouldn't look
  // frozen while it's in flight.
  const box = $("#chat-messages");
  box.insertAdjacentHTML("beforeend", `<div class="chat-msg outgoing"><div class="meta">You</div>${escapeHtml(text)}</div>`);
  box.scrollTop = box.scrollHeight;
  input.value = "";
  try {
    const result = await apiPost("/api/chats/send", { thread, message: text });
    if (result.state) { APP.state = result.state; }
    if (result.notifications) handleNotifications(result.notifications);
    const data = await apiGet("/api/chats");
    renderChatThread(thread, data);
    if (!result.reply) showToast(`${thread} hasn't replied yet.`, "system");
  } catch (e) {
    showToast(e.message, "danger");
  } finally {
    btn.disabled = false; input.disabled = false; btn.textContent = originalLabel; input.focus();
  }
});

// ---------------------------------------------------------------------------
// Advisor — Pax Historia-style meta guide: power levels, world state, advice.
// Out-of-character, no turn cost, no state changes. Responses are structured
// (summary + bullet points + suggested follow-ups) rather than a text blob.
// ---------------------------------------------------------------------------
function renderAdvisorMessage(m) {
  if (m.role === "player") {
    return `<div class="chat-msg outgoing"><div class="meta">You</div>${escapeHtml(m.text)}</div>`;
  }
  const points = (m.points || []).map((p) => `<li>${escapeHtml(p)}</li>`).join("");
  const countdown = m.canon_countdown?.label ? `<div class="advisor-countdown">⏳ ${escapeHtml(m.canon_countdown.label)}</div>` : "";
  return `<div class="chat-msg incoming"><div class="meta">Advisor${m.fourth_wall ? " · FOURTH-WALL" : ""}</div>
    <div class="advisor-msg-summary">${escapeHtml(m.summary || m.text || "...")}</div>
    ${countdown}${points ? `<ul class="advisor-msg-points">${points}</ul>` : ""}
  </div>`;
}

function renderAdvisorThread(thread) {
  const list = thread || [];
  const box = $("#advisor-messages");
  box.innerHTML = list.map(renderAdvisorMessage).join("") || '<p class="hint">No questions asked yet — try one of the prompts above.</p>';
  box.scrollTop = box.scrollHeight;
  $("#advisor-starters").style.display = list.length ? "none" : "flex";

  const last = list[list.length - 1];
  const followWrap = $("#advisor-followups");
  if (last && last.role === "advisor" && last.follow_ups && last.follow_ups.length) {
    followWrap.innerHTML = last.follow_ups.map((q) => `<button data-q="${escapeHtml(q)}">${escapeHtml(q)}</button>`).join("");
  } else {
    followWrap.innerHTML = "";
  }
}

async function askAdvisor(text) {
  if (!text) return;
  $("#advisor-input").value = "";
  $("#advisor-starters").style.display = "none";
  const box = $("#advisor-messages");
  if (box.querySelector(".hint")) box.innerHTML = "";
  box.innerHTML += renderAdvisorMessage({ role: "player", text });
  box.scrollTop = box.scrollHeight;
  $("#advisor-followups").innerHTML = "";
  try {
    const result = await apiPost("/api/advisor/ask", { question: text, fourth_wall: $("#advisor-fourth-wall").checked });
    playSfx("notify");
    renderState(result.state);
    const r = await apiGet("/api/advisor");
    renderAdvisorThread(r.thread);
  } catch (e) { showToast(e.message, "danger"); }
}

$("#btn-open-advisor").addEventListener("click", async () => {
  if (!APP.campaignActive) { showToast("Start a campaign first.", "system"); return; }
  try {
    const r = await apiGet("/api/advisor");
    renderAdvisorThread(r.thread);
    openModal("modal-advisor");
  } catch (e) { showToast(e.message, "danger"); }
});

$("#btn-advisor-send").addEventListener("click", () => askAdvisor($("#advisor-input").value.trim()));
$("#advisor-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); askAdvisor($("#advisor-input").value.trim()); }
});
$("#advisor-starters").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-q]");
  if (btn) askAdvisor(btn.getAttribute("data-q"));
});
$("#advisor-followups").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-q]");
  if (btn) askAdvisor(btn.getAttribute("data-q"));
});

// ---------------------------------------------------------------------------
// Journal (party / quests / codex / inventory / shops / map / combat)
// ---------------------------------------------------------------------------
$$("[data-journal]").forEach((btn) => btn.addEventListener("click", () => openJournal(btn.getAttribute("data-journal"))));
$$("#journal-tabs button[data-tab]").forEach((btn) => btn.addEventListener("click", () => openJournal(btn.getAttribute("data-tab"))));
$("#btn-journal-advanced-toggle").addEventListener("click", () => setJournalAdvancedOpen($("#journal-tabs-advanced").hidden));

function setJournalAdvancedOpen(open) {
  $("#journal-tabs-advanced").hidden = !open;
  $("#btn-journal-advanced-toggle").textContent = open ? "Less ▴" : "More ▾";
}

async function openJournal(tab) {
  APP.journalTab = tab;
  if ($(`#journal-tabs-advanced button[data-tab="${tab}"]`)) setJournalAdvancedOpen(true);
  $$("#journal-tabs button[data-tab]").forEach((b) => b.classList.toggle("active", b.getAttribute("data-tab") === tab));
  openModal("modal-journal");
  const data = await apiGet("/api/panels");
  const panel = $("#journal-panel");
  const s = APP.state || {};
  if (tab === "party") {
    const comp = data.companions || [];
    panel.innerHTML = comp.length ? comp.map((c) => `<div class="jrow"><b>${escapeHtml(c.name || "Companion")}</b><br/>${escapeHtml(c.notes || c.role || "")}</div>`).join("") : `<div class="jrow">No companions have joined you yet.</div>` + `<div class="jrow"><b>${escapeHtml(s.name || "Traveler")}</b> — Level ${s.level ?? 1} ${escapeHtml((s.special || {}).Archetype || "")}</div>`;
  } else if (tab === "quests") {
    const active = data.quests || [];
    panel.innerHTML = (active.length ? active.map((raw, index) => {
      const q = questView(raw, index);
      const line = (label, value) => value ? `<div class="quest-brief-line"><b>${escapeHtml(label)}</b><span>${escapeHtml(value)}</span></div>` : "";
      const list = (label, values, emptyText = "") => values.length ? `<div class="quest-detail-label">${escapeHtml(label)}</div><ul>${values.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul>` : (emptyText ? `<div class="quest-detail-label">${escapeHtml(label)}</div><p>${escapeHtml(emptyText)}</p>` : "");
      const knowledge = q.knowledge.length ? `<div class="quest-detail-label">Current knowledge</div><ul>${q.knowledge.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul>` : `<div class="quest-detail-label">Current knowledge</div><p>Nothing beyond the quest briefing is known yet.</p>`;
      const objectives = q.objectives.length ? `<div class="quest-detail-label">Tracked objectives</div><div class="objective-list">${q.objectives.map((obj) => `<div class="objective-row ${escapeHtml(obj.status || "active")}"><span>${obj.status === "complete" ? "✓" : obj.status === "failed" ? "✕" : obj.status === "locked" ? "◇" : "○"}</span><div><b>${escapeHtml(obj.text || obj.name || "Objective")}</b><small>${escapeHtml(obj.status || "active")}${obj.optional ? " · optional" : ""} · ${escapeHtml(obj.progress || 0)}%</small></div></div>`).join("")}</div>` : (q.conditions.length ? `<div class="quest-detail-label">Clear conditions / objectives</div><ul>${q.conditions.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul>` : `<div class="quest-detail-label">Clear conditions</div><p>Not yet known. Discover more information or advance the quest.</p>`);
      const branches = [...textList(q.branchState.available), ...textList(q.branchState.locked).map((x) => `${x} (locked)` )];
      const branchInfo = q.branchState.current || branches.length ? `<div class="quest-detail-label">Current route</div><p>${escapeHtml(q.branchState.current || "main")}</p>${list("Known branches", branches)}` : "";
      return `<details class="quest-card"${index === 0 ? " open" : ""}><summary>${escapeHtml(q.name)} <small>— ${escapeHtml(q.status)}</small></summary><div class="quest-details"><p class="quest-summary">${escapeHtml(q.explanation)}</p><div class="quest-brief-grid">${line("Giver / cause", q.giver)}${line("First step", q.firstStep)}${line("Deadline", q.deadline)}</div>${list("Known locations", q.locations)}${list("Known risks", q.risks)}${knowledge}${objectives}${branchInfo}${list("Known rewards", q.rewards)}<div class="quest-note-row"><input type="text" placeholder="Add your own quest note" data-quest-note-input="${escapeHtml(q.name)}"><button type="button" data-quest-note-save="${escapeHtml(q.name)}">SAVE NOTE</button></div></div></details>`;
    }).join("") : `<div class="jrow">No active quests yet.</div>`) + `<div class="jrow hint">Hidden quests discovered: ${data.hidden_quests_count}</div><h3>Completed / failed quests</h3>${(data.quest_archive || []).length ? data.quest_archive.map((q, i) => { const v = questView(q, i); return `<div class="jrow"><b>${escapeHtml(v.name)}</b> — ${escapeHtml(v.status)}<br>${escapeHtml(v.explanation)}</div>`; }).join("") : '<div class="jrow hint">No archived quests yet.</div>'}`;
  } else if (tab === "skills") {
    const skills = Object.entries(data.skills || {});
    const titles = data.titles || [];
    const skillRows = skills.length
      ? skills.map(([name, detail]) => renderSkillCard(name, detail)).join("")
      : '<div class="jrow">No learned skills yet.</div>';
    const titleRows = titles.length
      ? titles.map((title) => `<div class="jrow">🏅 ${escapeHtml(title)}</div>`).join("")
      : '<div class="jrow hint">No titles earned yet.</div>';
    panel.innerHTML = `<h3>Learned Skills</h3>${skillRows}<h3>Titles</h3>${titleRows}`;
  } else if (tab === "progression") {
    const logs = (data.progression_log || []).slice(-40).reverse();
    const rows = logs.map((entry) => {
      if (entry && entry.type === "xp") {
        const reasons = (entry.reasons || []).map((reason) => `<li><b>+${escapeHtml(reason.xp || 0)} XP</b> — ${escapeHtml(reason.action || "Progress")}: ${escapeHtml(reason.reason || "Meaningful activity")}</li>`).join("");
        const gains = Object.entries(entry.stat_gains || {}).map(([name, gain]) => `${name} +${gain}`).join(" · ");
        return `<article class="progress-entry xp-entry"><header><b>+${escapeHtml(entry.xp_awarded || 0)} XP</b><span>Turn ${escapeHtml(entry.turn ?? "—")}</span></header>${entry.levels_gained ? `<p class="level-gain">LEVEL UP ×${escapeHtml(entry.levels_gained)}${gains ? ` · ${escapeHtml(gains)}` : ""}</p>` : ""}<ul>${reasons}</ul></article>`;
      }
      const ability = entry && entry.ability ? entry.ability : "Training";
      return `<article class="progress-entry"><header><b>${escapeHtml(ability)}</b><span>${escapeHtml(entry?.effective_training_days ?? "—")} effective days</span></header><p>${escapeHtml(entry?.explanation || "Progress recorded.")}</p>${entry?.stat_gain ? `<small>Stat gain: +${escapeHtml(entry.stat_gain)}</small>` : ""}</article>`;
    }).join("");
    const summary = data.uses_xp
      ? `<div class="progress-summary"><b>LEVEL ${escapeHtml(data.level || 1)}</b><span>${escapeHtml(data.xp || 0)} / ${escapeHtml(data.xp_next || 100)} XP toward the next level</span></div><p class="hint">Meaningful actions earn contextual XP. Base stats increase automatically when XP produces a level.</p>`
      : `<div class="progress-summary"><b>WORLD-BASED GROWTH</b><span>No artificial XP or levels in this setting</span></div><p class="hint">Stats, techniques, knowledge, titles, ranks, and proficiency improve directly through world-valid experience.</p>`;
    panel.innerHTML = summary + (rows || '<div class="jrow hint">No progression has been recorded yet.</div>');
  } else if (tab === "chapters") {
    const chapters = [...(data.chapter_summaries || [])].reverse();
    const recent = data.chapter_buffer || [];
    panel.innerHTML = `<div class="system-summary"><b>CHAPTER MEMORY</b><span>${chapters.length} consolidated chapters · ${recent.length}/6 beats toward the next</span></div>` +
      (chapters.length ? chapters.map((chapter, index) => `<details class="quest-card"${index === 0 ? " open" : ""}><summary>${escapeHtml(chapter.title || `Chapter ${chapter.number}`)} <small>— turns ${escapeHtml((chapter.turns || []).join("–"))}</small></summary><div class="quest-details"><p>${escapeHtml(chapter.summary || "")}</p><div class="quest-detail-label">Key decisions</div><ul>${(chapter.key_decisions || []).map((x) => `<li>${escapeHtml(x)}</li>`).join("") || "<li>None recorded.</li>"}</ul><div class="quest-detail-label">Lasting changes</div><ul>${(chapter.lasting_changes || []).map((x) => `<li>${escapeHtml(x)}</li>`).join("") || "<li>None recorded.</li>"}</ul><small>${escapeHtml(chapter.time_span || "")}</small></div></details>`).join("") : '<div class="jrow">A chapter is consolidated after six resolved story beats.</div>');
  } else if (tab === "clocks") {
    const renderClocks = (title, clocks) => `<h3>${title}</h3>` + (Object.values(clocks || {}).length ? Object.values(clocks).map((clock) => `<article class="clock-row"><header><b>${escapeHtml(clock.name || "Unknown")}</b><span>${escapeHtml(clock.status || "active")}</span></header><p>${escapeHtml(clock.goal || "Private agenda")}</p><div class="clock-track"><i style="width:${Math.max(0, Math.min(100, Number(clock.progress || 0)))}%"></i></div><small>${escapeHtml(clock.progress || 0)} / ${escapeHtml(clock.threshold || 100)} · last moved ${escapeHtml(clock.last_update || "not yet")}</small></article>`).join("") : '<div class="jrow hint">No visible clocks yet. Important NPCs and factions gain clocks as they enter the campaign.</div>');
    panel.innerHTML = renderClocks("Faction agendas", data.faction_clocks) + renderClocks("NPC agendas", data.npc_clocks);
  } else if (tab === "relationships") {
    const people = data.relationships_view?.people || [];
    const factions = data.relationships_view?.factions || [];
    const affiliations = data.relationships_view?.affiliations || [];
    panel.innerHTML = `<div class="system-summary"><b>RELATIONSHIPS &amp; FACTIONS</b><span>Trust is evidence, not automatic obedience.</span></div>` +
      `<h3>Affiliations — your rank and standing</h3>` + (affiliations.length ? affiliations.map((a) => `<div class="jrow affiliation-row${a.status && a.status !== "active" ? ` ${escapeHtml(a.status)}` : ""}"><b>${escapeHtml(a.rank || "Member")}</b> — ${escapeHtml(a.faction)}${a.status && a.status !== "active" ? `<span class="affiliation-status">${escapeHtml(a.status)}</span>` : ""}${a.joined ? `<br><small>Joined: ${escapeHtml(a.joined)}</small>` : ""}${a.notes ? `<br><small>${escapeHtml(a.notes)}</small>` : ""}</div>`).join("") : '<div class="jrow hint">Not formally affiliated with any group, alliance, or hierarchy yet.</div>') +
      `<h3>People</h3>` + (people.length ? people.map((person) => `<details class="relationship-card"><summary><b>${escapeHtml(person.name)}</b><span>${escapeHtml(person.label)} · ${Number(person.score) >= 0 ? "+" : ""}${escapeHtml(person.score)}</span></summary><div><p><b>Goal:</b> ${escapeHtml(person.goal)}</p><p><b>Last known:</b> ${escapeHtml(person.last_known_location)}</p>${textList(person.promises).length ? `<p><b>Promises:</b> ${textList(person.promises).map(escapeHtml).join(" · ")}</p>` : ""}${textList(person.debts).length ? `<p><b>Debts:</b> ${textList(person.debts).map(escapeHtml).join(" · ")}</p>` : ""}</div></details>`).join("") : '<div class="jrow hint">No recurring relationships have been established.</div>') +
      `<h3>Faction standing</h3>` + (factions.length ? factions.map((f) => `<div class="jrow"><b>${escapeHtml(f.name)}</b><br>${escapeHtml(typeof f.standing === "object" ? compactReadable(f.standing.label || f.standing.status || f.standing.score) : f.standing)}</div>`).join("") : '<div class="jrow hint">No faction reputation has been recorded.</div>');
  } else if (tab === "prerequisites") {
    const tracks = data.prerequisite_tracks || [];
    panel.innerHTML = tracks.length ? tracks.map((track, index) => {
      const status = String(track.status || "in_progress").replace(/_/g, " ");
      const list = (label, values, cls) => `<div class="quest-detail-label ${cls || ""}">${label}</div>` + ((values || []).length ? `<ul>${values.map((v) => `<li>${escapeHtml(v)}</li>`).join("")}</ul>` : `<p class="hint">None recorded.</p>`);
      return `<details class="quest-card prereq-card"${index === 0 ? " open" : ""}><summary>${escapeHtml(track.name || "Capability")} <small class="prereq-status ${escapeHtml(track.status || "")}">— ${escapeHtml(status)}</small></summary><div class="quest-details"><p>${escapeHtml(track.source_feat || "")}</p>${list("Requirements met", track.met_requirements, "met")}${list("Still missing", track.missing_requirements, "missing")}${list("Next steps", track.next_steps, "next")}<div class="quest-detail-label">Notes</div><p>${escapeHtml(track.notes || "No additional notes.")}</p></div></details>`;
    }).join("") : `<div class="jrow"><b>No tracked capability yet.</b><br/>Tell the GM what canon feat, technique, class, item, transformation, or position you want to pursue. The requirements will appear here.</div>`;
  } else if (tab === "timeline") {
    const currentDay = Number(data.canon_day ?? -7);
    const fired = new Set(data.canon_events_fired || []);
    const rows = (data.canon_events || []).map((event) => {
      const id = `day:${event.day || 0}:${event.title || "event"}`;
      const occurred = fired.has(id) || Number(event.day) < currentDay;
      const current = Number(event.day) === currentDay;
      return `<div class="timeline-row ${occurred ? "occurred" : "upcoming"} ${current ? "current" : ""}"><div class="timeline-day">DAY ${Number(event.day) >= 0 ? "+" : ""}${escapeHtml(event.day)}</div><div><b>${escapeHtml(event.title || "World event")}</b><small>${escapeHtml(event.location || "")}</small><p>${escapeHtml(event.summary || "")}</p></div></div>`;
    }).join("");
    panel.innerHTML = `<div class="timeline-anchor"><b>Current: Canon Day ${currentDay >= 0 ? "+" : ""}${currentDay}</b><span>${escapeHtml(data.canon_anchor || "Before the main story")}</span></div>${rows || '<div class="jrow">No fixed canon timeline for this world.</div>'}<div class="jrow hint">Canon events are scheduled pressures, not rails. Player-caused divergences can alter or prevent their original form.</div>`;
  } else if (tab === "schedule") {
    const events = data.scheduled_events || [];
    panel.innerHTML = events.length ? events.map((event) => `<div class="timeline-row upcoming"><div class="timeline-day">${escapeHtml(event.when || event.day || event.time || "Upcoming")}</div><div><b>${escapeHtml(event.title || event.name || "Scheduled event")}</b><p>${escapeHtml(event.summary || event.description || event.notes || "Known details will develop as the date approaches.")}</p></div></div>`).join("") : '<div class="jrow">No visible deadlines or scheduled events. Hidden events remain hidden until your character could know them.</div>';
  } else if (tab === "continuity") {
    const ledger = data.continuity || {};
    const canon = data.campaign_canon || [];
    const facts = ledger.facts || [];
    const section = (title, values) => `<h3>${title}</h3>${(values || []).length ? values.slice(-30).reverse().map((x) => `<div class="jrow">${escapeHtml(typeof x === "object" ? x.text || x.description || JSON.stringify(x) : x)}</div>`).join("") : '<div class="jrow hint">Nothing recorded.</div>'}`;
    panel.innerHTML = section("Campaign canon", canon) + section("Location changes", facts.filter((x) => x.type === "location")) + section("Appearance changes", facts.filter((x) => x.type === "appearance")) + section("Quest changes", facts.filter((x) => x.type === "quest")) + section("Warnings", ledger.warnings);
  } else if (tab === "world-feed") {
    const feed = [...(data.world_events || []), ...(data.timeline || [])].slice(-40).reverse();
    panel.innerHTML = feed.length
      ? feed.map((entry) => {
          const text = typeof entry === "object" ? (entry.text || entry.summary || JSON.stringify(entry)) : entry;
          const kind = typeof entry === "object" ? (entry.type || entry.tag || "World update") : "World update";
          return `<div class="jrow"><b>${escapeHtml(String(kind).replace(/_/g, " "))}</b><br>${escapeHtml(text)}</div>`;
        }).join("")
      : '<div class="jrow">No major world updates have reached you yet.</div>';
  } else if (tab === "codex") {
    const codex = data.codex || [];
    panel.innerHTML = codex.length ? codex.map((c) => `<div class="jrow"><b>${escapeHtml(c.name || "Entry")}</b> <i>${escapeHtml(c.type || "")}</i><br/>${escapeHtml(c.notes || "")}</div>`).join("") : `<div class="jrow">No codex entries yet.</div>`;
  } else if (tab === "inventory") {
    const inv = data.inventory || [];
    const eq = data.equipment || {};
    const currencyRows = [`<div class="jrow"><b>${escapeHtml(data.currency.name)}:</b> ${escapeHtml(data.currency.amount)}</div>`]
      .concat(Object.entries(data.currencies || {}).map(([k, v]) => `<div class="jrow"><b>${escapeHtml(k)}:</b> ${escapeHtml(v)}</div>`));
    const bagRows = inv.length ? inv.map((i) => `<div class="jrow">${escapeHtml(typeof i === "object" ? i.name || JSON.stringify(i) : i)}</div>`).join("") : `<div class="jrow">Bag is empty.</div>`;
    if (data.gear_style === "full") {
      panel.innerHTML = currencyRows.join("") + buildMannequinHtml(eq) + bagRows;
      wireMannequinTooltips();
    } else {
      panel.innerHTML = currencyRows.join("") + bagRows +
        (Object.keys(eq).length ? `<div class="jrow"><b>Weapon</b><br/>${Object.entries(eq).map(([k, v]) => `${escapeHtml(k)}: ${escapeHtml(v)}`).join("<br/>")}</div>` : "");
    }
  } else if (tab === "shops") {
    const shops = data.shops || [];
    panel.innerHTML = `<div class="jrow"><b>${escapeHtml(data.currency.name)}:</b> ${escapeHtml(data.currency.amount)}</div>` +
      `<div class="jrow"><b>Local Commerce</b><br/>` + (shops.length ? shops.map((sh) => escapeHtml(typeof sh === "object" ? `${sh.name || "Shop"} — ${sh.type || "Merchant"}` : sh)).join("<br/>") : data.shop_types.map((t) => "? " + t).join("<br/>")) + `</div>` +
      `<div class="jrow"><b>Training Focus</b><br/>${data.training_options.map(escapeHtml).join(", ")}</div>` +
      (Object.keys(data.ability_progress || {}).length ? `<div class="jrow"><b>Progress</b><br/>${Object.entries(data.ability_progress).map(([k, v]) => `${escapeHtml(k)}: ${escapeHtml(v)}`).join("<br/>")}</div>` : "");
  } else if (tab === "map") {
    const nodes = data.map_data?.nodes || [];
    const knownCount = nodes.filter((node) => node.discovered).length;
    APP.mapRoute = [...(data.map_data?.planned_route || [])];
    const territories = groupNodesByController(nodes);
    const legendChips = territories.map((t) => `<span class="territory-chip" style="--tc:${t.color}">${escapeHtml(t.controller)}</span>`).join("");
    panel.innerHTML = `<div class="map-heading"><div><b>${escapeHtml(data.world || s.world || "World")} Atlas</b><small>${nodes.length} important landmarks · ${knownCount} visited/discovered</small></div><div class="map-legend"><span class="current">Current</span><span class="known">Discovered</span><span class="unknown">Known landmark</span></div></div>` +
      (legendChips ? `<div class="territory-legend">${legendChips}</div>` : "") +
      `<div class="map-layout"><div class="map-wrap" id="map-wrap"><div class="map-canvas" id="map-canvas" style="--map-image:url('${escapeHtml(data.map_image || "")}')"><svg class="map-territories" viewBox="0 0 100 100" preserveAspectRatio="none">${territories.map((t) => t.svg).join("")}</svg><svg class="map-routes" viewBox="0 0 100 100" preserveAspectRatio="none"><polyline points="${nodes.map((node) => `${node.x},${node.y}`).join(" ")}" /></svg></div><div class="map-zoom-controls"><button type="button" data-map-zoom-in title="Zoom in">+</button><button type="button" data-map-zoom-out title="Zoom out">−</button><button type="button" data-map-zoom-reset title="Reset view">⤾</button></div></div><aside class="map-detail" id="map-detail"><b>Select a landmark</b><p>Inspect travel time, control, quest links, and add destinations to an ordered route. Drag to pan, scroll or use the buttons to zoom.</p></aside></div><div class="route-planner"><div><b>PLANNED ROUTE</b><span id="map-route-label">${APP.mapRoute.length ? APP.mapRoute.map(escapeHtml).join(" → ") : "No destinations selected"}</span></div><button class="btn-ghost" data-map-route-clear>CLEAR</button><button class="btn-primary" data-map-route-queue ${APP.mapRoute.length ? "" : "disabled"}>QUEUE ROUTE</button></div>`;
    const canvas = $("#map-canvas");
    nodes.forEach((node) => {
      const dot = document.createElement("button");
      dot.type = "button";
      dot.className = "map-node " + (node.current ? "here" : node.discovered ? "known" : "unknown");
      dot.style.left = node.x + "%"; dot.style.top = node.y + "%";
      dot.title = `${node.name} · ${node.kind || "landmark"} · Tier ${node.tier ?? "?"}${node.controller && node.controller !== "Unknown" ? ` · Controlled by ${node.controller}` : ""}`;
      dot.setAttribute("data-map-node", node.name);
      dot.innerHTML = `<span class="map-pip"></span><span class="map-label">${escapeHtml(node.name)}</span>`;
      canvas.appendChild(dot);
    });
    APP.mapNodes = nodes;
    initMapPanZoom();
  } else if (tab === "lore") {
    const sources = data.lore_sources || [];
    panel.innerHTML = `<div class="system-summary"><b>OFFLINE LORE LIBRARY</b><span>The GM retrieves relevant entries on each action. Canon and world rules outrank uncertain notes.</span></div><form id="lore-import-form" class="lore-import"><label>Add a lore pack<input id="lore-file" type="file" accept=".json,.md,.txt" required></label><select id="lore-world"><option>${escapeHtml(data.world || "Custom World")}</option><option>Custom World</option></select><button class="btn-primary" type="submit">IMPORT</button></form>` +
      (sources.length ? sources.map((source) => `<div class="jrow"><b>${escapeHtml(source.name)}</b><br>${escapeHtml(source.kind)} · ${escapeHtml(source.entries || 0)} entries${source.worlds?.length ? ` · ${source.worlds.map(escapeHtml).join(", ")}` : ""}</div>`).join("") : '<div class="jrow">Only built-in setting guidance is available.</div>') + `<p class="hint">JSON format: world names mapped to arrays of {title, keys, text, source}. Markdown and text files are imported into the selected world.</p>`;
  } else if (tab === "tuning") {
    const t = data.difficulty_controls || {};
    const preset = data.progression_preset || {};
    const slider = (key, label, min, max, step, value, suffix = "×") => `<label class="tuning-row"><span><b>${label}</b><small id="${key}-value">${escapeHtml(value)}${suffix}</small></span><input type="range" id="${key}" min="${min}" max="${max}" step="${step}" value="${escapeHtml(value)}"></label>`;
    panel.innerHTML = `<div class="system-summary"><b>${escapeHtml(preset.label || "WORLD PROGRESSION")}</b><span>Separate controls change pacing and danger without rewriting lore.</span></div><form id="tuning-form" class="tuning-form">${slider("check_warning_threshold", "Difficult-check warning threshold", 40, 95, 1, t.check_warning_threshold || 65, "/100")}${slider("xp_rate", "XP rate", .5, 2, .05, t.xp_rate || 1)}${slider("training_rate", "Training rate", .5, 2, .05, t.training_rate || 1)}${slider("breakthrough_rate", "Breakthrough frequency", .5, 2, .05, t.breakthrough_rate || 1)}${slider("combat_danger", "Combat danger", .5, 2, .05, t.combat_danger || 1)}${slider("resource_pressure", "Resource pressure", .5, 2, .05, t.resource_pressure || 1)}<button class="btn-primary" type="submit">SAVE TUNING</button></form>`;
  } else if (tab === "health") {
    const health = data.campaign_health || { score: 100, status: "Healthy", issues: [], counts: {} };
    panel.innerHTML = `<div class="health-score ${health.score < 60 ? "bad" : health.score < 85 ? "warn" : "good"}"><strong>${escapeHtml(health.score)}</strong><div><b>${escapeHtml(health.status)}</b><span>Campaign structure and continuity check</span></div></div><div class="health-counts">${Object.entries(health.counts || {}).map(([key, value]) => `<span><b>${escapeHtml(value)}</b>${escapeHtml(humanLabel(key))}</span>`).join("")}</div>` +
      ((health.issues || []).length ? health.issues.map((issue) => `<article class="health-issue ${escapeHtml(issue.severity)}"><header><b>${escapeHtml(issue.area)}</b><span>${escapeHtml(issue.severity)}</span></header><p>${escapeHtml(issue.message)}</p><small>${escapeHtml(issue.suggestion)}</small></article>`).join("") : '<div class="jrow"><b>No structural problems detected.</b><br>The campaign has objectives, continuity, and enough persistent state to continue cleanly.</div>');
  } else if (tab === "combat") {
    const c = data.combat || {};
    if (!c || !c.active) {
      panel.innerHTML = `<div class="jrow">No active structured combat.</div><div class="jrow hint">Use the Combat panel in the right column once a fight starts — it's not part of this Journal.</div>`;
    } else {
      const e = c.enemy || {};
      panel.innerHTML = `<div class="jrow">Round: ${escapeHtml(c.round ?? 1)}</div><div class="jrow">${escapeHtml(e.name || "Enemy")} — HP ${escapeHtml(e.hp ?? "?")}/${escapeHtml(e.hp_max ?? "?")}${e.is_group ? " (group)" : ""}</div>`;
    }
  }
}

// ---------------------------------------------------------------------------
// Map territory outlines — nodes are grouped by their controlling faction
// (already computed server-side in map_data) into a convex-hull polygon per
// faction, colored by a stable hash of the faction's name so the same group
// always gets the same color across renders without a hardcoded palette.
// ---------------------------------------------------------------------------
function factionColor(name) {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
  return `hsl(${hash % 360}, 62%, 55%)`;
}
function convexHull(points) {
  const pts = [...new Map(points.map((p) => [`${p.x},${p.y}`, p])).values()].sort((a, b) => a.x - b.x || a.y - b.y);
  if (pts.length < 3) return pts;
  const cross = (o, a, b) => (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
  const lower = [];
  for (const p of pts) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) lower.pop();
    lower.push(p);
  }
  const upper = [];
  for (let i = pts.length - 1; i >= 0; i--) {
    const p = pts[i];
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) upper.pop();
    upper.push(p);
  }
  upper.pop(); lower.pop();
  return lower.concat(upper);
}
function groupNodesByController(nodes) {
  const byFaction = {};
  nodes.forEach((n) => {
    const controller = n.controller;
    if (!controller || controller === "Unknown") return;
    (byFaction[controller] = byFaction[controller] || []).push({ x: Number(n.x), y: Number(n.y) });
  });
  return Object.entries(byFaction).map(([controller, points]) => {
    const color = factionColor(controller);
    const cx = points.reduce((sum, p) => sum + p.x, 0) / points.length;
    const cy = points.reduce((sum, p) => sum + p.y, 0) / points.length;
    let svg;
    if (points.length < 3) {
      // A one- or two-node territory has no real hull — draw a soft halo
      // around each point instead of a degenerate polygon/line.
      svg = points.map((p) => `<circle cx="${p.x}" cy="${p.y}" r="9" class="territory-shape" style="--tc:${color}" />`).join("");
    } else {
      const hull = convexHull(points).map((p) => {
        // Inflate each hull point outward from the centroid so the outline
        // reads as territory around the landmarks, not a shape touching
        // their exact centers.
        const dx = p.x - cx, dy = p.y - cy, len = Math.hypot(dx, dy) || 1;
        return `${p.x + (dx / len) * 6},${p.y + (dy / len) * 6}`;
      }).join(" ");
      svg = `<polygon points="${hull}" class="territory-shape" style="--tc:${color}" />`;
    }
    return { controller, color, svg };
  });
}

// ---------------------------------------------------------------------------
// Map pan/zoom — drag to pan, wheel or the on-screen buttons to zoom.
// Percent-based node/territory positions are untouched; only map-canvas's
// CSS transform changes, so everything already on it stays in sync for free.
// ---------------------------------------------------------------------------
let mapView = { scale: 1, x: 0, y: 0, dragging: false, lastX: 0, lastY: 0 };
function applyMapView() {
  const canvas = $("#map-canvas");
  if (canvas) canvas.style.transform = `translate(${mapView.x}px, ${mapView.y}px) scale(${mapView.scale})`;
}
function clampMapPan(wrap) {
  const w = wrap.clientWidth, h = wrap.clientHeight;
  const scaledW = w * mapView.scale, scaledH = h * mapView.scale;
  const slackX = Math.max(0, (scaledW - w) / 2) + w * 0.4;
  const slackY = Math.max(0, (scaledH - h) / 2) + h * 0.4;
  mapView.x = Math.max(-slackX, Math.min(slackX, mapView.x));
  mapView.y = Math.max(-slackY, Math.min(slackY, mapView.y));
}
function setMapZoom(wrap, newScale, cx, cy) {
  const clamped = Math.max(0.6, Math.min(4, newScale));
  mapView.x = cx - ((cx - mapView.x) / mapView.scale) * clamped;
  mapView.y = cy - ((cy - mapView.y) / mapView.scale) * clamped;
  mapView.scale = clamped;
  clampMapPan(wrap);
  applyMapView();
}
function initMapPanZoom() {
  // #map-wrap is a fresh DOM element every time this tab renders (its
  // parent's innerHTML was just replaced), so listeners are re-attached
  // fresh each time too — the old element and its listeners are simply
  // garbage collected together.
  mapView = { scale: 1, x: 0, y: 0, dragging: false, lastX: 0, lastY: 0 };
  applyMapView();
  const wrap = $("#map-wrap");
  if (!wrap) return;
  wrap.addEventListener("pointerdown", (e) => {
    if (e.target.closest(".map-node")) return;
    mapView.dragging = true; mapView.lastX = e.clientX; mapView.lastY = e.clientY;
    wrap.classList.add("dragging");
    wrap.setPointerCapture(e.pointerId);
  });
  wrap.addEventListener("pointermove", (e) => {
    if (!mapView.dragging) return;
    mapView.x += e.clientX - mapView.lastX; mapView.y += e.clientY - mapView.lastY;
    mapView.lastX = e.clientX; mapView.lastY = e.clientY;
    clampMapPan(wrap);
    applyMapView();
  });
  const endDrag = () => { mapView.dragging = false; wrap.classList.remove("dragging"); };
  wrap.addEventListener("pointerup", endDrag);
  wrap.addEventListener("pointercancel", endDrag);
  wrap.addEventListener("wheel", (e) => {
    e.preventDefault();
    const rect = wrap.getBoundingClientRect();
    setMapZoom(wrap, mapView.scale * (e.deltaY < 0 ? 1.15 : 1 / 1.15), e.clientX - rect.left, e.clientY - rect.top);
  }, { passive: false });
}
$("#journal-panel").addEventListener("click", (event) => {
  const wrap = $("#map-wrap");
  if (!wrap) return;
  const rect = wrap.getBoundingClientRect(), cx = rect.width / 2, cy = rect.height / 2;
  if (event.target.closest("[data-map-zoom-in]")) setMapZoom(wrap, mapView.scale * 1.3, cx, cy);
  else if (event.target.closest("[data-map-zoom-out]")) setMapZoom(wrap, mapView.scale / 1.3, cx, cy);
  else if (event.target.closest("[data-map-zoom-reset]")) { mapView.scale = 1; mapView.x = 0; mapView.y = 0; applyMapView(); }
});

function humanDuration(minutes) {
  const value = Number(minutes || 0);
  if (value < 60) return `${Math.round(value)} minutes`;
  if (value < 1440) return `${Math.round(value / 60)} hours`;
  return `${Math.round(value / 144) / 10} days`;
}

function refreshMapRouteUi() {
  const label = $("#map-route-label");
  if (label) label.textContent = APP.mapRoute?.length ? APP.mapRoute.join(" → ") : "No destinations selected";
  const queue = document.querySelector("[data-map-route-queue]");
  if (queue) queue.disabled = !APP.mapRoute?.length;
}

$("#journal-panel").addEventListener("input", (event) => {
  if (!event.target.matches(".tuning-row input")) return;
  const out = document.getElementById(event.target.id + "-value");
  if (out) out.textContent = event.target.value + (event.target.id === "check_warning_threshold" ? "/100" : "×");
});

$("#journal-panel").addEventListener("submit", async (event) => {
  if (event.target.id === "tuning-form") {
    event.preventDefault();
    const keys = ["check_warning_threshold", "xp_rate", "training_rate", "breakthrough_rate", "combat_danger", "resource_pressure"];
    const payload = Object.fromEntries(keys.map((key) => [key, Number(document.getElementById(key).value)]));
    try { const result = await apiPost("/api/campaign/tuning", payload); APP.state = result.state; showToast("Campaign tuning saved.", "notify"); }
    catch (error) { showToast(error.message, "danger"); }
  } else if (event.target.id === "lore-import-form") {
    event.preventDefault();
    const file = $("#lore-file").files[0];
    if (!file) return;
    const form = new FormData(); form.append("file", file); form.append("world", $("#lore-world").value);
    try { await apiForm("/api/lore/import", form); showToast("Lore pack imported.", "notify"); await openJournal("lore"); }
    catch (error) { showToast(error.message, "danger"); }
  }
});

$("#journal-panel").addEventListener("click", async (event) => {
  const noteButton = event.target.closest("[data-quest-note-save]");
  if (noteButton) {
    const name = noteButton.getAttribute("data-quest-note-save");
    const input = Array.from(document.querySelectorAll("[data-quest-note-input]")).find((x) => x.getAttribute("data-quest-note-input") === name);
    if (!input?.value.trim()) return;
    try { await apiPost("/api/quests/note", { name, note: input.value.trim() }); input.value = ""; showToast("Quest note saved.", "notify"); }
    catch (error) { showToast(error.message, "danger"); }
    return;
  }
  const nodeButton = event.target.closest("[data-map-node]");
  if (nodeButton) {
    const node = (APP.mapNodes || []).find((row) => row.name === nodeButton.getAttribute("data-map-node"));
    if (!node) return;
    const detail = $("#map-detail");
    detail.innerHTML = `<b>${escapeHtml(node.name)}</b><small>${escapeHtml(node.kind || "landmark")} · tier ${escapeHtml(node.tier || 1)}</small><p>${escapeHtml(node.notes)}</p><dl><dt>Control</dt><dd>${escapeHtml(node.controller)}</dd><dt>Travel</dt><dd>${node.current ? "Current location" : humanDuration(node.travel_minutes)}</dd><dt>Quest links</dt><dd>${node.quests?.length ? node.quests.map(escapeHtml).join(", ") : "None known"}</dd></dl>${node.current ? "" : `<button class="btn-primary full" data-map-add="${escapeHtml(node.name)}">ADD WAYPOINT</button>`}`;
    return;
  }
  const add = event.target.closest("[data-map-add]");
  if (add) {
    const name = add.getAttribute("data-map-add");
    APP.mapRoute = APP.mapRoute || [];
    if (!APP.mapRoute.includes(name)) APP.mapRoute.push(name);
    refreshMapRouteUi();
    return;
  }
  if (event.target.closest("[data-map-route-clear]")) { APP.mapRoute = []; refreshMapRouteUi(); return; }
  if (event.target.closest("[data-map-route-queue]")) {
    try {
      const result = await apiPost("/api/map/route", { destinations: APP.mapRoute || [] });
      if (result.state) renderState(result.state);
      renderQueuedActions(result.queued_actions || []);
      showToast("Travel route added to the action queue.", "notify");
      closeModal("modal-journal");
    } catch (error) { showToast(error.message, "danger"); }
  }
});

// ---------------------------------------------------------------------------
// New Campaign modal
// ---------------------------------------------------------------------------
function fillSelect(sel, values, selected) {
  const safeValues = Array.isArray(values) ? values : [];
  sel.innerHTML = safeValues.map((v) => `<option value="${escapeHtml(v)}"${v === selected ? " selected" : ""}>${escapeHtml(v)}</option>`).join("");
}

function refreshCampaignWorldFields() {
  const world = $("#nc-world").value;
  const worlds = (APP.worldsMeta && APP.worldsMeta.worlds) || {};
  const wd = worlds[world];
  if (!wd) throw new Error(`World data for "${world || "unknown"}" is missing. Restart this updated build.`);
  const origins = Array.isArray(wd.origins) && wd.origins.length ? wd.origins : ["Local Resident"];
  const archetypes = Array.isArray(wd.archetypes) && wd.archetypes.length ? wd.archetypes : ["Adventurer"];
  $("#nc-tagline").textContent = wd.tagline || "Begin a new story in this world.";
  fillSelect($("#nc-origin"), origins, origins[0]);
  fillSelect($("#nc-archetype"), archetypes, archetypes[0]);
  $("#nc-custom-label").style.opacity = world === "Custom World" ? "1" : ".45";
  const abilities = wd.abilities || ["Strength", "Dexterity", "Constitution", "Intelligence", "Wisdom", "Charisma"];
  $("#nc-stats").innerHTML = abilities.map((k) => `<div><label>${abilityIcon(k)} ${escapeHtml(k)}</label><input type="number" min="-20" max="200" value="0" data-stat="${escapeHtml(k)}" title="Adjustment added to the generated world-relative value" /></div>`).join("");

  const startOpts = wd.start_options || [];
  const startWrap = $("#nc-start-wrap");
  if (startOpts.length) {
    $("#nc-start").innerHTML = startOpts.map((o, i) => `<option value="${i}">${escapeHtml(o.label)}</option>`).join("");
    startWrap.style.display = "";
  } else {
    $("#nc-start").innerHTML = "";
    startWrap.style.display = "none";
  }
  const characters = wd.playable_characters || [];
  $("#nc-character-mode").innerHTML = '<option value="">Original Character</option>' + characters.map((c) => `<option value="${escapeHtml(c.id)}">${escapeHtml(c.label || c.name)}</option>`).join("");
  $("#nc-character-note").textContent = characters.length
    ? "Choose an original character or take full control of a canon character at a major timeline moment. Canon will guide, never override, your choices."
    : "Create an original character shortly before the main storyline.";
}

function selectedCanonCharacter() {
  const wd = APP.worldsMeta?.worlds?.[$("#nc-world").value] || {};
  return (wd.playable_characters || []).find((c) => c.id === $("#nc-character-mode").value) || null;
}

function collectCampaignPayload() {
  const stats = {};
  $$("#nc-stats input").forEach((inp) => { stats[inp.getAttribute("data-stat")] = parseInt(inp.value || "0", 10); });
  const wd = APP.worldsMeta.worlds[$("#nc-world").value];
  const startOpts = wd.start_options || [];
  const chosenStart = startOpts.length ? startOpts[parseInt($("#nc-start").value || "0", 10)] : null;
  return {
    name: $("#nc-name").value.trim() || "Traveler", world: $("#nc-world").value,
    difficulty: $("#nc-difficulty").value, background: $("#nc-background").value,
    appearance: $("#nc-appearance").value, custom_world: $("#nc-custom").value,
    origin: $("#nc-origin").value, archetype: $("#nc-archetype").value, stats,
    start_location: chosenStart ? chosenStart.location : "", start_note: chosenStart ? chosenStart.note : "",
    canon_character_id: $("#nc-character-mode").value,
  };
}

async function openNewCampaignModal() {
  // Always refetch. This prevents character creation from using metadata left
  // in memory by an older build or a failed first request.
  APP.worldsMeta = await apiGet("/api/worlds");
  const worlds = APP.worldsMeta.worlds || {};
  const order = Array.isArray(APP.worldsMeta.order) ? APP.worldsMeta.order.filter((name) => worlds[name]) : Object.keys(worlds);
  const difficulties = APP.worldsMeta.difficulties || {};
  if (!order.length) throw new Error("No campaign worlds were returned by the game server.");
  const initialWorld = order.includes("One Piece") ? "One Piece" : order[0];
  const difficultyNames = Object.keys(difficulties);
  if (!difficultyNames.length) throw new Error("No campaign difficulties were returned by the game server.");
  const initialDifficulty = difficultyNames.includes("Adventurer") ? "Adventurer" : difficultyNames[0];
  fillSelect($("#nc-world"), order, initialWorld);
  fillSelect($("#nc-difficulty"), difficultyNames, initialDifficulty);
  $("#nc-diff-desc").textContent = (difficulties[initialDifficulty] || {}).description || "";
  refreshCampaignWorldFields();
  openModal("modal-campaign");
  closeModal("modal-welcome");
}
$("#nc-world").addEventListener("change", refreshCampaignWorldFields);
$("#nc-difficulty").addEventListener("change", () => { $("#nc-diff-desc").textContent = APP.worldsMeta.difficulties[$("#nc-difficulty").value].description; });
$("#nc-character-mode").addEventListener("change", () => {
  const c = selectedCanonCharacter();
  if (!c) return;
  $("#nc-name").value = c.name || "Traveler";
  $("#nc-background").value = c.background || "";
  $("#nc-appearance").value = c.appearance || "";
  if (Array.from($("#nc-origin").options).some((o) => o.value === c.origin)) $("#nc-origin").value = c.origin;
  if (Array.from($("#nc-archetype").options).some((o) => o.value === c.archetype)) $("#nc-archetype").value = c.archetype;
  $("#nc-character-note").textContent = `${c.name} begins at ${c.location}, Canon Day ${Number(c.start_day) >= 0 ? "+" : ""}${c.start_day}. You control every decision; canon events remain pressures that can change naturally.`;
});

$("#btn-begin-campaign").addEventListener("click", async () => {
  const payload = collectCampaignPayload();
  try {
    const result = await apiPost("/api/campaign/preview", payload);
    const p = result.preview;
    const profile = p.starting_profile || {};
    APP.pendingCampaign = { ...payload, preview_stats: p.abilities, preview_profile: profile };
    const loadout = [...(profile.titles || []).map((x) => `Title: ${x}`), ...Object.keys(profile.skills || {}).map((x) => `Skill: ${x}`), ...Object.values(profile.equipment || {}).map((x) => `Gear: ${x}`)];
    const generated = profile.generated_ability || null;
    const ability = generated && generated.details ? generated.details : {};
    const growth = profile.growth_profile || {};
    const generatedCard = generated ? `<section class="generated-ability"><b>GENERATED ABILITY — ${escapeHtml(generated.name)}</b><span>${escapeHtml(ability.effect || ability.description || "")}</span><span><strong>Origin:</strong> ${escapeHtml(ability.origin || "World-valid background talent.")}</span><span><strong>Limit:</strong> ${escapeHtml(ability.limitation || "Must be developed through play.")}</span><span><strong>Growth:</strong> ${escapeHtml(ability.growth_path || "Practice and suitable guidance.")}</span></section>` : "";
    const primer = p.world_primer || {};
    const primerCard = `<section class="world-primer"><div class="world-primer-kicker">WHAT YOU'RE GETTING INTO — NO SPOILERS</div><p class="world-primer-premise">${escapeHtml(primer.premise || "")}</p><div class="world-primer-row"><b>Tone</b><span>${escapeHtml(primer.tone || "")}</span></div><div class="world-primer-row"><b>How power works</b><span>${escapeHtml(primer.power_system || "")}</span></div>${(primer.factions || []).length ? `<div class="world-primer-row"><b>Major powers</b><ul>${primer.factions.map((f) => `<li>${escapeHtml(f)}</li>`).join("")}</ul></div>` : ""}${(primer.locations || []).length ? `<div class="world-primer-row"><b>Where the story ranges</b><ul>${primer.locations.map((l) => `<li>${escapeHtml(l)}</li>`).join("")}</ul></div>` : ""}<p class="world-primer-starting-note">${escapeHtml(primer.starting_note || "")}</p></section>`;
    $("#campaign-preview").innerHTML = `${primerCard}<div class="preview-hero"><h2>${escapeHtml(p.name)}</h2><p>${escapeHtml(p.world)} · ${escapeHtml(p.difficulty)}</p></div>${profile.power_notice ? `<div class="power-notice"><b>POWER NOTICE — ${escapeHtml(profile.power_band)}</b><span>${escapeHtml(profile.power_notice)}</span></div>` : ""}<div class="preview-grid"><div><b>Beginning</b><span>${escapeHtml(p.start_location)} · Canon Day ${Number(p.start_day) >= 0 ? "+" : ""}${escapeHtml(p.start_day)}</span></div><div><b>Role</b><span>${escapeHtml(p.origin)} · ${escapeHtml(p.archetype)}${p.race ? ` · ${escapeHtml(p.race)}` : ""}</span></div><div><b>Timeline</b><span>${escapeHtml(p.canon_anchor || "Before the main story")}</span></div><div><b>Starting pools</b><span>HP ${escapeHtml(profile.hp_max)} · ${escapeHtml(p.resource)} ${escapeHtml(profile.resource_max)}</span></div></div><h3>Open-ended starting abilities</h3><div class="preview-stats">${Object.entries(p.abilities || {}).map(([k,v]) => `<span><b>${escapeHtml(k)}</b> ${escapeHtml(v)}</span>`).join("")}</div><h3>Generated background loadout</h3><div class="preview-loadout">${loadout.map((x) => `<span>${escapeHtml(x)}</span>`).join("")}</div>${generatedCard}<section class="generated-backstory"><b>GENERATED BACKSTORY</b><p>${escapeHtml(p.background || "The GM will create a fitting background during the opening.")}</p></section><div class="growth-summary"><b>${escapeHtml(growth.aptitude || "Typical local potential")}</b><span>${escapeHtml(Number(growth.learning_rate || 1).toFixed(2))}× sustained-learning rate</span><small>${escapeHtml(growth.explanation || "Actual growth still depends on time, training conditions, and results.")}</small></div><p class="hint">${p.uses_xp ? "This setting canonically uses visible XP and levels." : "This setting progresses through stats, techniques, knowledge and titles—no artificial XP levels."} ${p.canon_character ? "You have full control of this major character." : "This original character begins shortly before the world's main story."}</p>`;
    openModal("modal-campaign-preview");
  } catch (e) { showToast(e.message, "danger"); }
});

$("#btn-preview-back").addEventListener("click", () => closeModal("modal-campaign-preview"));
$("#btn-confirm-campaign").addEventListener("click", async () => {
  if (!APP.pendingCampaign || APP.busy) return;
  setBusy(true); APP.deferPortraitGeneration = true; playSfx("world_event");
  try {
    const created = await apiPost("/api/campaign/new", APP.pendingCampaign);
    APP.campaignActive = true; APP.portraitAttempted.clear();
    $("#story-feed").innerHTML = ""; appendStoryEntries(created.story || []); renderState(created.state);
    // A new campaign always begins at the next story beat. Do not carry a
    // previous campaign's long-skip selection or intervention state forward.
    $("#time-unit").value = "moment";
    $("#time-amount").value = "1";
    $("#td-unit").value = "moment";
    $("#td-amount").value = "1";
    syncTimeControl("#time-unit", "#time-amount", null, null, "#time-control-help");
    syncTimeControl("#td-unit", "#td-amount", "#td-amount-field");
    $("#intervention-bar").hidden = true;
    APP.pendingIntervention = null;
    closeModal("modal-campaign-preview"); closeModal("modal-campaign"); closeModal("modal-welcome");
    $("#scene-title").textContent = "OPENING SCENE";
    try {
      const opening = await apiPost("/api/campaign/opening", {});
      appendStoryEntries(opening.story); renderState(opening.state);
      maybeShowOnboarding();
    } catch (error) {
      appendStoryEntries([{ text: "[AI SETUP REQUIRED]\nYour fresh campaign was created. Select a model in AI & Portrait Setup, then click RETRY OPENING.", tag: "system" }]);
      $("#hdr-ai").textContent = "AI: MODEL NOT SELECTED";
    }
  } catch (error) { showToast(error.message, "danger"); }
  finally { APP.deferPortraitGeneration = false; setBusy(false); APP.pendingCampaign = null; if (APP.state) ensureAiPortrait(APP.state); }
});

// ---------------------------------------------------------------------------
// First-time onboarding overlay — shown once, after a brand-new campaign's
// opening scene renders, so the player already has something on screen to
// relate the explanation to instead of reading it before any state exists.
// ---------------------------------------------------------------------------
async function maybeShowOnboarding() {
  try {
    const s = await apiGet("/api/settings");
    if (s.onboarding_seen) return;
    openModal("modal-onboarding");
  } catch (e) { /* non-critical: worst case the overlay just doesn't show */ }
}
$("#btn-onboarding-done").addEventListener("click", async () => {
  closeModal("modal-onboarding");
  try { await apiPost("/api/settings", { onboarding_seen: true }); } catch (e) { /* best effort */ }
});

// ---------------------------------------------------------------------------
// Settings modal
// ---------------------------------------------------------------------------
const CLOUD_MODEL_SUGGESTIONS = ["gpt-5.6-luna", "gpt-4o-mini", "gpt-5.4-nano", "gpt-5.6-terra"];

function refreshModelSuggestions() {
  const provider = ($$('input[name="provider"]:checked')[0] || {}).value || "local";
  const list = $("#model-suggestions");
  if (provider === "cloud") {
    list.innerHTML = CLOUD_MODEL_SUGGESTIONS.map((m) => `<option value="${escapeHtml(m)}">`).join("");
    $("#btn-detect-models").style.display = "none";
    $("#detect-status").textContent = "Cloud mode: GPT-5.6 Luna is the balanced low-cost GM default; GPT-4o mini remains the cheaper background model.";
  } else {
    $("#btn-detect-models").style.display = "";
    $("#detect-status").textContent = "Not tested yet.";
  }
}
$$('input[name="provider"]').forEach((r) => r.addEventListener("change", () => {
  refreshModelSuggestions();
  if (r.checked && r.value === "cloud") {
    const main = $("#st-main-model"), background = $("#st-bg-model");
    if (!main.value.trim() || !CLOUD_MODEL_SUGGESTIONS.includes(main.value.trim())) main.value = "gpt-5.6-luna";
    if (!background.value.trim() || !CLOUD_MODEL_SUGGESTIONS.includes(background.value.trim())) background.value = "gpt-4o-mini";
  }
}));

async function openSettingsModal() {
  const s = await apiGet("/api/settings");
  $$('input[name="provider"]').forEach((r) => r.checked = r.value === s.provider);
  $("#st-base-url").value = s.local_base_url || "http://localhost:1234/v1";
  $("#st-token").value = s.local_token || "";
  $("#st-main-model").value = s.model || "";
  $("#st-bg-model").value = s.secondary_model || "";
  $("#st-api-key").value = "";
  $("#st-narration").value = s.narration || "Concise";
  $("#st-autosave").checked = !!s.autosave;
  $("#st-sound").checked = !!s.sound_enabled;
  $("#st-music").checked = s.music_enabled !== false;
  $("#st-music-volume").value = Number(s.music_volume ?? .35);
  $("#st-anim").checked = !!s.animations_enabled;
  $("#st-portrait-enabled").checked = s.portrait_generation_enabled !== false;
  $("#st-image-model").value = s.image_model || "gpt-image-2";
  $("#st-local-image-model").value = s.local_image_model || "";
  $("#st-portrait-quality").value = s.portrait_quality || "low";
  $("#st-developer-mode").checked = !!s.developer_mode;
  refreshModelSuggestions();
  refreshUsagePill();
  openModal("modal-settings");
}

$("#btn-detect-models").addEventListener("click", async () => {
  $("#detect-status").textContent = "Checking LM Studio...";
  try {
    const r = await apiPost("/api/settings/detect_models", { base_url: $("#st-base-url").value.trim(), token: $("#st-token").value.trim() });
    if (!r.models || !r.models.length) { $("#detect-status").textContent = "Connected, but no models are visible."; return; }
    $("#model-suggestions").innerHTML = r.models.map((m) => `<option value="${escapeHtml(m)}">`).join("");
    if (!$("#st-main-model").value) $("#st-main-model").value = r.models[0];
    if (!$("#st-bg-model").value) $("#st-bg-model").value = r.models[0];
    $("#detect-status").textContent = `CONNECTED — ${r.models.length} model(s) found. Pick one from the suggestions.`;
  } catch (e) { $("#detect-status").textContent = "NOT CONNECTED"; showToast(e.message, "danger"); }
});

$("#btn-save-settings").addEventListener("click", async () => {
  const provider = $$('input[name="provider"]:checked')[0].value;
  const patch = {
    provider,
    local_base_url: $("#st-base-url").value.trim() || "http://localhost:1234/v1",
    local_token: $("#st-token").value.trim(),
    model: $("#st-main-model").value,
    secondary_model: $("#st-bg-model").value || $("#st-main-model").value,
    narration: $("#st-narration").value,
    autosave: $("#st-autosave").checked,
    sound_enabled: $("#st-sound").checked,
    music_enabled: $("#st-music").checked,
    music_volume: Number($("#st-music-volume").value || .35),
    animations_enabled: $("#st-anim").checked,
    portrait_generation_enabled: $("#st-portrait-enabled").checked,
    image_model: $("#st-image-model").value.trim() || "gpt-image-2",
    local_image_model: $("#st-local-image-model").value.trim(),
    portrait_quality: $("#st-portrait-quality").value,
    developer_mode: $("#st-developer-mode").checked,
  };
  if ($("#st-api-key").value.trim()) patch.api_key = $("#st-api-key").value.trim();
  await apiPost("/api/settings", patch);
  APP.soundEnabled = patch.sound_enabled;
  APP.musicEnabled = patch.music_enabled;
  APP.musicVolume = patch.music_volume;
  fadeAudioTo(musicPlayer(), patch.music_volume, 300);
  if (!APP.musicEnabled) musicPlayer().pause();
  APP.animationsEnabled = patch.animations_enabled;
  closeModal("modal-settings");
  showToast(`AI mode set to: ${provider === "cloud" ? "OpenAI Cloud" : "Local LM Studio"}`, "system");
  await refreshHeaderAiStatus();
  const refreshed = await apiGet("/api/state");
  APP.campaignActive = refreshed.campaign_active;
  renderState(refreshed.state);
});

$("#btn-portrait-regenerate").addEventListener("click", () => {
  if (APP.state) ensureAiPortrait(APP.state, true);
});

async function openPortraitManager() {
  if (!APP.campaignActive) { showToast("Start or load a campaign first.", "system"); return; }
  const result = await apiGet("/api/portrait/history");
  const identity = result.identity || {};
  $("#portrait-canonical").value = identity.canonical_description || APP.state.appearance_desc || "";
  $("#portrait-temporary").value = (identity.temporary_traits || []).join("\n");
  $("#portrait-locked").checked = !!identity.locked;
  $("#portrait-history").innerHTML = (result.history || []).length
    ? result.history.map((h) => `<div class="history-row"><b>Turn ${escapeHtml(h.turn ?? "?")}</b><span>${escapeHtml(h.canonical_description || h.appearance_desc || "Previous portrait")}</span></div>`).join("")
    : '<p class="hint">No earlier portrait identity is recorded.</p>';
  openModal("modal-portrait-manager");
}
$("#btn-portrait-manage").addEventListener("click", openPortraitManager);
$("#btn-portrait-accept").addEventListener("click", async () => {
  try {
    const result = await apiPost("/api/portrait/identity", {
      canonical_description: $("#portrait-canonical").value.trim(),
      temporary_traits: $("#portrait-temporary").value.split(/\n/).map((x) => x.trim()).filter(Boolean),
      locked: $("#portrait-locked").checked,
    });
    renderState(result.state); closeModal("modal-portrait-manager"); showToast("Portrait identity saved.", "notify");
  } catch (error) { showToast(error.message, "danger"); }
});
$("#btn-portrait-upload").addEventListener("click", async () => {
  const file = $("#portrait-reference-file").files[0];
  if (!file) { showToast("Choose a portrait image first.", "system"); return; }
  const form = new FormData(); form.append("image", file);
  try {
    const result = await api("/api/portrait/reference", { method: "POST", body: form });
    renderState(result.state); showToast("Reference portrait saved.", "notify");
  } catch (error) { showToast(error.message, "danger"); }
});
$("#btn-portrait-revert").addEventListener("click", async () => {
  try { const result = await apiPost("/api/portrait/revert", {}); renderState(result.state); await openPortraitManager(); }
  catch (error) { showToast(error.message, "danger"); }
});

function downloadEndpoint(path) {
  const anchor = document.createElement("a"); anchor.href = path; anchor.download = "";
  document.body.appendChild(anchor); anchor.click(); anchor.remove();
}

async function refreshUsagePill() {
  try {
    const u = await apiGet("/api/usage");
    const pill = $("#hdr-cost"), summary = $("#usage-summary");
    if (u.provider !== "cloud") {
      pill.hidden = true;
      if (summary) summary.textContent = "Local mode: text inference is free. Portrait counts still track below.";
    } else {
      const prefix = u.cost_estimate_complete ? "~$" : "$";
      pill.hidden = false;
      pill.textContent = `${prefix}${u.total_cost_usd.toFixed(2)} this session`;
      pill.title = `${u.total_calls} AI call(s) — main model + background model + ${u.portraits.generated} portrait(s).`
        + (u.cost_estimate_complete ? "" : " (one or more models are unpriced; total is a floor, not exact.)");
    }
    if (summary && u.provider === "cloud") {
      summary.textContent = `This session so far: ~$${u.total_cost_usd.toFixed(2)} across ${u.total_calls} AI call(s) `
        + `(${u.main.input_tokens + u.main.output_tokens} main-model tokens, ${u.background.input_tokens + u.background.output_tokens} background-model tokens) `
        + `and ${u.portraits.generated} portrait(s).`
        + (u.cost_estimate_complete ? "" : " Some pricing is unknown for the selected model(s), so this is a floor, not an exact total.");
    }
  } catch (e) { /* usage is a convenience readout, never block on it */ }
}

const PRESET_MODELS = {
  budget: { model: "gpt-5-nano", secondary_model: "gpt-5-nano", image_model: "gpt-image-2", portrait_quality: "low" },
  quality: { model: "gpt-5.6-terra", secondary_model: "gpt-5.6-luna", image_model: "gpt-image-2", portrait_quality: "high" },
};
function applyModelPreset(name) {
  const p = PRESET_MODELS[name];
  $$('input[name="provider"]').forEach((r) => r.checked = r.value === "cloud");
  $("#st-main-model").value = p.model;
  $("#st-bg-model").value = p.secondary_model;
  $("#st-image-model").value = p.image_model;
  $("#st-portrait-quality").value = p.portrait_quality;
  refreshModelSuggestions();
  showToast(`${name === "budget" ? "Budget" : "Quality"} preset applied — press SAVE to confirm.`, "system");
}
$("#btn-preset-budget").addEventListener("click", () => applyModelPreset("budget"));
$("#btn-preset-quality").addEventListener("click", () => applyModelPreset("quality"));

async function refreshHeaderAiStatus() {
  const st = await apiGet("/api/state");
  $("#hdr-ai").textContent = st.ai_ready ? "AI: READY" : "AI: MODEL NOT SELECTED";
}

// ---------------------------------------------------------------------------
// Menu bar actions
// ---------------------------------------------------------------------------
async function runMenuAction(action) {
  playSfx("ui_click");
  if (action === "new-campaign") await openNewCampaignModal();
  else if (action === "settings") await openSettingsModal();
  else if (action === "help") openModal("modal-help");
  else if (action === "save") { try { await apiPost("/api/save", {}); playSfx("save"); showToast("Campaign saved.", "notify"); } catch (err) { showToast(err.message, "danger"); } }
  else if (action === "load") await openLoadModal();
  else if (action === "undo") {
    try { const r = await apiPost("/api/action/undo", {}); appendStoryEntries(r.story); renderState(r.state); }
    catch (err) { showToast(err.message, "danger"); }
  }
  else if (action === "export") downloadEndpoint("/api/save/export");
  else if (action === "import") { await openLoadModal(); $("#campaign-import-file").click(); }
  else if (action === "world-packs") {
    const r = await apiGet("/api/world-packs");
    $("#world-pack-content").innerHTML = `<p>Drop validated JSON world packs into:</p><code>${escapeHtml(r.folder)}</code><h3>Loaded</h3>${(r.loaded || []).length ? (r.loaded || []).map((x) => `<div class="jrow">${escapeHtml(typeof x === "object" ? x.name || x.id || JSON.stringify(x) : x)}</div>`).join("") : '<p class="hint">Only built-in worlds are loaded.</p>'}<h3>Errors</h3>${(r.errors || []).length ? r.errors.map((x) => `<div class="advance-warning">${escapeHtml(typeof x === "object" ? JSON.stringify(x) : x)}</div>`).join("") : '<p class="hint">No world-pack errors.</p>'}`;
    openModal("modal-world-packs");
  }
  else if (action === "diagnostics") {
    const r = await apiGet("/api/diagnostics");
    $("#diagnostics-summary").innerHTML = `<div class="preview-grid"><div><b>Version</b><span>${escapeHtml(r.app_version || APP.state?._app_version || "?")}</span></div><div><b>Campaign</b><span>${escapeHtml(APP.state?.name || "None")}</span></div><div><b>Scene match</b><span>${escapeHtml(r.scene?.reason || "Unknown")}</span></div><div><b>Validation issues</b><span>${escapeHtml((r.validation_log || []).length)}</span></div></div>`;
    $("#diagnostics-json").textContent = JSON.stringify(r, null, 2); openModal("modal-diagnostics");
  }
  else if (action === "asset-folder") showToast("Scene art lives under assets/generated_scenes; custom overrides live under assets/user/<World>.", "system");
  else if (action === "music-folder") await openMusicFolder();
}

$("#btn-diagnostics-export").addEventListener("click", () => downloadEndpoint("/api/diagnostics/export"));

// Explicit listeners are more reliable than delegated clicks inside a native
// WebView. Menus also toggle on click, so they do not depend on hover support.
$$('[data-action]').forEach((btn) => btn.addEventListener("click", async (e) => {
  e.preventDefault();
  $$(".menu.open").forEach((m) => m.classList.remove("open"));
  try { await runMenuAction(btn.getAttribute("data-action")); }
  catch (err) { console.error(err); showToast(err.message || "That menu action could not be opened.", "danger"); }
}));
$$('.menu-btn').forEach((btn) => btn.addEventListener("click", (e) => {
  e.stopPropagation();
  const menu = btn.closest(".menu"), wasOpen = menu.classList.contains("open");
  $$(".menu.open").forEach((m) => m.classList.remove("open"));
  if (!wasOpen) menu.classList.add("open");
}));
document.addEventListener("click", (e) => {
  if (!e.target.closest(".menu")) $$(".menu.open").forEach((m) => m.classList.remove("open"));
});
$("#btn-settings-gear").addEventListener("click", openSettingsModal);

async function openLoadModal() {
  const r = await apiGet("/api/saves");
  const list = $("#load-list");
  list.innerHTML = r.saves.length ? "" : '<li class="empty">No saved campaigns yet.</li>';
  r.saves.forEach((entry) => {
    const save = typeof entry === "string" ? { id: entry, label: entry, kind: "manual", saved_at: "" } : entry;
    const li = document.createElement("li");
    li.className = save.kind === "autosave" ? "autosave-entry" : "manual-save-entry";
    li.innerHTML = `<div class="save-info"><b>${escapeHtml(save.label || save.id)}</b><small>Version ${escapeHtml(save.version || "Legacy")}${save.saved_at ? ` · ${escapeHtml(save.saved_at)}` : ""}${save.corrupt ? ` · CORRUPT: ${escapeHtml(save.error || "Unreadable")}` : ""}</small></div><div class="save-actions"><button type="button" data-save-load>LOAD</button>${save.recoverable ? '<button type="button" data-save-recover>RECOVER</button>' : ""}<button type="button" data-save-delete class="danger-link">DELETE</button></div>`;
    li.querySelector("[data-save-load]").disabled = !!save.corrupt;
    li.querySelector("[data-save-load]").addEventListener("click", async () => {
      try {
        const res = await apiPost("/api/load", { name: save.id });
        APP.campaignActive = true;
        $("#story-feed").innerHTML = "";
        appendStoryEntries(res.story.map((s) => ({ text: s.text, tag: s.tag })));
        renderState(res.state);
        closeModal("modal-load");
        showToast(save.kind === "autosave" ? "Autosave recovered." : "Campaign loaded.", "notify");
      } catch (err) { showToast(err.message, "danger"); }
    });
    li.querySelector("[data-save-recover]")?.addEventListener("click", async () => {
      try { const res = await apiPost("/api/save/recover", { name: save.id }); APP.campaignActive = true; $("#story-feed").innerHTML = ""; appendStoryEntries(res.story || []); renderState(res.state); closeModal("modal-load"); showToast("Campaign recovered from its newest autosave.", "notify"); }
      catch (err) { showToast(err.message, "danger"); }
    });
    li.querySelector("[data-save-delete]").addEventListener("click", async () => {
      if (!window.confirm(`Permanently delete ${save.label || save.id}?`)) return;
      try { await apiPost("/api/save/delete", { name: save.id }); li.remove(); showToast("Campaign save deleted.", "notify"); await refreshWelcomeSaveCount(); }
      catch (err) { showToast(err.message, "danger"); }
    });
    list.appendChild(li);
  });
  openModal("modal-load");
  closeModal("modal-welcome");
  return r.saves.length;
}

async function importSelectedCampaign() {
  const file = $("#campaign-import-file").files[0];
  if (!file) { showToast("Choose a Worldwalker JSON export first.", "system"); return; }
  const form = new FormData(); form.append("file", file);
  try {
    const result = await api("/api/save/import", { method: "POST", body: form });
    showToast(`Campaign imported from version ${result.version || "Legacy"}.`, "notify");
    await openLoadModal();
  } catch (error) { showToast(error.message, "danger"); }
}
$("#btn-campaign-import").addEventListener("click", importSelectedCampaign);
$("#campaign-import-file").addEventListener("change", () => { if ($("#campaign-import-file").files.length) importSelectedCampaign(); });

async function refreshWelcomeSaveCount() {
  try {
    const r = await apiGet("/api/saves");
    const count = (r.saves || []).length;
    $("#welcome-save-note").textContent = count ? `${count} saved campaign${count === 1 ? "" : "s"} found on this computer.` : "No saved campaigns found yet.";
  } catch (e) {
    $("#welcome-save-note").textContent = "Saved campaigns could not be checked.";
  }
}
$("#btn-welcome-new").addEventListener("click", async () => {
  try { await openNewCampaignModal(); }
  catch (e) { console.error(e); showToast("Could not open character creation: " + e.message, "danger"); }
});
$("#btn-welcome-load").addEventListener("click", async () => {
  try { await openLoadModal(); }
  catch (e) { console.error(e); showToast("Could not open saved games: " + e.message, "danger"); }
});

// ---------------------------------------------------------------------------
// Collapsible panels — every panel except Story & Events and the composer
// (the two the player always needs visible) can be collapsed to reclaim
// vertical space, per user request.
// ---------------------------------------------------------------------------
function initCollapsiblePanels() {
  $$(".panel").forEach((panel) => {
    if (panel.classList.contains("no-collapse")) return;
    const head = panel.querySelector(".panel-head");
    if (!head || head.querySelector(".collapse-chevron")) return;
    const chevron = document.createElement("span");
    chevron.className = "collapse-chevron";
    chevron.textContent = "▾";
    head.appendChild(chevron);
    head.addEventListener("click", (e) => {
      if (e.target.closest("button")) return;
      panel.classList.toggle("collapsed");
    });
  });
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------
async function boot() {
  try {
    const [settings, st] = await Promise.all([apiGet("/api/settings"), apiGet("/api/state")]);
    APP.soundEnabled = !!settings.sound_enabled;
    APP.musicEnabled = settings.music_enabled !== false;
    APP.musicVolume = Number(settings.music_volume ?? .35);
    musicPlayer().volume = APP.musicVolume;
    APP.animationsEnabled = !!settings.animations_enabled;
    APP.campaignActive = st.campaign_active;
    renderState(st.state);
    $("#hdr-ai").textContent = st.ai_ready ? "AI: READY" : "AI: READY TO TEST";
    if (st.campaign_active) {
      $("#story-feed").innerHTML = "";
      // story already flushed server-side across requests; nothing to replay on fresh boot
      appendStoryEntries([{ text: "Welcome back to " + (st.state.world || "Worldwalker") + ".", tag: "system" }]);
    } else {
      appendStoryEntries([
        { text: "Welcome to Worldwalker.", tag: "system" },
        { text: "You stand at the threshold of endless possibilities.", tag: "system" },
        { text: "The road ahead is long, but every legend begins with a single choice.", tag: "system" },
        { text: "What will you do?", tag: "system" },
      ]);
      await refreshWelcomeSaveCount();
      openModal("modal-welcome");
    }
  } catch (e) {
    console.error(e);
    $("#welcome-save-note").textContent = "The game server did not respond. Restart Worldwalker and try again.";
    openModal("modal-welcome");
  }
  initCollapsiblePanels();
  refreshUsagePill();
}
boot();
