/* Observed encounter scenes. All mutations use the signed activity workflow. */
window.CampaignEncounters = (() => {
  'use strict';
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let hub, dialog, data, selected='', revision=0, timer, campaign, painted='', stageKey='';
  const scenes=()=>data ? [...(data.encounters?.active?[{...data.encounters.active,key:'original'}]:[]),...(data.canon_encounters||[])] : [];
  function mount(){
    const host=document.querySelector('.col-right');if(!host)return false;
    if(!hub?.isConnected){
      hub=document.createElement('section');hub.id='campaign-encounter-hub';hub.className='panel encounter-hub';hub.hidden=true;host.prepend(hub);
    }
    return true;
  }
  function choices(scene){
    return (data?.actions||[]).filter(a=>scene.key==='original'?a.id.startsWith('encounter:'):a.id.startsWith('worldevent:')&&a.id.split(':').at(-1)===scene.key);
  }
  function ensureDialog(){
    if(dialog)return dialog;
    dialog=document.createElement('dialog');dialog.id='campaign-encounter';dialog.className='encounter-window';dialog.setAttribute('aria-labelledby','encounter-heading');document.body.append(dialog);
    dialog.addEventListener('close',()=>{selected='';});
    return dialog;
  }
  function paintScene(){
    const scene=scenes().find(s=>s.key===selected);if(!scene){dialog?.close();return;}
    const d=ensureDialog(),focus=d.querySelector(':focus')?.dataset.encounterChoice;
    const nextStage=JSON.stringify([campaign,selected,scene.stage]);
    const signature=JSON.stringify([data.world,data.place,data.scene_image,scene,choices(scene)]);
    if(signature===painted)return;
    painted=signature;
    d.dataset.world=data.world;
    const image=/^\/assets\//.test(data.scene_image||'')?`<img src="${esc(data.scene_image)}" alt="${esc(data.place)}" class="encounter-scene-art">`:'';
    const options=choices(scene);
    d.innerHTML=`<header class="encounter-header"><div><small>${esc(scene.kind)} · ${esc(scene.stage.replaceAll('_',' '))}</small><h2 id="encounter-heading">${esc(scene.title)}</h2></div><button type="button" data-encounter-close aria-label="Close encounter">×</button></header>
      <div class="encounter-layout"><aside class="encounter-dossier"><small>HERE & NOW</small><h3>${esc(data.place)}</h3><p>${esc(scene.person||'Local participants')}</p><hr><small>WHY THIS APPEARED</small><p>${esc(scene.basis)}</p><p class="encounter-muted">${esc(scene.authorship)}</p><button type="button" data-encounter-map>View this location</button></aside>
      <main class="encounter-story">${image}<article class="encounter-page"><small>${scene.stage==='aftermath'?'AFTERMATH':scene.stage==='decision'?'WHAT YOU KNOW':'THE ENCOUNTER'}</small><p>${esc(scene.narrative)}</p>${scene.available===false?'<p role="status">The participant is no longer available here. You can leave this encounter without a new penalty.</p>':''}${scene.changes?.length?`<section class="encounter-changes"><h3>What changed</h3>${scene.changes.map(c=>`<p>${esc(c)}</p>`).join('')}</section>`:''}${scene.history?.length>1?`<details><summary>Earlier in this encounter</summary>${scene.history.slice(0,-1).map(h=>`<h4>${esc(h.title)}</h4><p>${esc(h.text)}</p>`).join('')}</details>`:''}</article></main>
      <section class="encounter-decisions" aria-label="Encounter choices"><small>YOUR NEXT STEP</small><p class="encounter-muted">Review the time and confirm. Nothing happens just by opening a choice.</p>${options.map(a=>`<button type="button" data-encounter-choice="${esc(a.id)}"><b>${esc(a.label)}</b><span>${esc(LivingAdventures.duration(a.minutes))}${a.cost?` · ${esc(a.cost)} ${esc(a.currency)}`:''}</span></button>`).join('')||`<p>${scene.stage==='combat'?'Finish the active tactical battle to resolve this encounter.':'No encounter action is available now. Finish or cancel any paused activity first.'}</p>`}<p class="encounter-muted">You can close this window and return later. The campaign clock still applies.</p></section></div>`;
    d.querySelector('[data-encounter-close]').onclick=()=>d.close();
    d.querySelector('[data-encounter-map]').onclick=()=>{d.close();if(typeof setMobileView==='function'&&isMobileLayout())setMobileView('map');else document.getElementById('workspace-map-tab')?.click();LivingAdventures.showLocation(data.place);};
    d.querySelectorAll('[data-encounter-choice]').forEach(b=>b.onclick=()=>LivingAdventures.preview({place:data.place,action:b.dataset.encounterChoice}));
    d.querySelector('img')?.addEventListener('error',e=>{e.target.hidden=true;},{once:true});
    if(focus)[...d.querySelectorAll('[data-encounter-choice]')].find(b=>b.dataset.encounterChoice===focus)?.focus({preventScroll:true});
    if(stageKey!==nextStage){
      stageKey=nextStage;d.scrollTop=0;
      const heading=d.querySelector('#encounter-heading');heading.tabIndex=-1;
      if(d.open)heading.focus({preventScroll:true});
    }
  }
  function open(key){selected=key;paintScene();if(selected&&!dialog.open)dialog.showModal();}
  function paint(){
    if(!mount())return;
    const rows=scenes();const offers=(data?.encounters?.offers||[]).filter(o=>(data.actions||[]).some(a=>a.id===o.action));
    hub.hidden=!rows.length&&!offers.length;
    hub.innerHTML=`<header class="panel-head"><span>ENCOUNTERS</span><small>${esc(data?.place)}</small></header><div class="encounter-leads">${rows.map(s=>`<button type="button" data-encounter-open="${esc(s.key)}"><small>${esc(s.stage==='aftermath'?'Outcome recorded':s.kind)}</small><b>${esc(s.title)}</b><span>Open encounter →</span></button>`).join('')}${offers.map(o=>`<button type="button" data-encounter-begin="${esc(o.action)}"><small>${esc(o.basis)}</small><b>${esc(o.title)}</b><span>Review invitation · 15 min →</span></button>`).join('')}</div>`;
    hub.querySelectorAll('[data-encounter-open]').forEach(b=>b.onclick=()=>open(b.dataset.encounterOpen));
    hub.querySelectorAll('[data-encounter-begin]').forEach(b=>b.onclick=()=>LivingAdventures.preview({place:data.place,action:b.dataset.encounterBegin}));
    if(dialog?.open){if(APP.state?.combat?.active)dialog.close();else paintScene();}
  }
  async function refresh(){
    const run=++revision,id=APP.state?.campaign_id;
    if(!id||APP.state?.multiplayer?.active||APP.state?.combat?.active){data=null;if(hub)hub.hidden=true;dialog?.close();return;}
    if(campaign!==id){dialog?.close();data=null;if(hub)hub.hidden=true;campaign=id;}
    try{
      const result=await apiGet('/api/adventures/location');
      if(run!==revision||id!==APP.state?.campaign_id)return;
      data=result;paint();
    }catch{if(run===revision){data=null;if(hub)hub.hidden=true;dialog?.close();}}
  }
  function onState(){clearTimeout(timer);timer=setTimeout(refresh,80);}
  return Object.freeze({onState,refresh,open});
})();
