/* Approved Dream scenery mounted in the existing campaign projection. */
import * as T from '../vendor/three/three.module.js';
import {batchStatic} from './scenery-batching.js';
export const SUPPORTED_WORLDS=['Naruto','One Piece'];
export const supports=a=>SUPPORTED_WORLDS.includes(String(a?.id||'').split(':')[0]);
export function inside(x,y,p){let b=false;for(let i=0,j=p.length-1;i<p.length;j=i++){const[a,c]=p[i],[d,e]=p[j];if((c>y)!=(e>y)&&x<(d-a)*(y-c)/(e-c)+a)b=!b;}return b;}
const live=new WeakMap();
export async function mount(plane,atlas,ownerColor){
 live.get(plane)?.dispose();
 if(!supports(atlas)||!plane.isConnected||window.WorldwalkerGraphics?.low())return null;
 const world=atlas.id.split(':')[0],scene=new T.Scene();scene.background=new T.Color(world==='Naruto'?'#164958':'#074969');
 const camera=new T.OrthographicCamera(-80,80,50,-50,.1,500);camera.position.set(0,160,120);camera.lookAt(0,0,0);
 let renderer;try{renderer=new T.WebGLRenderer({alpha:true,antialias:true,powerPreference:'low-power'});}catch{return null;}
 renderer.outputColorSpace=T.SRGBColorSpace;renderer.toneMapping=T.ACESFilmicToneMapping;renderer.toneMappingExposure=world==='Naruto'?1.3:1.2;renderer.shadowMap.enabled=true;renderer.shadowMap.type=T.PCFSoftShadowMap;
 const canvas=renderer.domElement;canvas.className='atlas-scenery';canvas.setAttribute('aria-hidden','true');plane.prepend(canvas);
 let disposed=false,raf=0,last=0,zoom=1,lastWidth=0,model=null,dirty=true,visible=true;
 function release(){const resources=new Set();scene.traverse(o=>{if(o.geometry)resources.add(o.geometry);for(const m of (Array.isArray(o.material)?o.material:[o.material]))if(m){resources.add(m);Object.values(m).forEach(v=>{if(v?.isTexture)resources.add(v);});}if(o.shadow?.map)resources.add(o.shadow.map);});for(const t of model?.textures||[])resources.add(t);for(const r of resources)r.dispose?.();scene.clear();}
 function dispose(){if(disposed)return;disposed=true;cancelAnimationFrame(raf);visibility.disconnect();document.removeEventListener('visibilitychange',wake);plane.classList.remove('atlas-3d-ready');canvas.remove();release();renderer.dispose();renderer.forceContextLoss();if(live.get(plane)===handle)live.delete(plane);}
 function wake(){if(!disposed&&!document.hidden&&visible&&!raf)raf=requestAnimationFrame(frame);}
 const visibility=new IntersectionObserver(entries=>{visible=entries[0]?.isIntersecting!==false;if(!visible){cancelAnimationFrame(raf);raf=0;}else wake();});visibility.observe(plane);
 document.addEventListener('visibilitychange',wake);
 const handle={dispose,setZoom(z){zoom=Number.isFinite(z)?z:1;dirty=true;wake();},stats(){return {world,sites:model?.sites||0,zoom,drawCalls:renderer.info.render.calls,triangles:renderer.info.render.triangles,width:lastWidth};}};
 live.set(plane,handle);plane._atlasScenery=handle;canvas.addEventListener('webglcontextlost',e=>{e.preventDefault();dispose();});
 try{
  const module=await import(world==='Naruto'?'./dream-naruto-scene.js':'./dream-one-piece-scene.js');
  const extra=await fetch('/assets/dream-map/'+(world==='Naruto'?'naruto-biomes':'one-piece-positions')+'.json').then(r=>{if(!r.ok)throw Error('Map data unavailable');return r.json();});
  if(disposed)return null;
  model=await module.build(scene,{...atlas,...extra});
  if(disposed){release();return null;}
  const buckets=new Map();for(const c of atlas.cells||[]){const k=Math.floor(c.x/3)+':'+Math.floor(c.y/3);if(!buckets.has(k))buckets.set(k,[]);buckets.get(k).push(c);}
  function cellAt(x,y){let best=null,d=Infinity;for(let a=-1;a<=1;a++)for(let b=-1;b<=1;b++)for(const c of buckets.get((Math.floor(x/3)+a)+':'+(Math.floor(y/3)+b))||[]){const n=(x-c.x)**2+(y-c.y)**2;if(n<d){best=c;d=n;}}return best;}
  const colors=new Map();function tint(owner){if(!colors.has(owner))colors.set(owner,new T.Color(ownerColor(owner)));return colors.get(owner);}
  for(const mesh of model.terrainMeshes){mesh.material=mesh.material.clone();const p=mesh.geometry.attributes.position,old=mesh.geometry.attributes.color,col=new Float32Array(p.count*3);for(let i=0;i<p.count;i++){const c=cellAt(p.getX(i)+50,p.getZ(i)+50),base=old?new T.Color().fromBufferAttribute(old,i):new T.Color('#ffffff');if(c)base.lerp(tint(c.owner),.28);col.set([base.r,base.g,base.b],i*3);}mesh.geometry.setAttribute('color',new T.BufferAttribute(col,3));mesh.material.vertexColors=true;}
  const edges=new Map(),points=[];for(const c of atlas.cells||[]){const r=1.5/Math.sqrt(3),v=Array.from({length:6},(_,i)=>[+(c.x+r*Math.cos((30+i*60)*Math.PI/180)).toFixed(2),+(c.y+r*Math.sin((30+i*60)*Math.PI/180)).toFixed(2)]);for(let i=0;i<6;i++){const a=v[i],b=v[(i+1)%6],k=[a.join(','),b.join(',')].sort().join('|');if(edges.has(k))edges.get(k).internal=edges.get(k).owner===c.owner;else edges.set(k,{a,b,owner:c.owner});}}
  for(const e of edges.values()){if(e.internal)continue;const x=(e.a[0]+e.b[0])/2,y=(e.a[1]+e.b[1])/2;if(!atlas.land.some(l=>inside(x,y,l.polygon)))continue;for(const[a,b]of[e.a,e.b])points.push(a-50,model.heightAt(a,b)+.16,b-50);}
  scene.add(new T.LineSegments(new T.BufferGeometry().setAttribute('position',new T.Float32BufferAttribute(points,3)),new T.LineBasicMaterial({color:'#f4dd9c',transparent:true,opacity:.85})));
  batchStatic(scene,[...model.terrainMeshes,...(model.animatedRoots||[])]);
  const ground=new T.Group();for(const child of [...scene.children])if(!child.isLight){scene.remove(child);ground.add(child);}ground.scale.set(1.6,1,1.25);scene.add(ground);
  wake();return handle;
 }catch(error){dispose();console.warn('Detailed scenery unavailable; keeping 2D map.',error);return null;}
 function frame(now){
  raf=0;if(disposed)return;if(!plane.isConnected){dispose();return;}if(document.hidden||!visible)return;
  const moving=!matchMedia('(prefers-reduced-motion: reduce)').matches;
  if(plane.offsetWidth&&now-last>=66&&model){const width=Math.min(innerWidth<=850?1280:2048,Math.max(640,Math.round(plane.clientWidth*Math.min(zoom,2))));if(width!==lastWidth){renderer.setSize(width,Math.round(width/1.6),false);lastWidth=width;dirty=true;}if(moving||dirty){if(moving)model.animate(Math.min(.1,(now-last)/1000));renderer.render(scene,camera);plane.classList.add('atlas-3d-ready');dirty=false;}last=now;}
  raf=requestAnimationFrame(frame);
 }
}
