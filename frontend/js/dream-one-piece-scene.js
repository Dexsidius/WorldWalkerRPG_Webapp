import * as T from '../vendor/three/three.module.js';
export async function build(scene,data){
const loader=new T.TextureLoader(),[terrain,architecture]=await Promise.all([loader.loadAsync('/assets/dream-map/one-piece-terrain.png'),loader.loadAsync('/assets/dream-map/architecture.png')]);
function crop(source,x,y){const c=document.createElement('canvas');c.width=c.height=512;c.getContext('2d').drawImage(source.image,x*source.image.width/2,y*source.image.height/2,source.image.width/2,source.image.height/2,0,0,512,512);const t=new T.CanvasTexture(c);t.colorSpace=T.SRGBColorSpace;t.wrapS=t.wrapT=T.RepeatWrapping;t.anisotropy=8;return t}
const rock=crop(terrain,0,0),grass=crop(terrain,1,0),sand=crop(terrain,0,1),sea=crop(terrain,1,1),tile=crop(architecture,0,0),plaster=crop(architecture,1,0),wood=crop(architecture,0,1),slate=crop(architecture,1,1);
scene.add(new T.HemisphereLight('#c7eaff','#385548',2));const sun=new T.DirectionalLight('#ffdeac',3.2);sun.position.set(-30,80,-45);sun.castShadow=true;sun.shadow.mapSize.set(1024,1024);Object.assign(sun.shadow.camera,{left:-70,right:70,top:70,bottom:-70,near:1,far:220});sun.shadow.normalBias=.08;scene.add(sun);
const mat=(map,color='#ffffff',roughness=.8)=>new T.MeshStandardMaterial({map,color,roughness,bumpMap:map,bumpScale:.09});const materials={grass:mat(grass,'#c0d39a'),rock:mat(rock,'#e3b19a'),sand:mat(sand,'#ffe1a1'),wall:mat(plaster,'#fff0c7'),roof:mat(tile,'#d48b60'),wood:mat(wood),slate:mat(slate,'#76a3b6'),snow:mat(rock,'#dfedf9'),leaf:mat(grass,'#60843e'),gold:mat(plaster,'#e9b851')};
sea.repeat.set(10,10);const waterMaterial=new T.MeshStandardMaterial({map:sea,color:'#469dbc',roughness:.3,metalness:.23,bumpMap:sea,bumpScale:.32});waterMaterial.onBeforeCompile=shader=>{shader.uniforms.uTime={value:0};waterMaterial.userData.shader=shader;shader.vertexShader=shader.vertexShader.replace('#include <common>','#include <common>\nuniform float uTime;').replace('#include <begin_vertex>','#include <begin_vertex>\ntransformed.z += .065*sin(position.x*2.5+uTime)*cos(position.y*1.6+uTime*.7);')};const water=new T.Mesh(new T.PlaneGeometry(290,290,80,80),waterMaterial);water.rotation.x=-Math.PI/2;water.position.y=-.1;scene.add(water);
let seed=923;const rnd=()=>{seed=(seed*1664525+1013904223)>>>0;return seed/4294967296};const point=(x,y,z)=>new T.Vector3(x-50,y,z-50);
function mesh(g,m,x,y,z,parent=scene){const a=new T.Mesh(g,m);a.position.set(x,y,z);a.castShadow=true;a.receiveShadow=true;parent.add(a);return a}
function box(p,x,y,z,w,h,d,m){return mesh(new T.BoxGeometry(w,h,d),m,x,y,z,p)}
function inside(x,z,poly){let b=false;for(let i=0,j=poly.length-1;i<poly.length;j=i++){const[a,c]=poly[i],[d,e]=poly[j];if((c>z)!==(e>z)&&x<(d-a)*(z-c)/(e-c)+a)b=!b}return b}
function height(x,z,land){if(land.terrain==='stone')return 5.8+2.6*Math.sin(z*.9)**2+1.1*Math.sin(z*3.1+x);const d=Math.hypot(x-land.x,z-land.y);return .7+Math.max(0,1-d/5)*.9+.25*Math.sin(x*2+z)*Math.cos(z*2.1)}
const terrainMeshes=[];
for(const l of data.land){const red=l.terrain==='stone',isSand=l.name==='Alabasta',snow=l.name==='Drum Island';const pos=[],uv=[];const xs=l.polygon.map(p=>p[0]),zs=l.polygon.map(p=>p[1]),step=red?.5:.38;for(let x=Math.min(...xs);x<Math.max(...xs);x+=step)for(let z=Math.min(...zs);z<Math.max(...zs);z+=step){if(!inside(x+step/2,z+step/2,l.polygon))continue;for(const[dx,dz]of[[0,0],[0,step],[step,0],[step,0],[0,step],[step,step]]){const X=x+dx,Z=z+dz;pos.push(X-50,height(X,Z,l),Z-50);uv.push(X/7,Z/7)}}const g=new T.BufferGeometry();g.setAttribute('position',new T.Float32BufferAttribute(pos,3));g.setAttribute('uv',new T.Float32BufferAttribute(uv,2));g.computeVertexNormals();const a=mesh(g,red?materials.rock:snow?materials.snow:isSand?materials.sand:materials.grass,0,0,0);terrainMeshes.push(a);
const sidePos=[],sideUV=[];for(let i=0;i<l.polygon.length;i++){const p=l.polygon[i],q=l.polygon[(i+1)%l.polygon.length];for(const[v,h]of[[p,0],[q,0],[p,1],[p,1],[q,0],[q,1]]){sidePos.push(v[0]-50,h?height(v[0],v[1],l):-.3,v[1]-50);sideUV.push(v[1]/6,h*2)}}const sg=new T.BufferGeometry();sg.setAttribute('position',new T.Float32BufferAttribute(sidePos,3));sg.setAttribute('uv',new T.Float32BufferAttribute(sideUV,2));sg.computeVertexNormals();const sm=materials.rock.clone();sm.side=T.DoubleSide;mesh(sg,sm,0,0,0);
const pts=l.polygon.map(([x,z])=>point(x,.06,z));const curve=new T.CatmullRomCurve3(pts,true);for(const[r,c,o]of[[.55,'#15b0bb',.48],[.15,'#d6fff2',.7]]){const s=mesh(new T.TubeGeometry(curve,pts.length*2,r,4,true),new T.MeshBasicMaterial({color:c,transparent:true,opacity:o}),0,0,0);s.castShadow=false}
if(red)continue;
for(let i=0;i<65;i++){const x=l.x+(rnd()-.5)*9,z=l.y+(rnd()-.5)*8;if(!inside(x,z,l.polygon)||Math.hypot(x-l.x,z-l.y)<1.7)continue;const h=height(x,z,l);if(isSand){if(i%5===0)mesh(new T.ConeGeometry(.4,1.5,5),materials.sand,x-50,h+.5,z-50);continue}box(scene,x-50,h+.3,z-50,.12,.8,.12,materials.wood);const tree=mesh(snow?new T.ConeGeometry(.45,1.6,7):new T.IcosahedronGeometry(.38+rnd()*.3,1),snow?materials.snow:materials.leaf,x-50,h+.9,z-50);tree.scale.y=snow?1:1.25}
}
function house(p,x,z,s=1,roof=materials.roof){box(p,x,.55*s,z,.8*s,1.1*s,.8*s,materials.wall);const r=mesh(new T.ConeGeometry(.72*s,.58*s,4),roof,x,1.36*s,z,p);r.rotation.y=Math.PI/4;box(p,x,.4*s,z+.41*s,.2*s,.45*s,.03,materials.wood)}
function tower(p,x,z,h=3,r=.45,m=materials.wall){mesh(new T.CylinderGeometry(r,r*1.08,h,10),m,x,h/2,z,p);mesh(new T.ConeGeometry(r*1.5,1,8),materials.slate,x,h+.4,z,p);for(let j=0;j<3;j++)box(p,x,h*.3+j*.6,z+r,.12,.25,.03,materials.wood)}
function castle(p,kind){
 const desert=kind==='Alabasta';
 if(['Cactus Island','Little Garden','Jaya'].includes(kind)){for(let i=0;i<11;i++){const x=(rnd()-.5)*4,z=(rnd()-.5)*3,h=1+rnd()*2.5;mesh(new T.CylinderGeometry(.16,.23,h,7),materials.leaf,x,h/2,z,p);if(i%2===0){box(p,x+.3,h*.65,z,.7,.16,.17,materials.leaf);box(p,x+.6,h*.75,z,.16,.55,.17,materials.leaf)}}for(let i=0;i<5;i++)house(p,(rnd()-.5)*3,(rnd()-.5)*2,.45);return}
 if(kind==='Ohara'){const trunk=mesh(new T.CylinderGeometry(.38,.85,3.8,9),materials.wood,0,1.9,0,p);for(let i=0;i<9;i++){const a=i*2.4;const crown=mesh(new T.IcosahedronGeometry(1.3,2),materials.leaf,Math.cos(a)*1.4,3.2+rnd(),Math.sin(a)*1.3,p);crown.scale.y=.6}for(let i=0;i<6;i++)house(p,(rnd()-.5)*4,(rnd()-.5)*3,.5);return}
 if(kind==='Thriller Bark'){for(let i=0;i<7;i++){const a=i*2.4;tower(p,Math.cos(a)*1.5,Math.sin(a)*1.4,2+rnd()*2,.25,materials.rock)}box(p,0,1.2,0,2,2.4,1.6,materials.rock);return}
 const naval=['Marineford','Shells Town'].includes(kind),towers=desert?8:naval?6:9;
 for(let i=0;i<towers;i++){const a=i*Math.PI*2/towers,r=2.1;tower(p,Math.cos(a)*r,Math.sin(a)*r,1.3+(i%3)*.55,.19,desert?materials.gold:materials.wall)}
 box(p,0,.7,0,2.8,1.4,1.8,desert?materials.gold:materials.wall);
 if(desert){for(const x of[-.8,.8])mesh(new T.SphereGeometry(.55,12,8,0,Math.PI*2,0,Math.PI/2),materials.gold,x,1.5,0,p)}else tower(p,0,0,naval?3.3:2.8,.35,materials.wall);
 for(let i=0;i<12;i++)house(p,(rnd()-.5)*4,(rnd()-.5)*3,.3+rnd()*.25)
}
const windmills=[];function windmill(p){mesh(new T.CylinderGeometry(.45,.7,2.6,12),materials.wall,0,1.3,0,p);mesh(new T.ConeGeometry(.7,1,12),materials.roof,0,3,0,p);const rotor=new T.Group();rotor.position.set(0,2.4,.55);p.add(rotor);for(let i=0;i<4;i++){const arm=new T.Group();arm.rotation.z=i*Math.PI/2;rotor.add(arm);box(arm,0,.95,0,.09,2,.08,materials.wood);box(arm,.18,1.15,0,.36,1.25,.05,materials.wall)}windmills.push(rotor)}
function pagoda(p){for(let i=0;i<4;i++){const w=2.2-i*.35;box(p,0,.6+i*.9,0,w,.7,w,materials.wall);const roof=mesh(new T.ConeGeometry(w*.85,.6,4),materials.slate,0,1.15+i*.9,0,p);roof.rotation.y=Math.PI/4}mesh(new T.ConeGeometry(.12,1,5),materials.gold,0,4.7,0,p)}
const locations=[];for(const l of data.land){if(l.terrain==='stone')continue;const p=new T.Group();p.position.copy(point(l.x,height(l.x,l.y,l)+.2,l.y));scene.add(p);locations.push(p);
if(['Dawn Island','Orange Town','Syrup Village'].includes(l.name)){windmill(p);for(let i=0;i<8;i++)house(p,(rnd()-.5)*4,(rnd()-.5)*3,.5+rnd()*.35)}
else if(['Wano Country','Kano Country','Amazon Lily'].includes(l.name)){pagoda(p);for(let i=0;i<6;i++)house(p,(rnd()-.5)*4,(rnd()-.5)*4,.65,materials.slate)}
else if(l.name==='Zou'){const skin=mat(rock,'#858977');const body=mesh(new T.SphereGeometry(1.1,12,10),skin,0,1.7,0,p);body.scale.set(1,1,1.7);for(const x of[-.7,.7])for(const z of[-.8,.8])mesh(new T.CylinderGeometry(.28,.24,1.7,7),skin,x,.8,z,p);mesh(new T.SphereGeometry(.75,10,8),skin,0,2,-1.6,p);const trunk=new T.CatmullRomCurve3([new T.Vector3(0,2,-2),new T.Vector3(0,.7,-2.4),new T.Vector3(0,.3,-2.1)]);mesh(new T.TubeGeometry(trunk,15,.18,7,false),skin,0,0,0,p);house(p,0,0,.8);p.children.at(-1).position.y+=2.3}
else if(l.name==='Totto Land'){for(let i=0;i<4;i++)mesh(new T.CylinderGeometry(1.6-i*.3,1.8-i*.3,.7,24),mat(plaster,['#eea887','#df819d','#f1c45e','#f6e4b3'][i]),0,.4+i*.7,0,p);for(let i=0;i<8;i++){const a=i*Math.PI/4;tower(p,Math.cos(a)*1.8,Math.sin(a)*1.8,1.6,.22,materials.gold)}}
else if(l.name==='Water 7'){for(let i=0;i<3;i++)mesh(new T.CylinderGeometry(2.4-i*.65,2.6-i*.65,.55,32),materials.wall,0,i*.6,0,p);for(let i=0;i<14;i++){const a=i*Math.PI/7;house(p,Math.cos(a)*2,Math.sin(a)*2,.5)}tower(p,0,0,3,.4)}
else if(l.name==='Punk Hazard'||l.name==='Drum Island'){for(let i=0;i<7;i++){const h=2+rnd()*3;mesh(new T.ConeGeometry(.7+rnd(),h,7),l.name==='Drum Island'||i<3?materials.snow:materials.rock,(rnd()-.5)*4,h/2,(rnd()-.5)*3,p)}castle(p,l.name)}
else castle(p,l.name);
}
function ship(x,z,s=1){const p=new T.Group();p.position.copy(point(x,.3,z));p.scale.setScalar(s);scene.add(p);const hull=mesh(new T.SphereGeometry(.6,10,7),materials.wood,0,.15,0,p);hull.scale.set(.8,.55,2);box(p,0,1.3,0,.06,2.6,.06,materials.wood);const sail=mesh(new T.PlaneGeometry(1.25,1.6,8,8),new T.MeshStandardMaterial({map:plaster,side:T.DoubleSide,color:'#fff0c8'}),0,1.7,.04,p);for(let i=0;i<sail.geometry.attributes.position.count;i++){const a=sail.geometry.attributes.position;a.setZ(i,.2*Math.cos(a.getX(i)*2))}const foam=mesh(new T.ConeGeometry(.5,3,3),new T.MeshBasicMaterial({color:'#caede9',transparent:true,opacity:.3}),0,-.12,2,p);foam.rotation.x=Math.PI/2;p.rotation.y=.4+rnd()*.6;return p}
const ships=[[20,13],[20,25],[23,38],[40,38],[61,16],[90,43],[78,80],[40,74],[93,71]].map(([x,z])=>ship(x,z,.65+rnd()*.35));
// Layer the generated materials over sculpted coastal relief and varied settlements.
waterMaterial.color.set('#469aa4');waterMaterial.roughness=.34;waterMaterial.metalness=.12;waterMaterial.bumpScale=.045;sea.repeat.set(13,13);
// Keep the generated ocean's small surface detail while grading its electric blues
// into the quieter teal depths of the nautical chart.
const oceanCompile=waterMaterial.onBeforeCompile;
waterMaterial.onBeforeCompile=shader=>{oceanCompile(shader);shader.fragmentShader=shader.fragmentShader.replace('#include <map_fragment>','#include <map_fragment>\nfloat oceanLuma=dot(diffuseColor.rgb,vec3(.2126,.7152,.0722));\ndiffuseColor.rgb=mix(vec3(.008,.075,.13),vec3(.055,.27,.34),clamp(oceanLuma*1.6,0.,1.));');};
scene.children.find(o=>o.isHemisphereLight).intensity=2.8;
sun.intensity=3.5;sun.position.set(-35,90,35);materials.leaf.color.set('#a7bf72');materials.rock.color.set('#e8b497');materials.snow.bumpScale=.03;
const cliffMaterial=materials.rock.clone();cliffMaterial.color.set('#cf9d87');
for(const l of data.land){
 if(l.terrain==='stone'){
  // Broken buttresses give the meridians a rock silhouette instead of a thin wall.
  for(let z=0;z<100;z+=1.1){const candidates=l.polygon.filter(p=>Math.abs(p[1]-z)<10);const center=candidates.length?candidates.reduce((s,p)=>s+p[0],0)/candidates.length:l.x;for(const side of[-1,1]){const h=3+rnd()*5;const crag=mesh(new T.IcosahedronGeometry(1,1),cliffMaterial,center-50+side*(1.05+rnd()*.55),h*.42,z-50);crag.scale.set(.6+rnd()*.6,h,.75+rnd()*.6);crag.rotation.y=rnd()*3;}}
  continue;
 }
 // Warm little roof clusters and harbors provide an inhabited scale at every coast.
 const settlement=locations[data.land.filter(a=>a.terrain!=='stone').indexOf(l)];
 if(settlement){settlement.scale.set(1.3,1.12,1.3);for(let i=0;i<14;i++){const angle=i*2.4,r=2+rnd()*1.2,x=l.x+Math.cos(angle)*r,z=l.y+Math.sin(angle)*r;if(inside(x,z,l.polygon)){const hamlet=new T.Group();hamlet.position.copy(point(x,height(x,z,l),z));scene.add(hamlet);house(hamlet,0,0,.26+rnd()*.2);}}}
 for(let i=0;i<l.polygon.length;i+=3){const [x,z]=l.polygon[i];const boulder=mesh(new T.IcosahedronGeometry(.24+rnd()*.25,1),l.name==='Drum Island'?materials.snow:materials.rock,x-50,.25,z-50);boulder.scale.y=1.5;}
 if(['Dawn Island','Water 7','Shells Town','Orange Town'].includes(l.name)){const edge=l.polygon.reduce((a,b)=>b[1]>a[1]?b:a);const dock=new T.Group();dock.position.copy(point(edge[0],.4,edge[1]));scene.add(dock);for(let i=0;i<12;i++)box(dock,0,0,i*.14,.75,.09,.11,materials.wood);for(const x of[-.34,.34])for(const z of[0,1.4])box(dock,x,-.1,z,.08,.7,.08,materials.wood);ship(edge[0]+1,edge[1]+1.2,.7);}
}
// Glassy undersea dome, an emblematic landmark absent from the land polygons.
const fish=new T.Group();fish.position.copy(point(...[54,.3,66]));scene.add(fish);mesh(new T.CylinderGeometry(2.8,3,.4,40),materials.sand,0,0,0,fish);for(let i=0;i<10;i++){const a=i*Math.PI/5;tower(fish,Math.cos(a)*1.8,Math.sin(a)*1.8,1.2+(i%3)*.5,.16,materials.gold)}
mesh(new T.SphereGeometry(2.7,32,20,0,Math.PI*2,0,Math.PI/2),new T.MeshPhysicalMaterial({color:'#8ee8f6',transparent:true,opacity:.18,roughness:.06,metalness:.1,depthWrite:false}),0,.2,0,fish);
// Low sea mist catches the light along the monumental red cliffs.
const mistCanvas=document.createElement('canvas');mistCanvas.width=mistCanvas.height=128;const mistContext=mistCanvas.getContext('2d'),mistGradient=mistContext.createRadialGradient(64,64,4,64,64,64);mistGradient.addColorStop(0,'rgba(223,239,241,.55)');mistGradient.addColorStop(.45,'rgba(206,225,231,.22)');mistGradient.addColorStop(1,'rgba(206,225,231,0)');mistContext.fillStyle=mistGradient;mistContext.fillRect(0,0,128,128);const mistTexture=new T.CanvasTexture(mistCanvas);
for(const x of[8,53])for(let z=1;z<100;z+=3.2){const cloud=new T.Sprite(new T.SpriteMaterial({map:mistTexture,transparent:true,opacity:.38+rnd()*.25,depthWrite:false}));cloud.position.copy(point(x-2+rnd()*3,2+rnd()*3,z));cloud.scale.set(5+rnd()*3,3+rnd()*2,1);scene.add(cloud)}

let time=0;return {terrainMeshes,sites:locations.length,animatedRoots:[...windmills,...ships],heightAt(x,y){const land=data.land.find(l=>inside(x,y,l.polygon));return land?height(x,y,land):0;},animate(dt){time+=dt;sea.offset.x=time*.002;if(waterMaterial.userData.shader)waterMaterial.userData.shader.uniforms.uTime.value=time;windmills.forEach(w=>w.rotation.z=time*.5);ships.forEach((s,i)=>{s.rotation.z=Math.sin(time*1.3+i)*.05;});},textures:[terrain,architecture]};
}
