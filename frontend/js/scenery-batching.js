import * as T from '../vendor/three/three.module.js';
/* Bake static architecture by material; keep animated roots and instances intact. */
export function batchStatic(scene, excluded=[]){
 scene.updateMatrixWorld(true);const groups=new Map(),oldGeometries=new Set();
 const skip=o=>{for(let p=o;p;p=p.parent)if(excluded.includes(p))return true;return false;};
 scene.traverse(o=>{if(!o.isMesh||o.isInstancedMesh||Array.isArray(o.material)||o.material.transparent||o.material.isShaderMaterial||skip(o))return;if(!groups.has(o.material))groups.set(o.material,[]);groups.get(o.material).push(o);});
 for(const [material,meshes]of groups){if(meshes.length<3)continue;const pos=[],norm=[],uv=[],colors=[],v=new T.Vector3(),n=new T.Vector3();let hasColor=false;
  for(const m of meshes){const g=m.geometry,a=g.attributes,normalMatrix=new T.Matrix3().getNormalMatrix(m.matrixWorld),index=g.index,count=index?index.count:a.position.count;hasColor||=!!a.color;
   for(let j=0;j<count;j++){const i=index?index.getX(j):j;v.fromBufferAttribute(a.position,i).applyMatrix4(m.matrixWorld);pos.push(v.x,v.y,v.z);if(a.normal)n.fromBufferAttribute(a.normal,i).applyMatrix3(normalMatrix).normalize();else n.set(0,1,0);norm.push(n.x,n.y,n.z);uv.push(a.uv?.getX(i)||0,a.uv?.getY(i)||0);colors.push(a.color?.getX(i)??1,a.color?.getY(i)??1,a.color?.getZ(i)??1);}oldGeometries.add(g);m.removeFromParent();
  }
  const g=new T.BufferGeometry();g.setAttribute('position',new T.Float32BufferAttribute(pos,3));g.setAttribute('normal',new T.Float32BufferAttribute(norm,3));g.setAttribute('uv',new T.Float32BufferAttribute(uv,2));if(hasColor)g.setAttribute('color',new T.Float32BufferAttribute(colors,3));const merged=new T.Mesh(g,material);merged.castShadow=merged.receiveShadow=true;scene.add(merged);
 }
 const kept=new Set();scene.traverse(o=>{if(o.geometry)kept.add(o.geometry);});for(const g of oldGeometries)if(!kept.has(g))g.dispose();
}
