import * as THREE from 'three';
import {drawScreen,scenes} from './screen-demo.js';
import {icon} from './icons.js';
import {RoomEnvironment} from './vendor/three/RoomEnvironment.js';
const host=document.querySelector('#scene'),reduced=matchMedia('(prefers-reduced-motion: reduce)');
const renderer=new THREE.WebGLRenderer({alpha:true,antialias:true,powerPreference:'low-power'});
renderer.setPixelRatio(Math.min(devicePixelRatio,1.7));renderer.setClearColor(0,0);renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.35;host.append(renderer.domElement);
const scene=new THREE.Scene(),camera=new THREE.PerspectiveCamera(31,1,.1,100);camera.position.set(0,1.0,19);camera.lookAt(0,0,0);
const pmrem=new THREE.PMREMGenerator(renderer),room=new RoomEnvironment();scene.environment=pmrem.fromScene(room,.04).texture;room.dispose();pmrem.dispose();
scene.add(new THREE.HemisphereLight(0xf8fff7,0x6c8275,2.5));
for(const [x,y,z,color,power] of [[-5,7,9,0xffffff,4],[6,2,6,0xd6ffef,2],[-4,-2,-5,0xffffff,3]]){const light=new THREE.DirectionalLight(color,power);light.position.set(x,y,z);scene.add(light);}
const mat=(color,metalness=0,roughness=.35)=>new THREE.MeshStandardMaterial({color,metalness,roughness});
const silver=mat(0xbfc7c5,.9,.24),dark=mat(0x151917,.2,.31),glass=mat(0x010605,.15,.12),white=mat(0xdedfd6,.15,.30),port=mat(0x07100d,0,.6);
function roundedShape(w,h,r){const s=new THREE.Shape(),x=-w/2,y=-h/2;s.moveTo(x+r,y);s.lineTo(x+w-r,y);s.quadraticCurveTo(x+w,y,x+w,y+r);s.lineTo(x+w,y+h-r);s.quadraticCurveTo(x+w,y+h,x+w-r,y+h);s.lineTo(x+r,y+h);s.quadraticCurveTo(x,y+h,x,y+h-r);s.lineTo(x,y+r);s.quadraticCurveTo(x,y,x+r,y);return s;}
function box(parent,w,h,d,r,m,x=0,y=0,z=0){const g=new THREE.ExtrudeGeometry(roundedShape(w,h,r),{depth:d,steps:1,bevelEnabled:true,bevelThickness:Math.min(d*.2,.04),bevelSize:Math.min(d*.2,.04),bevelSegments:3,curveSegments:16});g.translate(0,0,-d/2);const mesh=new THREE.Mesh(g,m);mesh.position.set(x,y,z);parent.add(mesh);return mesh;}
function disc(parent,r,d,m,z){const g=new THREE.CylinderGeometry(r,r,d,96);g.rotateX(Math.PI/2);const mesh=new THREE.Mesh(g,m);mesh.position.z=z;parent.add(mesh);return mesh;}
let selected='round',sceneIndex=0,paused=reduced.matches,dirty=true,dragYaw=0,drag=null,last=0,clock=0,previous=0,manualUntil=0,lastModelSlot=0,lastSceneSlot=0;
const devices=[];
function make(id,w,h,d){const group=new THREE.Group();group.rotation.x=-.14;const canvas=document.createElement('canvas');canvas.width=512;canvas.height=Math.round(512*h/w);const texture=new THREE.CanvasTexture(canvas);texture.colorSpace=THREE.SRGBColorSpace;texture.anisotropy=4;const screenMaterial=new THREE.MeshBasicMaterial({map:texture,toneMapped:false});
 if(id==='round'){
  const profile=[[-.7525,2.40],[-.7,2.54],[-.55,2.70],[-.35,2.75],[.35,2.75],[.55,2.65],[.7525,2.448]].map(([z,r])=>new THREE.Vector2(r,z));
  const shell=new THREE.Mesh(new THREE.LatheGeometry(profile,128),silver);shell.rotation.x=Math.PI/2;group.add(shell);disc(group,2.41,.08,glass,d/2);disc(group,2.39,.05,silver,-d/2);
  const rim=new THREE.Mesh(new THREE.TorusGeometry(2.432,.035,12,128),silver);rim.position.z=d/2+.025;group.add(rim);
  for(const angle of [-.65,.65]){const b=box(group,.17,.53,.20,.07,silver,Math.cos(angle)*2.69,Math.sin(angle)*2.69,0);b.rotation.z=angle;}
  box(group,.83,.09,.34,.04,port,0,-2.71,0);for(const y of [-.55,0,.55])box(group,.07,.10,.11,.035,port,-2.718,y,0);
  const screen=new THREE.Mesh(new THREE.CircleGeometry(2.397,96),screenMaterial);screen.position.z=d/2+.048;group.add(screen);
 }else{
  box(group,w,h,d,id==='square'?.55:.39,id==='square'?white:dark);box(group,w-.08,h-.08,.10,.43,id==='square'?silver:dark,0,0,d/2);
  const shape=new THREE.ShapeGeometry(roundedShape(w-.38,h-.38,.38));const pos=shape.attributes.position,uv=shape.attributes.uv;for(let i=0;i<pos.count;i++)uv.setXY(i,(pos.getX(i)+(w-.38)/2)/(w-.38),(pos.getY(i)+(h-.38)/2)/(h-.38));
  const screen=new THREE.Mesh(shape,screenMaterial);screen.position.z=d/2+.10;group.add(screen);
  if(id==='rect'){box(group,.10,.88,.34,.06,silver,-w/2-.03,-.7,0);box(group,.12,.67,.18,.05,port,-w/2-.07,-.7,0);for(const y of [-1.2,1.2])box(group,.18,.5,.4,.07,dark,w/2+.04,y,0);box(group,.06,.65,.08,.025,port,-w/2-.04,.7,0);}
  else{box(group,.80,.09,.30,.04,port,0,-h/2-.045,.25);box(group,.07,1.2,.16,.03,port,-w/2-.04,0,.29);for(const x of [-1,0,1]){const b=new THREE.Mesh(new THREE.CylinderGeometry(.265,.265,.12,32),white);b.position.set(x,h/2+.08,-.165);group.add(b);}}
  for(const x of [-w/2+.45,w/2-.45])for(const y of [-h/2+.45,h/2-.45]){disc(group,.095,.05,silver,-d/2-.03).position.set(x,y,-d/2-.03);}
 }
 scene.add(group);const item={id,group,canvas,ctx:canvas.getContext('2d'),texture,w,h,d,target:new THREE.Vector3(),scale:1,screenKey:''};devices.push(item);return item;}
make('rect',3.76,4.52,1.5);make('round',5.5,5.5,1.505);make('square',4.6,4.6,2.25);
const shadowCanvas=document.createElement('canvas');shadowCanvas.width=256;shadowCanvas.height=128;const sx=shadowCanvas.getContext('2d'),gradient=sx.createRadialGradient(128,64,5,128,64,105);gradient.addColorStop(0,'#496a4c37');gradient.addColorStop(1,'#496a4c00');sx.fillStyle=gradient;sx.fillRect(0,0,256,128);const shadow=new THREE.Mesh(new THREE.PlaneGeometry(13,1.8),new THREE.MeshBasicMaterial({map:new THREE.CanvasTexture(shadowCanvas),transparent:true,depthWrite:false}));shadow.position.set(0,-3.15,-2);scene.add(shadow);
function layout(immediate=false){const others=devices.filter(d=>d.id!==selected);for(const d of devices){const active=d.id===selected;const index=others.indexOf(d);d.target.set(active?0:(index===0?-1:1)*(host.clientWidth<500?3.1:4.1),active?.08:-.15,active?1.35:-2.3);d.scale=active?1:host.clientWidth<500?.60:.69;if(immediate){d.group.position.copy(d.target);d.group.scale.setScalar(d.scale);}}dirty=true;}
layout(true);
function paint(d,t){const key=Math.floor(t*24)+':'+sceneIndex+':'+selected;if(key===d.screenKey)return;d.screenKey=key;drawScreen(d.canvas,sceneIndex,t,d.id==='round'?0:d.id==='rect'?1:2);d.texture.needsUpdate=true;}
function resize(){const {width,height}=host.getBoundingClientRect();renderer.setSize(width,height,false);camera.aspect=width/height;camera.position.z=width<500?14.8:12.8;camera.updateProjectionMatrix();layout();dirty=true;}
new ResizeObserver(resize).observe(host);resize();
function updateLabels(){document.querySelectorAll('[data-model]').forEach(x=>{const active=x.dataset.model===selected;x.classList.toggle('selected',active);x.setAttribute('aria-pressed',String(active));});document.querySelectorAll('[data-scene]').forEach(x=>{const active=Number(x.dataset.scene)===sceneIndex;x.classList.toggle('selected',active);x.setAttribute('aria-pressed',String(active));});document.querySelector('#screen-state').textContent=scenes[sceneIndex].detail;document.querySelector('#model-status').textContent=selected==='round'?'Waveshare 1.75C · הדגמה מונפשת עם נתונים לדוגמה':`Waveshare ${selected==='rect'?'1.8':'2.16'} · הדמיית ממשק, הקושחה בהכנה`;}
function chooseModel(id,manual=false){selected=id;dragYaw=0;layout(reduced.matches);updateLabels();if(manual)manualUntil=clock+12;}
function chooseScene(index,manual=false){sceneIndex=index;devices.forEach(d=>d.screenKey='');dirty=true;updateLabels();if(manual)manualUntil=clock+12;}
function render(ms){const delta=previous?Math.min((ms-previous)/1000,.1):0;previous=ms;if(document.hidden)return;if(!paused)clock+=delta;if((!dirty&&paused)||ms-last<33)return;last=ms;
 if(!paused&&!drag&&clock>manualUntil){const modelSlot=Math.floor(clock/12),sceneSlot=Math.floor(clock/5);if(modelSlot!==lastModelSlot){lastModelSlot=modelSlot;chooseModel(['round','rect','square'][modelSlot%3]);}if(sceneSlot!==lastSceneSlot){lastSceneSlot=sceneSlot;chooseScene(sceneSlot%scenes.length);}}
 let moving=false;for(const d of devices){const before=d.group.position.distanceTo(d.target);d.group.position.lerp(d.target,.09);const scale=THREE.MathUtils.lerp(d.group.scale.x,d.scale,.09);d.group.scale.setScalar(scale);if(before>.002||Math.abs(scale-d.scale)>.002)moving=true;const yaw=d.id===selected?-.14+dragYaw+Math.sin(clock*.6)*.17:d.target.x<0?.35:-.35;d.group.rotation.y=THREE.MathUtils.lerp(d.group.rotation.y,yaw,.1);if(Math.abs(d.group.rotation.y-yaw)>.002)moving=true;if(!paused)d.group.position.y+=Math.sin(clock*1.4+d.target.x)*.006;paint(d,clock);}renderer.render(scene,camera);dirty=moving;}
renderer.setAnimationLoop(render);
const motion=document.querySelector('#motion');function updateMotion(){motion.setAttribute('aria-pressed',String(paused));motion.setAttribute('aria-label',paused?'הפעלת ההדגמה':'עצירת ההדגמה');motion.innerHTML=icon(paused?'play':'pause');dirty=true;}motion.onclick=()=>{paused=!paused;updateMotion();};reduced.addEventListener('change',()=>{paused=reduced.matches;updateMotion();});updateMotion();updateLabels();
document.querySelectorAll('[data-model]').forEach(b=>b.onclick=()=>chooseModel(b.dataset.model,true));document.querySelectorAll('[data-scene]').forEach(b=>b.onclick=()=>chooseScene(Number(b.dataset.scene),true));
document.querySelector('#demo').onclick=()=>chooseScene((sceneIndex+1)%scenes.length,true);
host.onpointerdown=e=>{drag={x:e.clientX,yaw:dragYaw};manualUntil=clock+12;host.setPointerCapture(e.pointerId);host.classList.add('dragging');};host.onpointermove=e=>{if(drag){dragYaw=drag.yaw+(e.clientX-drag.x)*.014;dirty=true;}};host.onpointerup=host.onpointercancel=()=>{drag=null;host.classList.remove('dragging');};host.onkeydown=e=>{if(['ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();dragYaw+=e.key==='ArrowLeft'?-.2:.2;manualUntil=clock+12;dirty=true;}};
document.addEventListener('visibilitychange',()=>{previous=0;if(!document.hidden)dirty=true;});renderer.domElement.addEventListener('webglcontextlost',()=>{renderer.setAnimationLoop(null);document.querySelector('#fallback').hidden=false;});
// Ensure the first still frame also loads when reduced motion is enabled.
document.fonts.ready.then(()=>{devices.forEach(d=>d.screenKey='');dirty=true;});setTimeout(()=>{devices.forEach(d=>d.screenKey='');dirty=true;},800);

window.addEventListener("wappai-art-ready",()=>{devices.forEach(d=>d.screenKey="");dirty=true;});
