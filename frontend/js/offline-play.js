/* Choice-only adapter. The current Chronicle, atlas and tactical UI stay native. */
window.OfflinePlay = (() => {
  'use strict';
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let panel, creator, metadata, active='Adventure', revision=0, scheduled;
  const categories=['Adventure','Encounters','People','Work','Life','Mastery','Economy','Politics','World'];
  const category=a=>a.category||(/^(train:|path:)/.test(a.id)?'Mastery':/^(purchase:|property:|craft:)/.test(a.id)?'Economy':/^(conflict:|reputation:)/.test(a.id)?'World':a.id.startsWith('talk:')?'People':'Adventure');
  const editable='textarea,input:not([type]),input[type=text],input[type=search],input[type=email],input[type=password],input[type=url],input[type=number],[contenteditable]';
  const watched=new WeakSet();
  function guard(doc){
    if(!doc?.documentElement)return;
    const clean=()=>{
      for(const form of doc.querySelectorAll('.atlas-search'))if(!form.querySelector('[data-offline-map-choice]')){
        const input=form.querySelector('input'),options=[...form.querySelectorAll('datalist option')];
        if(input&&options.length){const select=doc.createElement('select');select.dataset.offlineMapChoice='';select.setAttribute('aria-label','Choose a mapped location');select.innerHTML='<option value="">Choose a mapped location</option>'+options.map(o=>`<option value="${esc(o.value)}">${esc(o.value)}</option>`).join('');input.after(select);select.onchange=()=>{input.value=select.value;if(select.value)form.requestSubmit();};}
      }
      for(const el of doc.querySelectorAll(editable)){
        if(el.tagName==='INPUT'||el.tagName==='TEXTAREA'){if(!el.readOnly)el.readOnly=true;if(!el.disabled)el.disabled=true;}
        else if(el.getAttribute('contenteditable')!=='false')el.setAttribute('contenteditable','false');
        if(!el.hidden)el.hidden=true;
      }
      for(const frame of doc.querySelectorAll('iframe'))if(!watched.has(frame)){
        watched.add(frame);frame.addEventListener('load',()=>{try{guard(frame.contentDocument);}catch{}});
        try{guard(frame.contentDocument);}catch{}
      }
    };
    clean();if(watched.has(doc))return;watched.add(doc);
    new MutationObserver(clean).observe(doc.documentElement,{childList:true,subtree:true});
    doc.addEventListener('beforeinput',e=>{if(e.target.matches?.(editable))e.preventDefault();},true);
  }
  function mount(){
    if(panel?.isConnected)return;
    const host=document.querySelector('.col-right');if(!host)return;
    panel=document.createElement('section');panel.className='panel offline-play';panel.id='offline-play';
    panel.innerHTML='<header class="panel-head"><span>LIVE YOUR STORY</span><small>OFFLINE · CHOICES ONLY</small></header><div class="offline-intro"></div><nav class="offline-categories" aria-label="Activity categories"></nav><div class="offline-actions" aria-live="polite"></div>';
    host.prepend(panel);
    panel.querySelector('nav').innerHTML=categories.map(c=>`<button type="button" data-category="${c}">${c}</button>`).join('');
    panel.querySelectorAll('[data-category]').forEach(b=>b.onclick=()=>{active=b.dataset.category;refresh();});
  }
  async function refresh(){
    mount();if(!panel)return;const s=APP.state;
    if(!s?.campaign_id){panel.querySelector('.offline-intro').innerHTML='<p>Choose a world and begin an independent life.</p><button type="button" data-begin>Begin a life</button>';panel.querySelector('[data-begin]').onclick=create;return;}
    const run=++revision;
    try{
      const [v,life]=await Promise.all([apiGet('/api/adventures/location?place='+encodeURIComponent(s.location)),apiGet('/api/offline/life')]);
      if(run!==revision||s.campaign_id!==APP.state?.campaign_id)return;
      panel.querySelector('.offline-intro').innerHTML=`<h2>${esc(s.location)}</h2><p>${esc(life.ambition)}${life.ambition_complete?' · ACHIEVED':''}</p><small>${life.career} work shifts · ${life.stories_completed} local stories · ${life.legacy.length} legacy milestones</small><p>Choose an activity, review its time and consequences, then confirm. Select another place on the map to travel.</p><button type="button" data-map>Open local map details</button>`;
      panel.querySelector('[data-map]').onclick=()=>{document.getElementById('workspace-map-tab')?.click();if(typeof setMobileView==='function'&&isMobileLayout())setMobileView('map');LivingAdventures.showLocation(s.location);};
      const all=v.actions||[];
      const rows=all.filter(a=>category(a)===active||(active==='Adventure'&&a.category==='Local story')||/^(activity:|journey:)/.test(a.id));
      panel.querySelectorAll('[data-category]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.category===active)));
      panel.querySelector('.offline-actions').innerHTML=s.combat?.active?'<p>A battle is in progress. Use the tactical board to act, move, defend, or retreat.</p>':rows.length?rows.map(a=>`<button type="button" class="offline-choice" data-activity="${esc(a.id)}"><b>${esc(a.label)}</b><small>${esc(LivingAdventures.duration(a.minutes))}${a.cost?' · '+esc(a.cost)+' '+esc(a.currency):''}</small>${a.description?`<span>${esc(a.description)}</span>`:''}</button>`).join(''):`<p>${active==='People'?'Meet a local contact under People when one is available. Travel to find other communities.':'No activities in this category are available here yet. Try Adventure, Work, or another mapped location.'}</p>`;
      panel.querySelectorAll('[data-activity]').forEach(b=>b.onclick=()=>LivingAdventures.preview({place:s.location,action:b.dataset.activity}));
      if(active==='Politics' && life.politics){
        const p=life.politics, summary=document.createElement('p');
        summary.textContent=Object.entries(p.support||{}).map(([group,value])=>`${group}: ${value}/60`).join(' · ')+(p.mandate?` · ${p.mandate}`:'')+(p.pending?' · Petition awaiting review':'')+(p.government?.last_decision?` · ${p.government.owner}: ${p.government.last_decision}`:'');
        panel.querySelector('.offline-actions').prepend(summary);
      }
    }catch(e){if(run===revision)panel.querySelector('.offline-actions').textContent=e.message;}
  }
  function requestRefresh(){clearTimeout(scheduled);scheduled=setTimeout(refresh,80);}
  async function create(){
    metadata=metadata||await apiGet('/api/offline/creation');
    if(!creator){creator=document.createElement('dialog');creator.className='adventure-dialog offline-creator';creator.id='offline-creator';document.body.append(creator);}
    const select=(key,label,items)=>`<label>${label}<select name="${key}">${items.map(x=>`<option value="${esc(typeof x==='object'?x.value:x)}">${esc(typeof x==='object'?x.label:x)}</option>`).join('')}</select></label>`;
    creator.innerHTML=`<small>AN INDEPENDENT LIFE</small><h2>Choose who you become</h2><p>Your origin sets your starting opportunities. Your actions determine your relationships, livelihood, and influence.</p><form>${select('world','World',Object.keys(metadata.worlds))}${select('name','Name',metadata.names)}${select('age','Starting age',metadata.ages)}${select('background','Personal history',metadata.backgrounds)}${select('difficulty','Difficulty',metadata.difficulties)}<div data-world-choices></div><p role="alert" data-create-error></p><footer><button type="button" data-cancel>Cancel</button><button type="submit" class="primary">Begin this life</button></footer></form>`;
    const form=creator.querySelector('form');
    const update=()=>{const c=metadata.worlds[form.elements.world.value];creator.querySelector('[data-world-choices]').innerHTML=select('origin','Origin',c.origins)+select('archetype','Calling',c.archetypes)+select('start_location','Home',c.starts.map(x=>({value:x.location,label:x.label})))+select('starting_era_id','Era',c.eras.map(x=>({value:x.id,label:x.label})));};
    form.elements.difficulty.value='Adventurer';form.elements.world.value=metadata.worlds['One Piece']?'One Piece':Object.keys(metadata.worlds)[0];update();form.elements.world.onchange=update;
    creator.querySelector('[data-cancel]').onclick=()=>creator.close();
    form.onsubmit=async e=>{e.preventDefault();const b=form.querySelector('[type=submit]');b.disabled=true;b.textContent='Beginning your life…';
      try{const payload=Object.fromEntries(new FormData(form));payload.age=Number(payload.age);const r=await apiPost('/api/offline/create',payload);creator.close();location.reload();}
      catch(err){creator.querySelector('[data-create-error]').textContent=err.message;b.disabled=false;b.textContent='Begin this life';}
    };
    if(!creator.open)creator.showModal();
  }
  openNewCampaignModal=create;
  aiStatusLabel=()=> 'OFFLINE · READY';
  const originalBusy=setBusy;
  setBusy=function(b){originalBusy(b);document.getElementById('hdr-ai').textContent=b?'RESOLVING…':'OFFLINE · READY';};
  const originalMenu=runMenuAction;
  runMenuAction=async function(action){
    if(action!=='help')return originalMenu(action);
    let help=document.getElementById('offline-help');
    if(!help){help=document.createElement('dialog');help.id='offline-help';help.className='adventure-dialog';help.innerHTML='<h2>Live your story</h2><p><b>Adventure:</b> investigate local problems, choose a peaceful approach or enter a tactical battle. Different outcomes leave persistent changes.</p><p><b>Build a life:</b> work for income, meet a contact, earn their trust, form a company, study, own property, and teach an apprentice. Life activities advance the same calendar as your adventures.</p><p><b>Travel:</b> open Living Map and select a destination. Review a mapped route, its cost and access requirements, then confirm.</p><p><b>Every choice:</b> review time and costs first. Canceling a preview changes nothing. Events can interrupt long activities; continue or cancel the unfinished task afterward.</p><p><b>Battle:</b> select an ability, target or movement tile on the board. Follow the stated objective. Retreat is a valid choice.</p><p><b>Your record:</b> the Chronicle records resolved events. Game → Save/Load/Export keeps your life available offline. No account, model, or typing is needed.</p><button type="button">Return to game</button>';help.querySelector('button').onclick=()=>help.close();document.body.append(help);}
    help.showModal();
  };
  openActionDeck=()=>{active='Adventure';refresh();document.getElementById('offline-play')?.scrollIntoView({block:'nearest'});if(typeof setMobileView==='function')setMobileView('actions');};
  openNpcChat=async()=>{active='People';await refresh();if(typeof setMobileView==='function'&&isMobileLayout())setMobileView('actions');panel?.scrollIntoView({block:'nearest'});};
  const originalRender=renderState;
  renderState=function(...args){const r=originalRender.apply(this,args);requestRefresh();return r;};
  document.addEventListener('DOMContentLoaded',()=>{guard(document);mount();requestRefresh();});
  if(document.readyState!=='loading'){guard(document);mount();requestRefresh();}
  return {refresh:requestRefresh,create};
})();
