/* Local-only scenery adapter. Campaign atlas remains authoritative for ownership,
   positions and interaction. No requests to an AI or external asset host. */
import * as T from '../vendor/three/three.module.js';
export const SUPPORTED_WORLDS = ['Naruto', 'One Piece'];
export function supports(atlas) { return SUPPORTED_WORLDS.includes(String(atlas?.id||'').split(':')[0]); }
export function inside(x,y,poly) {let yes=false;for(let i=0,j=poly.length-1;i<poly.length;j=i++){const [a,b]=poly[i],[c,d]=poly[j];if((b>y)!=(d>y)&&x<(c-a)*(y-b)/(d-b)+a)yes=!yes;}return yes;}
export function landmarkStyle(name, world) {
 const n=String(name).toLowerCase();
 if(world==='Naruto')return /suna/.test(n)?'sand':/amegakure/.test(n)?'rain':/kumo/.test(n)?'cloud':/iwa/.test(n)?'rock':/kiri/.test(n)?'mist':/valley/.test(n)?'statues':/bridge/.test(n)?'bridge':/ruins/.test(n)?'ruins':'leaf';
 return /red line|reverse mountain/.test(n)?'redline':/drum/.test(n)?'winter':/alabasta/.test(n)?'desert':/water 7/.test(n)?'canal':/marineford|enies lobby/.test(n)?'fortress':/sabaody/.test(n)?'mangrove':/wano/.test(n)?'pagoda':/dressrosa/.test(n)?'palace':/totto/.test(n)?'confection':/egghead/.test(n)?'future':/punk hazard/.test(n)?'split':/impel/.test(n)?'prison':/little garden/.test(n)?'jungle':'port';
}
const live = new WeakMap();
export function mount(plane, atlas, ownerColor) {
 live.get(plane)?.dispose();
 if(!supports(atlas)||!plane.isConnected)return null;
 let renderer;try{renderer=new T.WebGLRenderer({alpha:true,antialias:true,powerPreference:'low-power'});}catch{return null;}
 const canvas=renderer.domElement;canvas.className='atlas-scenery';canvas.setAttribute('aria-hidden','true');plane.prepend(canvas);
 const world=atlas.id.split(':')[0],scene=new T.Scene();scene.background=new T.Color('#245a6b');
 const camera=new T.OrthographicCamera(-80,80,50,-50,.1,400);camera.position.set(0,160,120);camera.lookAt(0,0,0);
 renderer.outputColorSpace=T.SRGBColorSpace;renderer.toneMapping=T.ACESFilmicToneMapping;renderer.toneMappingExposure=1.1;
 renderer.shadowMap.enabled=true;renderer.shadowMap.type=T.PCFSoftShadowMap;
 scene.add(new T.HemisphereLight('#e9eed9','#31472e',1.5));const sun=new T.DirectionalLight('#ffe4b7',2.4);sun.position.set(-65,100,35);sun.castShadow=true;sun.shadow.mapSize.set(1024,1024);Object.assign(sun.shadow.camera,{left:-100,right:100,top:100,bottom:-100,far:250});sun.shadow.normalBias=.12;scene.add(sun);
 let rng=734;function rand(){rng=(rng*1664525+1013904223)>>>0;return rng/4294967296;}
 const textures=[],materials=[],geometries=[];const G=g=>(geometries.push(g),g);
 function material(color, textured=false){const m=new T.MeshStandardMaterial({color,roughness:.95});if(textured){const c=document.createElement('canvas');c.width=c.height=64;const ctx=c.getContext('2d');ctx.fillStyle='#e0dfd5';ctx.fillRect(0,0,64,64);for(let i=0;i<2000;i++){ctx.fillStyle=`rgba(38,32,19,${rand()*.12})`;ctx.fillRect(rand()*64,rand()*64,1,1);}const tex=new T.CanvasTexture(c);tex.wrapS=tex.wrapT=T.RepeatWrapping;tex.colorSpace=T.SRGBColorSpace;textures.push(tex);m.map=tex;}materials.push(m);return m;}
 const mats={green:material('#496b37'),wood:material('#614b31'),wall:material('#d9c7a2',true),roof:material('#a84331',true),stone:material('#9a8769',true),sand:material('#d5b982',true),metal:material('#536a72'),blue:material('#518990'),white:material('#dbe3df'),pink:material('#c98493'),gold:material('#d4aa54'),dark:material('#233939')};
 const box=G(new T.BoxGeometry(1,1,1)),ball=G(new T.IcosahedronGeometry(1,1)),cylinder=G(new T.CylinderGeometry(1,1,1,10)),cone=G(new T.ConeGeometry(1,1,10));
 const regions=atlas.land||[],cells=atlas.cells||[],bucket=new Map();for(const c of cells){const key=`${Math.floor(c.x/3)}:${Math.floor(c.y/3)}`;if(!bucket.has(key))bucket.set(key,[]);bucket.get(key).push(c);}
 function cellAt(x,y){let best=null,dist=Infinity;const xx=Math.floor(x/3),yy=Math.floor(y/3);for(let a=-1;a<=1;a++)for(let b=-1;b<=1;b++)for(const c of bucket.get(`${xx+a}:${yy+b}`)||[]){const d=(c.x-x)**2+(c.y-y)**2;if(d<dist){dist=d;best=c;}}return best;}
 const landAt=(x,y)=>regions.findIndex(l=>inside(x,y,l.polygon));
 function biome(x,y,land){const name=regions[land]?.name||'',c=cellAt(x,y);return world==='One Piece'?landmarkStyle(name,world):/wind/i.test(c?.district||'')?'desert':/earth|lightning|iron/i.test(c?.district||'')?'rock':'jungle';}
 function elevation(x,y,land){let h=.45+.14*Math.sin(x*.8)*Math.cos(y*.63);if(world==='Naruto')for(const r of atlas.relief||[])for(const [a,b]of r)h+=2.3*Math.exp(-((x-a)**2+(y-b)**2)/12);else{const l=regions[land];if(l){const style=landmarkStyle(l.name,world);h+=['winter','redline'].includes(style)?2.5:style==='jungle'?.8:.2;}}return h;}
 const xyz=(x,y,h=0)=>[(x-50)*1.6,h,(y-50)*1.25];
 const pos=[],col=[],uv=[];
 function vertex(x,y,li){const c=cellAt(x,y),b=biome(x,y,li);let tint=new T.Color(b==='desert'?'#c7ad79':b==='winter'?'#b9cdc5':b==='redline'?'#a76a53':b==='rock'?'#9b926d':'#6e8a50');tint.lerp(new T.Color(ownerColor(c?.owner||regions[li].owner)),.3);tint.multiplyScalar(.95+.06*Math.sin(x*2+y));pos.push(...xyz(x,y,elevation(x,y,li)));col.push(tint.r,tint.g,tint.b);uv.push(x/3,y/3);}
 // Subdivide polygon triangles instead of rasterizing coastlines into square cells.
 regions.forEach((land,li)=>{const contour=land.polygon.map(([x,y])=>new T.Vector2(x,y));for(const tri of T.ShapeUtils.triangulateShape(contour,[])){const [a,b,c]=tri.map(i=>contour[i]);const n=Math.max(1,Math.ceil(Math.max(a.distanceTo(b),b.distanceTo(c),c.distanceTo(a))/1.2));const at=(i,j)=>[a.x+(b.x-a.x)*i/n+(c.x-a.x)*j/n,a.y+(b.y-a.y)*i/n+(c.y-a.y)*j/n];for(let i=0;i<n;i++)for(let j=0;j<n-i;j++){for(const [u,v]of[[i,j],[i,j+1],[i+1,j]])vertex(...at(u,v),li);if(i+j<n-1)for(const [u,v]of[[i+1,j],[i,j+1],[i+1,j+1]])vertex(...at(u,v),li);}}});
 const geo=G(new T.BufferGeometry());geo.setAttribute('position',new T.Float32BufferAttribute(pos,3));geo.setAttribute('color',new T.Float32BufferAttribute(col,3));geo.setAttribute('uv',new T.Float32BufferAttribute(uv,2));geo.computeVertexNormals();const ground=material('#ffffff',true);ground.vertexColors=true;const terrain=new T.Mesh(geo,ground);terrain.receiveShadow=true;scene.add(terrain);
 const lineMat=new T.LineBasicMaterial({color:'#eedda6',transparent:true,opacity:.8});materials.push(lineMat);
 const edges=new Map();for(const c of cells){const r=1.5/Math.sqrt(3),v=Array.from({length:6},(_,i)=>[+(c.x+r*Math.cos((30+i*60)*Math.PI/180)).toFixed(2),+(c.y+r*Math.sin((30+i*60)*Math.PI/180)).toFixed(2)]);for(let i=0;i<6;i++){const a=v[i],b=v[(i+1)%6],key=[a.join(','),b.join(',')].sort().join('|');if(edges.has(key)){const e=edges.get(key);e.internal=e.owner===c.owner;}else edges.set(key,{a,b,owner:c.owner});}}
 const ep=[];for(const e of edges.values()){if(e.internal)continue;const mx=(e.a[0]+e.b[0])/2,my=(e.a[1]+e.b[1])/2,li=landAt(mx,my);if(li<0)continue;for(const [x,y]of[e.a,e.b])ep.push(...xyz(x,y,elevation(x,y,li)+.08));}const eg=G(new T.BufferGeometry());eg.setAttribute('position',new T.Float32BufferAttribute(ep,3));scene.add(new T.LineSegments(eg,lineMat));
 const detail=[],dummy=new T.Object3D(),trees=[];for(let i=0;i<9500;i++){const x=rand()*100,y=rand()*100,li=landAt(x,y);if(li<0)continue;const b=biome(x,y,li);if(['desert','winter','redline','rock'].includes(b)||rand()>.6||elevation(x,y,li)>2)continue;trees.push({x,y,h:elevation(x,y,li),s:.25+rand()*.35});}
 const canopy=new T.InstancedMesh(ball,mats.green,trees.length),trunks=new T.InstancedMesh(cylinder,mats.wood,trees.length);for(let i=0;i<trees.length;i++){const t=trees[i];dummy.position.set(...xyz(t.x,t.y,t.h+t.s));dummy.scale.set(t.s,t.s*.8,t.s);dummy.updateMatrix();canopy.setMatrixAt(i,dummy.matrix);dummy.position.y-=t.s*.6;dummy.scale.set(t.s*.1,t.s*.9,t.s*.1);dummy.updateMatrix();trunks.setMatrixAt(i,dummy.matrix);}canopy.castShadow=true;scene.add(canopy,trunks);detail.push(trunks);
 function part(g,shape,x,y,z,a,b,c,m){const mesh=new T.Mesh(shape,m);mesh.position.set(x,y,z);mesh.scale.set(a,b,c);mesh.castShadow=mesh.receiveShadow=true;g.add(mesh);return mesh;}
 const sites=world==='One Piece'?regions.filter(l=>!l.name.includes('Red Line')).map(l=>[l.name,l.x,l.y]):[['Konohagakure',51,52],['Sunagakure',20,67],['Iwagakure',20,20],['Kumogakure',73,19],['Amegakure',31,47],['Kirigakure',85,61],['Valley of the End',49,42],['Kannabi Bridge',34,35],['Uzushiogakure Ruins',68,68]];
 for(const [name,x,y]of sites){const li=landAt(x,y);if(li<0)continue;const g=new T.Group();g.position.set(...xyz(x,y,elevation(x,y,li)));scene.add(g);const d=new T.Group();g.add(d);detail.push(d);const style=landmarkStyle(name,world),roof=['mist','cloud','canal','future'].includes(style)?mats.blue:style==='desert'||style==='sand'?mats.sand:mats.roof;
  for(let i=0;i<8;i++){const a=i*2.4,r=.3+Math.sqrt(i)*.35,X=Math.cos(a)*r,Z=Math.sin(a)*r,h=style==='rain'?.8+rand()*1.4:.45+rand()*.4;part(g,cylinder,X,h/2,Z,.22,h,.22,style==='rain'?mats.metal:mats.wall);part(g,cone,X,h+.14,Z,.3,.3,.3,roof);part(d,box,X,h*.6,Z+.22,.12,.19,.025,mats.dark);}
  if(['sand','fortress','prison'].includes(style)){for(let i=0;i<14;i++){const a=i/14*Math.PI*2;if(i===3)continue;part(g,style==='sand'?ball:box,Math.cos(a)*1.7,.6,Math.sin(a)*1.7,.45,style==='sand'?.9:1.2,.45,style==='sand'?mats.sand:mats.white);}}
  if(['cloud','rock','winter'].includes(style))for(let i=0;i<4;i++)part(g,ball,(i-1.5)*.65,.2,-.6,.55,1+rand(),.55,style==='winter'?mats.white:mats.stone);
  if(style==='leaf'){part(g,box,0,.8,-1.3,2.5,1.6,.4,mats.stone);for(let i=0;i<4;i++)part(d,ball,-.9+i*.6,1,-1.02,.2,.38,.15,mats.stone);}
  if(style==='canal'){for(let i=0;i<3;i++)part(g,cylinder,0,i*.35,0,1.5-i*.35,.3,1.5-i*.35,i%2?mats.blue:mats.wall);part(g,box,0,1.5,0,.2,1,.2,mats.white);}
  if(style==='mangrove'){for(let i=0;i<3;i++){part(g,cylinder,i-1,.8,0,.15,1.6,.15,mats.wood);part(g,ball,i-1,1.8,0,.75,.6,.75,mats.green);}}
  if(style==='pagoda')for(let i=0;i<4;i++){part(g,box,0,.4+i*.4,0,1-i*.15,.35,1-i*.15,mats.wall);part(g,cone,0,.65+i*.4,0,.9-i*.13,.35,.9-i*.13,mats.roof);}
  if(['palace','confection','desert'].includes(style)){part(g,box,0,.8,0,1,1.6,.8,style==='confection'?mats.pink:mats.wall);for(const xx of[-.7,.7]){part(g,cylinder,xx,1,0,.25,2,.25,mats.wall);part(g,cone,xx,2.2,0,.35,.6,.35,style==='desert'?mats.gold:mats.pink);}}
  if(style==='future'){part(g,ball,0,1.2,0,1,.7,1,mats.white);part(g,cylinder,0,.5,0,.25,1,.25,mats.metal);}
  if(style==='bridge'){part(g,box,0,.5,0,3,.2,.5,mats.wood);}
  if(style==='statues'){for(const xx of[-.8,.8]){part(g,box,xx,1,0,.45,1.6,.4,mats.stone);part(g,ball,xx,2,0,.25,.35,.25,mats.stone);}}
 }
 let raf=0,disposed=false,zoom=1,last=0,lastWidth=0;
 function dispose(){if(disposed)return;disposed=true;cancelAnimationFrame(raf);plane.classList.remove('atlas-3d-ready');canvas.remove();scene.clear();for(const g of geometries)g.dispose();for(const m of materials)m.dispose();for(const t of textures)t.dispose();renderer.dispose();live.delete(plane);}
 canvas.addEventListener('webglcontextlost',e=>{e.preventDefault();dispose();});
 const handle={dispose,setZoom(z){zoom=Number.isFinite(z)?z:1;},stats(){return {world,sites:sites.length,trees:trees.length,zoom,drawCalls:renderer.info.render.calls};}};live.set(plane,handle);
 function frame(now){if(!plane.isConnected){dispose();return;}raf=requestAnimationFrame(frame);if(document.hidden||!plane.offsetWidth||now-last<66)return;last=now;const width=Math.min(innerWidth<800?1600:2560,Math.max(800,Math.round(plane.clientWidth*Math.min(zoom,3))));if(width!==lastWidth){renderer.setSize(width,Math.round(width/1.6),false);lastWidth=width;}detail.forEach(m=>m.visible=zoom>=2);renderer.render(scene,camera);plane.classList.add('atlas-3d-ready');}raf=requestAnimationFrame(frame);
 return handle;
}
