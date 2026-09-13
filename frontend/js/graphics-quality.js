/* Device-local presentation preferences; never campaign or combat rules. */
window.WorldwalkerGraphics = (() => {
  const key='worldwalker.graphics.v1', media=matchMedia('(max-width: 850px)');
  let choice='auto';try{choice=localStorage.getItem(key)||'auto';}catch{}
  if(!['auto','high','low'].includes(choice))choice='auto';
  const low=()=>choice==='low'||choice==='auto'&&(media.matches||navigator.connection?.saveData===true);
  function apply(){document.documentElement.dataset.graphicsQuality=low()?'low':'high';document.querySelectorAll('select[data-graphics-quality]').forEach(s=>s.value=choice);window.dispatchEvent(new Event('worldwalker-graphics-change'));}
  function set(value){if(!['auto','high','low'].includes(value))return;choice=value;try{localStorage.setItem(key,choice);}catch{}apply();}
  function control(host){if(!host||host.querySelector('select[data-graphics-quality]'))return;const label=document.createElement('label');label.className='graphics-quality';label.append('Graphics ');const select=document.createElement('select');select.dataset.graphicsQuality='';select.setAttribute('aria-label','Graphics quality');for(const [value,text]of [['auto','Auto · low on phones'],['high','High · 3D and effects'],['low','Low · 2D, light effects']])select.add(new Option(text,value));select.value=choice;select.addEventListener('change',()=>set(select.value));label.append(select);host.append(label);}
  media.addEventListener('change',apply);window.addEventListener('storage',e=>{if(e.key===key){choice=['auto','high','low'].includes(e.newValue)?e.newValue:'auto';apply();}});
  const style=document.createElement('style');style.textContent='.graphics-quality{display:inline-flex;gap:5px;align-items:center;font:12px/1.3 Arial;max-width:100%;flex-wrap:wrap}.graphics-quality select{max-width:100%;min-height:36px;background:#15272d;color:#f3e4ba;border:1px solid #8d784e;border-radius:4px;padding:4px}html[data-graphics-quality="low"] .map-person,html[data-graphics-quality="low"] .piece{transition:none!important}html[data-graphics-quality="low"] .atlas-control-change{animation:none!important}html[data-graphics-quality="low"] .atlas-scenery{display:none!important}';document.head.append(style);apply();
  const theme=document.createElement('link');theme.rel='stylesheet';theme.href='/css/dream-worlds.css?v=3.64.0-dream-mobile-1';document.head.append(theme);
  return {low,set,control,get:()=>choice};
})();
