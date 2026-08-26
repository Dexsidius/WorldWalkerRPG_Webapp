"use strict";
/* Worldwalker RPG — frontend engine: API glue, rendering, animation, sound. */

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

const CURRENCY_ICON_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M9.2 14.8c.4 1 1.5 1.7 2.8 1.7 1.7 0 2.8-.9 2.8-2s-1.1-1.7-2.8-2c-1.7-.3-2.8-.9-2.8-2s1.1-2 2.8-2c1.3 0 2.4.7 2.8 1.7"/><path d="M12 7.2v1.1M12 15.7v1.1"/></svg>';
// Shops are only loosely specified in the GM prompt, so an inventory item's
// price might be a plain number or free text like "50 Berries" — mirrors
// backend systems.py's parse_price() so the Buy button only appears/enables
// when the server-side purchase would actually succeed.
function parsePriceClient(value) {
  if (typeof value === "number" && Number.isFinite(value)) return Math.max(0, Math.trunc(value));
  if (typeof value === "string") {
    const m = value.replace(/,/g, "").match(/\d+(?:\.\d+)?/);
    if (m) return Math.max(0, Math.trunc(parseFloat(m[0])));
  }
  return null;
}
function currencyRowHtml(name, amount) {
  return `<div class="jrow currency-jrow"><i class="currency-icon">${CURRENCY_ICON_SVG}</i><b>${escapeHtml(amount)}</b> ${escapeHtml(name)}</div>`;
}
// A title is USUALLY a plain string, but a model that mimics the shape of
// its own context occasionally hands one back as {name/title: "..."} —
// naive escapeHtml(title) on that renders literal "[object Object]".
function titleLabel(t) {
  return (t && typeof t === "object" ? compactReadable(t.name || t.title) : "") || compactReadable(t) || "Title";
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
  // The pywebview desktop shell always talks to its own same-machine Flask
  // server, so there is no offline scenario for it to guard against — only
  // register for a real browser tab (e.g. a phone connecting over LAN),
  // where `window.pywebview` (injected by pywebview itself) is absent.
  if ("serviceWorker" in navigator && window.isSecureContext) {
    if (window.pywebview) {
      // Tear down any worker a previous desktop build left registered —
      // an already-active one keeps controlling this page (and serving
      // whatever it cached) indefinitely, even after the page itself
      // stops calling register(). This is a one-time cleanup, not a
      // recurring cost: once nothing is registered, this is a no-op.
      navigator.serviceWorker.getRegistrations().then((regs) => regs.forEach((r) => r.unregister())).catch(() => {});
    } else {
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    }
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
  pendingPowerGoal: null, // the time-skip payload awaiting confirmed_power_goal
  pendingAdvance: null,
  pendingManualRoll: null,
  pendingDifficulty: null,
  challenge: null,
  pendingCampaign: null,
  pendingPreview: null,
  journalTab: "party",
  portraitAttempted: new Set(),
  portraitInFlight: false,
  deferPortraitGeneration: false,
  lastChapterCount: null,
  statusWindowOpen: false,
  lastLocation: null,
  lastCombatActive: false,
  lastMajorVisualKey: "",
};

// ---------------------------------------------------------------------------
// Sound
// ---------------------------------------------------------------------------
function playSfx(name) {
  if (!APP.soundEnabled) return;
  const el = document.getElementById("snd-" + name);
  if (!el) return;
  const worldPitch = {
    "One Piece": 0.94,
    "Hunter x Hunter": 1.02,
    "Naruto": 1.08,
    "Solo Max-Level Newbie": 1.15,
    "Overgeared": 0.88,
    "Reincarnated as a Slime": 1.04,
    "Bleach": 0.97,
    "Custom": 1,
  };
  const worldGain = {
    "One Piece": .82, "Hunter x Hunter": .76, "Naruto": .84,
    "Solo Max-Level Newbie": .72, "Overgeared": .9,
    "Reincarnated as a Slime": .7, "Bleach": .78, "Custom": .8,
  };
  try {
    // Give each interface its own subtle audio character without multiplying
    // the size of the installation with another full sound pack.
    el.playbackRate = worldPitch[APP.state?.world] || 1;
    el.volume = worldGain[APP.state?.world] || .8;
    el.currentTime = 0;
    el.play().catch(() => {});
  } catch (e) {}
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

const CINEMATIC_ICON = { level_up: "🎉", xp: "✦", notify: "★", danger: "⚠", message: "✉", world: "🌍", time: "⏳", damage: "💥", position: "👑", achievement: "🏆", canon_event: "⚡" };
function clearTransientFeedback() {
  const banner = $("#cinematic-banner");
  clearTimeout(banner._t);
  clearTimeout(banner._clearT);
  banner.classList.remove("show");
  banner.replaceChildren();
  $("#toast-stack").replaceChildren();
}

function showCinematic(type, message) {
  const banner = $("#cinematic-banner");
  const icon = CINEMATIC_ICON[type] || "★";
  banner.innerHTML = `<div class="banner-card ${type === "danger" || type === "damage" ? "danger" : type === "achievement" ? "achievement" : type === "canon_event" ? "canon-event" : ""}"><span class="banner-icon">${icon}</span><span>${escapeHtml(message)}</span></div>`;
  banner.classList.add("show");
  clearTimeout(banner._t);
  clearTimeout(banner._clearT);
  banner._t = setTimeout(() => {
    banner.classList.remove("show");
    banner._clearT = setTimeout(() => {
      if (!banner.classList.contains("show")) banner.replaceChildren();
    }, 500);
  }, 3200);
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
    const majorCinematics = new Set(["level_up", "position", "danger", "damage", "achievement", "canon_event"]);
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
      else if (n.cinematic === "canon_event") { playSfx("world_event"); flashScreen("danger"); shakeApp(); }
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
  const raw = String(entry.text || "").trim().replace(/([.!?])\1+(?=[”"'’\s]|$)/g, "$1");
  const lines = raw.split("\n");
  const bracket = lines[0]?.match(/^\[([^\]]+)\]\s*$/);
  const labelByTag = { narrative: "Story", player: "Your action", system: "Notice", danger: "Urgent", roll: "Check", growth: "Growth", canon_event: "Major Canon Event" };
  const label = bracket ? bracket[1].replace(/[_-]+/g, " ") : (labelByTag[tag] || "Story");
  const body = bracket ? lines.slice(1).join("\n").trim() : raw.replace(/^>\s*/, "");
  return { tag, label, body: body || raw, hasOwnTitle: !!bracket };
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

// Mirrors backend worlds.py's format_calendar_date/canon_day_to_calendar_parts
// exactly (same start days, same named months, same 30-day-month/12-month-year
// scheme) so the Chronicle's day-group headers read as real dates instead of
// the internal "Canon Day +7" counter, without a round trip per label.
const WORLD_START_DAY = {
  "One Piece": -7, "Hunter x Hunter": -7, "Naruto": -7, "Solo Max-Level Newbie": -3,
  "Overgeared": -3, "Reincarnated as a Slime": -7, "Custom World": -7,
};
const REAL_MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const WORLD_CALENDAR_MONTHS = {
  "One Piece": REAL_MONTH_NAMES, "Naruto": REAL_MONTH_NAMES, "Hunter x Hunter": REAL_MONTH_NAMES,
  "Overgeared": REAL_MONTH_NAMES, "Reincarnated as a Slime": REAL_MONTH_NAMES,
};

function formatCalendarDate(world, canonDay, calendarEpoch, anchorDay) {
  const startDay = (anchorDay !== undefined && anchorDay !== null) ? anchorDay : (WORLD_START_DAY[world] ?? -7);
  const daysPerMonth = 30, daysPerYear = 360;
  const absoluteDay = Number(canonDay) - startDay;
  let year = Math.floor(absoluteDay / daysPerYear);
  const monthDay = absoluteDay - year * daysPerYear;
  let month = Math.floor(monthDay / daysPerMonth);
  const day = monthDay - month * daysPerMonth + 1;
  year += 1; month += 1;
  if (world === "Solo Max-Level Newbie") {
    const epoch = calendarEpoch ? new Date(calendarEpoch + "T00:00:00") : new Date();
    const elapsedDays = (year - 1) * daysPerYear + (month - 1) * daysPerMonth + (day - 1);
    const real = new Date(epoch.getTime() + elapsedDays * 86400000);
    return `${REAL_MONTH_NAMES[real.getMonth()]} ${real.getDate()}, ${real.getFullYear()}`;
  }
  const months = WORLD_CALENDAR_MONTHS[world];
  if (months) return `${months[(month - 1) % months.length]} ${day}, Year ${year}`;
  return `Year ${year}, Month ${month}, Day ${day}`;
}

function dayLabel(canonDay) {
  const n = Number(canonDay);
  if (!Number.isFinite(n)) return "";
  const world = (APP.state && APP.state.world) || "Custom World";
  return formatCalendarDate(world, n, APP.state && APP.state.calendar_epoch, APP.state && APP.state.calendar_anchor_day);
}

// The Chronicle only ever grew by appending — nothing ever removed an old
// entry, so a long single play session (the normal way to use this app —
// nobody restarts mid-campaign) built up an ever-larger DOM tree over time.
// That's what actually made the app feel sluggish: more nodes for the
// browser to lay out and repaint on every scroll and re-render, not AI
// latency. Trimming old beats once the feed gets long keeps recent
// scrollback intact while capping how much the live DOM can grow — the
// full history still lives in the save file and Journal -> Chapters either
// way, this only bounds what stays mounted on screen.
const STORY_FEED_MAX_ENTRIES = 300;
function pruneStoryFeed(feed, maxEntries = STORY_FEED_MAX_ENTRIES) {
  let count = feed.querySelectorAll(".story-entry").length;
  while (count > maxEntries && feed.children.length > 1) {
    const oldest = feed.firstElementChild;
    if (!oldest) break;
    count -= oldest.querySelectorAll(".story-entry").length;
    oldest.remove();
  }
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
    const worldTime = String(run.entries.find((entry) => entry.world_time)?.world_time || "");
    const worldParts = worldTime.split(/\s+[—-]\s+/);
    const dateText = dayLabel(run.day) || (worldParts.length > 1 ? worldParts[0] : "");
    const clockLabel = worldParts.length > 1 ? worldParts.slice(1).join(" — ") : "";
    beat.innerHTML = `<header class="story-beat-head"><span>${escapeHtml(dateText || storyBeatLabel(run.entries))}</span>${clockLabel ? `<time>${escapeHtml(clockLabel)}</time>` : ""}</header>`;
    const entriesWrap = document.createElement("div");
    entriesWrap.className = "story-beat-entries";
    beat.appendChild(entriesWrap);
    let lastRow = null;
    // Only merge an entry into the previous one visually when NEITHER carries
    // its own AI-given title — that's the "two paragraphs of one flowing
    // scene" case. An entry with its own [TITLE] is a distinct, separately
    // dated/sequenced sub-event (e.g. several updates that all happen to
    // land on the same calendar day during a multi-day skip) and must keep
    // its own visible label — otherwise it silently reads as a continuation
    // of the previous event instead of a separate one.
    let lastWasUntitledNarrative = false;
    // Purely mechanical/administrative notices (an undo confirmation, a
    // stat-delta readout, "quest complete" bookkeeping) don't belong in the
    // middle of the story being told — collected here and rendered as one
    // collapsed strip at the end of the beat instead of a normal row, same
    // idea as the roll pill below but for things with no single narrative
    // line to attach to.
    const metaEntries = [];
    run.entries.forEach((entry) => {
      const part = storyEntryParts(entry);
      if (part.tag === "meta") {
        metaEntries.push(part);
        return;
      }
      // Attach a roll only when the preceding row is the action named by
      // its detail. Multi-action skips may return checks before their later
      // narrative cards; those checks stay as explicit rows so they can never
      // appear to belong to the final or otherwise unrelated queued action.
      if (part.tag === "roll" && lastRow) {
        const detailText = typeof entry.detail === "string" ? entry.detail : "";
        const actionMatch = detailText.match(/^Action:\s*(.*?)(?:\s+·|$)/);
        const actionText = actionMatch ? actionMatch[1].trim() : "";
        const rowText = lastRow.querySelector(".story-entry-copy")?.textContent?.trim() || "";
        if (actionText && rowText.includes(actionText)) {
          const pill = document.createElement("span");
          const positive = /SUCCESS|BREAKTHROUGH/.test(part.body);
          pill.className = "story-roll-pill " + (positive ? "hit" : "miss");
          pill.textContent = part.body.startsWith(actionText + " — ") ? part.body.slice(actionText.length + 3) : part.body;
          pill.title = detailText;
          lastRow.querySelector(".story-entry-copy")?.appendChild(pill);
          return;
        }
      }
      const div = document.createElement("div");
      const isContinuation = part.tag === "narrative" && !part.hasOwnTitle && lastWasUntitledNarrative;
      div.className = "story-entry " + part.tag + (isContinuation ? " continuation" : "");
      lastWasUntitledNarrative = part.tag === "narrative" && !part.hasOwnTitle;
      const label = document.createElement("div");
      label.className = "story-entry-label";
      label.textContent = part.label;
      // bodyWrap (not body itself) is the grid's 2nd column — body keeps its
      // exact class/role as the typeText/renderBoldedText target either way,
      // but any richer beat extras below live as normal stacked children of
      // bodyWrap instead of extra grid siblings, so they can never fight the
      // label/body column placement no matter how many of them there are.
      const bodyWrap = document.createElement("div");
      bodyWrap.className = "story-entry-body";
      const body = document.createElement("div");
      body.className = "story-entry-copy";
      bodyWrap.appendChild(body);
      div.append(label, bodyWrap);
      entriesWrap.appendChild(div);
      if (part.tag === "narrative" && APP.animationsEnabled) {
        typeText(body, part.body);
      } else if (part.tag === "narrative" || part.tag === "system" || part.tag === "canon_event") {
        renderBoldedText(body, part.body);
      } else {
        body.textContent = part.body;
      }
      // Only a dated multi-beat update carries this — a plain moment-to-
      // moment turn's entry.detail (if any) is the roll-tooltip string
      // handled above, never an object, so this can't misfire on those.
      if (entry.detail && typeof entry.detail === "object") {
        if (entry.detail.entities && entry.detail.entities.length) {
          const chips = document.createElement("div");
          chips.className = "story-entry-chips";
          chips.innerHTML = entry.detail.entities.map((name) => `<span>${escapeHtml(name)}</span>`).join("");
          bodyWrap.insertBefore(chips, body);
        }
        if (entry.detail.quote && entry.detail.quote.text) {
          const quote = document.createElement("blockquote");
          quote.className = "story-entry-quote";
          quote.innerHTML = `<p>${escapeHtml(entry.detail.quote.text)}</p>` + (entry.detail.quote.speaker ? `<cite>— ${escapeHtml(entry.detail.quote.speaker)}</cite>` : "");
          bodyWrap.appendChild(quote);
        }
        if (entry.detail.map_changes && entry.detail.map_changes.length) {
          const details = document.createElement("details");
          details.className = "story-entry-map-changes";
          const n = entry.detail.map_changes.length;
          details.innerHTML = `<summary>${n} Map Change${n === 1 ? "" : "s"}</summary><ul>${entry.detail.map_changes.map((c) => `<li>${escapeHtml(c)}</li>`).join("")}</ul>`;
          bodyWrap.appendChild(details);
        }
        if (entry.detail.purchase_offer) {
          const offer = entry.detail.purchase_offer;
          const card = document.createElement("div");
          card.className = "story-purchase-offer";
          card.innerHTML = `<span class="story-purchase-offer-name">${escapeHtml(offer.item)}</span>` +
            (offer.vendor ? `<span class="story-purchase-offer-vendor">from ${escapeHtml(offer.vendor)}</span>` : "") +
            `<span class="story-purchase-offer-price">${escapeHtml(offer.price)} ${escapeHtml(offer.currency || "")}</span>` +
            `<button type="button" class="story-purchase-offer-buy" data-offer-buy="${escapeHtml(offer.id)}">Buy</button>`;
          bodyWrap.appendChild(card);
        }
      }
      lastRow = div;
    });
    if (metaEntries.length) {
      const strip = document.createElement("details");
      strip.className = "story-beat-system";
      strip.innerHTML = `<summary>System (${metaEntries.length})</summary>` +
        metaEntries.map((part) => `<div class="story-beat-system-row"><b>${escapeHtml(part.label)}</b><span>${escapeHtml(part.body)}</span></div>`).join("");
      entriesWrap.appendChild(strip);
    }
    feed.appendChild(beat);
  });
  pruneStoryFeed(feed);
  feed.scrollTop = feed.scrollHeight + 400;
}

// Loading a save stays fast on its own — this fires as an unawaited
// follow-up right after, so the recap (if the real-world gap since the
// save was written was long enough) lands a moment later instead of
// blocking the load itself on an AI round trip.
function maybeFetchReentryRecap(state) {
  if (!state || !state._reentry_gap_hours) return;
  apiPost("/api/reentry_recap", {}).then((res) => {
    if (res.story && res.story.length) appendStoryEntries(res.story);
    if (res.state) renderState(res.state);
  }).catch(() => { /* best effort — a missed recap just means the world was silent this time */ });
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

$("#btn-rate-turn-good").addEventListener("click", async () => {
  try {
    await apiPost("/api/turn/rate_good", {});
    showToast("Marked as a good turn — the GM will draw on it as a real example.", "notify");
  } catch (error) { showToast(error.message, "danger"); }
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
// Consequence chain (continuity.py): a short "why did this relationship end
// up here" trail attached to an NPC or faction. Most recent first, already
// capped server-side — this just renders it or omits the section entirely
// when there's nothing recorded yet.
function chainHistoryHtml(entries) {
  if (!Array.isArray(entries) || !entries.length) return "";
  const rows = entries.map((e) => `<li>${escapeHtml(e.event)}${e.canon_day != null ? ` <small>(Day ${escapeHtml(e.canon_day)})</small>` : ""}</li>`).join("");
  return `<p><b>History:</b></p><ul class="chain-history">${rows}</ul>`;
}

function questView(q, index = 0) {
  if (typeof q !== "object" || q === null) {
    return { name: String(q || `Quest ${index + 1}`), status: "Active", explanation: "No additional explanation has been discovered yet.", knowledge: [], conditions: [], objectives: [], branchState: {}, giver: "", locations: [], risks: [], firstStep: "", deadline: "", rewards: [], developments: [], commitments: [], optionalObjectives: [], progress: 0 };
  }
  return {
    name: q.name || q.title || `Quest ${index + 1}`,
    status: q.status || q.stage || "Active",
    explanation: q.explanation || q.description || q.notes || q.summary || "No additional explanation has been discovered yet.",
    knowledge: textList(q.discovered_clues || q.current_knowledge || q.knowledge || q.clues || q.known_facts),
    conditions: textList(q.clear_conditions || q.completion_conditions || q.conditions || q.objectives || q.objective),
    objectives: Array.isArray(q.objectives) ? q.objectives : [],
    branchState: q.branch_state && typeof q.branch_state === "object" ? q.branch_state : {},
    giver: q.giver || q.cause || q.employer || "",
    locations: textList(q.locations || q.location),
    risks: textList(q.current_obstacles || q.risks || q.known_risks || q.consequences),
    optionalObjectives: textList(q.optional_objectives),
    firstStep: q.next_hint || q.first_step || q.next_step || "",
    progress: Number(q.progress_percent || 0),
    deadline: q.deadline || "",
    rewards: textList(q.rewards || q.reward),
    developments: textList(q.developments || q.recent_developments),
    commitments: textList(q.commitments || q.promises),
  };
}

function questPresentation(world) {
  const presentations = {
    "Overgeared": { literal: true, tab_label: "Quests", rail_label: "Active Quest", empty_label: "No active quest", entry_label: "Quest", archive_label: "Completed / failed quests" },
    "Solo Max-Level Newbie": { literal: true, tab_label: "System Quests", rail_label: "Active Quest", empty_label: "No active quest", entry_label: "Quest", archive_label: "Completed / failed quests" },
    "Naruto": { literal: false, tab_label: "Mission Agenda", rail_label: "Current Assignment", empty_label: "No current assignment", entry_label: "Assignment", archive_label: "Mission history" },
    "One Piece": { literal: false, tab_label: "Voyage Log", rail_label: "Current Priority", empty_label: "No current priority", entry_label: "Priority", archive_label: "Past voyages and promises" },
    "Hunter x Hunter": { literal: false, tab_label: "Hunter Agenda", rail_label: "Current Case", empty_label: "No current case", entry_label: "Case", archive_label: "Closed cases and hunts" },
    "Bleach": { literal: false, tab_label: "Division Agenda", rail_label: "Current Order", empty_label: "No current order", entry_label: "Order", archive_label: "Completed orders and incidents" },
    "Reincarnated as a Slime": { literal: false, tab_label: "Journey Agenda", rail_label: "Current Concern", empty_label: "No current concern", entry_label: "Concern", archive_label: "Resolved concerns" },
  };
  return presentations[world] || { literal: false, tab_label: "Agenda", rail_label: "Current Direction", empty_label: "No current direction", entry_label: "Agenda", archive_label: "Past goals and outcomes" };
}

function humanLabel(value) {
  return String(value || "Detail").replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function compactReadable(value) {
  if (value === null || value === undefined || value === "") return "";
  if (Array.isArray(value)) return value.map(compactReadable).filter(Boolean).join("; ");
  if (typeof value === "object") return "";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  const text = String(value).trim();
  // Same JSON-string recovery as renderSkillCard: a field the model returned
  // as a JSON-encoded string instead of plain text would otherwise print its
  // literal braces/brackets straight into the UI.
  if ((text.startsWith("{") && text.endsWith("}")) || (text.startsWith("[") && text.endsWith("]"))) {
    try { return compactReadable(JSON.parse(text)); } catch (e) { /* not actually JSON */ }
  }
  return text;
}

function renderSkillCard(name, rawDetail) {
  if (rawDetail === null || rawDetail === undefined) rawDetail = {};
  if (typeof rawDetail === "string") {
    // The model occasionally returns a skill's detail as a JSON-encoded
    // string instead of an actual object — displaying that string verbatim
    // is exactly what shows up as literal {"rank":"B",...} brace-and-quote
    // soup in the Journal. Recover the real object when the string is
    // actually parseable JSON before falling back to showing it as text.
    const trimmed = rawDetail.trim();
    if ((trimmed.startsWith("{") && trimmed.endsWith("}")) || (trimmed.startsWith("[") && trimmed.endsWith("]"))) {
      try { rawDetail = JSON.parse(trimmed); } catch (e) { /* not actually JSON — keep the original string */ }
    }
  }
  if (typeof rawDetail !== "object" || Array.isArray(rawDetail)) {
    return `<article class="skill-journal-card"><h3>✦ ${escapeHtml(name)}</h3><p>${escapeHtml(compactReadable(rawDetail) || "This skill has not been described yet.")}</p></article>`;
  }
  const detail = rawDetail;
  const rank = compactReadable(detail.rank ?? detail.tier ?? detail.level);
  const bonus = Number.isFinite(Number(detail.bonus)) ? Number(detail.bonus) : null;
  const category = compactReadable(detail.category);
  const effectType = compactReadable(detail.effect_type);
  const targetType = compactReadable(detail.target_type);
  const duration = Number(detail.duration_rounds || 0);
  const summary = compactReadable(detail.effect || detail.description || detail.summary) || "The exact practical effect has not been recorded yet.";
  const rows = [
    ["Combat use", detail.combat_usable ? [effectType && humanLabel(effectType), targetType && `targets ${humanLabel(targetType)}`, duration > 0 && `${duration} rounds`].filter(Boolean).join(" · ") : ""],
    ["How it works", detail.use || detail.activation || detail.usage || detail.requirements],
    ["Origin", detail.origin],
    ["Cost / limits", detail.limitation || detail.limitations || detail.cost || detail.drawback],
    ["How to improve", detail.growth_path || detail.growth || detail.next_steps],
  ].map(([label, value]) => [label, compactReadable(value)]).filter(([, value]) => value);
  const chips = [rank ? `<span>${escapeHtml(rank)}</span>` : "", category ? `<span>${escapeHtml(humanLabel(category))}</span>` : "", bonus !== null ? `<span>${bonus >= 0 ? "+" : ""}${escapeHtml(bonus)} check bonus</span>` : ""].filter(Boolean).join("");
  return `<article class="skill-journal-card"><header><h3>✦ ${escapeHtml(name)}</h3>${chips ? `<div class="skill-chips">${chips}</div>` : ""}</header><p class="skill-summary">${escapeHtml(summary)}</p>${rows.map(([label, value]) => `<div class="skill-detail"><b>${escapeHtml(label)}</b><span>${escapeHtml(value)}</span></div>`).join("")}</article>`;
}

function formatDuration(minutes) {
  const total = Math.max(0, Number(minutes || 0));
  if (total >= 1440) return `${Math.round(total / 144) / 10} day${total >= 2160 ? "s" : ""}`;
  if (total >= 60) return `${Math.round(total / 6) / 10} hour${total >= 90 ? "s" : ""}`;
  return `${Math.round(total)} minute${total === 1 ? "" : "s"}`;
}

function renderClassCard(rawClass) {
  const cls = rawClass && typeof rawClass === "object" ? { ...rawClass } : {};
  const rawDiscovery = cls.discovery && typeof cls.discovery === "object" ? cls.discovery : null;
  if (rawDiscovery?.concealed) {
    cls.name = rawDiscovery.public_name || "Unidentified Class Signature";
    cls.description = rawDiscovery.clue || "A dormant class-shaped power is present, but its nature is not yet understood.";
    cls.effect = Number(rawDiscovery.progress || 0) < 70 ? "Some bonuses are already active; their exact source remains unclear." : cls.effect;
    if (Number(rawDiscovery.progress || 0) < 50) cls.signature_skill = "";
    if (Number(rawDiscovery.progress || 0) < 70) {
      cls.stat_bonuses = {};
      cls.limitation = "Use, appraisal, or class-relevant training is required to identify it.";
      cls.growth_path = "Experiment with the unusual capability and seek a way to appraise hidden paths.";
    }
  }
  if (!cls.name) return "";
  const bonuses = cls.stat_bonuses && typeof cls.stat_bonuses === "object"
    ? Object.entries(cls.stat_bonuses).map(([name, value]) => `${name} ${Number(value) >= 0 ? "+" : ""}${value}`).join(" · ")
    : "";
  const rows = [
    ["Class feature", cls.effect],
    ["Starting bonuses", bonuses],
    ["Signature skill", cls.signature_skill],
    ["Limits", cls.limitation],
    ["Advancement", cls.growth_path],
    ["World-scale balance", cls.canon_balance],
    ["Why it is rare", cls.rarity_reason],
  ].map(([label, value]) => [label, compactReadable(value)]).filter(([, value]) => value);
  const discovery = cls.discovery && typeof cls.discovery === "object" ? cls.discovery : null;
  const discoveryRow = discovery ? `<div class="class-discovery"><div><b>Discovery</b><span>${escapeHtml(discovery.stage || "dormant")} · ${escapeHtml(discovery.progress ?? 0)}%</span></div><i style="width:${Math.max(0, Math.min(100, Number(discovery.progress || 0)))}%"></i>${textList(discovery.reveal_requirements).length ? `<small>${textList(discovery.reveal_requirements).map(escapeHtml).join(" · ")}</small>` : ""}</div>` : "";
  return `<article class="skill-journal-card class-profile-card"><header><h3>◆ ${escapeHtml(cls.name)}</h3><div class="skill-chips"><span>${escapeHtml(cls.kind || "Hidden Class")}</span><span>${escapeHtml(cls.rank || "Rare")}</span></div></header><p class="skill-summary">${escapeHtml(compactReadable(cls.description) || "A rare path whose full nature is still being discovered.")}</p>${discoveryRow}${rows.map(([label, value]) => `<div class="skill-detail"><b>${escapeHtml(label)}</b><span>${escapeHtml(value)}</span></div>`).join("")}</article>`;
}

function renderBleachReleases(special) {
  const profile = special?.["Zanpakuto Profile"] && typeof special["Zanpakuto Profile"] === "object" ? special["Zanpakuto Profile"] : {};
  const shikai = String(special?.Shikai || "Unachieved");
  const bankai = String(special?.Bankai || "Unachieved");
  const achieved = (value) => !/^(?:unachieved|none|unknown|)$/i.test(value);
  const row = (label, value) => value ? `<div class="release-detail"><b>${escapeHtml(label)}</b><span>${escapeHtml(compactReadable(value))}</span></div>` : "";
  const shikaiCard = `<article class="release-card shikai-card ${achieved(shikai) ? "awakened" : "sealed"}"><header><span>始解</span><div><small>FIRST RELEASE</small><h3>${escapeHtml(achieved(shikai) ? (profile.shikai_name || shikai) : "Shikai — Unachieved")}</h3></div></header>${achieved(shikai) ? `${row("Release command", profile.release_command)}${row("Form", profile.shikai_form)}${row("Ability", profile.shikai_effect)}${row("Limits", profile.shikai_limitation)}${row("Counters", profile.shikai_counters)}` : `<p>Learn the spirit's identity and true name through Jinzen, training, battle and a personal inner-world trial.</p>`}</article>`;
  const bankaiCard = `<article class="release-card bankai-card ${achieved(bankai) ? "awakened" : "sealed"}"><header><span>卍解</span><div><small>FINAL RELEASE</small><h3>${escapeHtml(achieved(bankai) ? (profile.bankai_name || bankai) : "Bankai — Unachieved")}</h3></div></header>${achieved(bankai) ? `${row("Manifestation", profile.bankai_manifestation)}${row("Ability", profile.bankai_effect)}${row("Cost", profile.bankai_cost)}${row("Counters", profile.bankai_counters)}` : `<p>Requires an achieved Shikai, spirit manifestation, sufficient spiritual capacity and a character-specific mastery trial.</p>`}</article>`;
  return `<section class="bleach-release-grid">${shikaiCard}${bankaiCard}</section>`;
}

function worldIdentityLabel(state) {
  const special = state?.special || {}, world = state?.world;
  if (world === "One Piece") return special["Crew Role"] || special.Archetype || "Seafarer";
  if (world === "Hunter x Hunter") {
    const license = special["Hunter License"] || "Unlicensed", category = special["Nen Category"] || "Unknown";
    return !/^(?:unknown|none)$/i.test(category) ? `${license} · ${category} Nen` : license;
  }
  if (world === "Naruto") return special["Shinobi Rank"] || special.Archetype || "Shinobi";
  if (world === "Solo Max-Level Newbie") return special["System Class"] || special.Archetype || "Player";
  if (world === "Overgeared") return special.Class || "Player";
  if (world === "Reincarnated as a Slime") return special.Species || state.race || "Otherworlder";
  if (world === "Bleach") return special["Shinigami Rank"] || special.Archetype || "Soul Reaper";
  return state?.class_profile?.name || special.Archetype || "Adventurer";
}

function renderWorldProgression(world, special, classProfile, data = {}) {
  const value = (raw, fallback = "Not established") => compactReadable(raw) || fallback;
  const card = (eyebrow, title, rows, tone = "") => `<article class="world-system-card ${tone}"><header><small>${escapeHtml(eyebrow)}</small><h3>${escapeHtml(value(title))}</h3></header>${rows.filter(([,v]) => v !== undefined && v !== null && value(v, "") !== "").map(([label,v]) => `<div><b>${escapeHtml(label)}</b><span>${escapeHtml(value(v))}</span></div>`).join("")}</article>`;
  const namedRows = (rows, empty = "None recorded") => rows?.length ? rows.map((row) => {
    const title = row?.name || row?.class || "Record";
    const detail = row && typeof row === "object"
      ? Object.entries(row).filter(([key, entry]) => key !== "name" && entry !== undefined && entry !== null && compactReadable(entry)).map(([key, entry]) => `${humanLabel(key)}: ${compactReadable(entry)}`).join(" · ")
      : compactReadable(row);
    return `<div class="lit-system-row"><b>${escapeHtml(title)}</b><span>${escapeHtml(detail)}</span></div>`;
  }).join("") : `<p class="hint">${escapeHtml(empty)}</p>`;
  if (world === "One Piece") {
    const fruit = special["Devil Fruit Profile"] || {}, haki = special["Haki Profile"] || {};
    const hakiLine = (name) => `${Number(haki[name]?.mastery || 0)} mastery${textList(haki[name]?.applications).length ? ` · ${textList(haki[name].applications).join(", ")}` : ""}`;
    return `<section class="world-system-grid">${card("DEVIL FRUIT", fruit.name || special["Devil Fruit"], [["Type",fruit.type],["Abilities",fruit.abilities],["Limits",fruit.limitations],["Awakening",fruit.awakening_status]], "one-piece-system")}${card("HAKI", "Haki Development", [["Observation",hakiLine("Observation")],["Armament",hakiLine("Armament")],["Conqueror",hakiLine("Conqueror")],["Bounty",special.Bounty ?? 0]], "one-piece-system")}</section>`;
  }
  if (world === "Hunter x Hunter") {
    const nen = special["Nen Profile"] || {}, hatsu = nen.hatsu_profile || {};
    if ((nen.visibility || special["Nen Access"]) === "Undiscovered") return card("NEN", "Undiscovered", [["Current understanding","Aura terminology and techniques have not been learned in character."],["Discovery route","Find a legitimate teacher, survive an awakening, or encounter a setting-valid initiation."]], "hxh-system");
    return `<section class="world-system-grid">${card("NEN TYPE", nen.category || special["Nen Category"], [["Ten",nen.ten],["Zetsu",nen.zetsu],["Ren",nen.ren],["Status",nen.visibility]], "hxh-system")}${card("HATSU", hatsu.name || special.Hatsu, [["Category mix",hatsu.category_mix],["Effect",hatsu.effect],["Activation",hatsu.activation],["Vows",hatsu.vows],["Limits",hatsu.limitations],["Growth",hatsu.growth_path]], "hxh-system")}</section>`;
  }
  if (world === "Naruto") {
    const p = special["Shinobi Profile"] || {};
    return `<section class="world-system-grid">${card("SERVICE RECORD", p.rank || special["Shinobi Rank"], [["Home village",p.home_village],["Clan",p.clan],["Mission record",p.mission_record]], "naruto-system")}${card("CHAKRA & TECHNIQUES", p.kekkei_genkai && p.kekkei_genkai !== "None" ? p.kekkei_genkai : "Shinobi Development", [["Nature affinities",p.nature_affinities],["Known jutsu",p.known_jutsu],["Summons",p.summons],["Transformations",p.transformations]], "naruto-system")}</section>`;
  }
  if (world === "Solo Max-Level Newbie") {
    const p = special["System Profile"] || {}, sys = data.solo_system || {}, floor = sys.floor_state || {};
    const copied = Array.isArray(p.copied_abilities) ? p.copied_abilities : [];
    const copyRows = copied.map((entry) => typeof entry === "object" ? `${entry.name} — ${entry.condition_progress || 0}% · ${entry.copy_condition || "condition unknown"}` : entry);
    const hidden = (floor.hidden_conditions || []).map((entry) => `${entry.discovered ? "Known" : "Hidden"}: ${entry.discovered ? entry.name : "Unidentified condition"}${entry.completed ? " · Complete" : ""}`);
    const rivals = (sys.rivals || []).map((r) => `${r.name}: Floor ${r.floor}, Level ${r.level} — ${r.current_goal}`);
    const reports = (sys.floor_history || []).slice(-3).reverse();
    return `<section class="world-system-grid system-window-grid">${card("CURRENT SCENARIO", floor.name || `Floor ${p.floor ?? special.Floor ?? 1}`, [["Clear condition",floor.clear_condition],["Environment rule",floor.environment_rule],["Recommended power",floor.recommended_power],["Administrator",floor.administrator?.name],["Hidden routes",hidden]], "solo-system")}${card("ABILITY COPY", `${copied.reduce((n,e)=>n+Number(e?.slot_cost || 1),0)} / ${p.copy_capacity || 1} slots`, [["Copied abilities",copyRows],["Tracked attempts",sys.copy_attempts?.length || 0]], "solo-system")}</section><details class="lit-system-section"><summary>Foreknowledge, rivals, artifacts, and party roles</summary><div class="lit-system-body">${card("FOREKNOWLEDGE", `${sys.foreknowledge?.remembered?.length || 0} remembered`, [["Confirmed",sys.foreknowledge?.confirmed?.length || 0],["Changed",sys.foreknowledge?.changed?.length || 0],["Suspected conditions",sys.foreknowledge?.suspected_hidden_conditions?.length || 0],["Spent exploits",sys.foreknowledge?.spent_exploits?.length || 0]], "solo-system")}${card("RIVAL PROGRESS", `${rivals.length} tracked`, [["Current positions",rivals]], "solo-system")}${card("ARTIFACTS", `${sys.artifact_index?.length || 0} indexed`, [["Known artifacts",(sys.artifact_index || []).map(a=>`${a.name} (${a.grade}) — ${textList(a.main_effect).join(", ")}`)]], "solo-system")}${card("PARTY ROLES", `${sys.party_roles?.length || 0} assigned`, [["Contributions",(sys.party_roles || []).map(x=>`${x.name}: ${x.role}`)]], "solo-system")}</div></details>${reports.length ? `<details class="lit-system-section"><summary>Recent floor reports</summary>${namedRows(reports.map(r=>({name:`Floor ${r.floor}`,objective:r.main_objective,hidden_completed:r.hidden_completed,hidden_missed:r.hidden_missed,xp_gained:r.xp_gained,levels_gained:r.levels_gained,items:r.items})))}</details>` : ""}`;
  }
  if (world === "Overgeared") {
    const p = special["Satisfy Profile"] || {}, sys = data.overgeared_system || {};
    const paths = Object.entries(sys.production_paths || {}).map(([name,row]) => `${name}: ${row.mastery || 0} mastery (${row.rank || "Beginner"})`);
    const affinities = Object.entries(sys.npc_affinity || {}).map(([name,row]) => `${name}: ${row.score ?? 0} (${row.tier || "Unknown"})`);
    const rankings = Object.entries(sys.rankings || {}).map(([name,row]) => `${name}: ${row.band || "Unranked"} · ${row.score || 0}`);
    const orders = (sys.crafting_orders || []).map((o) => `${o.name}: ${o.progress || 0}% — ${o.status || "Active"}`);
    const classProgress = sys.class_progression || {};
    return `<section class="world-system-grid">${card("SATISFY CLASS", p.primary_class || special.Class, [["Rarity",p.class_rarity],["Secondary class",p.secondary_class],["Class stage",`${classProgress.stage || "Foundation"} · ${classProgress.stage_progress || 0}%`],["Next unlock",classProgress.next_unlock],["Guild",p.guild]], "overgeared-system")}${card("PRODUCTION PATHS", `${p.crafting_mastery ?? 0} peak mastery`, [["Separate disciplines",paths],["Specialties",p.production_specialties],["Known recipes",p.known_recipes]], "overgeared-system")}</section>${renderClassCard(classProfile)}<details class="lit-system-section"><summary>Affinity, guild, territory, orders, economy, and rankings</summary><div class="lit-system-body">${card("NPC AFFINITY", `${affinities.length} tracked`, [["Relationships",affinities]], "overgeared-system")}${card("GUILD & TERRITORY", sys.guild?.name || "Independent", [["Guild rank",sys.guild?.rank],["Guild resources",sys.guild?.resources],["Controlled territory",sys.territory?.controlled],["Morale",sys.territory?.morale],["Projects",sys.territory?.projects]], "overgeared-system")}${card("CRAFTING ORDERS", `${orders.length} tracked`, [["Orders",orders],["Reminder","Materials and routine output remain in the Chronicle; only memorable reusable products enter the Bag."]], "overgeared-system")}${card("ECONOMY & RANKINGS", `${sys.economy?.personal_gold ?? 0} personal Gold`, [["This turn",`${Number(sys.economy?.change_this_turn || 0) >= 0 ? "+" : ""}${sys.economy?.change_this_turn || 0} Gold`],["Workshop income",sys.economy?.workshop_income],["Guild funds",sys.economy?.guild_funds],["Territory revenue",sys.economy?.territory_revenue],["Public standings",rankings]], "overgeared-system")}</div></details>`;
  }
  if (world === "Reincarnated as a Slime") {
    const p = special["Evolution Profile"] || {};
    return `<section class="world-system-grid">${card("EVOLUTION", p.species || special.Species, [["Stage",p.stage],["Naming",p.named_status],["Magicule capacity",p.magicule_capacity],["Next requirements",p.evolution_requirements]], "slime-system")}${card("SKILL TAXONOMY", "Acquired Abilities", [["Intrinsic",p.intrinsic_skills],["Extra",p.extra_skills],["Unique",p.unique_skills],["Ultimate",p.ultimate_skills],["Resistances",p.resistances]], "slime-system")}</section>`;
  }
  return "";
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
  else status.textContent = s._portrait_auto_generate ? "AI PORTRAIT QUEUED" : "AI PORTRAIT · GENERATE WHEN READY";
  $("#btn-portrait-regenerate").disabled = APP.portraitInFlight || !APP.campaignActive;
  if (!APP.deferPortraitGeneration && s._portrait_auto_generate) ensureAiPortrait(s);
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

const WORLD_UI_THEMES = {
  "One Piece": { sheet: "Crew Record", attributes: "Capabilities", skills: "Techniques & Titles", chronicle: "Voyage Log" },
  "Hunter x Hunter": { sheet: "Hunter Record", attributes: "Aptitudes", skills: "Nen & Titles", chronicle: "Case Log" },
  "Naruto": { sheet: "Shinobi Record", attributes: "Shinobi Arts", skills: "Jutsu & Titles", chronicle: "Mission Scroll" },
  "Solo Max-Level Newbie": { sheet: "Status Window", attributes: "System Stats", skills: "Skills & Achievements", chronicle: "System Log" },
  "Overgeared": { sheet: "Player Status", attributes: "Character Stats", skills: "Classes & Skills", chronicle: "Adventure Log" },
  "Reincarnated as a Slime": { sheet: "Analysis Record", attributes: "Existence Values", skills: "Unique Skills & Titles", chronicle: "Great Sage Record" },
  "Bleach": { sheet: "Soul Record", attributes: "Spiritual Arts", skills: "Techniques & Releases", chronicle: "Soul Chronicle" },
  "Custom World": { sheet: "Character Sheet", attributes: "Attributes", skills: "Skills & Titles", chronicle: "Chronicle" },
};
function applyWorldInterfaceTheme(world) {
  const theme = WORLD_UI_THEMES[world] || WORLD_UI_THEMES["Custom World"];
  $("#character-sheet-title").textContent = theme.sheet;
  $("#attributes-title").lastChild.textContent = theme.attributes;
  $("#skills-panel-title").textContent = theme.skills;
  $("#chronicle-title").textContent = theme.chronicle;
}

function renderState(state) {
  APP.state = state;
  const s = state;
  document.body.setAttribute("data-world", s.world || "Custom World");
  document.body.classList.toggle("motion-off", !APP.animationsEnabled);
  applyWorldInterfaceTheme(s.world || "Custom World");
  applyPortraitAmbient(s);

  $("#hdr-world").textContent = s.world || "Custom World";
  $("#hdr-location").textContent = s.location || "Unknown";
  $("#hdr-turn").textContent = "Turn " + (s.turn || 0);
  const tension = s._tension || { score: 0, label: "Calm", reasons: [] };
  const tensionPill = $("#hdr-tension");
  tensionPill.textContent = "● " + tension.label;
  tensionPill.className = "pill tension-pill tension-" + tension.label.toLowerCase();
  tensionPill.title = tension.reasons && tension.reasons.length
    ? "How dangerous your current situation is: " + tension.reasons.join(", ") + "."
    : "How dangerous your current situation is, at a glance.";
  const saved = s._last_autosave || s.last_autosave || "";
  $("#hdr-autosave").textContent = saved ? `Saved ${String(saved).replace("T", " ").slice(0, 16)}` : "Not saved";
  renderQueuedActions(s.queued_actions || []);
  $("#scene-title").textContent = Number(s.turn || 0) > 0 ? "CURRENT SCENE" : "OPENING SCENE";
  $("#btn-retry-opening").hidden = Boolean(s.opening_complete);

  // Generated portraits are keyed by visually relevant state and update only
  // when appearance, form, or visible equipment actually changes.
  renderAiPortrait(s);
  $("#portrait-name").textContent = s.name || "Traveler";
  $("#portrait-class").textContent = worldIdentityLabel(s);
  const locationEl = $("#portrait-location");
  const locationText = (s.location || "").trim();
  if (locationText) { $("#portrait-location-text").textContent = locationText; locationEl.hidden = false; }
  else locationEl.hidden = true;
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
  const towerLabel = $("#stat-tower-timer-label"), towerTimer = $("#stat-tower-timer");
  if (typeof s._tower_days_left === "number") {
    towerLabel.hidden = false; towerTimer.hidden = false;
    towerTimer.textContent = `${s._tower_days_left} day${s._tower_days_left === 1 ? "" : "s"} left`;
    towerTimer.classList.toggle("tower-timer-critical", s._tower_days_left <= 14);
  } else {
    towerLabel.hidden = true; towerTimer.hidden = true;
  }
  const currency = s.currency || {};
  const tracksCurrency = s._tracks_currency !== false && currency.tracked !== false;
  $("#currency-row").style.display = tracksCurrency ? "" : "none";
  $("#stat-currency-label").textContent = currency.name || "Currency";
  $("#stat-currency").textContent = currency.amount !== undefined ? Number(currency.amount).toLocaleString() : "0";
  $("#stat-summary-body").classList.toggle("narrative-progression", !s._uses_xp);

  // attributes — dynamic per world (see backend worlds.WORLD_ABILITIES)
  const attrs = s.stats || {};
  const abilityProgress = s.ability_progress || {};
  const attrKeys = Object.keys(attrs);
  $("#attributes-grid").innerHTML = attrKeys.map((k) => {
    const v = attrs[k] ?? 1;
    const progress = Number(abilityProgress[k] || 0);
    const progressText = progress > .001
      ? (s._uses_xp ? `Practice +${progress.toFixed(progress >= 10 ? 1 : 2)}` : `${Math.round(progress * 100)}% to next point`)
      : "";
    return `<div class="attr-cell"><div class="attr-name"><i class="a-icon">${abilityIcon(k)}</i>${escapeHtml(k)}</div><div class="attr-right">${progressText ? `<small class="attr-progress">${escapeHtml(progressText)}</small>` : ""}<span class="attr-val">${escapeHtml(v)}</span></div></div>`;
  }).join("");

  const isFullSheet = s._stat_style === "full_sheet";
  const hiddenWrap = $("#hidden-stats-wrap");
  if (isFullSheet) {
    const revealed = { ...(s.hidden_stats || {}) };
    if (s.class_profile?.name) revealed["Hidden Class"] = s.class_profile.name;
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
  const classItems = s.class_profile?.name ? [`◆ ${escapeHtml(s.class_profile.name)} <small>(${escapeHtml(s.class_profile.kind || "Hidden Class")})</small>`] : [];
  const skillItems = Object.keys(s.skills || {}).map((k) => `✦ ${escapeHtml(k)}`);
  const titleItems = (s.titles || []).map((t) => `🏅 ${escapeHtml(titleLabel(t))}`);
  renderTagListHtml("#skills-list", [...classItems, ...titleItems, ...skillItems], "None");

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
  const questUi = questPresentation(s.world);
  const questTab = $('#journal-tabs button[data-tab="quests"]');
  if (questTab) questTab.textContent = questUi.tab_label;
  if (activeQuests.length) {
    const q = questView(activeQuests[0]);
    questPreview.classList.remove("empty");
    questPreview.innerHTML = `<span>${escapeHtml(questUi.rail_label)}</span><small>${escapeHtml(q.name)}</small>`;
  } else {
    questPreview.classList.add("empty");
    questPreview.innerHTML = `<span>${escapeHtml(questUi.rail_label)}</span><small>${escapeHtml(questUi.empty_label)}</small>`;
  }

  const feedItems = [...(s.world_events || []), ...(s.timeline || []).slice(-5)].slice(-8).map((e) => escapeHtml(typeof e === "object" ? (e.text || JSON.stringify(e)) : e));
  const worldFeedNav = $("#world-feed-nav");
  worldFeedNav.innerHTML = `<span>World Feed</span><small>${feedItems.length ? escapeHtml(String(feedItems.length) + " recent updates") : "No updates yet"}</small>`;

  // messages
  renderMessagesPanel(s);

  // time mode + world systems icons
  updateSelectedTimeLabel();
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
  const reasons = Array.isArray(s.last_cause_effect) ? s.last_cause_effect : [];
  const reasonBox = $("#change-reasons");
  reasonBox.hidden = !reasons.length;
  $("#change-reasons-list").innerHTML = reasons.map((row) => `<div class="change-reason"><b>${escapeHtml(row.target || row.category || "Change")}</b><span>${escapeHtml(row.change || "Changed")}</span><small>${escapeHtml(row.because || "The resolved turn changed this.")}</small></div>`).join("");
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
  $("#sw-class").textContent = worldIdentityLabel(s);
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
  const classItems = s.class_profile?.name ? [`<li>◆ ${escapeHtml(s.class_profile.name)} <small>(${escapeHtml(s.class_profile.kind || "Hidden Class")})</small></li>`] : [];
  const skillItems = Object.keys(s.skills || {}).map((k) => `<li>✦ ${escapeHtml(k)}</li>`);
  const titleItems = (s.titles || []).map((t) => `<li>🏅 ${escapeHtml(titleLabel(t))}</li>`);
  $("#sw-skills").innerHTML = [...classItems, ...titleItems, ...skillItems].join("") || '<li class="hint">None yet.</li>';
  const currency = s.currency || {};
  const misc = [
    (s._tracks_currency !== false && currency.tracked !== false && currency.name) ? `<div><b>${escapeHtml(currency.amount ?? 0)}</b> ${escapeHtml(currency.name)}</div>` : "",
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
  const unit = $("#time-unit")?.value || "moment";
  const amount = Number($("#time-amount")?.value || 1);
  const totalDays = unit === "days" ? amount : unit === "weeks" ? amount * 7 : unit === "months" ? amount * 30 : 0;
  const span = actions.length && totalDays ? totalDays / actions.length : 0;
  const risk = (action) => /kill|death|assassinate|alone against|boss|invade/i.test(action) ? "Extreme risk" : /fight|attack|duel|battle|infiltrate|steal|escape|master|awaken/i.test(action) ? "High risk" : /train|practice|study|research|craft|persuade|convince/i.test(action) ? "Uncertain" : "Routine";
  const schedule = (index) => {
    if (unit === "moment") return index ? "Held for a later Advance" : "Next meaningful beat · up to 24 hours";
    if (unit === "next_event") return `Step ${index + 1} before the next major turning point`;
    const start = Math.floor(index * span) + 1, end = Math.max(start, Math.round((index + 1) * span));
    return `Approx. day ${start}${end > start ? `–${end}` : ""} · ${risk(actions[index])}`;
  };
  const countdown = APP.state?._canon_countdown?.available ? `<div class="queue-interruption">Possible interruption: ${escapeHtml(APP.state._canon_countdown.label)}</div>` : "";
  box.innerHTML = actions.map((action, index) => `<div class="queued-action"><span class="queue-index">${index + 1}</span><span class="queue-copy"><b>${escapeHtml(action)}</b><small>${escapeHtml(schedule(index))}</small></span><span class="queue-controls"><button type="button" data-move-action="${index}" data-to-index="${index - 1}" title="Move earlier" ${index === 0 ? "disabled" : ""}>↑</button><button type="button" data-move-action="${index}" data-to-index="${index + 1}" title="Move later" ${index === actions.length - 1 ? "disabled" : ""}>↓</button><button type="button" data-edit-action="${index}" title="Edit queued action">✎</button><button type="button" data-remove-action="${index}" title="Remove queued action">✕</button></span></div>`).join("") + countdown;
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
  const button = event.target.closest("[data-remove-action], [data-edit-action], [data-move-action]");
  if (!button || APP.busy) return;
  try {
    let result;
    if (button.hasAttribute("data-remove-action")) {
      result = await apiPost("/api/actions/remove", { index: Number(button.getAttribute("data-remove-action")) });
    } else if (button.hasAttribute("data-move-action")) {
      result = await apiPost("/api/actions/move", { index: Number(button.getAttribute("data-move-action")), to_index: Number(button.getAttribute("data-to-index")) });
    } else {
      const index = Number(button.getAttribute("data-edit-action"));
      const revised = window.prompt("Edit queued action", APP.state.queued_actions[index]);
      if (revised === null) return;
      result = await apiPost("/api/actions/update", { index, action: revised });
    }
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
let scenePaint = { canvas: null, ctx: null, w: 0, h: 0, lastKey: null };

// Weather is tracked in state and normalized to the small native visual
// vocabulary used by the scene, portrait, and map ambience layers.
function weatherKeyFor(weather) {
  const w = String(weather || "").toLowerCase();
  if (/storm|thunder|typhoon|hurricane/.test(w)) return "storm";
  if (/rain|drizzle|monsoon/.test(w)) return "rain";
  if (/snow|blizzard|sleet/.test(w)) return "snow";
  if (/fog|mist|haze/.test(w)) return "fog";
  return "";
}

const FIRE_SCENES = new Set(["merchant_shop", "tavern_inn", "indoor_grandhall", "dungeon_cave", "monster_lair", "battlefield_dusk"]);
const STAR_SCENES = new Set(["starry_sky", "night_wilderness", "tower_hub"]);
const WIND_SCENES = new Set(["harbor_port", "ship_deck", "forest_path", "mountain_castle", "snow_region"]);

function timeOfDayFor(s) {
  const hour = Number(s?.calendar?.hour);
  if (Number.isFinite(hour)) {
    if (hour < 5 || hour >= 21) return "night";
    if (hour < 8) return "dawn";
    if (hour < 17) return "day";
    if (hour < 20) return "dusk";
    return "night";
  }
  const text = String(s?.world_time || "").toLowerCase();
  if (/night|midnight/.test(text)) return "night";
  if (/dawn|sunrise|morning/.test(text)) return "dawn";
  if (/dusk|sunset|evening/.test(text)) return "dusk";
  return "day";
}

function activityFor(s) {
  if (s?.combat?.active) return "combat";
  const text = [s?.current_activity, ...(s?.queued_actions || []), ...(s?.standing_orders || [])].join(" ").toLowerCase();
  if (/train|practice|study|meditat|spar/.test(text)) return "training";
  if (/travel|sail|walk|fly|journey|depart/.test(text)) return "travel";
  if (/craft|forge|smith|cook|brew/.test(text)) return "crafting";
  if (/talk|meet|negot|ask|diploma/.test(text)) return "social";
  return "idle";
}

function ambientModeFor(category, weather, s) {
  const weatherMode = weatherKeyFor(weather);
  if (weatherMode) return weatherMode;
  if (s?.combat?.active || ["duel", "monster_battlefield", "battlefield_dusk"].includes(category)) return "sparks";
  if (activityFor(s) === "training") return s?.world === "Bleach" ? "spirit" : s?.world === "Naruto" ? "chakra" : "energy";
  if (FIRE_SCENES.has(category)) return "embers";
  if (STAR_SCENES.has(category)) return "stars";
  if (WIND_SCENES.has(category)) return category === "forest_path" ? "leaves" : "wind";
  if (category === "rain_city") return "rain";
  if (category === "underwater") return "bubbles";
  if (s?.world === "One Piece") return "wind";
  if (s?.world === "Hunter x Hunter" || s?.world === "Naruto") return "leaves";
  if (s?.world === "Overgeared") return "embers";
  if (s?.world === "Bleach") return "spirit";
  if (s?.world === "Solo Max-Level Newbie") return "system";
  if (s?.world === "Reincarnated as a Slime") return "magic";
  return "motes";
}

function stableAmbientUnit(seed) {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) { h ^= seed.charCodeAt(i); h = Math.imul(h, 16777619); }
  return (h >>> 0) / 4294967295;
}

function fillAmbientLayer(el, mode, count, key) {
  if (!el) return;
  const renderKey = `${mode}:${count}:${key}`;
  if (el.dataset.renderKey === renderKey) return;
  el.dataset.renderKey = renderKey;
  el.dataset.effect = mode;
  el.replaceChildren(...Array.from({ length: count }, (_, index) => {
    const mote = document.createElement("i");
    const u = (suffix) => stableAmbientUnit(`${key}:${index}:${suffix}`);
    mote.style.setProperty("--x", `${Math.round(u("x") * 100)}%`);
    mote.style.setProperty("--y", `${Math.round(u("y") * 100)}%`);
    mote.style.setProperty("--size", `${(2 + u("s") * 7).toFixed(1)}px`);
    mote.style.setProperty("--delay", `${(-u("d") * 9).toFixed(2)}s`);
    mote.style.setProperty("--duration", `${(4 + u("t") * 8).toFixed(2)}s`);
    mote.style.setProperty("--drift", `${Math.round((u("r") - .5) * 80)}px`);
    return mote;
  }));
}

function applyNativeSceneFx(category, weather, s) {
  const layer = $("#scene-ambient");
  const mode = ambientModeFor(category, weather, s);
  const time = timeOfDayFor(s);
  document.body.setAttribute("data-time", time);
  layer.dataset.time = time;
  layer.dataset.activity = activityFor(s);
  fillAmbientLayer(layer, mode, mode === "rain" || mode === "snow" ? 26 : 18, `${s?.world}:${category}:${mode}`);
}

function applyPortraitAmbient(s) {
  const layer = $("#portrait-ambient");
  if (!layer) return;
  const mode = s?.combat?.active ? "sparks" : s?.world === "Bleach" ? "spirit" : s?.world === "Naruto" ? "chakra" : s?.world === "Solo Max-Level Newbie" ? "system" : s?.world === "Overgeared" ? "embers" : s?.world === "Reincarnated as a Slime" ? "magic" : s?.world === "One Piece" ? "wind" : "motes";
  fillAmbientLayer(layer, mode, 12, `portrait:${s?.world}:${mode}`);
}

function applyNativeMapFx(nodes) {
  const layer = $("#map-ambient");
  if (!layer) return;
  const dangerNodes = (nodes || []).filter((n) => String(n.danger_level || "").toLowerCase() === "critical");
  layer.replaceChildren(...dangerNodes.map((node) => {
    const glow = document.createElement("i");
    glow.className = "map-danger-glow";
    glow.style.left = `${node.x}%`;
    glow.style.top = `${node.y}%`;
    return glow;
  }));
  layer.dataset.dangerCount = String(dangerNodes.length);
}

function playSceneTransition(kind, s) {
  if (!APP.animationsEnabled) return;
  const transition = $("#scene-transition");
  transition.dataset.kind = kind;
  transition.dataset.world = s?.world || "Custom World";
  transition.classList.remove("playing");
  void transition.offsetWidth;
  transition.classList.add("playing");
}

function updateScene(s) {
  const url = s._scene_image;
  const cat = s._scene_category || "starry_sky";
  const sceneLabel = s._scene_label || cat;
  const img = $("#scene-img");
  document.body.setAttribute("data-scene", cat);
  const sceneBadge = $("#scene-category-badge");
  sceneBadge.textContent = sceneLabel.replace(/_/g, " ").toUpperCase();
  const artMatch = s._scene_confidence || {};
  sceneBadge.title = artMatch.score !== undefined
    ? `Art match ${artMatch.score}% · ${artMatch.label || "Environment"}: ${artMatch.reason || s._scene_reason || ""}`
    : (s._scene_reason || "Environment art selected from current location and activity.");
  $("#scene-location").textContent = s.location || "Unknown";
  $("#scene-world").textContent = s.world || "Custom World";

  applyNativeSceneFx(cat, s.weather, s);

  // A location change gets a quick cut-to-black-and-back in the scene box
  // only — deliberately not anywhere else in the UI — so travel reads as a
  // moment instead of the background image just silently swapping.
  if (APP.lastLocation === null) {
    APP.lastLocation = s.location;
  } else if (s.location && s.location !== APP.lastLocation) {
    APP.lastLocation = s.location;
    playSceneTransition("travel", s);
  }
  const combatActive = Boolean(s.combat?.active);
  if (combatActive && !APP.lastCombatActive) playSceneTransition("combat", s);
  APP.lastCombatActive = combatActive;
  const majorVisualKey = String(s.active_canon_event || s.active_major_event || "");
  if (majorVisualKey && majorVisualKey !== APP.lastMajorVisualKey) playSceneTransition("event", s);
  APP.lastMajorVisualKey = majorVisualKey;

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
  paintScene(cat, s.world || "Custom World");
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

function rand(a, b) { return a + Math.random() * (b - a); }


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
  const locked = new Set(["modal-welcome", "modal-difficult-check", "modal-timing-challenge", "modal-tactical-challenge", "modal-major-roll", "modal-lethal", "modal-power-goal", "modal-event-window"]);
  if (e.target === m && !locked.has(m.id)) closeModal(m.id);
}));

// Major/canon events use a short informational notice only. The event's
// actual scene, position-aware prompt, suggested actions and any combat all
// remain in their normal Chronicle/Action Chat panels behind it.
function openEventNotice(result) {
  const isCanon = result.interruption_kind === "canon_event";
  const isDanger = result.interruption_kind === "danger";
  const title = result.major_event_title || result.state?.active_canon_event ||
    (isCanon ? "MAJOR CANON EVENT" : isDanger ? "DANGER" : "MAJOR EVENT");
  playSceneTransition(result.state?.combat?.active ? "combat" : "event", result.state || APP.state);
  $("#event-window-title").textContent = isCanon ? "MAJOR CANON EVENT" : isDanger ? "DANGER" : "MAJOR EVENT";
  $("#event-window-kicker").textContent = result.state?.combat?.active
    ? "COMBAT HAS BEGUN"
    : "THE SIMULATION HAS STOPPED HERE";
  $("#event-window-heading").textContent = title;
  $("#event-window-context").textContent = result.interruption_context || result.interruption_reason ||
    "An important event has reached your character's current place in the story.";
  const banner = $("#event-window-banner");
  const bannerUrl = isCanon ? (result.state?._scene_image || "") : "";
  if (bannerUrl && bannerUrl.includes("/assets/canon_events/")) {
    banner.src = bannerUrl; banner.hidden = false;
  } else {
    banner.removeAttribute("src"); banner.hidden = true;
  }
  openModal("modal-event-window");
}

function closeEventNotice() {
  closeModal("modal-event-window");
  $("#time-unit").value = "moment";
  syncTimeControl("#time-unit", "#time-amount", null, null, "#time-control-help");
  const input = $("#action-input");
  input.placeholder = APP.state?.combat?.active
    ? "Combat is active — use the combat controls, or describe a specific combat action here."
    : "Respond to the event here, add your action, then Advance the next beat.";
  requestAnimationFrame(() => (APP.state?.combat?.active ? $("#btn-combat-attack") : input).focus());
}
$("#btn-event-window-leave").addEventListener("click", closeEventNotice);
$("#btn-event-window-continue").addEventListener("click", closeEventNotice);

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
    appendStoryEntries([{ text: "[ACTION NOT POSSIBLE]\n" + result.reason, tag: "meta" }]);
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
  if (e.actor === "player" && ["buff", "shield", "cleanse", "control", "summon", "movement", "detect", "stealth", "transform", "utility"].includes(e.action)) {
    const label = e.ability && e.ability !== "Attack" ? e.ability : "the technique";
    const costNote = e.resource_cost ? ` (-${e.resource_cost} ${APP.state?.resource_name || "Energy"})` : "";
    if (!e.applied) return { text: `You try ${label}, but it fails to take hold${costNote}.`, cls: "miss" };
    if (e.action === "shield") return { text: `${label} forms a ${e.shield || 0}-point barrier${costNote}.`, cls: "player" };
    if (e.action === "cleanse") return { text: `${label} clears ${e.removed?.length ? e.removed.join(", ") : "harmful effects"}${costNote}.`, cls: "player" };
    if (e.action === "summon") return { text: `${label} calls ${e.summon || "an ally"} into the fight${costNote}.`, cls: "player" };
    if (e.action === "control") return { text: `${label} inflicts ${e.status || "Control"} on ${e.target || "the enemy"}${costNote}.`, cls: "player" };
    return { text: `${label} grants ${e.status || humanLabel(e.action)} for ${e.duration || 1} round${e.duration === 1 ? "" : "s"}${costNote}.`, cls: "player" };
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
    if (e.action === "controlled") return { text: `${e.name || "The enemy"} cannot act while ${e.status || "controlled"}.`, cls: "player" };
    if (e.shrugged) return { text: `You completely shrug off ${e.name || "the enemy"}'s attack${swingNote}.`, cls: "player" };
    const shieldNote = e.absorbed ? ` (${e.absorbed} absorbed by your barrier)` : "";
    return e.success
      ? { text: `${e.name || "The enemy"} hits you for ${e.damage ?? 0} dmg${shieldNote}${e.massive ? " — MASSIVE" : ""}${swingNote}.`, cls: "hit" }
      : { text: `${e.name || "The enemy"}'s attack misses${swingNote}.`, cls: "miss" };
  }
  if (e.actor === "status") return { text: `${e.status || "A lingering effect"} deals ${e.damage || 0} damage to ${e.target === "player" ? "you" : "the enemy"}.`, cls: "hit" };
  return { text: "Something happens.", cls: "" };
}

const COMBAT_EFFECT_ICON = { damage: "⚔ ", heal: "🩹 ", buff: "⬆ ", debuff: "⛓ ", shield: "🛡 ", cleanse: "✦ ", control: "⊘ ", summon: "♟ ", movement: "➜ ", detect: "◉ ", stealth: "◌ ", transform: "◆ ", utility: "◇ " };
function combatAbilityEffectType(s, name) {
  const detail = (s.skills || {})[name];
  const t = String((detail && typeof detail === "object" ? detail.effect_type : "") || "").toLowerCase();
  const valid = ["damage", "heal", "buff", "debuff", "shield", "cleanse", "control", "summon", "movement", "detect", "stealth", "transform", "utility"];
  if (valid.includes(t)) return t;
  const blob = `${name} ${detail?.description || ""} ${detail?.effect || ""}`.toLowerCase();
  if (/heal|restore hp|regenerat/.test(blob)) return "heal";
  if (/shield|barrier|ward/.test(blob)) return "shield";
  if (/stun|bind|paraly|sleep|freeze|bakud/.test(blob)) return "control";
  if (/summon|familiar|construct/.test(blob)) return "summon";
  if (/transform|shikai|bankai|awakening/.test(blob)) return "transform";
  if (/stealth|invisib|conceal/.test(blob)) return "stealth";
  if (/detect|sense|scan/.test(blob)) return "detect";
  if (/dash|teleport|movement|blink/.test(blob)) return "movement";
  if (/buff|empower|enhance/.test(blob)) return "buff";
  if (/debuff|weaken|slow|poison|burn|bleed/.test(blob)) return "debuff";
  return "damage";
}
function combatAbilityUsable(s, name) {
  const detail = (s.skills || {})[name];
  if (!detail || typeof detail !== "object") return false;
  if (detail.combat_usable === false) return false;
  if (detail.combat_usable === true) return true;
  if (["damage", "heal", "buff", "debuff", "shield", "cleanse", "control", "summon", "movement", "detect", "stealth", "transform"].includes(String(detail.effect_type || "").toLowerCase())) return true;
  // Backward-compatible inference for older saves whose skills predate the
  // combat_usable field.  Profession/knowledge fundamentals no longer turn
  // into attacks merely because they have a numeric bonus.
  const blob = `${name} ${detail.description || ""} ${detail.effect || ""}`.toLowerCase();
  if (/navigator|navigation|craft|smith|cooking|merchant|account|research|history|language|fundamentals expected of this role/.test(blob)) return false;
  return /attack|strike|damage|weapon|combat|fight|jutsu|spell|blast|projectile|heal|restore hp|shield|guard|weaken|debuff|stun|bind|poison|haki|nen|chakra/.test(blob);
}
function populateCombatAbilitySelect(s) {
  const combat = s.combat || {};
  const cooldowns = combat.cooldowns || {};
  const abilitySel = $("#combat-ability");
  const skills = Object.keys(s.skills || {}).filter((name) => combatAbilityUsable(s, name));
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
for (const kind of ["buff", "shield", "cleanse", "control", "summon", "movement", "detect", "stealth", "transform", "utility"]) COMBAT_ACTION_ICON[kind] = ICONS.sparkles || ICONS.sword;
const COMBAT_ACTION_LABEL = { damage: "ATTACK", heal: "HEAL", buff: "EMPOWER", debuff: "WEAKEN", shield: "BARRIER", cleanse: "CLEANSE", control: "CONTROL", summon: "SUMMON", movement: "MOVE", detect: "ANALYZE", stealth: "CONCEAL", transform: "TRANSFORM", utility: "USE" };
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
  const actionInput = $("#action-input");
  if (!combat.active) {
    panel.hidden = true;
    actionInput.placeholder = "TYPE AN ACTION HERE\nPress Enter or Add to keep it in this chat until you Advance.";
    return;
  }
  panel.hidden = false;
  actionInput.placeholder = "Combat is active — use the combat controls, or describe a specific combat action here.";
  $("#combat-round").textContent = combat.round ?? 1;
  $("#combat-mode-badge").hidden = !combat.non_lethal;
  // The mercy toggle only means anything for a real, lethal-by-default fight
  // — a spar/test (non_lethal) already floors both sides, so the choice is
  // moot there and the row is hidden rather than shown disabled.
  const mercyRow = $("#combat-mercy-row");
  mercyRow.hidden = !!combat.non_lethal;
  $("#combat-mercy-toggle").checked = !!combat.spare_enemy;
  const e = combat.enemy || {};
  const dead = e.alive === false || Number(e.hp) <= 0;
  const pct = 100 * (Number(e.hp) || 0) / Math.max(1, Number(e.hp_max) || 1);
  const enemyBox = $("#combat-enemy");
  enemyBox.classList.toggle("dead", dead);
  const groupNote = e.is_group ? `<div class="combat-enemy-sub">Fighting as a group${e.group_size ? ` — roughly ${escapeHtml(e.group_size)} strong` : ""}</div>` : "";
  const defeatedLabel = (combat.non_lethal || combat.spare_enemy) ? "SUBDUED" : "DEFEATED";
  enemyBox.innerHTML = `<div class="combat-enemy-head"><b>${escapeHtml(e.name || "Enemy")}</b><span>${dead ? defeatedLabel : `${escapeHtml(e.hp)} / ${escapeHtml(e.hp_max)}`}</span></div>${groupNote}<div class="bar-track"><div class="bar-fill" style="width:${Math.max(0, Math.min(100, pct))}%"></div></div>`;
  const resourceRow = $("#combat-resource-row");
  if (s.resource_max) resourceRow.innerHTML = `<span>${escapeHtml(s.resource_name || "Energy")}</span><b>${escapeHtml(s.resource ?? 0)} / ${escapeHtml(s.resource_max)}</b>`;
  else resourceRow.innerHTML = "";
  const conditionRows = [
    Number(combat.player_shield || 0) > 0 ? { name: `Barrier ${combat.player_shield}`, rounds_left: null } : null,
    ...(combat.player_buffs || []), ...(combat.player_statuses || []), ...(combat.summons || []),
  ].filter(Boolean);
  $("#combat-status-row").innerHTML = conditionRows.map((row) => `<span title="${row.rounds_left ? `${escapeHtml(row.rounds_left)} round${Number(row.rounds_left) === 1 ? "" : "s"} remaining` : "Absorbs incoming damage"}">${escapeHtml(row.name || "Active effect")}${row.rounds_left ? ` · ${escapeHtml(row.rounds_left)}` : ""}</span>`).join("");
  const enemyConditions = [...(combat.enemy_debuffs || []), ...(combat.enemy_statuses || [])];
  if (enemyConditions.length) enemyBox.insertAdjacentHTML("beforeend", `<div class="combat-condition-strip">${enemyConditions.map((row) => `<span>${escapeHtml(row.name || "Affected")} · ${escapeHtml(row.rounds_left || 1)}</span>`).join("")}</div>`);
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
  // Mirror the same lines into the Chronicle, styled like a dice check, so
  // combat rounds remain visible in the same log as every other story beat.
  const chronicleLines = (entries || []).map((e) => combatLogLine(e).text).join("\n");
  if (chronicleLines) {
    const entry = { text: "[COMBAT]\n" + chronicleLines, tag: "roll" };
    appendStoryEntries([entry]);
  }
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
$("#combat-mercy-toggle").addEventListener("change", async (e) => {
  const spare = e.target.checked;
  try {
    const result = await apiPost("/api/combat/mercy", { spare });
    if (APP.state) APP.state.combat = result.combat;
    showToast(spare ? "You'll spare this enemy if you win — losing is still real." : "Mercy toggle off — winning this fight plays out at full stakes.", "system");
  } catch (err) { e.target.checked = !spare; showToast(err.message, "danger"); }
});

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
  appendStoryEntries([{ text: "[ACTION REVERTED]\nYou stop before committing to the lethal decision.", tag: "meta" }]);
  APP.pendingLethal = null;
});

$("#btn-power-goal-confirm").addEventListener("click", async () => {
  closeModal("modal-power-goal");
  const pending = APP.pendingPowerGoal;
  if (!pending) return;
  setBusy(true);
  try {
    const payload = { ...pending, confirmed_power_goal: true };
    const result = await apiPost("/api/time/resolve", payload);
    await processTimeSkipResolution(result, payload);
  } catch (e) { showToast(e.message, "danger"); playSfx("error"); }
  finally { setBusy(false); APP.pendingPowerGoal = null; runBackgroundCheck(); }
});
$("#btn-power-goal-cancel").addEventListener("click", () => {
  closeModal("modal-power-goal");
  APP.pendingPowerGoal = null;
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

function removeOpeningSetupNotice() {
  $("#story-feed .story-entry").forEach((row) => {
    if (row.textContent.includes("AI SETUP REQUIRED")) row.remove();
  });
  $("#story-feed .story-beat").forEach((beat) => {
    if (!beat.querySelector(".story-entry, .story-beat-system")) beat.remove();
  });
}

$("#btn-retry-opening").addEventListener("click", async () => {
  if (!APP.campaignActive) { openModal("modal-campaign"); return; }
  setBusy(true);
  try {
    const result = await apiPost("/api/campaign/opening", {});
    removeOpeningSetupNotice();
    appendStoryEntries(result.story);
    renderState(result.state);
  } catch (e) {
    showToast(e.message, "danger");
    removeOpeningSetupNotice();
    appendStoryEntries([{ text: "[AI SETUP REQUIRED]\n" + e.message, tag: "danger" }]);
  }
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
  if (unitSelector === "#time-unit" && APP.state) renderQueuedActions(APP.state.queued_actions || []);
  if (unitSelector === "#time-unit") updateSelectedTimeLabel();
}

function updateSelectedTimeLabel() {
  const label = $("#time-mode-label");
  const unitEl = $("#time-unit");
  const amountEl = $("#time-amount");
  if (!label || !unitEl) return;
  const unit = unitEl.value || "moment";
  if (unit === "moment") label.textContent = "Selected skip: next story beat";
  else if (unit === "next_event") label.textContent = "Selected skip: next major event";
  else {
    const amount = Number(amountEl?.value || 1);
    const shownUnit = amount === 1 ? unit.replace(/s$/, "") : unit;
    label.textContent = `Selected skip: ${amount} ${shownUnit}`;
  }
}

$("#time-unit").addEventListener("change", () => syncTimeControl("#time-unit", "#time-amount", null, null, "#time-control-help"));
$("#time-amount").addEventListener("input", () => { renderQueuedActions(APP.state?.queued_actions || []); updateSelectedTimeLabel(); });
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
    const lethal = ["high", "extreme"].includes(String(check.risk || "").toLowerCase());
    const riskText = lethal ? `${String(check.risk).toUpperCase()} — FAILURE MAY BE FATAL` : `${check.risk || "none"} risk`;
    return `<article class="difficult-check-row"><header><b>${escapeHtml(check.action || check.reason)}</b><span>${escapeHtml(riskText)}</span></header><div><strong>Needed total ${escapeHtml(range[0])}–${escapeHtml(range[1])}</strong><span>Expected raw roll: about ${escapeHtml(check.expected_raw_needed)}/100 (~${escapeHtml(check.odds_percent ?? "?")}% odds)</span><span>${escapeHtml(check.ability)}${check.skill ? ` · ${escapeHtml(check.skill)}` : ""} · total bonus ${bonus >= 0 ? "+" : ""}${escapeHtml(bonus)}</span>${breakdown ? `<span class="difficult-check-breakdown">${escapeHtml(breakdown)}</span>` : ""}</div></article>`;
  }).join("");
}

function acceptedDifficultyPayload(pending) {
  const lethal = (pending?.checks || []).some((check) => ["high", "extreme"].includes(String(check.risk || "").toLowerCase()));
  return {
    ...pending.payload,
    danger_warning_acknowledged: true,
    confirmed_lethal: Boolean(pending.payload.confirmed_lethal || lethal),
  };
}

$("#btn-difficult-roll").addEventListener("click", async () => {
  const pending = APP.pendingDifficulty;
  if (!pending) return;
  closeModal("modal-difficult-check");
  APP.pendingDifficulty = null;
  await resolveAssessedTimeSkip(acceptedDifficultyPayload(pending));
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

// Each stage is a risk-tolerance choice, not a specific action — the check
// title above these options already names the actual action (a jutsu, a
// negotiation, a lockpick, whatever it is), so the options themselves stay
// domain-neutral instead of forcing combat phrasing ("technique", "feint")
// onto checks that aren't a fight at all, which used to read as a total
// non sequitur against a social or stealth check.
const TACTICAL_SCENES = {
  archive: [
    { title: "Approach the archive", help: "Choose a believable way inside.", options: [
      { label: "Wear a clerk's disguise", detail: "Blend into the shift change and carry forged work orders.", points: 23, volatility: 7 },
      { label: "Enter across the rooftops", detail: "Avoid the doors and reach an upper records window.", points: 27, volatility: 16 },
      { label: "Bribe a records clerk", detail: "Trade coin or leverage for a quiet route through security.", points: 21, volatility: 9 },
    ]},
    { title: "Pass the inner watch", help: "The guarded stacks require a second decision.", options: [
      { label: "Follow the filing carts", detail: "Use routine traffic as moving cover.", points: 21, volatility: 6 },
      { label: "Create a false summons", detail: "Pull the watch away with a convincing emergency.", points: 25, volatility: 13 },
      { label: "Question a junior clerk", detail: "Risk conversation to learn the exact shelf and patrol gap.", points: 23, volatility: 10 },
    ]},
    { title: "Secure the record", help: "Take the objective without losing the escape route.", options: [
      { label: "Copy only the key page", detail: "Leave the archive intact and minimize evidence.", points: 20, volatility: 4 },
      { label: "Swap in a forged file", detail: "Hide the theft, but the replacement must survive inspection.", points: 26, volatility: 14 },
      { label: "Take the whole dossier", detail: "Gain everything now and outrun the alarm it may cause.", points: 30, volatility: 22 },
    ]},
  ],
  duel: [
    { title: "Take the initiative", help: "Choose how to shape the opening exchange.", options: [
      { label: "Apply measured pressure", detail: "Probe the opponent while protecting your guard.", points: 22, volatility: 6 },
      { label: "Invite the counterattack", detail: "Offer an opening and punish the committed response.", points: 26, volatility: 14 },
      { label: "Claim the terrain", detail: "Move the duel toward ground that favors your reach or abilities.", points: 24, volatility: 10 },
    ]},
    { title: "Read the adjustment", help: "Your opponent changes rhythm after the opening.", options: [
      { label: "Break their tempo", detail: "Interrupt combinations before they develop.", points: 23, volatility: 8 },
      { label: "Conserve for a reversal", detail: "Yield space now to preserve the stronger finish.", points: 20, volatility: 4 },
      { label: "Attack the exposed weakness", detail: "Commit immediately to the flaw you noticed.", points: 29, volatility: 19 },
    ]},
    { title: "Decide the clash", help: "Choose how to turn your advantage into an outcome.", options: [
      { label: "Force a clean surrender", detail: "Control the finish and limit needless harm.", points: 22, volatility: 6 },
      { label: "Land the decisive counter", detail: "Trust your read and end it in one exchange.", points: 27, volatility: 15 },
      { label: "Risk your strongest technique", detail: "Stake everything on overwhelming the opponent.", points: 32, volatility: 24 },
    ]},
  ],
  dungeon: [
    { title: "Read the passage", help: "Choose how to enter hostile ground.", options: [
      { label: "Scout every sign", detail: "Study tracks, airflow, seams, and recent disturbances.", points: 22, volatility: 5 },
      { label: "Disarm the obvious traps", detail: "Make a controlled lane before the party commits.", points: 25, volatility: 11 },
      { label: "Force a fast passage", detail: "Rely on speed and toughness before the dungeon reacts.", points: 29, volatility: 20 },
    ]},
    { title: "Cross the hazard", help: "The route closes around a new obstacle.", options: [
      { label: "Test a hidden route", detail: "Search for a builder's access or creature trail.", points: 24, volatility: 10 },
      { label: "Use tools and wards", detail: "Spend prepared resources to neutralize the danger.", points: 22, volatility: 5 },
      { label: "Trigger it on your terms", detail: "Control where and when the hazard releases.", points: 28, volatility: 18 },
    ]},
    { title: "Reach the objective", help: "The final chamber can still turn success into disaster.", options: [
      { label: "Secure an escape first", detail: "Protect the retreat before touching the objective.", points: 21, volatility: 4 },
      { label: "Separate prize from trap", detail: "Work carefully against the chamber's mechanism.", points: 26, volatility: 12 },
      { label: "Seize it before opposition arrives", detail: "Trade certainty for a decisive finish.", points: 31, volatility: 23 },
    ]},
  ],
  social: [
    { title: "Open the conversation", help: "Choose what gives your words weight.", options: [
      { label: "Appeal to shared interests", detail: "Show how cooperation serves both sides.", points: 23, volatility: 6 },
      { label: "Offer verifiable proof", detail: "Anchor your claim in facts the other side can test.", points: 25, volatility: 9 },
      { label: "Apply quiet leverage", detail: "Reveal what refusal may cost without making an open threat.", points: 28, volatility: 18 },
    ]},
    { title: "Answer resistance", help: "The other party exposes their real concern.", options: [
      { label: "Address the fear directly", detail: "Name the risk and offer a safeguard.", points: 24, volatility: 8 },
      { label: "Trade a limited concession", detail: "Give something useful without surrendering the goal.", points: 22, volatility: 5 },
      { label: "Call the bluff", detail: "Challenge whether they can afford to walk away.", points: 29, volatility: 19 },
    ]},
    { title: "Close the agreement", help: "Turn momentum into a clear commitment.", options: [
      { label: "Define the next concrete step", detail: "Secure a modest promise that is hard to misunderstand.", points: 22, volatility: 4 },
      { label: "Bind it with witnesses", detail: "Make the agreement costly to deny later.", points: 26, volatility: 12 },
      { label: "Demand the full commitment", detail: "Press for everything while your advantage lasts.", points: 31, volatility: 23 },
    ]},
  ],
  craft: [
    { title: "Prepare the work", help: "Choose how to handle the material's greatest uncertainty.", options: [
      { label: "Test a small sample", detail: "Learn its tolerances before risking the whole piece.", points: 22, volatility: 4 },
      { label: "Adapt a proven design", detail: "Modify reliable methods for this unusual commission.", points: 25, volatility: 10 },
      { label: "Attempt a breakthrough design", detail: "Pursue a much stronger result with little margin for error.", points: 30, volatility: 21 },
    ]},
    { title: "Control the critical step", help: "The work reaches the point where flaws become permanent.", options: [
      { label: "Slow the process", detail: "Protect stability at the cost of time and output.", points: 21, volatility: 4 },
      { label: "Correct the forming flaw", detail: "Intervene precisely before the weakness spreads.", points: 26, volatility: 13 },
      { label: "Use rare material now", detail: "Spend a valuable reserve to force a better result.", points: 29, volatility: 17 },
    ]},
    { title: "Finish and prove it", help: "Choose what standard the completed work must survive.", options: [
      { label: "Tune for reliability", detail: "Favor a dependable creation over peak performance.", points: 22, volatility: 5 },
      { label: "Field-test every function", detail: "Expose weaknesses now and repair what fails.", points: 26, volatility: 12 },
      { label: "Push beyond the safe limit", detail: "Try to awaken the work's exceptional potential.", points: 32, volatility: 24 },
    ]},
  ],
};

function tacticalStagesFor(check) {
  const action = String(check?.action || check?.reason || "").toLowerCase();
  if (/archive|records?|infiltrat|break in|steal|heist|guarded file/.test(action)) return TACTICAL_SCENES.archive;
  if (/duel|fight|battle|attack|combat|opponent|enemy|guardian/.test(action)) return TACTICAL_SCENES.duel;
  if (/dungeon|cave|ruin|trap|passage|tomb|labyrinth/.test(action)) return TACTICAL_SCENES.dungeon;
  if (/persuad|convince|negot|meeting|bargain|ask|recruit|diplom/.test(action)) return TACTICAL_SCENES.social;
  if (/craft|forge|smith|repair|build|enchant|brew|sew/.test(action)) return TACTICAL_SCENES.craft;
  return TACTICAL_SCENES.dungeon;
}
function startChallenge(mode) {
  const pending = APP.pendingDifficulty;
  if (!pending) return;
  const resolutionMode = $$('input[name="challenge-resolution"]:checked')[0]?.value === "continue" ? "continue" : "stop";
  closeModal("modal-difficult-check");
  APP.challenge = { mode, resolutionMode, payload: acceptedDifficultyPayload(pending), checks: pending.checks, index: 0, scores: {}, modes: {}, attempts: [], stage: 0, tacticalPoints: 10 };
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
  const payload = { ...challenge.payload, manual_rolls: { ...(challenge.payload.manual_rolls || {}), ...challenge.scores }, challenge_modes: challenge.modes, challenge_resolution_mode: challenge.resolutionMode };
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
  const challenge = APP.challenge, stage = tacticalStagesFor(currentChallengeCheck())[challenge.stage];
  $("#tactical-stage-title").textContent = stage.title;
  $("#tactical-stage-help").textContent = stage.help;
  $("#tactical-progress").textContent = `Approach score so far: ${challenge.tacticalPoints}`;
  $("#tactical-options").innerHTML = stage.options.map((option, index) => `<button type="button" data-tactical-option="${index}"><b>${escapeHtml(option.label)}</b><span>${escapeHtml(option.detail)}</span><small>Base +${option.points} · uncertainty ±${option.volatility}</small></button>`).join("");
}

$("#tactical-options").addEventListener("click", (event) => {
  const button = event.target.closest("[data-tactical-option]");
  const challenge = APP.challenge;
  if (!button || !challenge || challenge.mode !== "tactical") return;
  const stages = tacticalStagesFor(currentChallengeCheck());
  const option = stages[challenge.stage].options[Number(button.getAttribute("data-tactical-option"))];
  const random = new Uint32Array(1); crypto.getRandomValues(random);
  const swing = (random[0] % (option.volatility * 2 + 1)) - option.volatility;
  challenge.tacticalPoints += option.points + swing;
  challenge.stage += 1;
  if (challenge.stage >= stages.length) finishChallengeCheck(challenge.tacticalPoints);
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
  if (result.status === "power_goal_confirm_required") {
    APP.pendingPowerGoal = payload;
    $("#power-goal-warning").textContent = result.warning || "This path may lead somewhere far beyond where you are now.";
    openModal("modal-power-goal");
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
  // A resolved skip always returns the backend to moment mode. Mirror that
  // locally so the selector and World Systems label never disagree.
  $("#time-unit").value = "moment";
  syncTimeControl("#time-unit", "#time-amount", null, null, "#time-control-help");
  handleNotifications(result.notifications);
  // The Advance button lives below Action Chat in its own scrolling column.
  // After a turn, return that column to the composer so the player's next
  // input is visible instead of leaving the view parked on Time Control.
  requestAnimationFrame(() => {
    const rightColumn = document.querySelector(".col-right");
    if (rightColumn) rightColumn.scrollTop = 0;
  });
  if (result.died) {
    // A time skip can end in death too (an extreme roll, the Tower's floor
    // countdown) — same death/rewind modal every other death path already
    // uses, just reached from a different resolution pipeline.
    playSfx("danger"); shakeApp();
    openModal("modal-death");
  }
  if (result.major_event_reached) {
    showToast(`Major event reached: ${result.major_event_title || "campaign turning point"}.`, "world");
  }
  const eventStop = ["canon_event", "world_event"].includes(result.interruption_kind);
  const freshDangerStop = result.interruption_kind === "danger" && result.danger_notice_required !== false;
  if (result.interrupted && (eventStop || freshDangerStop)) {
    openEventNotice(result);
  } else if (result.interrupted && result.interruption_reason) {
    showToast(result.interruption_reason, result.interruption_kind === "goal_complete" ? "notify" : "system");
  }
}

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
// Power Summary — an instant, no-AI-call read of the character's current
// standing: an estimated tier (mirrors worlds.py's POWER_TIERS, the same
// ladder the Advisor anchors its own power comparisons to, so the two never
// contradict each other), key stats, and titles. Deliberately does NOT
// fabricate a comparison against named rivals — Worldwalker has no tracked
// per-NPC power data to draw that from honestly, so that judgment call is
// handed off to the Advisor instead, which has real campaign context.
// ---------------------------------------------------------------------------
const POWER_TIERS = [
  [0, "Mundane", "An ordinary person with no combat training."],
  [1, "Trained", "A capable fighter or specialist."],
  [2, "Skilled", "A seasoned professional."],
  [3, "Elite", "Among the best in a city or region."],
  [4, "Exceptional", "A nationally recognized talent."],
  [5, "Powerhouse", "Capable of single-handedly turning a battle."],
  [6, "Superhuman", "Clearly beyond ordinary human limits."],
  [7, "Legendary", "A living legend."],
  [8, "World-Class", "Among the strongest beings in the setting."],
  [9, "Cataclysmic", "Can reshape a region or end a war single-handedly."],
  [10, "Reality-Bending", "Power that strains or breaks the setting's normal rules entirely."],
];
const POWER_TIER_THRESHOLDS = [20, 35, 50, 65, 90, 130, 200, 350, 600, 1000];

function powerTierFromScore(score) {
  const numeric = Math.max(0, Number(score) || 0);
  let index = 0;
  for (const threshold of POWER_TIER_THRESHOLDS) { if (numeric >= threshold) index++; else break; }
  const [, name, description] = POWER_TIERS[index];
  return { index, name, description, score: numeric };
}

function estimatePowerTier(stats) {
  const values = Object.values(stats || {}).map(Number).filter((n) => Number.isFinite(n));
  const score = values.length ? values.length / values.reduce((total, value) => total + (1 / Math.max(1, value)), 0) : 0;
  return powerTierFromScore(score);
}

function openPowerSummary() {
  const s = APP.state || {};
  const profile = s._power_profile || {};
  const tier = profile.combat || estimatePowerTier(s.stats);
  const overall = profile.overall || estimatePowerTier(s.stats);
  const peak = profile.peak || {};
  const axes = profile.axes || {};
  const maxStat = Math.max(1, ...Object.values(s.stats || {}).map(Number).filter(Number.isFinite));
  const statRows = Object.entries(s.stats || {})
    .sort((a, b) => Number(b[1]) - Number(a[1]))
    .map(([name, value]) => {
      const pct = Math.max(2, Math.min(100, (Number(value) || 0) / maxStat * 100));
      return `<div class="power-stat-row"><i class="a-icon">${abilityIcon(name)}</i><span>${escapeHtml(name)}</span>
        <div class="clock-track"><i style="width:${pct}%"></i></div><b>${escapeHtml(value)}</b></div>`;
    }).join("") || '<div class="hint">No stats recorded yet.</div>';
  const titles = (s.titles || []).map((t) => `<span class="power-title-chip">🏅 ${escapeHtml(titleLabel(t))}</span>`).join("");
  const classCard = s.world !== "Bleach" && s.class_profile?.name ? renderClassCard(s.class_profile) : "";
  const releaseCards = s.world === "Bleach" ? renderBleachReleases(s.special || {}) : "";
  $("#power-summary-body").innerHTML = `
    <div class="power-summary-head">
      <div><b>${escapeHtml(s.name || "Traveler")}</b><span>${escapeHtml(s.world || "")}${s.position ? ` · ${escapeHtml(s.position)}` : ""}</span></div>
    </div>
    <div class="power-tier-card">
      <div class="power-tier-badge">Balanced Combat · Tier ${escapeHtml(tier.index)} · ${escapeHtml(tier.name)}</div>
      <p>${escapeHtml(tier.description)}</p>
      <div class="power-axis-grid">
        <span><b>Peak</b>${escapeHtml(peak.stat || "—")} ${escapeHtml(peak.value ?? "—")}</span>
        <span><b>Offense</b>${escapeHtml(axes.offense?.stat || "—")} ${escapeHtml(axes.offense?.value ?? "—")}</span>
        <span><b>Speed</b>${escapeHtml(axes.speed?.stat || "—")} ${escapeHtml(axes.speed?.value ?? "—")}</span>
        <span><b>Defense</b>${escapeHtml(axes.defense?.stat || "—")} ${escapeHtml(axes.defense?.value ?? "—")}</span>
      </div>
      <small>Overall foundation: Tier ${escapeHtml(overall.index)} · ${escapeHtml(overall.name)} (balanced score ${escapeHtml(overall.score ?? "—")}). Peak output is not treated as every stat. ${escapeHtml(profile.interpretation || "")}</small>
    </div>
    <div class="power-stat-list">${statRows}</div>
    ${releaseCards}
    ${classCard}
    ${titles ? `<div class="power-title-list">${titles}</div>` : ""}
    <button id="btn-power-summary-ask-advisor" class="btn-ghost full">⚖ Ask the Advisor how you compare</button>
  `;
  $("#btn-power-summary-ask-advisor").addEventListener("click", () => {
    closeModal("modal-power-summary");
    closeModal("modal-journal");
    openModal("modal-advisor");
    askAdvisor("How strong am I compared to the threats and rivals around me right now?");
  });
  openModal("modal-power-summary");
}

// ---------------------------------------------------------------------------
// Advisor — Pax Historia-style meta guide: power levels, world state, advice.
// Out-of-character, no turn cost, no state changes. Responses are structured
// (summary + bullet points + suggested follow-ups) rather than a text blob.
// ---------------------------------------------------------------------------
function renderAdvisorChart(chart) {
  if (!chart || !chart.items || !chart.items.length) return "";
  const max = Math.max(...chart.items.map((it) => Math.abs(it.value)), 1e-9);
  const rows = chart.items.map((it) => {
    const pct = Math.max(2, Math.abs(it.value) / max * 100);
    const valueLabel = Number.isFinite(it.value) ? (Math.abs(it.value) >= 1000 ? it.value.toLocaleString() : String(it.value)) : "";
    return `<div class="advisor-chart-row">
      <div class="advisor-chart-label">${escapeHtml(it.label)}</div>
      <div class="advisor-chart-track"><div class="advisor-chart-bar" style="width:${pct}%"></div></div>
      <div class="advisor-chart-value">${escapeHtml(valueLabel)}</div>
    </div>`;
  }).join("");
  return `<div class="advisor-chart">
    <div class="advisor-chart-title">${escapeHtml(chart.title || "Comparison")}${chart.unit ? ` <span>(${escapeHtml(chart.unit)})</span>` : ""}</div>
    ${rows}
  </div>`;
}

function renderAdvisorMessage(m) {
  if (m.role === "player") {
    return `<div class="chat-msg outgoing"><div class="meta">You</div>${escapeHtml(m.text)}</div>`;
  }
  const points = (m.points || []).map((p) => `<li>${escapeHtml(p)}</li>`).join("");
  const countdown = m.canon_countdown?.label ? `<div class="advisor-countdown">⏳ ${escapeHtml(m.canon_countdown.label)}</div>` : "";
  return `<div class="chat-msg incoming advisor-msg"><div class="meta">Advisor${m.fourth_wall ? " · FOURTH-WALL" : ""}</div>
    <div class="advisor-msg-summary">${escapeHtml(m.summary || m.text || "...")}</div>
    ${renderAdvisorChart(m.chart)}
    ${countdown}${points ? `<ul class="advisor-msg-points">${points}</ul>` : ""}
  </div>`;
}

function renderAdvisorThread(thread) {
  const list = thread || [];
  const box = $("#advisor-messages");
  box.innerHTML = list.map(renderAdvisorMessage).join("") || '<p class="hint">No questions asked yet — try one of the prompts above.</p>';
  // Open on the beginning of the newest answer, not the bottom half of a
  // long briefing. On phones the old bottom-scroll made a briefing appear
  // to begin at point two or three with its summary off-screen.
  requestAnimationFrame(() => {
    const latest = box.querySelector(".advisor-msg:last-of-type") || box.lastElementChild;
    box.scrollTop = latest ? Math.max(0, latest.offsetTop - box.offsetTop - 6) : 0;
  });
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
    const playerSummary = s._uses_xp ? `Level ${s.level ?? 1} · ${worldIdentityLabel(s)}` : worldIdentityLabel(s);
    panel.innerHTML = comp.length ? comp.map((c) => `<div class="jrow"><b>${escapeHtml(c.name || "Companion")}</b><br/>${escapeHtml(c.notes || c.role || "")}</div>`).join("") : `<div class="jrow">No companions have joined you yet.</div>` + `<div class="jrow"><b>${escapeHtml(s.name || "Traveler")}</b> — ${escapeHtml(playerSummary)}</div>`;
  } else if (tab === "search") {
    panel.innerHTML = `<div class="system-summary"><b>SEARCH YOUR CAMPAIGN</b><span>Find old actions, people, quests, skills, chapters, facts, and player corrections without scrolling through the entire Chronicle.</span></div><form id="campaign-search-form" class="campaign-search-form"><input id="campaign-search-query" type="search" minlength="2" placeholder="Try a name, place, ability, promise, or event" required><button class="btn-primary" type="submit">SEARCH</button></form><div id="campaign-search-results" class="campaign-search-results"><div class="jrow hint">Enter at least two characters to search locally. This makes no AI call.</div></div>`;
    setTimeout(() => $("#campaign-search-query")?.focus(), 0);
  } else if (tab === "corrections") {
    const corrections = [...(data.simulation?.integrity?.corrections || [])].reverse();
    const currencyCorrection = data.tracks_currency === false ? "" : `<option value="currency">Currency amount</option>`;
    panel.innerHTML = `<div class="system-summary"><b>CORRECT THE GM</b><span>Your correction becomes an authoritative campaign fact, repairs the selected state immediately, and is included in future GM context. This makes no AI call and does not advance time.</span></div><form id="gm-correction-form" class="gm-correction-form"><label>What needs correcting<select id="correction-type"><option value="fact">Story fact</option><option value="location">Current location</option><option value="inventory_add">Missing inventory item</option><option value="inventory_remove">Item you no longer own</option>${currencyCorrection}<option value="hp">Current health</option><option value="resource">Current energy pool</option><option value="quest_status">Quest status</option><option value="skill">Skill description</option></select></label><label>Target or name<input id="correction-target" type="text" placeholder="Sword, quest name, skill name, character…"></label><label>Correct value<textarea id="correction-value" rows="3" placeholder="Write the correct fact or value" required></textarea></label><label>Why, if useful<textarea id="correction-explanation" rows="2" placeholder="Optional context that helps the GM preserve this correction"></textarea></label><button class="btn-primary" type="submit">APPLY CORRECTION</button></form><h3>Correction history</h3>${corrections.length ? corrections.map((row) => `<article class="correction-card"><header><b>${escapeHtml(row.target || humanLabel(row.type))}</b><span>Turn ${escapeHtml(row.turn ?? 0)}</span></header><p>${escapeHtml(row.fact)}</p>${row.explanation ? `<small>${escapeHtml(row.explanation)}</small>` : ""}</article>`).join("") : '<div class="jrow hint">No player corrections have been needed.</div>'}`;
  } else if (tab === "simulation") {
    const integrity = data.simulation?.integrity || {}, reports = [...(integrity.recent_validation || [])].reverse();
    const schedules = Object.entries(integrity.npc_schedules || {}), packets = [...(integrity.information_packets || [])].reverse();
    const canon = integrity.canon_dependencies || { counts: {}, events: [] };
    const direction = data.simulation?.campaign_direction || {}, approaching = direction.approaching_canon_event || {};
    panel.innerHTML = `<div class="system-summary"><b>CAMPAIGN DIRECTOR</b><span>Keeps goals, pressures, and opportunities coherent locally without another AI call.</span></div><div class="director-grid"><div><b>Current goal</b><span>${escapeHtml(direction.primary_goal || "Choose a goal")}</span></div><div><b>Next obstacle</b><span>${escapeHtml(direction.next_obstacle || "None confirmed")}</span></div><div><b>Approaching event</b><span>${escapeHtml(approaching.title ? `${approaching.title} · ${approaching.days_until} days` : "No dated event loaded")}</span></div><div><b>Unresolved people</b><span>${escapeHtml((direction.unresolved_characters || []).map((x) => x.name).join(", ") || "None")}</span></div></div><div class="system-summary"><b>LOCAL SIMULATION SAFETY</b><span>These checks run on your computer after the GM writes a turn. They do not make another AI call.</span></div><div class="integrity-stats"><span><b>${escapeHtml(integrity.travel?.nodes || 0)}</b> mapped places</span><span><b>${escapeHtml(integrity.travel?.connections || 0)}</b> travel routes</span><span><b>${escapeHtml((integrity.active_goals || []).length)}</b> active stop goals</span><span><b>${escapeHtml(schedules.length)}</b> NPC schedules</span></div><h3>Recent turn checks</h3>${reports.length ? reports.map((row) => `<details class="integrity-report ${escapeHtml(row.status || "passed")}"><summary><b>Turn ${escapeHtml(row.turn)} · ${escapeHtml(row.status || "passed")}</b><span>${escapeHtml(row.actions_checked || 0)} actions · ${escapeHtml(row.rolls_checked || 0)} rolls</span></summary>${(row.repairs || []).length ? `<p><b>Repaired locally</b></p><ul>${row.repairs.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul>` : ""}${(row.warnings || []).length ? `<p><b>Warnings</b></p><ul>${row.warnings.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul>` : '<p>No mismatch was found.</p>'}</details>`).join("") : '<div class="jrow hint">Resolve a turn to create the first integrity report.</div>'}<h3>Active action goals</h3>${(integrity.active_goals || []).length ? integrity.active_goals.map((row) => `<div class="jrow"><b>${escapeHtml(row.kind || "goal")}</b><br>${escapeHtml(row.condition || row.action)}</div>`).join("") : '<div class="jrow hint">No “until/master/find/reach” goal is currently active.</div>'}<h3>NPC commitments</h3>${schedules.length ? schedules.map(([name,row]) => `<article class="schedule-card"><header><b>${escapeHtml(name)}</b><span>${escapeHtml(row.status || "planned")}</span></header><p>${escapeHtml(row.goal || "Private commitment")}</p><small>${escapeHtml(row.location || "Unknown")} · due around Canon Day ${escapeHtml(row.due_day ?? "?")}</small></article>`).join("") : '<div class="jrow hint">Schedules appear when recurring NPCs establish a real goal.</div>'}<h3>Information in motion</h3>${packets.length ? packets.slice(0,20).map((row) => `<div class="jrow"><b>${escapeHtml(row.fact)}</b><br><small>${escapeHtml(row.channel || "unknown route")} · ${escapeHtml(row.confidence || 0)}% confidence · recipients: ${escapeHtml((row.recipients || []).join(", ") || "none")}${Number(row.available_after_minutes || 0) > 0 ? ` · arrives in ${escapeHtml(row.available_after_minutes)} minutes` : " · delivered"}</small></div>`).join("") : '<div class="jrow hint">No structured news packet has moved yet.</div>'}<h3>Canon dependency health</h3><div class="jrow">${Object.entries(canon.counts || {}).filter(([,v]) => v).map(([k,v]) => `<b>${escapeHtml(v)} ${escapeHtml(k)}</b>`).join(" · ") || "No fixed canon dependencies."}</div>`;
  } else if (tab === "quests") {
    const active = data.quests || [];
    const qp = data.quest_presentation || questPresentation(data.world);
    const line = (label, value) => value ? `<div class="quest-brief-line"><b>${escapeHtml(label)}</b><span>${escapeHtml(value)}</span></div>` : "";
    const list = (label, values, emptyText = "") => values.length ? `<div class="quest-detail-label">${escapeHtml(label)}</div><ul>${values.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul>` : (emptyText ? `<div class="quest-detail-label">${escapeHtml(label)}</div><p>${escapeHtml(emptyText)}</p>` : "");
    const archive = `<h3>${escapeHtml(qp.archive_label)}</h3>${(data.quest_archive || []).length ? data.quest_archive.map((q, i) => { const v = questView(q, i); return `<div class="jrow"><b>${escapeHtml(v.name)}</b> — ${escapeHtml(v.status)}<br>${escapeHtml(v.explanation)}</div>`; }).join("") : '<div class="jrow hint">Nothing has moved into campaign history yet.</div>'}`;
    if (qp.literal) {
      panel.innerHTML = (active.length ? active.map((raw, index) => {
      const q = questView(raw, index);
      const knowledge = q.knowledge.length ? `<div class="quest-detail-label">Discovered clues</div><ul>${q.knowledge.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul>` : `<div class="quest-detail-label">Discovered clues</div><p>Nothing beyond the quest briefing is known yet.</p>`;
      const objectives = q.objectives.length ? `<div class="quest-detail-label">Tracked objectives</div><div class="objective-list">${q.objectives.map((obj) => `<div class="objective-row ${escapeHtml(obj.status || "active")}"><span>${obj.status === "complete" ? "✓" : obj.status === "failed" ? "✕" : obj.status === "locked" ? "◇" : "○"}</span><div><b>${escapeHtml(obj.text || obj.name || "Objective")}</b><small>${escapeHtml(obj.status || "active")}${obj.optional ? " · optional" : ""} · ${escapeHtml(obj.progress || 0)}%</small></div></div>`).join("")}</div>` : (q.conditions.length ? `<div class="quest-detail-label">Clear conditions / objectives</div><ul>${q.conditions.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul>` : `<div class="quest-detail-label">Clear conditions</div><p>Not yet known. Discover more information or advance the quest.</p>`);
      const branches = [...textList(q.branchState.available), ...textList(q.branchState.locked).map((x) => `${x} (locked)` )];
      const branchInfo = q.branchState.current || branches.length ? `<div class="quest-detail-label">Current route</div><p>${escapeHtml(q.branchState.current || "main")}</p>${list("Known branches", branches)}` : "";
      return `<details class="quest-card"${index === 0 ? " open" : ""}><summary>${escapeHtml(q.name)} <small>— ${escapeHtml(q.status)} · ${escapeHtml(q.progress)}%</small></summary><div class="quest-details"><p class="quest-summary">${escapeHtml(q.explanation)}</p><div class="quest-progress"><i style="width:${Math.max(0, Math.min(100, q.progress))}%"></i></div><div class="quest-brief-grid">${line("Giver / cause", q.giver)}${line("Suggested next lead", q.firstStep)}${line("Deadline", q.deadline)}</div>${list("Known locations", q.locations)}${list("Current obstacles", q.risks)}${knowledge}${objectives}${list("Optional objectives", q.optionalObjectives)}${branchInfo}${list("Known rewards", q.rewards)}<div class="quest-note-row"><input type="text" placeholder="Add your own quest note" data-quest-note-input="${escapeHtml(q.name)}"><button type="button" data-quest-note-save="${escapeHtml(q.name)}">SAVE NOTE</button></div></div></details>`;
      }).join("") : `<div class="jrow">${escapeHtml(qp.empty_label)}.</div>`) + `<div class="jrow hint">Hidden quests discovered: ${data.hidden_quests_count}</div>` + archive;
    } else {
      const intro = `<div class="system-summary agenda-intro"><b>${escapeHtml(qp.tab_label.toUpperCase())}</b><span>This records responsibilities, promises, investigations, and developing situations. It follows what happens in the story—not percentages, mandatory steps, or a fixed solution.</span></div>`;
      const cards = active.length ? active.map((raw, index) => {
        const q = questView(raw, index);
        const possible = [...new Set([
          q.firstStep,
          ...textList(q.branchState.available),
        ].filter(Boolean))];
        const openThreads = [...new Set(q.objectives.filter((obj) => obj && obj.status !== "complete" && obj.status !== "failed").map((obj) => obj.text || obj.name).filter(Boolean))];
        const commitments = [...new Set([...q.commitments, ...q.optionalObjectives])];
        const knowledge = list("What you currently know", q.knowledge, "Only the original situation is confirmed so far.");
        return `<details class="quest-card agenda-card"${index === 0 ? " open" : ""}><summary>${escapeHtml(q.name)} <small>— ${escapeHtml(q.status)}</small></summary><div class="quest-details"><div class="quest-detail-label">Situation</div><p class="quest-summary">${escapeHtml(q.explanation)}</p><div class="quest-brief-grid">${line("Responsibility / source", q.giver)}${line("Current direction", q.firstStep)}${line("Time pressure", q.deadline)}</div>${list("Relevant places", q.locations)}${list("Immediate pressures", q.risks)}${knowledge}${list("Threads still in play", openThreads)}${list("Possible approaches", possible, "Choose any approach that makes sense in the story; you are not limited to a listed route.")}${list("Commitments and possibilities", commitments)}${list("Recent developments", q.developments)}<div class="quest-note-row"><input type="text" placeholder="Add your own agenda note" data-quest-note-input="${escapeHtml(q.name)}"><button type="button" data-quest-note-save="${escapeHtml(q.name)}">SAVE NOTE</button></div></div></details>`;
      }).join("") : `<div class="jrow">${escapeHtml(qp.empty_label)}. New responsibilities and leads will appear through play.</div>`;
      panel.innerHTML = intro + cards + archive;
    }
  } else if (tab === "skills") {
    const skills = Object.entries(data.skills || {});
    const titles = data.titles || [];
    const isBleach = data.world === "Bleach";
    const classRow = isBleach ? "" : renderClassCard(data.class_profile);
    const worldProgression = isBleach ? "" : renderWorldProgression(data.world, data.special || {}, data.class_profile || {}, data);
    const kido = skills.filter(([name, detail]) => /^(?:Had[ōo]|Bakud[ōo])\s*#/i.test(name) || (detail && typeof detail === "object" && detail.kido));
    const releases = skills.filter(([name, detail]) => /^(?:Shikai|Bankai)\b/i.test(name) || (detail && typeof detail === "object" && detail.release_stage));
    const foundations = skills.filter((row) => !kido.includes(row) && !releases.includes(row));
    const skillRows = skills.length
      ? skills.map(([name, detail]) => renderSkillCard(name, detail)).join("")
      : '<div class="jrow">No learned skills yet.</div>';
    const titleRows = titles.length
      ? titles.map((title) => `<div class="jrow">🏅 ${escapeHtml(titleLabel(title))}</div>`).join("")
      : '<div class="jrow hint">No titles earned yet.</div>';
    panel.innerHTML = isBleach
      ? `<button id="btn-open-power-summary" class="btn-ghost full">⚔ Power Summary</button><h3>Zanpakutō Releases</h3>${renderBleachReleases(data.special || {})}<h3>Hadō & Bakudō</h3>${kido.length ? kido.map(([name, detail]) => renderSkillCard(name, detail)).join("") : '<div class="jrow hint">No numbered Kidō learned yet.</div>'}<h3>Soul Reaper Training</h3>${foundations.length ? foundations.map(([name, detail]) => renderSkillCard(name, detail)).join("") : '<div class="jrow hint">No additional training recorded.</div>'}<h3>Titles</h3>${titleRows}`
      : `<button id="btn-open-power-summary" class="btn-ghost full">⚔ Power Summary</button>${worldProgression ? `<h3>World Progression</h3>${worldProgression}` : ""}${classRow && data.world !== "Overgeared" ? `<h3>Class / Path</h3>${classRow}` : ""}<h3>Learned Skills</h3>${skillRows}<h3>Titles</h3>${titleRows}`;
    $("#btn-open-power-summary").addEventListener("click", openPowerSummary);
  } else if (tab === "achievements") {
    const achievements = data.achievements || [];
    const titles = data.titles || [];
    const achievementView = (entry, index) => {
      const obj = entry && typeof entry === "object" ? entry : {};
      const name = compactReadable(obj.name || obj.title) || (typeof entry === "string" ? entry : `Achievement ${index + 1}`);
      const description = compactReadable(obj.description || obj.notes || obj.summary);
      const when = obj.turn !== undefined && obj.turn !== null ? `Turn ${compactReadable(obj.turn)}` : compactReadable(obj.date);
      return { name, description, when };
    };
    const achievementCards = achievements.length
      ? achievements.map((entry, i) => {
          const v = achievementView(entry, i);
          return `<article class="achievement-card" data-achievement-replay="${escapeHtml(v.name)}" title="Click to replay the unlock moment">
            <span class="achievement-icon">🏆</span>
            <div class="achievement-copy"><b>${escapeHtml(v.name)}</b>${v.description ? `<p>${escapeHtml(v.description)}</p>` : ""}${v.when ? `<small>${escapeHtml(v.when)}</small>` : ""}</div>
          </article>`;
        }).join("")
      : '<div class="jrow hint">No achievements unlocked yet.</div>';
    const titleCards = titles.length
      ? titles.map((t) => `<article class="achievement-card title-card"><span class="achievement-icon">🎖</span><div class="achievement-copy"><b>${escapeHtml(titleLabel(t))}</b></div></article>`).join("")
      : '<div class="jrow hint">No titles earned yet.</div>';
    panel.innerHTML = `<h3>Achievements</h3><div class="achievement-grid">${achievementCards}</div><h3>Titles Earned</h3><div class="achievement-grid">${titleCards}</div>`;
    $$("[data-achievement-replay]").forEach((card) => card.addEventListener("click", () => {
      const name = card.getAttribute("data-achievement-replay");
      showCinematic("achievement", "ACHIEVEMENT UNLOCKED: " + name);
      playSfx("achievement");
    }));
  } else if (tab === "progression") {
    const logs = (data.progression_log || []).slice(-40).reverse();
    const ledger = (data.progression_ledger || []).slice(-40).reverse();
    const ledgerRows = ledger.map((entry) => {
      const changes = (entry.changes || []).map((change) => {
        if (change.before !== undefined && change.after !== undefined) return `<li><b>${escapeHtml(change.name)}</b> ${escapeHtml(change.before)} → ${escapeHtml(change.after)} (${Number(change.delta) >= 0 ? "+" : ""}${escapeHtml(change.delta)})</li>`;
        return `<li><b>${escapeHtml(change.name)}</b> — ${escapeHtml(change.change || "changed")}</li>`;
      }).join("");
      const rolls = (entry.rolls || []).map((roll) => `<li>${escapeHtml(roll)}</li>`).join("");
      const duration = Number(entry.elapsed_minutes || 0) > 0 ? ` · ${escapeHtml(entry.elapsed_minutes)} minutes` : "";
      return `<details class="progress-entry ledger-entry"><summary><b>${escapeHtml(entry.cause || "Progress")}</b><span>Turn ${escapeHtml(entry.turn ?? "—")}${duration}</span></summary><div><ul>${changes}</ul>${rolls ? `<small>Relevant checks</small><ul>${rolls}</ul>` : ""}<p>${escapeHtml(entry.explanation || "Growth followed from the listed actions and outcomes.")}</p></div></details>`;
    }).join("");
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
    panel.innerHTML = summary + `<h3>Why your character changed</h3>` + (ledgerRows || '<div class="jrow hint">No lasting growth changes have been recorded yet.</div>') + `<h3>Training and XP history</h3>` + (rows || '<div class="jrow hint">No progression has been recorded yet.</div>');
  } else if (tab === "chapters") {
    const chapters = [...(data.chapter_summaries || [])].reverse();
    const recent = data.chapter_buffer || [];
    const daysIntoChapter = recent.length ? Math.max(0, Number(data.canon_day ?? 0) - Number(recent[0].canon_day ?? data.canon_day ?? 0)) : 0;
    panel.innerHTML = `<div class="system-summary"><b>CHAPTER MEMORY</b><span>${chapters.length} consolidated chapters · ${daysIntoChapter}/90 days toward the next</span></div>` +
      (chapters.length ? chapters.map((chapter, index) => `<details class="quest-card"${index === 0 ? " open" : ""}><summary>${escapeHtml(chapter.title || `Chapter ${chapter.number}`)} <small>— turns ${escapeHtml((chapter.turns || []).join("–"))}</small></summary><div class="quest-details"><p>${escapeHtml(chapter.summary || "")}</p><div class="quest-detail-label">Key decisions</div><ul>${(chapter.key_decisions || []).map((x) => `<li>${escapeHtml(x)}</li>`).join("") || "<li>None recorded.</li>"}</ul><div class="quest-detail-label">Lasting changes</div><ul>${(chapter.lasting_changes || []).map((x) => `<li>${escapeHtml(x)}</li>`).join("") || "<li>None recorded.</li>"}</ul><small>${escapeHtml(chapter.time_span || "")}</small></div></details>`).join("") : '<div class="jrow">A chapter is consolidated roughly every 3 in-game months, or sooner if a long stretch passes without much time advancing.</div>');
  } else if (tab === "clocks") {
    const renderClocks = (title, clocks) => `<h3>${title}</h3>` + (Object.values(clocks || {}).length ? Object.values(clocks).map((clock) => {
      // mid_term_goal/core_ambition are optional depth beyond the one
      // immediate_goal/goal line every clock already gets — most won't
      // have them, same as the NPC relationship cards.
      const layers = (clock.mid_term_goal ? `<p><b>Building toward:</b> ${escapeHtml(clock.mid_term_goal)}</p>` : "") +
        (clock.core_ambition ? `<p><b>Deep down wants:</b> ${escapeHtml(clock.core_ambition)}</p>` : "");
      return `<article class="clock-row"><header><b>${escapeHtml(clock.name || "Unknown")}</b><span class="clock-status ${escapeHtml(clock.status || "active")}">${escapeHtml((clock.status || "active").replace(/_/g, " "))}</span></header><p>${escapeHtml(clock.immediate_goal || clock.goal || "Private agenda")}</p>${layers}<div class="clock-track"><i style="width:${Math.max(0, Math.min(100, Number(clock.progress || 0)))}%"></i></div><small>${escapeHtml(clock.progress || 0)} / ${escapeHtml(clock.threshold || 100)} · last moved ${escapeHtml(clock.last_update || "not yet")}</small>${clock.last_cause ? `<small class="causal-reason">Because: ${escapeHtml(clock.last_cause)}</small>` : ""}${clock.blocked_reason ? `<small class="causal-blocked">Blocked: ${escapeHtml(clock.blocked_reason)}</small>` : ""}${clock.opponent ? `<small>⚔ Power ${escapeHtml(clock.power ?? 50)} vs ${escapeHtml(clock.opponent)}${clock.contested_location ? ` over ${escapeHtml(clock.contested_location)}` : ""}</small>` : ""}</article>`;
    }).join("") : '<div class="jrow hint">No visible clocks yet. Important NPCs and factions gain clocks as they enter the campaign.</div>');
    panel.innerHTML = renderClocks("Faction agendas", data.faction_clocks) + renderClocks("NPC agendas", data.npc_clocks);
  } else if (tab === "causality") {
    const recent = [...(data.causality?.recent || [])].reverse();
    const actorRows = [...(data.causality?.factions || []), ...(data.causality?.npcs || [])];
    const sim = data.simulation || {}, profile = sim.profile || { label: "Balanced", description: "Focused world detail" };
    const intentions = Object.entries(sim.intentions || {}), simEvents = [...(sim.recent_events || [])].reverse().slice(0, 20);
    panel.innerHTML = `<div class="system-summary"><b>${escapeHtml(profile.label)} WORLD CAUSALITY</b><span>${escapeHtml(profile.description)} Nearby actors receive full detail; distant actors use compact intentions and clocks.</span></div>` +
      `<h3>Persistent NPC intentions</h3>` + (intentions.length ? intentions.map(([name,row]) => `<article class="causality-card${row.status === "turning_point" ? " blocked" : ""}"><header><b>${escapeHtml(name)}</b><span>${escapeHtml(row.detail || "coarse")} · ${escapeHtml(row.progress || 0)}%</span></header><p>${escapeHtml(row.goal || "Private objective")}</p><small>Next: ${escapeHtml(row.next_action || row.plan || "Continue the plan")}</small><small>Location: ${escapeHtml(row.location || "Unknown")} · ${escapeHtml(row.status || "active")}</small></article>`).join("") : '<div class="jrow hint">Intentions appear after recurring characters establish goals.</div>') +
      `<h3>Current causal actors</h3>` + (actorRows.length ? actorRows.map((row) => `<article class="causality-card${row.blocked_reason ? " blocked" : ""}"><header><b>${escapeHtml(row.name)}</b><span>${escapeHtml(row.status)}</span></header><p>${escapeHtml(row.goal || "No concrete goal recorded.")}</p>${row.target_location ? `<small>Target: ${escapeHtml(row.target_location)}</small>` : ""}${row.last_cause ? `<small>Last cause: ${escapeHtml(row.last_cause)}</small>` : ""}${row.blocked_reason ? `<small class="causal-blocked">Blocked: ${escapeHtml(row.blocked_reason)}</small>` : ""}${Object.keys(row.resources || {}).length ? `<small>Resources: ${Object.entries(row.resources).map(([k,v]) => `${escapeHtml(k)} ${escapeHtml(v)}`).join(" · ")}</small>` : ""}</article>`).join("") : '<div class="jrow hint">No causal actors are active yet.</div>') +
      `<h3>Consolidated event record</h3>` + (simEvents.length ? simEvents.map((row) => `<details class="causality-entry"><summary><b>${escapeHtml(row.summary || "World development")}</b><span>${escapeHtml(row.importance || 0)}/100</span></summary><small>Turn ${escapeHtml(row.turn ?? "?")} · Day ${escapeHtml(row.canon_day ?? "?")} · ${escapeHtml((row.sources || []).join(", "))}</small></details>`).join("") : '<div class="jrow hint">No consolidated events recorded yet.</div>') +
      `<h3>Why the world moved</h3>` + (recent.length ? recent.map((row) => `<details class="causality-entry"><summary><b>${escapeHtml(row.actor)}</b><span>${Number(row.progress_delta) > 0 ? `+${escapeHtml(row.progress_delta)} progress` : "no progress"}</span></summary><p>${escapeHtml(row.goal || "Agenda")}</p>${row.reason ? `<small>Cause: ${escapeHtml(row.reason)}</small>` : ""}${row.blocked_reason ? `<small class="causal-blocked">Blocked: ${escapeHtml(row.blocked_reason)}</small>` : ""}</details>`).join("") : '<div class="jrow hint">No causal progress has been recorded yet.</div>');
  } else if (tab === "knowledge") {
    const people = data.npc_knowledge?.people || [];
    const buckets = [["confirmed","Confirmed"],["heard","Heard from others"],["suspected","Suspected"],["false_beliefs","False beliefs"]];
    panel.innerHTML = `<div class="system-summary"><b>NPC KNOWLEDGE BOUNDARIES</b><span>The narrator knows the campaign; characters act only on what they witnessed, heard, inferred, researched, or falsely believe.</span></div>` +
      (people.length ? people.map((person) => `<details class="knowledge-card"><summary><b>${escapeHtml(person.name)}</b><span>${escapeHtml(person.last_known_location || "Unknown")}</span></summary><div>${buckets.map(([key,label]) => { const rows = person.knowledge?.[key] || []; return `<section><b>${label}</b>${rows.length ? `<ul>${rows.map((row) => `<li>${escapeHtml(row.fact || row)}${row.source ? `<small>Source: ${escapeHtml(row.source)}${row.confidence !== undefined ? ` · ${escapeHtml(row.confidence)}%` : ""}</small>` : ""}</li>`).join("")}</ul>` : '<p class="hint">None recorded.</p>'}</section>`; }).join("")}</div></details>`).join("") : '<div class="jrow hint">No NPC has a structured knowledge record yet.</div>') +
      ((data.npc_knowledge?.recent_audit || []).length ? `<h3>Prevented omniscience</h3>${data.npc_knowledge.recent_audit.slice().reverse().map((row) => `<div class="jrow"><b>${escapeHtml(row.npc)}</b><br>${escapeHtml(row.fact)}<br><small>${escapeHtml(row.reason)}</small></div>`).join("")}` : "");
  } else if (tab === "relationships") {
    const people = data.relationships_view?.people || [];
    const factions = data.relationships_view?.factions || [];
    const affiliations = data.relationships_view?.affiliations || [];
    const npcNetwork = data.relationships_view?.npc_network || [];
    const intentionMap = data.simulation?.intentions || {};
    panel.innerHTML = `<div class="system-summary"><b>RELATIONSHIPS &amp; FACTIONS</b><span>Trust is evidence, not automatic obedience.</span></div>` +
      `<h3>Affiliations — your rank and standing</h3>` + (affiliations.length ? affiliations.map((a) => `<div class="jrow affiliation-row${a.status && a.status !== "active" ? ` ${escapeHtml(a.status)}` : ""}"><b>${escapeHtml(a.rank || "Member")}</b> — ${escapeHtml(a.faction)}${a.status && a.status !== "active" ? `<span class="affiliation-status">${escapeHtml(a.status)}</span>` : ""}${a.joined ? `<br><small>Joined: ${escapeHtml(a.joined)}</small>` : ""}${a.notes ? `<br><small>${escapeHtml(a.notes)}</small>` : ""}</div>`).join("") : '<div class="jrow hint">Not formally affiliated with any group, alliance, or hierarchy yet.</div>') +
      `<h3>People</h3>` + (people.length ? people.map((person) => {
        // mid_term_goal/core_ambition are optional depth beyond the one
        // goal line every tracked NPC already gets — most won't have them,
        // so the extra rows only render for characters the GM actually
        // bothered to layer.
        const layers = (person.mid_term_goal ? `<p><b>Building toward:</b> ${escapeHtml(person.mid_term_goal)}</p>` : "") +
          (person.core_ambition ? `<p><b>Deep down wants:</b> ${escapeHtml(person.core_ambition)}</p>` : "");
        const motive = intentionMap[person.name] || {};
        const motiveLines = `${textList(motive.loyalties).length ? `<p><b>Loyalties:</b> ${textList(motive.loyalties).map(escapeHtml).join(" · ")}</p>` : ""}${textList(motive.fears).length ? `<p><b>Known concerns:</b> ${textList(motive.fears).map(escapeHtml).join(" · ")}</p>` : ""}${motive.opinion_of_player ? `<p><b>Opinion of you:</b> ${escapeHtml(motive.opinion_of_player)}</p>` : ""}`;
        return `<details class="relationship-card${person.nemesis ? " nemesis-card" : ""}"><summary><b>${person.nemesis ? "⚠ " : ""}${escapeHtml(person.name)}</b><span>${escapeHtml(person.label)} · ${Number(person.score) >= 0 ? "+" : ""}${escapeHtml(person.score)}</span></summary><div><p><b>Goal:</b> ${escapeHtml(person.goal)}</p>${layers}${motiveLines}<p><b>Last known:</b> ${escapeHtml(person.last_known_location)}</p>${textList(person.promises).length ? `<p><b>Promises:</b> ${textList(person.promises).map(escapeHtml).join(" · ")}</p>` : ""}${textList(person.debts).length ? `<p><b>Debts:</b> ${textList(person.debts).map(escapeHtml).join(" · ")}</p>` : ""}${chainHistoryHtml(person.chain)}</div></details>`;
      }).join("") : '<div class="jrow hint">No recurring relationships have been established.</div>') +
      // NPCs relating to each other independent of the player — allies,
      // rivals, grudges the GM has established between two named
      // characters. This is the only place that data is actually visible;
      // without it, tracked NPC-to-NPC dynamics would just be invisible
      // bookkeeping the player has no way to see or reason about.
      `<h3>NPC Network — how they relate to each other</h3>` + (npcNetwork.length ? npcNetwork.map((rel) => {
        const negative = rel.strength < 0;
        return `<div class="jrow npc-network-row"><b>${escapeHtml(rel.a)}</b> <span class="npc-network-type">${escapeHtml(rel.type)}</span> <b>${escapeHtml(rel.b)}</b>
          <span class="npc-network-strength ${negative ? "negative" : "positive"}">${rel.strength > 0 ? "+" : ""}${escapeHtml(rel.strength)}</span>
          ${rel.status && rel.status !== "active" ? `<span class="affiliation-status">${escapeHtml(rel.status)}</span>` : ""}
          ${rel.note ? `<br><small>${escapeHtml(rel.note)}</small>` : ""}</div>`;
      }).join("") : '<div class="jrow hint">No relationships between other characters have been established yet.</div>') +
      `<h3>Faction standing</h3>` + (factions.length ? factions.map((f) => `<div class="jrow"><b>${escapeHtml(f.name)}</b><br>${escapeHtml(typeof f.standing === "object" ? compactReadable(f.standing.label || f.standing.status || f.standing.score) : f.standing)}${chainHistoryHtml(f.chain)}</div>`).join("") : '<div class="jrow hint">No faction reputation has been recorded.</div>');
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
    const rows = (data.canon_dependencies?.events || data.canon_event_tracker || data.canon_events || []).map((event) => {
      const id = `day:${event.day || 0}:${event.title || "event"}`;
      const occurred = fired.has(id) || Number(event.day) < currentDay;
      const current = Number(event.day) === currentDay;
      const world = data.world || "Custom World";
      const status = event.status || (occurred ? "occurred" : "likely");
      const effectiveDay = event.effective_day ?? event.day;
      const confidence = event.confidence || {};
      return `<div class="timeline-row ${escapeHtml(status)} ${current ? "current" : ""}"><div class="timeline-day">${escapeHtml(formatCalendarDate(world, effectiveDay, data.calendar_epoch, data.calendar_anchor_day))}</div><div><header><b>${escapeHtml(event.title || "World event")}</b><span class="canon-status ${escapeHtml(status)}">${escapeHtml(status)}</span></header><small>${escapeHtml(event.location || "")}${confidence.label ? ` · ${escapeHtml(confidence.label)}` : ""}</small><p>${escapeHtml(event.summary || "")}</p>${(event.requires || []).length ? `<p class="timeline-dependencies"><b>Depends on:</b> ${event.requires.map(escapeHtml).join(" → ")}</p>` : ""}${event.reason && !["likely","upcoming","occurred"].includes(status) ? `<p class="timeline-reason"><b>Why changed:</b> ${escapeHtml(event.reason)}</p>` : ""}${event.replacement ? `<p class="timeline-replacement"><b>What may happen instead:</b> ${escapeHtml(event.replacement)}</p>` : ""}${confidence.note ? `<p class="timeline-confidence">${escapeHtml(confidence.note)}</p>` : ""}</div></div>`;
    }).join("");
    panel.innerHTML = `<div class="timeline-anchor"><b>Current: ${escapeHtml(formatCalendarDate(data.world || "Custom World", currentDay, data.calendar_epoch, data.calendar_anchor_day))}</b><span>${escapeHtml(data.canon_anchor || "Before the main story")}</span></div>${rows || '<div class="jrow">No fixed canon timeline for this world.</div>'}<div class="jrow hint">Canon events are scheduled pressures, not rails. Player-caused divergences can alter or prevent their original form.</div>`;
  } else if (tab === "schedule") {
    const events = data.scheduled_events || [];
    panel.innerHTML = events.length ? events.map((event) => `<div class="timeline-row upcoming"><div class="timeline-day">${escapeHtml(event.when || event.day || event.time || "Upcoming")}</div><div><b>${escapeHtml(event.title || event.name || "Scheduled event")}</b><p>${escapeHtml(event.summary || event.description || event.notes || "Known details will develop as the date approaches.")}</p></div></div>`).join("") : '<div class="jrow">No visible deadlines or scheduled events. Hidden events remain hidden until your character could know them.</div>';
  } else if (tab === "continuity") {
    const ledger = data.continuity || {};
    const canon = data.campaign_canon || [];
    const facts = ledger.facts || [];
    const section = (title, values) => `<h3>${title}</h3>${(values || []).length ? values.slice(-30).reverse().map((x) => `<div class="jrow">${escapeHtml(typeof x === "object" ? x.text || x.description || JSON.stringify(x) : x)}</div>`).join("") : '<div class="jrow hint">Nothing recorded.</div>'}`;
    panel.innerHTML = section("Campaign canon", canon) + section("Location changes", facts.filter((x) => x.type === "location")) + section("Appearance changes", facts.filter((x) => x.type === "appearance")) + section("Quest changes", facts.filter((x) => x.type === "quest")) + section("Warnings", ledger.warnings);
  } else if (tab === "memory") {
    const memory = data.narrative_memory || {};
    const memorySection = (title, key, empty) => {
      const rows = (memory[key] || []).slice().reverse();
      return `<section class="memory-section"><h3>${escapeHtml(title)}</h3>${rows.length ? rows.map((row) => `<article class="memory-row"><p>${escapeHtml(typeof row === "object" ? row.text : row)}</p><small>${escapeHtml(typeof row === "object" ? row.source || "Campaign" : "Campaign")}${row?.canon_day != null ? ` · Canon Day ${escapeHtml(row.canon_day)}` : ""}${row?.status ? ` · ${escapeHtml(row.status)}` : ""}</small></article>`).join("") : `<div class="jrow hint">${escapeHtml(empty)}</div>`}</section>`;
    };
    panel.innerHTML = `<div class="system-summary"><b>LONG-TERM NARRATIVE MEMORY</b><span>Campaign facts are separated by purpose so later turns can preserve them without rereading the entire Chronicle.</span></div>` +
      memorySection("Established facts", "established_facts", "No lasting facts recorded yet.") +
      memorySection("Player goals", "player_goals", "No long-term goal recorded yet.") +
      memorySection("Unresolved mysteries", "unresolved_mysteries", "No unresolved mystery recorded yet.") +
      memorySection("Promises", "promises", "No promises recorded yet.") +
      memorySection("Relationships", "relationships", "No recurring relationship recorded yet.") +
      memorySection("Consequences", "consequences", "No lasting consequence recorded yet.");
  } else if (tab === "world-feed") {
    // Split into what the player actually experienced vs. the world moving
    // on its own (NPC/faction clocks, canon beats delivered as background
    // texture rather than lived through) — background_world_feed mirrors
    // the exact same text those specific entries already carry in
    // world_events/timeline, so matching on content is enough to tell them
    // apart without changing the shape either list has always had.
    const entryText = (entry) => typeof entry === "object" ? (entry.text || entry.summary || JSON.stringify(entry)) : entry;
    const renderFeedEntry = (entry) => {
      const text = entryText(entry);
      const kind = typeof entry === "object" ? (entry.type || entry.tag || "World update") : "World update";
      return `<div class="jrow"><b>${escapeHtml(String(kind).replace(/_/g, " "))}</b><br>${escapeHtml(text)}</div>`;
    };
    const backgroundTexts = new Set((data.background_world_feed || []).map(entryText));
    const seen = new Set();
    const personal = [];
    [...(data.world_events || []), ...(data.timeline || [])].forEach((entry) => {
      const text = entryText(entry);
      if (seen.has(text)) return;
      seen.add(text);
      if (!backgroundTexts.has(text)) personal.push(entry);
    });
    const personalRows = personal.slice(-40).reverse().map(renderFeedEntry).join("")
      || '<div class="jrow">No major world updates have reached you yet.</div>';
    const backgroundRows = (data.background_world_feed || []).slice(-40).reverse().map(renderFeedEntry).join("")
      || '<div class="jrow hint">Nothing else has moved independently yet.</div>';
    panel.innerHTML = `<h3>Your Story</h3>${personalRows}<h3>The Wider World</h3><p class="hint">Things happening on their own, whether or not you were there for them.</p>${backgroundRows}`;
  } else if (tab === "codex") {
    const codex = data.codex || [];
    panel.innerHTML = codex.length ? codex.map((c) => `<div class="jrow"><b>${escapeHtml(c.name || "Entry")}</b> <i>${escapeHtml(c.type || "")}</i><br/>${escapeHtml(c.notes || "")}</div>`).join("") : `<div class="jrow">No codex entries yet.</div>`;
  } else if (tab === "inventory") {
    const inv = data.inventory || [];
    const eq = data.equipment || {};
    const currencyRows = data.tracks_currency === false ? [] : [currencyRowHtml(data.currency.name, data.currency.amount)]
      .concat(Object.entries(data.currencies || {}).map(([k, v]) => `<div class="jrow"><b>${escapeHtml(k)}:</b> ${escapeHtml(v)}</div>`));
    const bagRows = inv.length ? inv.map((i) => {
      if (!i || typeof i !== "object") return `<div class="jrow">${escapeHtml(i)}</div>`;
      const effects = textList(i.effects || i.effect), limits = textList(i.restrictions || i.restriction);
      return `<article class="inventory-detail-card"><header><b>${escapeHtml(i.name || "Item")}</b><span>${escapeHtml(i.rating || i.grade || i.category || "Item")}</span></header>${effects.length ? `<p>${escapeHtml(effects.join(" · "))}</p>` : ""}${limits.length ? `<small>Limits: ${escapeHtml(limits.join(" · "))}</small>` : ""}${i.source || i.creator ? `<small>${escapeHtml(i.source || `Created by ${i.creator}`)}</small>` : ""}</article>`;
    }).join("") : `<div class="jrow">Bag is empty.</div>`;
    if (data.gear_style === "full") {
      panel.innerHTML = currencyRows.join("") + buildMannequinHtml(eq) + bagRows;
      wireMannequinTooltips();
    } else {
      panel.innerHTML = currencyRows.join("") + bagRows +
        (Object.keys(eq).length ? `<div class="jrow"><b>Weapon</b><br/>${Object.entries(eq).map(([k, v]) => `${escapeHtml(k)}: ${escapeHtml(v)}`).join("<br/>")}</div>` : "");
    }
  } else if (tab === "shops") {
    const shops = data.shops || [];
    const currency = data.currency || { name: "Currency", amount: 0 };
    const tracksCurrency = data.tracks_currency !== false;
    const shopBlocks = shops.length ? shops.map((sh) => {
      if (typeof sh !== "object" || !sh) return `<div class="jrow">${escapeHtml(sh)}</div>`;
      const inventory = Array.isArray(sh.inventory) ? sh.inventory : (Array.isArray(sh.items) ? sh.items : []);
      const itemRows = inventory.length ? inventory.map((it) => {
        const itemObj = (it && typeof it === "object") ? it : { name: it };
        const name = itemObj.name || itemObj.item || String(it);
        const price = parsePriceClient(itemObj.price ?? itemObj.cost ?? itemObj.value);
        const canAfford = price != null && currency.amount >= price;
        const priceLabel = tracksCurrency ? (price != null ? `${price} ${escapeHtml(currency.name)}` : "price unclear") : escapeHtml(itemObj.access || "Narrative access");
        return `<div class="shop-item-row"><span class="shop-item-name">${escapeHtml(name)}</span><span class="shop-item-price">${priceLabel}</span>` +
          (tracksCurrency && price != null ? `<button type="button" class="shop-buy-btn" data-shop-buy="${escapeHtml(sh.name || "")}" data-shop-item="${escapeHtml(name)}"${canAfford ? "" : " disabled"}>Buy</button>` : "") +
          `</div>`;
      }).join("") : `<div class="shop-item-row muted">No priced inventory listed here yet.</div>`;
      return `<div class="jrow shop-block"><b>${escapeHtml(sh.name || "Shop")}</b><small>${escapeHtml(sh.type || "Merchant")}</small>${itemRows}</div>`;
    }).join("") : `<div class="jrow">${data.shop_types.map((t) => "• " + t).join("<br/>")}</div>`;
    const accessNote = tracksCurrency ? currencyRowHtml(currency.name, currency.amount) : `<div class="system-summary"><b>SUPPLY ACCESS</b><span>Bleach does not track a money balance. Important equipment comes through rank, authorization, favors, requisitions, availability, or story events.</span></div>`;
    panel.innerHTML = accessNote + shopBlocks +
      `<div class="jrow"><b>Training Focus</b><br/>${data.training_options.map(escapeHtml).join(", ")}</div>` +
      (Object.keys(data.ability_progress || {}).length ? `<div class="jrow"><b>Progress</b><br/>${Object.entries(data.ability_progress).map(([k, v]) => `${escapeHtml(k)}: ${escapeHtml(v)}`).join("<br/>")}</div>` : "");
  } else if (tab === "map") {
    const nodes = data.map_data?.nodes || [];
    const knownCount = nodes.filter((node) => node.discovered).length;
    const legendChips = groupNodesByController(nodes).map((t) => `<span class="territory-chip" style="--tc:${t.color}">${escapeHtml(t.controller)}</span>`).join("");
    panel.innerHTML = `<div class="map-heading"><div><b>${escapeHtml(data.world || s.world || "World")} Atlas</b><small>${nodes.length} important landmarks · ${knownCount} visited/discovered</small></div><div class="map-legend"><span class="current">Current</span><span class="known">Discovered</span><span class="unknown">Known landmark</span></div></div>` +
      (legendChips ? `<div class="territory-legend">${legendChips}</div>` : "") +
      `<div class="map-layout"><div class="map-wrap" id="map-wrap"><div class="map-canvas" id="map-canvas" style="--map-image:url('${escapeHtml(data.map_image || "")}')"><canvas class="map-territories" id="map-territory-canvas"></canvas><div id="map-ambient" class="map-ambient" aria-hidden="true"></div></div><div class="map-zoom-controls"><button type="button" data-map-zoom-in title="Zoom in">+</button><button type="button" data-map-zoom-out title="Zoom out">−</button><button type="button" data-map-zoom-reset title="Reset view">⤾</button></div></div><aside class="map-detail" id="map-detail"><b>Select a landmark</b><p>A reference atlas — click a landmark for what's known about it, who's tied to it, and who controls it. Drag to pan, scroll or use the buttons to zoom.</p></aside></div>`;
    const canvas = $("#map-canvas");
    paintMapTerritories($("#map-territory-canvas"), nodes);
    applyNativeMapFx(nodes);
    nodes.forEach((node) => {
      const dot = document.createElement("button");
      dot.type = "button";
      dot.className = "map-node " + (node.current ? "here" : node.discovered ? "known" : "unknown") + (node.danger_level ? " danger-" + node.danger_level.toLowerCase() : "") + (node.recently_changed ? " territory-changed" : "");
      dot.style.left = node.x + "%"; dot.style.top = node.y + "%";
      dot.title = `${node.name} · ${node.kind || "landmark"} · Tier ${node.tier ?? "?"}${node.controller && node.controller !== "Unknown" ? ` · Controlled by ${node.controller}` : ""}${node.danger_level ? ` · ${node.danger_level} danger` : ""}${node.recently_changed ? " · Control recently changed" : ""}`;
      dot.setAttribute("data-map-node", node.name);
      dot.innerHTML = `<span class="map-pip"></span><span class="map-label">${escapeHtml(node.name)}</span>`;
      canvas.appendChild(dot);
    });
    APP.mapNodes = nodes;
    APP.travelGraph = data.travel_graph || { edges: {} };
    initMapPanZoom();
  } else if (tab === "lore") {
    const sources = data.lore_sources || [];
    const conflicts = data.lore_status?.conflicts || [];
    panel.innerHTML = `<div class="system-summary"><b>AUTHORITY-RANKED LORE LIBRARY</b><span>Official sources outrank references, wikis, forums, and fan analysis. Conflicting claims remain visible instead of being silently blended.</span></div><form id="lore-import-form" class="lore-import"><label>Add a lore pack<input id="lore-file" type="file" accept=".json,.md,.txt" required></label><select id="lore-world"><option>${escapeHtml(data.world || "Custom World")}</option><option>Custom World</option></select><button class="btn-primary" type="submit">IMPORT</button></form>` +
      (sources.length ? sources.map((source) => `<div class="jrow"><b>${escapeHtml(source.name)}</b><br>${escapeHtml(source.kind)} · authority ${escapeHtml(source.authority || 0)}/100 · ${escapeHtml(source.entries || 0)} entries${source.source_types?.length ? ` · ${source.source_types.map(escapeHtml).join(", ")}` : source.source_type ? ` · ${escapeHtml(source.source_type)}` : ""}${source.worlds?.length ? ` · ${source.worlds.map(escapeHtml).join(", ")}` : ""}</div>`).join("") : '<div class="jrow">Only built-in setting guidance is available.</div>') +
      `<h3>Source conflicts</h3>` + (conflicts.length ? conflicts.map((row) => `<details class="lore-conflict"><summary><b>${escapeHtml(row.claim)}</b><span>Resolved at ${escapeHtml(row.authority)}/100</span></summary><p>${escapeHtml(row.resolution)}</p><small>Preferred source: ${escapeHtml(row.source)} (${escapeHtml(row.source_type)})</small><ul>${(row.alternatives || []).map((alt) => `<li>Disputed: ${escapeHtml(alt.value)} — ${escapeHtml(alt.source)} (${escapeHtml(alt.authority)}/100)</li>`).join("")}</ul></details>`).join("") : '<div class="jrow hint">No explicit claim conflicts detected for this world.</div>') +
      `<p class="hint">JSON entries may include title, keys, text, source, source_type, citation, and claims. Source types: official_source, official_reference, licensed_reference, curated, wiki, forum, fan_analysis, imported, or custom.</p>`;
  } else if (tab === "tuning") {
    const t = data.difficulty_controls || {};
    const preset = data.progression_preset || {};
    const slider = (key, label, min, max, step, value, suffix = "×") => `<label class="tuning-row"><span><b>${label}</b><small id="${key}-value">${escapeHtml(value)}${suffix}</small></span><input type="range" id="${key}" min="${min}" max="${max}" step="${step}" value="${escapeHtml(value)}"></label>`;
    panel.innerHTML = `<div class="system-summary"><b>${escapeHtml(preset.label || "WORLD PROGRESSION")}</b><span>Separate controls change pacing and danger without rewriting lore.</span></div><form id="tuning-form" class="tuning-form">${slider("check_warning_threshold", "Difficult-check warning threshold", 40, 95, 1, t.check_warning_threshold || 65, "/100")}${slider("xp_rate", "XP rate", .5, 2, .05, t.xp_rate || 1)}${slider("training_rate", "Training rate", .5, 2, .05, t.training_rate || 1)}${slider("breakthrough_rate", "Breakthrough frequency", .5, 2, .05, t.breakthrough_rate || 1)}${slider("combat_danger", "Combat danger", .5, 2, .05, t.combat_danger || 1)}${slider("resource_pressure", "Resource pressure", .5, 2, .05, t.resource_pressure || 1)}<label class="tuning-notes-row"><span><b>Director's Notes</b><small>A standing note to the GM — tone, pacing, what to lean into or away from.</small></span><textarea id="director_notes" maxlength="500" placeholder="e.g. more politics and less combat; slow down on romance subplots">${escapeHtml(data.director_notes || "")}</textarea></label><button class="btn-primary" type="submit">SAVE TUNING</button></form>`;
  } else if (tab === "health") {
    const health = data.campaign_health || { score: 100, status: "Healthy", issues: [], counts: {} };
    panel.innerHTML = `<div class="health-score ${health.score < 60 ? "bad" : health.score < 85 ? "warn" : "good"}"><strong>${escapeHtml(health.score)}</strong><div><b>${escapeHtml(health.status)}</b><span>Campaign structure, knowledge, causality, and continuity check</span></div></div><div class="health-actions"><button type="button" class="btn-primary" data-health-repair="safe_all">APPLY ALL SAFE REPAIRS</button><button type="button" class="btn-ghost" data-support-bundle>DOWNLOAD SUPPORT ZIP</button></div><div class="health-counts">${Object.entries(health.counts || {}).map(([key, value]) => `<span><b>${escapeHtml(value)}</b>${escapeHtml(humanLabel(key))}</span>`).join("")}</div>` +
      ((health.issues || []).length ? health.issues.map((issue) => `<article class="health-issue ${escapeHtml(issue.severity)}"><header><b>${escapeHtml(issue.area)}</b><span>${escapeHtml(issue.severity)}</span></header><p>${escapeHtml(issue.message)}</p><small>${escapeHtml(issue.suggestion)}</small>${issue.repairable ? `<button type="button" class="health-repair-btn" data-health-repair="${escapeHtml(issue.repair_id)}">REPAIR THIS</button>` : ""}</article>`).join("") : '<div class="jrow"><b>No structural problems detected.</b><br>The campaign has objectives, continuity, causal world state, and enough persistent memory to continue cleanly.</div>');
  } else if (tab === "evaluations") {
    const scenarios = data.evaluations?.scenarios || [];
    const history = data.evaluations?.history || [];
    panel.innerHTML = `<div class="system-summary"><b>LIVE NARRATOR EVALUATIONS</b><span>These isolated scenarios call AI models but never change the campaign. Each model/scenario pair uses one AI call and may incur its normal cost.</span></div><div class="evaluation-actions"><button type="button" class="btn-primary" data-eval-run="all">RUN ALL ${scenarios.length}</button><label class="evaluation-compare"><span>Compare models on the same scenarios</span><input id="evaluation-models" placeholder="gpt-5-mini, gpt-5.4-mini" value="${escapeHtml((data.evaluation_models || []).join(", "))}"><small>Two to five model IDs. This can make several paid calls.</small></label><button type="button" class="btn-ghost" data-eval-compare>COMPARE ON ALL SCENARIOS</button></div><div class="evaluation-grid">${scenarios.map((row) => `<article class="evaluation-card"><header><b>${escapeHtml(row.name)}</b><span>${escapeHtml(row.world)}</span></header><p>${escapeHtml(row.action)}</p><button type="button" class="btn-ghost" data-eval-run="${escapeHtml(row.id)}">RUN THIS SCENARIO</button></article>`).join("")}</div><h3>Recent reports</h3><div id="evaluation-result">${history.length ? history.map((row) => `<div class="jrow"><b>${escapeHtml(row.score)}/100 · ${escapeHtml(row.model || "Unknown model")}</b><br>${escapeHtml(row.scenario_count)} scenario(s) · ${escapeHtml(row.created_at || "")}</div>`).join("") : '<div class="jrow hint">No live model evaluation has been run yet.</div>'}</div>`;
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
// Map territories — a Voronoi-style mosaic (nearest controlled landmark wins
// each cell) instead of isolated per-faction blobs/circles, so territories
// read like regions on a real map: they border directly on their neighbors
// with no gaps and never overlap, even though the borders themselves are
// rough rather than hand-drawn coastlines. Colored by a stable hash of the
// faction's name so the same group always gets the same color across
// renders without a hardcoded palette.
// ---------------------------------------------------------------------------
function factionColor(name) {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
  return `hsl(${hash % 360}, 62%, 55%)`;
}
function groupNodesByController(nodes) {
  const byFaction = {};
  nodes.forEach((n) => {
    const controller = n.controller;
    if (!controller || controller === "Unknown") return;
    (byFaction[controller] = byFaction[controller] || []).push(n);
  });
  return Object.keys(byFaction).map((controller) => ({ controller, color: factionColor(controller) }));
}
function paintMapTerritories(canvas, nodes) {
  if (!canvas) return;
  const owners = nodes.filter((n) => n.controller && n.controller !== "Unknown");
  const GRID = 120;
  canvas.width = GRID;
  canvas.height = GRID;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, GRID, GRID);
  if (!owners.length) return;
  const colors = new Map(owners.map((n) => [n.controller, factionColor(n.controller)]));
  const withAlpha = new Map([...colors].map(([k, v]) => [k, v.replace("hsl(", "hsla(").replace(")", ",.22)")]));
  for (let gy = 0; gy < GRID; gy++) {
    for (let gx = 0; gx < GRID; gx++) {
      const px = ((gx + 0.5) / GRID) * 100, py = ((gy + 0.5) / GRID) * 100;
      let best = null, bestDist = Infinity;
      for (const n of owners) {
        const dx = Number(n.x) - px, dy = Number(n.y) - py, d = dx * dx + dy * dy;
        if (d < bestDist) { bestDist = d; best = n; }
      }
      if (best) {
        ctx.fillStyle = withAlpha.get(best.controller);
        ctx.fillRect(gx, gy, 1, 1);
      }
    }
  }
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


$("#journal-panel").addEventListener("input", (event) => {
  if (!event.target.matches(".tuning-row input")) return;
  const out = document.getElementById(event.target.id + "-value");
  if (out) out.textContent = event.target.value + (event.target.id === "check_warning_threshold" ? "/100" : "×");
});

$("#journal-panel").addEventListener("submit", async (event) => {
  if (event.target.id === "campaign-search-form") {
    event.preventDefault();
    const query = $("#campaign-search-query").value.trim();
    if (query.length < 2) return;
    const target = $("#campaign-search-results");
    target.innerHTML = '<div class="jrow hint">Searching this campaign…</div>';
    try {
      const result = await apiGet(`/api/campaign/search?q=${encodeURIComponent(query)}`);
      target.innerHTML = result.results?.length ? result.results.map((row) => `<article class="search-result"><header><b>${escapeHtml(row.title || humanLabel(row.kind))}</b><span>${escapeHtml(humanLabel(row.kind))}${row.turn != null ? ` · Turn ${escapeHtml(row.turn)}` : ""}</span></header><p>${escapeHtml(row.text || "")}</p></article>`).join("") : `<div class="jrow">No campaign record matched “${escapeHtml(query)}”.</div>`;
    } catch (error) { target.innerHTML = `<div class="jrow">${escapeHtml(error.message)}</div>`; }
  } else if (event.target.id === "gm-correction-form") {
    event.preventDefault();
    const payload = { type: $("#correction-type").value, target: $("#correction-target").value.trim(), value: $("#correction-value").value.trim(), explanation: $("#correction-explanation").value.trim() };
    try {
      const result = await apiPost("/api/campaign/correct", payload);
      renderState(result.state); appendStoryEntries(result.story || []);
      showToast("Correction saved as an authoritative campaign fact.", "notify");
      await openJournal("corrections");
    } catch (error) { showToast(error.message, "danger"); }
  } else if (event.target.id === "tuning-form") {
    event.preventDefault();
    const keys = ["check_warning_threshold", "xp_rate", "training_rate", "breakthrough_rate", "combat_danger", "resource_pressure"];
    const payload = Object.fromEntries(keys.map((key) => [key, Number(document.getElementById(key).value)]));
    payload.director_notes = document.getElementById("director_notes").value;
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
  const repairButton = event.target.closest("[data-health-repair]");
  if (repairButton) {
    repairButton.disabled = true;
    try {
      const result = await apiPost("/api/campaign/health/repair", { repair_id: repairButton.getAttribute("data-health-repair") });
      renderState(result.state);
      showToast((result.repair?.applied || []).length ? result.repair.applied.join(" ") : "No safe repair was needed.", "notify");
      await openJournal("health");
    } catch (error) { showToast(error.message, "danger"); repairButton.disabled = false; }
    return;
  }
  if (event.target.closest("[data-support-bundle]")) {
    downloadEndpoint("/api/diagnostics/bundle");
    return;
  }
  const evalButton = event.target.closest("[data-eval-run]");
  if (evalButton) {
    const key = evalButton.getAttribute("data-eval-run");
    evalButton.disabled = true;
    evalButton.textContent = "RUNNING — THE CAMPAIGN WILL NOT CHANGE";
    try {
      const index = await apiGet("/api/evaluations");
      const scenarioIds = key === "all" ? (index.scenarios || []).map((row) => row.id) : [key];
      const report = await apiPost("/api/evaluations/run", { scenario_ids: scenarioIds });
      const target = $("#evaluation-result");
      if (target) target.innerHTML = `<div class="evaluation-score"><strong>${escapeHtml(report.score)}/100</strong><div><b>${escapeHtml(report.model || "Configured model")}</b><span>${escapeHtml(report.results?.length || 0)} isolated scenario(s) · ${escapeHtml(report.usage?.calls || 0)} AI call(s)</span></div></div>` + (report.results || []).map((row) => `<details class="evaluation-result"><summary><b>${escapeHtml(row.name)}</b><span>${escapeHtml(row.score)}/100</span></summary>${(row.criteria || []).map((item) => `<div><b>${escapeHtml(item.name)} — ${escapeHtml(item.score)}/${escapeHtml(item.max)}</b><p>${escapeHtml(item.detail)}</p></div>`).join("")}${row.error ? `<p class="causal-blocked">${escapeHtml(row.error)}</p>` : ""}</details>`).join("");
      showToast(`Model evaluation finished at ${report.score}/100. The campaign was not changed.`, "notify");
    } catch (error) { showToast(error.message, "danger"); }
    finally { evalButton.disabled = false; evalButton.textContent = key === "all" ? "RUN ALL" : "RUN THIS SCENARIO"; }
    return;
  }
  const compareButton = event.target.closest("[data-eval-compare]");
  if (compareButton) {
    const models = String($("#evaluation-models")?.value || "").split(",").map((x) => x.trim()).filter(Boolean);
    compareButton.disabled = true;
    compareButton.textContent = "COMPARING — CAMPAIGN WILL NOT CHANGE";
    try {
      const index = await apiGet("/api/evaluations");
      const comparison = await apiPost("/api/evaluations/compare", { models, scenario_ids: (index.scenarios || []).map((row) => row.id) });
      const target = $("#evaluation-result");
      if (target) target.innerHTML = `<div class="evaluation-ranking"><h3>Same-scenario ranking</h3>${(comparison.ranking || []).map((row) => `<div class="jrow"><b>#${escapeHtml(row.rank)} ${escapeHtml(row.model)} — ${escapeHtml(row.score)}/100</b><br>${escapeHtml(row.duration_seconds)}s · ${escapeHtml(row.calls)} calls · $${Number(row.cost_usd || 0).toFixed(4)}</div>`).join("")}</div>`;
      showToast("Model comparison complete. The campaign was not changed.", "notify");
    } catch (error) { showToast(error.message, "danger"); }
    finally { compareButton.disabled = false; compareButton.textContent = "COMPARE ON ALL SCENARIOS"; }
    return;
  }
  const noteButton = event.target.closest("[data-quest-note-save]");
  if (noteButton) {
    const name = noteButton.getAttribute("data-quest-note-save");
    const input = Array.from(document.querySelectorAll("[data-quest-note-input]")).find((x) => x.getAttribute("data-quest-note-input") === name);
    if (!input?.value.trim()) return;
    try { await apiPost("/api/quests/note", { name, note: input.value.trim() }); input.value = ""; showToast("Quest note saved.", "notify"); }
    catch (error) { showToast(error.message, "danger"); }
    return;
  }
  const buyButton = event.target.closest("[data-shop-buy]");
  if (buyButton) {
    if (buyButton.disabled) return;
    buyButton.disabled = true;
    const shop = buyButton.getAttribute("data-shop-buy");
    const item = buyButton.getAttribute("data-shop-item");
    try {
      const result = await apiPost("/api/shop/buy", { shop, item });
      showToast(result.message, "notify");
      const refreshed = await apiGet("/api/state");
      APP.campaignActive = refreshed.campaign_active;
      renderState(refreshed.state);
      await openJournal("shops");
    } catch (error) {
      showToast(error.message, "danger");
      buyButton.disabled = false;
    }
    return;
  }
  const nodeButton = event.target.closest("[data-map-node]");
  if (nodeButton) {
    const node = (APP.mapNodes || []).find((row) => row.name === nodeButton.getAttribute("data-map-node"));
    if (!node) return;
    const detail = $("#map-detail");
    const people = node.notable_individuals || [];
    const links = APP.travelGraph?.edges?.[node.name] || [];
    detail.innerHTML = `<b>${escapeHtml(node.name)}</b><small>${escapeHtml(node.kind || "landmark")} · tier ${escapeHtml(node.tier || 1)}${node.current ? " · current location" : ""}</small><p>${escapeHtml(node.notes)}</p><dl><dt>Control</dt><dd>${escapeHtml(node.controller)}</dd>${node.danger_level ? `<dt>Danger</dt><dd class="danger-label danger-${escapeHtml(node.danger_level.toLowerCase())}">${escapeHtml(node.danger_level)}</dd>` : ""}<dt>Notable individuals</dt><dd>${people.length ? people.map(escapeHtml).join(", ") : "None recorded yet"}</dd><dt>Quest links</dt><dd>${node.quests?.length ? node.quests.map(escapeHtml).join(", ") : "None known"}</dd><dt>Direct routes</dt><dd>${links.length ? links.map((x) => `${escapeHtml(x.to)} (${escapeHtml(formatDuration(x.minutes))})`).join("<br>") : "No direct route recorded"}</dd></dl><div id="map-route-preview" class="map-route-preview">Calculating route from your current location…</div>`;
    try {
      const route = await apiGet(`/api/travel/route?destination=${encodeURIComponent(node.name)}`);
      const preview = $("#map-route-preview");
      if (preview) preview.innerHTML = route.reachable ? `<b>Route from ${escapeHtml(route.origin)}</b><p>${(route.route || []).map(escapeHtml).join(" → ")}</p><small>Ordinary travel: about ${escapeHtml(formatDuration(route.minutes))}${(route.requirements || []).length ? ` · Needs: ${route.requirements.map(escapeHtml).join("; ")}` : ""}</small>` : `<b>No established route</b><p>${escapeHtml(route.reason || "This destination is not connected yet.")}</p>`;
    } catch (error) { /* The static landmark details remain useful offline. */ }
    return;
  }
});

// Delegated from document (not #story-feed) because that container gets
// replaced when the campaign view mounts — same reason .codex-term clicks
// above are delegated from document instead of a specific ancestor.
document.addEventListener("click", async (event) => {
  const buyButton = event.target.closest("[data-offer-buy]");
  if (!buyButton) return;
  if (buyButton.disabled) return;
  buyButton.disabled = true;
  const id = buyButton.getAttribute("data-offer-buy");
  try {
    const result = await apiPost("/api/purchase_offer/buy", { id });
    showToast(result.message, "notify");
    buyButton.textContent = "Bought";
    const card = buyButton.closest(".story-purchase-offer");
    if (card) card.classList.add("resolved");
    const refreshed = await apiGet("/api/state");
    APP.campaignActive = refreshed.campaign_active;
    renderState(refreshed.state);
  } catch (error) {
    showToast(error.message, "danger");
    buyButton.disabled = false;
  }
});

// ---------------------------------------------------------------------------
// New Campaign modal
// ---------------------------------------------------------------------------
function fillSelect(sel, values, selected) {
  const safeValues = Array.isArray(values) ? values : [];
  sel.innerHTML = safeValues.map((v) => `<option value="${escapeHtml(v)}"${v === selected ? " selected" : ""}>${escapeHtml(v)}</option>`).join("");
}

let ncCharacterStash = null;

function refreshCampaignWorldFields() {
  ncCharacterStash = null;
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
    if (world === "One Piece") {
      const recommended = new Set([0, 1, 6, 8, 14]);
      const groups = [
        ["Recommended", (_, i) => recommended.has(i)],
        ["East Blue", (_, i) => i <= 8 && !recommended.has(i)],
        ["Grand Line & Sky", (_, i) => i >= 9 && i <= 18 && !recommended.has(i)],
        ["Government & Revolution", (_, i) => [19, 20, 21, 30].includes(i)],
        ["Other Blues", (_, i) => i >= 22 && i <= 24],
        ["New World", (_, i) => i >= 25 && i <= 29],
      ];
      $("#nc-start").innerHTML = groups.map(([label, include]) => {
        const options = startOpts.map((o, i) => include(o, i) ? `<option value="${i}">${escapeHtml(o.label)}</option>` : "").join("");
        return options ? `<optgroup label="${escapeHtml(label)}">${options}</optgroup>` : "";
      }).join("");
    } else {
      $("#nc-start").innerHTML = startOpts.map((o, i) => `<option value="${i}">${escapeHtml(o.label)}</option>`).join("");
    }
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
  refreshEraRow();
}

function refreshEraRow() {
  const wd = APP.worldsMeta?.worlds?.[$("#nc-world").value] || {};
  const eras = wd.starting_eras || [];
  const row = $("#nc-era-row");
  if (!eras.length || $("#nc-character-mode").value) {
    row.hidden = true;
    $("#nc-starting-era").innerHTML = "";
    $("#nc-era-note").textContent = "";
    return;
  }
  row.hidden = false;
  $("#nc-starting-era").innerHTML = eras.map((e) => `<option value="${escapeHtml(e.id)}">${escapeHtml(e.label)}</option>`).join("");
  $("#nc-starting-era").value = eras[0].id;
  $("#nc-era-note").textContent = eras[0].anchor || "";
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
    age: $("#nc-age").value.trim(),
    start_location: chosenStart ? chosenStart.location : "", start_note: chosenStart ? chosenStart.note : "",
    canon_character_id: $("#nc-character-mode").value,
    starting_era_id: $("#nc-era-row").hidden ? "" : ($("#nc-starting-era").value || ""),
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
  refreshEraRow();
  const c = selectedCanonCharacter();
  if (!c) {
    if (ncCharacterStash) {
      $("#nc-name").value = ncCharacterStash.name;
      $("#nc-background").value = ncCharacterStash.background;
      $("#nc-appearance").value = ncCharacterStash.appearance;
      $("#nc-origin").value = ncCharacterStash.origin;
      $("#nc-archetype").value = ncCharacterStash.archetype;
      $("#nc-age").value = ncCharacterStash.age;
      $("#nc-character-note").textContent = ncCharacterStash.note;
      ncCharacterStash = null;
    }
    return;
  }
  if (!ncCharacterStash) {
    ncCharacterStash = {
      name: $("#nc-name").value, background: $("#nc-background").value, appearance: $("#nc-appearance").value,
      origin: $("#nc-origin").value, archetype: $("#nc-archetype").value, note: $("#nc-character-note").textContent,
      age: $("#nc-age").value,
    };
  }
  $("#nc-name").value = c.name || "Traveler";
  $("#nc-background").value = c.background || "";
  $("#nc-appearance").value = c.appearance || "";
  $("#nc-age").value = (c.age ?? "") === "" ? "" : String(c.age);
  if (Array.from($("#nc-origin").options).some((o) => o.value === c.origin)) $("#nc-origin").value = c.origin;
  if (Array.from($("#nc-archetype").options).some((o) => o.value === c.archetype)) $("#nc-archetype").value = c.archetype;
  $("#nc-character-note").textContent = `${c.name} begins at ${c.location}, ${formatCalendarDate($("#nc-world").value, c.start_day, null, c.start_day)}. You control every decision; canon events remain pressures that can change naturally.`;
});
$("#nc-starting-era").addEventListener("change", () => {
  const wd = APP.worldsMeta?.worlds?.[$("#nc-world").value] || {};
  const era = (wd.starting_eras || []).find((e) => e.id === $("#nc-starting-era").value);
  $("#nc-era-note").textContent = era ? era.anchor || "" : "";
});

function renderCampaignPreview(p, payload) {
    const profile = p.starting_profile || {};
    APP.pendingPreview = p;
    APP.pendingCampaign = { ...payload, preview_stats: p.abilities, preview_profile: profile };
    const concealedSignature = profile.hidden_class?.discovery?.concealed && Number(profile.hidden_class.discovery.progress || 0) < 50 ? profile.hidden_class.signature_skill : "";
    const loadout = [...(profile.titles || []).map((x) => `Title: ${x}`), ...Object.keys(profile.skills || {}).filter((x) => x !== concealedSignature).map((x) => `Skill: ${x}`), ...Object.values(profile.equipment || {}).map((x) => `Gear: ${x}`)];
    const startingAbility = profile.generated_ability || null;
    const ability = startingAbility && startingAbility.details ? startingAbility.details : {};
    const startingTechniques = startingAbility && Array.isArray(startingAbility.additional_skills) ? startingAbility.additional_skills : [];
    const growth = profile.growth_profile || {};
    const abilityCard = p.world !== "Bleach" && startingAbility ? `<section class="generated-ability"><b>STARTING ABILITY — ${escapeHtml(startingAbility.name)}</b>${ability.kind ? `<span><strong>Type:</strong> ${escapeHtml(ability.kind)}</span>` : ""}<span>${escapeHtml(ability.effect || ability.description || "")}</span>${startingTechniques.length ? `<span><strong>Starting techniques:</strong> ${startingTechniques.map((row) => escapeHtml(row.name || "")).filter(Boolean).join(" · ")}</span>` : ""}<span><strong>In-world origin:</strong> ${escapeHtml(ability.origin || "A rare talent that has begun to surface.")}</span><span><strong>Limit:</strong> ${escapeHtml(ability.limitation || "Must be developed through play.")}</span><span><strong>Growth:</strong> ${escapeHtml(ability.growth_path || "Practice and suitable guidance.")}</span>${ability.canon_balance ? `<span><strong>World-scale balance:</strong> ${escapeHtml(ability.canon_balance)}</span>` : ""}</section>` : "";
    const classCard = p.world !== "Bleach" && (profile.class_profile || profile.hidden_class) ? renderClassCard(profile.class_profile || profile.hidden_class) : "";
    const bleachReleaseCard = p.world === "Bleach" ? renderBleachReleases(profile.bleach_release_profile ? {
      "Zanpakuto Profile": profile.bleach_release_profile,
      Shikai: `Achieved — ${profile.bleach_release_profile.shikai_name || profile.bleach_release_profile.name}`,
      Bankai: profile.bleach_release_profile.stage === "Bankai" ? profile.bleach_release_profile.bankai_name : "Unachieved",
    } : { Shikai: "Unachieved", Bankai: "Unachieved" }) : "";
    const startWarnings = (p.start_warnings || []).filter(Boolean);
    const warningCard = startWarnings.length ? `<section class="start-warnings"><b>START CONSISTENCY NOTE</b>${startWarnings.map((warning) => `<span>${escapeHtml(warning)}</span>`).join("")}</section>` : "";
    const primer = p.world_primer || {};
    const primerCard = `<section class="world-primer"><div class="world-primer-kicker">WHAT YOU'RE GETTING INTO — NO SPOILERS</div><p class="world-primer-premise">${escapeHtml(primer.premise || "")}</p><div class="world-primer-row"><b>Tone</b><span>${escapeHtml(primer.tone || "")}</span></div><div class="world-primer-row"><b>How power works</b><span>${escapeHtml(primer.power_system || "")}</span></div>${(primer.factions || []).length ? `<div class="world-primer-row"><b>Major powers</b><ul>${primer.factions.map((f) => `<li>${escapeHtml(f)}</li>`).join("")}</ul></div>` : ""}${(primer.locations || []).length ? `<div class="world-primer-row"><b>Where the story ranges</b><ul>${primer.locations.map((l) => `<li>${escapeHtml(l)}</li>`).join("")}</ul></div>` : ""}<p class="world-primer-starting-note">${escapeHtml(primer.starting_note || "")}</p></section>`;
    const classLabels = {
        "Overgeared": "Hidden class",
        "Solo Max-Level Newbie": "Hidden class",
        "Naruto": "Secret shinobi path",
        "One Piece": "Hidden potential",
        "Hunter x Hunter": "Rare Nen potential",
        "Reincarnated as a Slime": "Unique evolution path",
        "Bleach": "Secret spiritual path",
        "Custom World": "Hidden potential",
    };
    const classLabel = classLabels[p.world] || "Hidden potential";
    const rerolls = p.canon_character ? "" : `<section class="preview-rerolls"><b>Keep the character, reroll one part</b><div>${p.world === "Bleach" ? "" : `<button type="button" data-preview-reroll="class">${escapeHtml(classLabel)}</button><button type="button" data-preview-reroll="ability">Starting ability</button>`}<button type="button" data-preview-reroll="backstory">Expanded backstory</button><button type="button" data-preview-reroll="loadout">Starting loadout</button></div><small>Only the selected part changes. Everything else remains locked.</small></section>`;
    const learningRate = Number(growth.learning_rate || 1);
    const ordinaryGrowth = Math.abs(learningRate - 1) < 0.005 && String(growth.aptitude || "").toLowerCase().includes("typical");
    const growthLabel = !ordinaryGrowth && String(growth.aptitude || "").toLowerCase().includes("typical") ? "Modified learning potential" : (growth.aptitude || "Unusual potential");
    const growthSummary = ordinaryGrowth ? "" : `<div class="growth-summary"><b>${escapeHtml(growthLabel)}</b><span>${escapeHtml(learningRate.toFixed(2))}× sustained-learning rate</span><small>${escapeHtml(growth.explanation || "Actual growth still depends on time, training conditions, instruction, and recovery.")}</small></div>`;
    $("#campaign-preview").innerHTML = `${primerCard}<div class="preview-hero"><h2>${escapeHtml(p.name)}</h2><p>${escapeHtml(p.world)} · ${escapeHtml(p.difficulty)}</p></div>${warningCard}${profile.power_notice ? `<div class="power-notice"><b>POWER NOTICE — ${escapeHtml(profile.power_band)}</b><span>${escapeHtml(profile.power_notice)}</span></div>` : ""}<div class="preview-grid"><div><b>Beginning</b><span>${escapeHtml(p.start_location)} · ${escapeHtml(formatCalendarDate(p.world, p.start_day, null, p.start_day))}</span></div><div><b>Role</b><span>${escapeHtml(p.origin)} · ${escapeHtml(p.archetype)}${p.race ? ` · ${escapeHtml(p.race)}` : ""}</span></div><div><b>Timeline</b><span>${escapeHtml(p.canon_anchor || "Before the main story")}</span></div><div><b>Starting pools</b><span>HP ${escapeHtml(profile.hp_max)} · ${escapeHtml(p.resource)} ${escapeHtml(profile.resource_max)}</span></div></div><h3>Open-ended starting abilities</h3><div class="preview-stats">${Object.entries(p.abilities || {}).map(([k,v]) => `<span><b>${escapeHtml(k)}</b> ${escapeHtml(v)}</span>`).join("")}</div><h3>Starting loadout</h3><div class="preview-loadout">${loadout.map((x) => `<span>${escapeHtml(x)}</span>`).join("")}</div>${bleachReleaseCard}${classCard}${abilityCard}<section class="generated-backstory"><b>BACKGROUND</b><p>${escapeHtml(p.background || "The GM will complete a fitting background during the opening.")}</p></section>${growthSummary}${rerolls}<p class="hint">${p.uses_xp ? "This setting canonically uses visible XP and levels." : "This setting progresses through stats, techniques, knowledge and titles—no artificial XP levels."} ${p.canon_character ? "You have full control of this major character." : (p.starting_era ? "This original character begins in the selected timeline era." : "This original character begins shortly before the world's main story.")}</p>`;
    openModal("modal-campaign-preview");
}

$("#btn-begin-campaign").addEventListener("click", async () => {
  const payload = collectCampaignPayload();
  try {
    const result = await apiPost("/api/campaign/preview", payload);
    renderCampaignPreview(result.preview, payload);
  } catch (e) { showToast(e.message, "danger"); }
});

$("#campaign-preview").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-preview-reroll]");
  if (!button || !APP.pendingPreview || !APP.pendingCampaign) return;
  button.disabled = true;
  const kind = button.getAttribute("data-preview-reroll");
  try {
    const result = await apiPost("/api/campaign/preview/reroll", {
      preview: APP.pendingPreview, kind, background: APP.pendingCampaign.background || "",
    });
    renderCampaignPreview(result.preview, APP.pendingCampaign);
    showToast(`${humanLabel(kind)} rerolled.`, "notify");
  } catch (error) {
    showToast(error.message, "danger");
    button.disabled = false;
  }
});

$("#btn-preview-back").addEventListener("click", () => closeModal("modal-campaign-preview"));
$("#btn-confirm-campaign").addEventListener("click", async () => {
  if (!APP.pendingCampaign || APP.busy) return;
  setBusy(true); APP.deferPortraitGeneration = true; playSfx("world_event");
  try {
    const created = await apiPost("/api/campaign/new", APP.pendingCampaign);
    APP.campaignActive = true; APP.portraitAttempted.clear();
    clearTransientFeedback();
    $("#story-feed").innerHTML = ""; appendStoryEntries(created.story || []); renderState(created.state);
    // A new campaign always begins at the next story beat. Do not carry a
    // previous campaign's long-skip selection or intervention state forward.
    $("#time-unit").value = "moment";
    $("#time-amount").value = "1";
    $("#td-unit").value = "moment";
    $("#td-amount").value = "1";
    syncTimeControl("#time-unit", "#time-amount", null, null, "#time-control-help");
    syncTimeControl("#td-unit", "#td-amount", "#td-amount-field");
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
const CLOUD_MODELS = [
  { id: "gpt-5-nano", label: "Lowest cost · $0.05 input / $0.40 output per 1M tokens" },
  { id: "gpt-4o-mini", label: "Fast background model · $0.15 / $0.60" },
  { id: "gpt-5.6-luna", label: "Recommended balanced GM · $0.20 / $1.20" },
  { id: "gpt-5.4-nano", label: "Compact reasoning · $0.20 / $1.25" },
  { id: "gpt-5-mini", label: "Legacy budget reasoning · $0.25 / $2.00" },
  { id: "gpt-5.4-mini", label: "Stronger mini model · $0.75 / $4.50" },
  { id: "gpt-5.6-terra", label: "High-quality GM · $2.00 / $12.00" },
  { id: "gpt-5.4", label: "High-quality established model · $2.50 / $15.00" },
  { id: "gpt-5.6-sol", label: "Highest-quality GM · $4.00 / $20.00" },
];
const CLOUD_MODEL_SUGGESTIONS = CLOUD_MODELS.map((m) => m.id);

function refreshModelSelectionHelp() {
  const help = $("#model-selection-help");
  if (!help) return;
  const provider = ($$('input[name="provider"]:checked')[0] || {}).value || "local";
  if (provider !== "cloud") {
    help.textContent = "Local model quality and speed depend on your hardware and the model loaded in LM Studio.";
    return;
  }
  const describe = (id) => CLOUD_MODELS.find((m) => m.id === String(id || "").trim())?.label || "Custom model · price estimate unavailable";
  const major = $("#st-major-model")?.value?.trim();
  help.textContent = `Main: ${describe($("#st-main-model").value)} · Background: ${describe($("#st-bg-model").value)}${major ? ` · Major events: ${describe(major)}` : " · Major events inherit Main"}`;
}

function refreshModelSuggestions() {
  const provider = ($$('input[name="provider"]:checked')[0] || {}).value || "local";
  const list = $("#model-suggestions");
  if (provider === "cloud") {
    list.innerHTML = CLOUD_MODELS.map((m) => `<option value="${escapeHtml(m.id)}" label="${escapeHtml(m.label)}">`).join("");
    $("#btn-detect-models").style.display = "none";
    $("#detect-status").textContent = "Cloud mode: choose a preset or mix models. Balanced is the recommended starting point.";
  } else {
    $("#btn-detect-models").style.display = "";
    $("#detect-status").textContent = "Not tested yet.";
  }
  refreshModelSelectionHelp();
}
$$('input[name="provider"]').forEach((r) => r.addEventListener("change", () => {
  refreshModelSuggestions();
  if (r.checked && r.value === "cloud") {
    const main = $("#st-main-model"), background = $("#st-bg-model");
    if (!main.value.trim() || !CLOUD_MODEL_SUGGESTIONS.includes(main.value.trim())) main.value = "gpt-5.6-luna";
    if (!background.value.trim() || !CLOUD_MODEL_SUGGESTIONS.includes(background.value.trim())) background.value = "gpt-4o-mini";
  }
}));
[$("#st-main-model"), $("#st-bg-model"), $("#st-major-model")].forEach((input) => {
  input.addEventListener("input", refreshModelSelectionHelp);
  input.addEventListener("change", refreshModelSelectionHelp);
});

async function openSettingsModal() {
  const s = await apiGet("/api/settings");
  $$('input[name="provider"]').forEach((r) => r.checked = r.value === s.provider);
  $("#st-base-url").value = s.local_base_url || "http://localhost:1234/v1";
  $("#st-token").value = s.local_token || "";
  $("#st-main-model").value = s.model || "";
  $("#st-bg-model").value = s.secondary_model || "";
  $("#st-major-model").value = s.major_event_model || "";
  $("#st-cost-request-limit").value = Number(s.max_ai_cost_per_request_usd || 0);
  $("#st-session-budget").value = Number(s.session_budget_warning_usd ?? 5);
  $("#st-api-key").value = "";
  $("#st-narration").value = s.narration || "Concise";
  $("#st-simulation-mode").value = s.simulation_mode || "balanced";
  $("#st-autosave").checked = !!s.autosave;
  $("#st-sound").checked = !!s.sound_enabled;
  $("#st-music").checked = s.music_enabled !== false;
  $("#st-music-volume").value = Number(s.music_volume ?? .35);
  $("#st-anim").checked = !!s.animations_enabled;
  $("#st-portrait-enabled").checked = s.portrait_generation_enabled !== false;
  $("#st-portrait-auto").checked = s.portrait_auto_generate === true;
  $("#st-canon-foreknowledge").checked = s.canon_foreknowledge === true;
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
    major_event_model: $("#st-major-model").value.trim(),
    max_ai_cost_per_request_usd: Number($("#st-cost-request-limit").value || 0),
    session_budget_warning_usd: Number($("#st-session-budget").value || 0),
    narration: $("#st-narration").value,
    simulation_mode: $("#st-simulation-mode").value,
    autosave: $("#st-autosave").checked,
    sound_enabled: $("#st-sound").checked,
    music_enabled: $("#st-music").checked,
    music_volume: Number($("#st-music-volume").value || .35),
    animations_enabled: $("#st-anim").checked,
    portrait_generation_enabled: $("#st-portrait-enabled").checked,
    portrait_auto_generate: $("#st-portrait-auto").checked,
    canon_foreknowledge: $("#st-canon-foreknowledge").checked,
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
  showToast(`AI mode: ${provider === "cloud" ? "OpenAI Cloud" : "Local LM Studio"} · ${patch.simulation_mode} simulation`, "system");
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
      pill.classList.toggle("over-budget", !!u.over_session_budget);
      pill.title = `${u.total_calls} AI call(s) — main model + background model + ${u.portraits.generated} portrait(s).`
        + (u.cached_input_tokens ? ` ${u.cached_input_tokens.toLocaleString()} input tokens were reported as cached.` : "")
        + (u.cost_is_conservative ? " Cached-input discounts are not subtracted, so this is a conservative ceiling." : "")
        + (u.cost_estimate_complete ? "" : " (one or more models are unpriced; total is a floor, not exact.)");
    }
    if (summary && u.provider === "cloud") {
      summary.textContent = `${u.over_session_budget ? "SESSION WARNING — " : ""}This session so far: ~$${u.total_cost_usd.toFixed(2)} across ${u.total_calls} AI call(s) `
        + `(${u.main.input_tokens + u.main.output_tokens} main-model tokens, ${u.background.input_tokens + u.background.output_tokens} background-model tokens) `
        + `${u.major_is_separate ? `${u.major.input_tokens + u.major.output_tokens} major-event tokens, ` : ""}`
        + `and ${u.portraits.generated} portrait(s).`
        + (u.cached_input_tokens ? ` Cached input reported: ${u.cached_input_tokens.toLocaleString()} tokens.` : "")
        + (u.cost_is_conservative ? " The dollar estimate keeps cached input at full rate, so actual provider billing may be lower." : "")
        + (u.cost_estimate_complete ? "" : " Some pricing is unknown for the selected model(s), so this is a floor, not an exact total.");
    }
  } catch (e) { /* usage is a convenience readout, never block on it */ }
}

const PRESET_MODELS = {
  budget: { model: "gpt-5-nano", secondary_model: "gpt-5-nano", major_event_model: "", image_model: "gpt-image-2", portrait_quality: "low" },
  balanced: { model: "gpt-5.6-luna", secondary_model: "gpt-4o-mini", major_event_model: "", image_model: "gpt-image-2", portrait_quality: "low" },
  quality: { model: "gpt-5.6-terra", secondary_model: "gpt-5.6-luna", major_event_model: "", image_model: "gpt-image-2", portrait_quality: "high" },
  premium: { model: "gpt-5.6-sol", secondary_model: "gpt-5.6-terra", major_event_model: "", image_model: "gpt-image-2", portrait_quality: "high" },
};
function applyModelPreset(name) {
  const p = PRESET_MODELS[name];
  $$('input[name="provider"]').forEach((r) => r.checked = r.value === "cloud");
  $("#st-main-model").value = p.model;
  $("#st-bg-model").value = p.secondary_model;
  $("#st-major-model").value = p.major_event_model;
  $("#st-image-model").value = p.image_model;
  $("#st-portrait-quality").value = p.portrait_quality;
  refreshModelSuggestions();
  showToast(`${name[0].toUpperCase() + name.slice(1)} preset applied — press SAVE to confirm.`, "system");
}
$("#btn-preset-budget").addEventListener("click", () => applyModelPreset("budget"));
$("#btn-preset-balanced").addEventListener("click", () => applyModelPreset("balanced"));
$("#btn-preset-quality").addEventListener("click", () => applyModelPreset("quality"));
$("#btn-preset-premium").addEventListener("click", () => applyModelPreset("premium"));

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
$("#btn-diagnostics-bundle").addEventListener("click", () => downloadEndpoint("/api/diagnostics/bundle"));

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
        clearTransientFeedback();
        $("#story-feed").innerHTML = "";
        appendStoryEntries(res.story.map((s) => ({ text: s.text, tag: s.tag })));
        renderState(res.state);
        closeModal("modal-load");
        showToast(save.kind === "autosave" ? "Autosave recovered." : "Campaign loaded.", "notify");
        maybeFetchReentryRecap(res.state);
      } catch (err) { showToast(err.message, "danger"); }
    });
    li.querySelector("[data-save-recover]")?.addEventListener("click", async () => {
      try { const res = await apiPost("/api/save/recover", { name: save.id }); APP.campaignActive = true; clearTransientFeedback(); $("#story-feed").innerHTML = ""; appendStoryEntries(res.story || []); renderState(res.state); closeModal("modal-load"); showToast("Campaign recovered from its newest autosave.", "notify"); maybeFetchReentryRecap(res.state); }
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
