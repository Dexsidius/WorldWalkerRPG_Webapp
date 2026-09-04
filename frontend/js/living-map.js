"use strict";

/* Production Living Map renderer. Worldwalker remains authoritative: this
   module only adapts GET data and never advances, mutates, or simulates. */
(() => {
  const LM = {
    open: false, mode: "political", scale: 1, x: 0, y: 0, board: "",
    selection: null, data: null, drag: null, movementTimers: [], pollTimer: null, fingerprint: "",
  };
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const norm = (value) => String(value || "").toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, " ").trim();
  const list = (value) => Array.isArray(value) ? value : value && typeof value === "object" ? Object.values(value) : [];
  const hashColor = (name) => {
    let h = 0; for (const ch of String(name || "Unknown")) h = ((h << 5) - h + ch.charCodeAt(0)) | 0;
    return `hsl(${Math.abs(h) % 360} 52% 52%)`;
  };

  function ensureShell() {
    let root = document.getElementById("living-map-shell");
    if (root) return root;
    root = document.createElement("section");
    root.id = "living-map-shell"; root.className = "living-map-shell"; root.hidden = true;
    root.setAttribute("aria-label", "Living world map");
    root.innerHTML = `
      <header class="lm-topbar">
        <div class="lm-brand"><img src="/assets/branding/worldwalker-emblem.png" alt=""><span><b>WORLDWALKER</b><small>Living Map</small></span></div>
        <div class="lm-timeline"><span><small>Canon timeline</small><b id="lm-date">Campaign date</b></span><span class="lm-canon-chip" id="lm-canon">No imminent canon pressure</span></div>
        <div class="lm-actions"><nav class="lm-modes" id="lm-modes" aria-label="Map modes"><button data-mode="political" class="active">Political</button><button data-mode="danger">Danger</button><button data-mode="relationships">Relationships</button><button data-mode="events">Events</button></nav><select class="lm-board-select" id="lm-board" hidden aria-label="Realm map"></select><button class="lm-icon-btn lm-mobile-player" id="lm-player-toggle" hidden title="Character">♙</button><button class="lm-icon-btn lm-close" id="lm-close" title="Close map">×</button></div>
      </header>
      <main class="lm-main">
        <aside class="lm-panel lm-player" id="lm-player"></aside>
        <section class="lm-map-viewport" id="lm-viewport">
          <div class="lm-map-stage" id="lm-stage"><svg class="lm-washes" id="lm-washes" viewBox="0 0 100 100" preserveAspectRatio="none"></svg><svg class="lm-routes" id="lm-routes" viewBox="0 0 100 100" preserveAspectRatio="none"></svg><div class="lm-markers" id="lm-markers"></div></div>
          <span class="lm-zoom-label" id="lm-zoom-label">World view</span>
          <div class="lm-controls"><button data-zoom="in">+</button><button data-zoom="out">−</button><button data-zoom="focus">◉</button><button data-zoom="reset">⤢</button></div>
          <div class="lm-map-legend" id="lm-legend"></div>
        </section>
        <aside class="lm-panel lm-inspector" id="lm-inspector"></aside>
      </main>
      <footer class="lm-dock"><section class="lm-chronicle"><h3>Chronicle</h3><div id="lm-chronicle"></div></section><section class="lm-composer"><h3>Continue your story</h3><p>The map visualizes the campaign. Actions still use Worldwalker's normal freeform queue.</p><div class="lm-composer-row"><button class="lm-write" id="lm-write">Write or choose an action…</button><button id="lm-advance">ADVANCE</button></div></section></footer>`;
    document.body.appendChild(root);
    root.querySelector("#lm-close").addEventListener("click", close);
    root.querySelector("#lm-player-toggle").addEventListener("click", () => root.querySelector("#lm-player").classList.toggle("open"));
    root.querySelector("#lm-modes").addEventListener("click", (event) => { const b=event.target.closest("[data-mode]"); if(!b)return; LM.mode=b.dataset.mode; renderLayers(); });
    root.querySelector("#lm-board").addEventListener("change", (event) => { LM.board=event.target.value; LM.selection=null; render(); });
    root.querySelector("#lm-write").addEventListener("click", () => { close(); setMobileView?.("actions"); document.getElementById("action-input")?.focus(); });
    root.querySelector("#lm-advance").addEventListener("click", () => { close(); document.getElementById(isMobileLayout?.() ? "btn-mobile-advance" : "btn-advance")?.click(); });
    root.querySelector(".lm-controls").addEventListener("click", (event) => { const z=event.target.dataset.zoom; if(!z)return; if(z==="in") zoom(LM.scale*1.3); if(z==="out")zoom(LM.scale/1.3); if(z==="reset")resetView(); if(z==="focus")focusPlayer(); });
    initPanZoom(root.querySelector("#lm-viewport"));
    document.addEventListener("keydown", (event) => { if(LM.open && event.key === "Escape") close(); });
    return root;
  }

  function relationshipRows(data) {
    const view = data.relationships_view || {};
    if (Array.isArray(view)) return view;
    return list(view.people || view.relationships || view.npcs || view);
  }
  function scoreOf(row) { return Number(row.score ?? row.value ?? row.relationship ?? row.affinity ?? row.trust ?? 0) || 0; }
  function sharedRosterNames(data, state) {
    const names = new Set();
    list(data.companions || state.companions).forEach((r) => names.add(norm(typeof r === "string" ? r : r.name)));
    const roster = data.organization_roster || state._organization_roster || {};
    list(roster.groups || roster.organizations || roster).forEach((group) => list(group.members || group.roster).forEach((r) => names.add(norm(typeof r === "string" ? r : r.name))));
    return names;
  }
  function trackedPeople(data, nodes, state) {
    const roster = sharedRosterNames(data,state), memories = state.npc_memories || {}, contacts=state.contacts || {};
    return relationshipRows(data).filter((raw) => {
      const row = raw && typeof raw === "object" ? raw : {name:String(raw)};
      const name = row.name || row.npc || row.character || row.target || "";
      const flags = `${row.role||""} ${row.flags||""} ${row.relationship_type||""}`;
      return Math.abs(scoreOf(row)) >= 20 || roster.has(norm(name)) || row.nemesis === true || /companion|mentor|nemesis/i.test(flags);
    }).map((raw,index) => {
      const row=raw&&typeof raw==="object"?raw:{name:String(raw)}; const name=row.name||row.npc||row.character||row.target||"Unknown";
      const record=memories[name]||contacts[name]||row; const loc=row.location||row.last_known_location||record.location||record.last_known_location||"";
      const anchor=nodes.find((n)=>norm(n.name)===norm(loc)) || nodes.find((n)=>norm(loc).includes(norm(n.name))||norm(n.name).includes(norm(loc)));
      if(!anchor) return null;
      const jitter=((index%5)-2)*.7;
      return {kind:"person",name,role:row.role||record.role||"Known person",score:scoreOf(row),x:Number(anchor.x)+jitter,y:Number(anchor.y)+jitter,location:anchor.name,record};
    }).filter(Boolean);
  }
  function currentBoard(data) {
    const payload=data.map_data||{}, boards=list(payload.boards);
    if(!boards.length) return {name:data.world||APP.state?.world||"World",image:data.map_image,nodes:list(payload.nodes),regions:list(payload.regions)};
    return boards.find((b)=>b.name===LM.board)||boards.find((b)=>b.name===payload.active_board)||boards[0];
  }
  function normalizeData(data) {
    const state=APP.state||{}, board=currentBoard(data), nodes=list(board.nodes||data.map_data?.nodes);
    const regions=list(board.regions||data.map_data?.regions);
    return {data,state,board,nodes,regions,people:trackedPeople(data,nodes,state),events:list(data.world_events).concat(list(data.scheduled_events)).slice(-24)};
  }
  function nextCanon(data,state) {
    const now=Number(data.canon_day??state.canon_day??0);
    return list(data.canon_event_tracker||data.canon_events).filter((e)=>Number(e.day??Infinity)>=now && !e.fired).sort((a,b)=>Number(a.day)-Number(b.day))[0];
  }
  function renderPlayer(ctx) {
    const s=ctx.state, stats=Object.entries(s.stats||{}).slice(0,8);
    const portrait=typeof personPortraitHtml==="function"?personPortraitHtml(s.name||"Traveler",s,{size:"lg"}):`<span>${esc((s.name||"?")[0])}</span>`;
    document.getElementById("lm-player").innerHTML=`<span class="lm-panel-kicker">Player character</span><div class="lm-player-card">${portrait}<div><h2>${esc(s.name||"Traveler")}</h2><p>${esc(s.class_name||s.archetype||s.special?.Archetype||"Adventurer")}</p><p>${esc(s.location||"Unknown location")}</p></div></div><div class="lm-stat-grid">${stats.map(([k,v])=>`<div class="lm-stat"><small>${esc(k)}</small><b>${esc(typeof v==="object"?(v.value??v.rank??"—"):v)}</b></div>`).join("")}</div><section class="lm-section"><h3>Current state</h3><div class="lm-list"><article><b>${esc(Array.isArray(s.status)?s.status.join(", "):(s.status||"Normal"))}</b><small>${esc(s.world_time||"")}</small></article><article><b>${esc(s._tension?.label||"Calm")}</b><small>${esc(s.current_goal||s.goal||"No immediate objective recorded")}</small></article></div></section>`;
  }
  function renderHeader(ctx) {
    const next=nextCanon(ctx.data,ctx.state);
    document.getElementById("lm-date").textContent=ctx.state.world_time||`Day ${ctx.data.canon_day??ctx.state.canon_day??0}`;
    document.getElementById("lm-canon").textContent=next?`${next.title||"Canon event"} · ${Math.max(0,Number(next.day)-Number(ctx.data.canon_day??0))} days`:`Canon follows the changed timeline`;
    const select=document.getElementById("lm-board"), boards=list(ctx.data.map_data?.boards); select.hidden=!boards.length;
    if(boards.length){select.innerHTML=boards.map((b)=>`<option value="${esc(b.name)}"${b.name===ctx.board.name?" selected":""}>${esc(b.name)}${b.name===ctx.data.map_data?.active_board?" · here":""}</option>`).join("");}
  }
  function markerHtml(item,index) {
    const current=item.current?" current":""; const major=/capital|city|village|nation|region|realm|island/i.test(item.kind||"")?" major":"";
    return `<button class="lm-marker ${esc(item.kind||"location")}${current}${major}" data-marker="${index}" style="left:${Number(item.x)||50}%;top:${Number(item.y)||50}%"><i class="lm-marker-dot"></i><span class="lm-marker-label">${esc(item.name)}</span></button>`;
  }
  function renderLayers() {
    const ctx=LM.data;if(!ctx)return; const stage=document.getElementById("lm-stage");stage.dataset.mode=LM.mode;
    document.querySelectorAll("#lm-modes button").forEach((b)=>b.classList.toggle("active",b.dataset.mode===LM.mode));
    const regions=ctx.regions.length?ctx.regions:ctx.nodes.filter((n)=>n.controller&&n.controller!=="Unknown");
    let washes="<defs>";regions.forEach((r,i)=>{const color=hashColor(r.controller||r.name);washes+=`<radialGradient id="lmw${i}"><stop offset="0" stop-color="${color}" stop-opacity=".58"/><stop offset=".63" stop-color="${color}" stop-opacity=".22"/><stop offset="1" stop-color="${color}" stop-opacity="0"/></radialGradient>`});washes+="</defs>";
    if(LM.mode==="political") regions.forEach((r,i)=>{washes+=`<ellipse cx="${Number(r.x)||50}" cy="${Number(r.y)||50}" rx="${Math.max(5,Number(r.size)||12)}" ry="${Math.max(4,(Number(r.size)||12)*.68)}" fill="url(#lmw${i})"/>`});
    if(LM.mode==="danger") ctx.nodes.filter((n)=>n.danger_level).forEach((n)=>{const color=/critical|high/i.test(n.danger_level)?"#ef492f":"#e6a33d";washes+=`<circle cx="${n.x}" cy="${n.y}" r="10" fill="${color}" opacity=".28"/>`});
    document.getElementById("lm-washes").innerHTML=washes;
    const eventItems=ctx.events.map((e)=>{const anchor=ctx.nodes.find((n)=>norm(e.location||e.region).includes(norm(n.name))||norm(n.name).includes(norm(e.location||e.region)));return anchor?{...e,kind:"event",name:e.title||e.name||"World event",x:anchor.x,y:anchor.y,location:anchor.name}:null}).filter(Boolean);
    const here=ctx.nodes.find((n)=>n.current);
    const player=here?{kind:"player",name:ctx.state.name||"Player",role:ctx.state.class_name||ctx.state.special?.Archetype||"Player character",x:Number(here.x),y:Number(here.y)-1.2,location:here.name,current:true}:null;
    LM.items=[...ctx.nodes.map((n)=>({...n,kind:"location"})),...(player?[player]:[]),...ctx.people,...eventItems];
    let visible=LM.items;if(LM.mode==="relationships")visible=visible.filter((x)=>x.kind==="person"||x.current);if(LM.mode==="events")visible=visible.filter((x)=>x.kind==="event"||x.current);
    const markerRoot=document.getElementById("lm-markers");markerRoot.innerHTML=visible.map((item)=>markerHtml(item,LM.items.indexOf(item))).join("");
    markerRoot.querySelectorAll("[data-marker]").forEach((button)=>button.addEventListener("click",()=>selectItem(LM.items[Number(button.dataset.marker)],button)));
    const controllers=[...new Set(regions.map((r)=>r.controller).filter(Boolean))];document.getElementById("lm-legend").innerHTML=controllers.map((c)=>`<span><i style="background:${hashColor(c)}"></i>${esc(c)}</span>`).join("");
    renderRoutes(ctx); animateKnownTravel(ctx); animateMarkerChanges(ctx);
  }
  function renderRoutes(ctx) {
    const edges=ctx.data.travel_graph?.edges||{};let out="";
    Object.entries(edges).slice(0,60).forEach(([from,tos])=>{const a=ctx.nodes.find((n)=>norm(n.name)===norm(from));if(!a)return;list(tos).forEach((to)=>{const name=typeof to==="string"?to:(to.to||to.name);const b=ctx.nodes.find((n)=>norm(n.name)===norm(name));if(b)out+=`<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="#d7bd7a" stroke-opacity=".18" stroke-width=".28" stroke-dasharray="1 1.3"/>`})});
    document.getElementById("lm-routes").innerHTML=out;
  }
  function animateKnownTravel(ctx) {
    LM.movementTimers.forEach(clearTimeout);LM.movementTimers=[];
    const travel=ctx.state.travel||ctx.state.active_travel||ctx.state.planned_route||null;if(!travel)return;
    const from=ctx.nodes.find((n)=>norm(n.name)===norm(travel.from||travel.origin));const to=ctx.nodes.find((n)=>norm(n.name)===norm(travel.to||travel.destination));if(!from||!to)return;
    const player=document.querySelector(".lm-marker.player,.lm-marker.current");if(!player)return;player.classList.add("is-moving");player.style.left=`${from.x}%`;player.style.top=`${from.y}%`;
    LM.movementTimers.push(setTimeout(()=>{player.style.left=`${to.x}%`;player.style.top=`${to.y}%`;},120));
  }
  function animateMarkerChanges(ctx) {
    const campaign=ctx.state.campaign_id||`${ctx.state.world||"world"}:${ctx.state.name||"player"}`;
    LM.items.filter((item)=>item.kind==="player"||item.kind==="person").forEach((item,index)=>{
      const key=`worldwalker_map_piece:${campaign}:${norm(item.name)}`;
      let previous=null;try{previous=JSON.parse(sessionStorage.getItem(key)||"null");}catch(_){previous=null;}
      const current={x:Number(item.x)||50,y:Number(item.y)||50};
      try{sessionStorage.setItem(key,JSON.stringify(current));}catch(_){}
      if(!previous||Math.hypot(current.x-Number(previous.x),current.y-Number(previous.y))<.2)return;
      const itemIndex=LM.items.indexOf(item), marker=document.querySelector(`[data-marker="${itemIndex}"]`);if(!marker)return;
      marker.classList.add("is-moving");marker.style.left=`${Number(previous.x)||current.x}%`;marker.style.top=`${Number(previous.y)||current.y}%`;
      LM.movementTimers.push(setTimeout(()=>{marker.style.left=`${current.x}%`;marker.style.top=`${current.y}%`;},90));
      LM.movementTimers.push(setTimeout(()=>marker.classList.remove("is-moving"),1450));
    });
  }
  function selectItem(item,button) {
    LM.selection=item;document.querySelectorAll(".lm-marker").forEach((m)=>m.classList.toggle("selected",m===button));
    const lines=[];if(item.location)lines.push(["Location",item.location]);if(item.controller)lines.push(["Control",item.controller]);if(item.role)lines.push(["Role",item.role]);if(item.score!=null)lines.push(["Relationship",item.score]);if(item.danger_level)lines.push(["Danger",item.danger_level]);if(item.kind)lines.push(["Type",item.kind]);
    const summary=item.summary||item.description||item.record?.summary||item.record?.last_interaction||"This is part of the living campaign state.";
    const panel=document.getElementById("lm-inspector");panel.innerHTML=`<span class="lm-panel-kicker">${esc(item.kind||"Map detail")}</span><h2>${esc(item.name||item.title||"Unknown")}</h2><p>${esc(summary)}</p><dl>${lines.map(([k,v])=>`<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}</dl>`;if(isMobileLayout?.())panel.classList.add("open");
  }
  function renderInspector(ctx){const current=ctx.nodes.find((n)=>n.current);if(current){selectItem({...current,kind:"location"},null);if(isMobileLayout?.())document.getElementById("lm-inspector").classList.remove("open");}else document.getElementById("lm-inspector").innerHTML=`<span class="lm-panel-kicker">World pulse</span><h2>${esc(ctx.board.name||ctx.data.world)}</h2><p>${esc(ctx.data.map_data?.meta?.accuracy_note||"Select a marker to inspect the living world.")}</p>`;}
  function renderChronicle(ctx){const rows=list(ctx.state.story||ctx.state.chronicle||ctx.state.history).slice(-10).reverse();document.getElementById("lm-chronicle").innerHTML=rows.length?rows.map((r)=>`<article><time>${esc(r.date||r.turn||"")}</time><span>${esc(r.text||r.content||r.narrative||r.message||String(r))}</span></article>`).join(""):`<article><time>Now</time><span>The living world is ready.</span></article>`;}
  function render(){const ctx=LM.data;if(!ctx)return;const fresh=normalizeData(ctx.data);LM.data=fresh;document.getElementById("lm-stage").style.backgroundImage=`linear-gradient(#02040626,#0204063d),url("${String(fresh.board.image||fresh.data.map_image||"").replace(/"/g,"%22")}")`;renderHeader(fresh);renderPlayer(fresh);renderLayers();renderInspector(fresh);renderChronicle(fresh);applyView();}
  function applyView(){const stage=document.getElementById("lm-stage");if(stage)stage.style.transform=`translate(${LM.x}px,${LM.y}px) scale(${LM.scale})`;const label=document.getElementById("lm-zoom-label");if(label)label.textContent=LM.scale>=2.8?"Local view":LM.scale>=1.65?"Regional view":"World view";}
  function zoom(value,cx,cy){const view=document.getElementById("lm-viewport");if(!view)return;const old=LM.scale,next=Math.max(1,Math.min(5,value));const x=cx??view.clientWidth/2,y=cy??view.clientHeight/2;LM.x=x-(x-LM.x)/old*next;LM.y=y-(y-LM.y)/old*next;LM.scale=next;clamp();applyView();}
  function clamp(){const v=document.getElementById("lm-viewport");if(!v)return;LM.x=Math.min(0,Math.max(v.clientWidth*(1-LM.scale),LM.x));LM.y=Math.min(0,Math.max(v.clientHeight*(1-LM.scale),LM.y));}
  function resetView(){LM.scale=1;LM.x=0;LM.y=0;applyView();}
  function focusPlayer(){const n=LM.data?.nodes.find((x)=>x.current);if(!n)return;zoom(Math.max(2,LM.scale));const v=document.getElementById("lm-viewport");LM.x=v.clientWidth/2-v.clientWidth*(n.x/100)*LM.scale;LM.y=v.clientHeight/2-v.clientHeight*(n.y/100)*LM.scale;clamp();applyView();}
  function initPanZoom(view){view.addEventListener("pointerdown",(e)=>{if(e.target.closest(".lm-marker"))return;document.querySelectorAll(".lm-panel.open").forEach((p)=>p.classList.remove("open"));LM.drag={id:e.pointerId,x:e.clientX,y:e.clientY};view.setPointerCapture(e.pointerId)});view.addEventListener("pointermove",(e)=>{if(!LM.drag)return;LM.x+=e.clientX-LM.drag.x;LM.y+=e.clientY-LM.drag.y;LM.drag.x=e.clientX;LM.drag.y=e.clientY;clamp();applyView()});const end=()=>LM.drag=null;view.addEventListener("pointerup",end);view.addEventListener("pointercancel",end);view.addEventListener("wheel",(e)=>{e.preventDefault();const r=view.getBoundingClientRect();zoom(LM.scale*(e.deltaY<0?1.16:1/1.16),e.clientX-r.left,e.clientY-r.top)},{passive:false});}
  function dataFingerprint(data){return JSON.stringify([APP.state?.campaign_id,APP.state?.turn,APP.state?.location,data.map_data,data.world_events,data.relationships_view,data.travel_graph]);}
  async function poll(){if(!LM.open||document.hidden)return;try{const data=await apiGet("/api/panels");const fp=dataFingerprint(data);if(fp!==LM.fingerprint){LM.fingerprint=fp;LM.data={data};render();}}catch(_){} }
  async function open() {
    const root=ensureShell();root.hidden=false;LM.open=true;document.body.classList.add("living-map-open");
    if (isMobileLayout?.()) {
      document.body.setAttribute("data-mobile-view", "map");
      const advanceDock=document.getElementById("mobile-advance-dock"); if(advanceDock){advanceDock.hidden=true;advanceDock.style.setProperty("display","none","important");}
    }
    try{const data=await apiGet("/api/panels");LM.fingerprint=dataFingerprint(data);LM.data={data};render();clearInterval(LM.pollTimer);LM.pollTimer=setInterval(poll,2000);}catch(error){document.getElementById("lm-inspector").innerHTML=`<h2>Map unavailable</h2><p>${esc(error.message)}</p>`;}
  }
  function close(){const root=ensureShell();root.hidden=true;LM.open=false;clearInterval(LM.pollTimer);LM.pollTimer=null;document.body.classList.remove("living-map-open");document.querySelectorAll(".lm-panel.open").forEach((p)=>p.classList.remove("open"));if(isMobileLayout?.()){const advanceDock=document.getElementById("mobile-advance-dock");if(advanceDock)advanceDock.style.removeProperty("display");setMobileView(APP.mobileView||"chronicle",false);renderMobileState?.(APP.state||{});}}
  window.WorldwalkerLivingMap={open,close,refresh:async()=>{if(LM.open)await open()},state:LM};
})();
