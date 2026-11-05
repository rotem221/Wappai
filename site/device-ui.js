// Presentation layouts at the catalog's native resolutions. No board drivers or device calls.
export const displayProfiles=Object.freeze({round:{width:466,height:466,board:'ws-s3-175c'},rect:{width:368,height:448,board:'ws-s3-18'},square:{width:480,height:480,board:'ws-s3-216'}});
export const theme=Object.freeze({bg:'#02070d',surface:'#172536',raised:'#253b54',border:'#496783',accent:'#a4d2ff',ink:'#e9f1fa',muted:'#91a6bc'});
export function layoutFor(shape,width,height){
 if(!displayProfiles[shape]||!Number.isFinite(width)||!Number.isFinite(height)||width<200||height<200)throw Error('Invalid display profile');
 const unit=Math.min(width,height)/466,round=shape==='round',inset=round?width*.22:width*.075;
 return {width,height,unit,cx:width/2,cy:height/2,round,inset,contentWidth:width-2*inset,buttonHeight:Math.max(46,64*unit),radius:Math.min(width,height)*.485};
}
function text(c,value,x,y,size,color=theme.ink,weight=600){c.fillStyle=color;c.textAlign='center';c.textBaseline='middle';c.font=`${weight} ${size}px Heebo, sans-serif`;c.fillText(value,x,y);}
function line(c,x,y,xx,yy,width,color){c.strokeStyle=color;c.lineWidth=width;c.lineCap='round';c.beginPath();c.moveTo(x,y);c.lineTo(xx,yy);c.stroke();}
function box(c,x,y,w,h,r,fill=theme.surface){c.fillStyle=fill;c.strokeStyle=theme.border;c.lineWidth=1;c.beginPath();c.roundRect(x+.5,y+.5,w-1,h-1,r);c.fill();c.stroke();}
function circle(c,x,y,r,color){c.fillStyle=color;c.beginPath();c.arc(x,y,r,0,Math.PI*2);c.fill();}
function title(c,label,l){text(c,label,l.cx,l.height*.20,Math.max(18,23*l.unit),theme.muted);}
export function drawDeviceUI(canvas,mode,t=0,shape='round',clockStyle=0){
 const c=canvas.getContext('2d'),l=layoutFor(shape,canvas.width,canvas.height),{width:W,height:H,unit:u,cx,cy}=l;
 c.save();c.fillStyle=theme.bg;c.fillRect(0,0,W,H);
 if(mode==='clock')drawClock(c,l,clockStyle,t);
 else if(mode==='timer-picker'){
  title(c,'טיימר',l);const gap=12*u,cw=Math.min(84*u,(W-2*l.inset-2*gap)/3),x0=cx-(3*cw+2*gap)/2,top=H*.40,fh=86*u,bh=Math.max(44,46*u);
  ['שעות','דקות','שניות'].forEach((name,i)=>{const x=x0+i*(cw+gap),center=x+cw/2;
   box(c,x,top-bh-14*u,cw,bh,16*u,theme.raised);line(c,center-8*u,top-bh/2-14*u,center+8*u,top-bh/2-14*u,3*u,theme.accent);line(c,center,top-bh/2-22*u,center,top-bh/2-6*u,3*u,theme.accent);
   box(c,x,top,cw,fh,20*u);text(c,i===1?'05':'00',center,top+34*u,36*u);text(c,name,center,top+66*u,Math.max(13,15*u),theme.muted);
   box(c,x,top+fh+12*u,cw,bh,16*u,theme.raised);line(c,center-8*u,top+fh+12*u+bh/2,center+8*u,top+fh+12*u+bh/2,3*u,theme.accent);
  });box(c,cx-80*u,H*.81,160*u,l.buttonHeight*.8,20*u);text(c,'התחלה',cx,H*.81+l.buttonHeight*.4,22*u,theme.accent);
 }else{
  title(c,'הגדרות',l);const x=l.inset,w=l.contentWidth,h=l.buttonHeight;
  ['רשת Wi-Fi','כיבוי מסך'].forEach((label,i)=>{const y=H*.33+i*(h+20*u);box(c,x,y,w,h,22*u);text(c,label,cx,y+h/2,Math.max(18,23*u));});
  text(c,'ימין: בהירות · שמאל: עוצמה',cx,H*.79,Math.max(13,16*u),theme.muted);
  // Brief illustrative edge feedback, matching the hardware overlay.
  if(t%6>3){const w=Math.min(W*.72,270*u),h=128*u,y=cy-h/2;box(c,cx-w/2,y,w,h,26*u);text(c,'בהירות',cx,y+27*u,18*u,theme.muted);text(c,'70%',cx,y+65*u,36*u);line(c,cx-85*u,y+103*u,cx+85*u,y+103*u,7*u,theme.raised);line(c,cx-85*u,y+103*u,cx+34*u,y+103*u,7*u,theme.accent);}
 }
 c.restore();
}
function drawClock(c,l,style,t){
 const {width:W,height:H,cx,unit:u}=l;style=((style%6)+6)%6;
 const cy=l.round?H/2:Math.min(H/2,H*.46),r=l.round?l.radius:Math.min(W*.46,H*.42),seconds=Math.floor(t)%60;
 const label=(v,x,y,size,color,weight)=>text(c,v,x,y,size*u,color,weight);
 if(style===0){label('יום חמישי, 5 בנובמבר',cx,H*.22,22,theme.muted);label('09:41',cx,H*.45,98,theme.ink,700);label('18°  ☀',cx,H*.69,46,theme.accent);label('מעונן חלקית',cx,H*.81,20,theme.muted);return;}
 if(style===2){label('09',cx,H*.31,153,'#dbb9ff',700);label('41',cx,H*.66,153,'#8764c5',700);label('05 / 11',cx,H*.89,18,theme.muted);return;}
 if(style===5){markers(c,cx,cy,r-7*u,theme.border,false,u);label('יום חמישי, 5 בנובמבר',cx,H*.30,20,theme.muted);label('09:41',cx,cy,106,theme.ink,700);label('WAPPAI',cx,H*.72,18,theme.muted);return;}
 const classic=style===1,sport=style===4,ink=classic?'#d9c79a':sport?'#dbeaf1':'#fff2d9',accent=classic?'#9cdfc1':sport?'#ff884d':'#ff7547';
 circle(c,cx,cy,r,classic?'#071d17':sport?'#07101d':'#211008');
 if(classic||sport){c.strokeStyle=theme.border;c.lineWidth=u;c.beginPath();c.arc(cx,cy,r-5*u,0,Math.PI*2);c.stroke();markers(c,cx,cy,r-20*u,ink,classic,u);label('WAPPAI',cx,cy-r*.40,18,ink);label(classic?'קלאסי':'ספורט',cx,cy+r*.35,17,theme.muted);
  box(c,cx+r*.45,cy-17*u,48*u,34*u,6*u,'#cad9ce');text(c,'05',cx+r*.45+24*u,cy,22*u,'#13251e',700);
 }
 if(sport||style===3){const n=style===3?72:42,margin=style===3?.74:.68;for(const [v,a] of [['12',-Math.PI/2],['3',0],['6',Math.PI/2],['9',Math.PI]])if(!(sport&&v==='3'))label(v,cx+Math.cos(a)*r*margin,cy+Math.sin(a)*r*margin,n,style===3?'#ffaa68':ink,700);}
 const hand=(angle,length,width,color)=>line(c,cx,cy,cx+Math.cos(angle)*length,cy+Math.sin(angle)*length,width*u,color);
 hand((9+41/60)*Math.PI/6-Math.PI/2,r*.44,10,ink);hand((41+seconds/60)*Math.PI/30-Math.PI/2,r*.67,6,ink);hand(seconds*Math.PI/30-Math.PI/2,r*.77,2,accent);circle(c,cx,cy,8*u,ink);circle(c,cx,cy,3*u,accent);
 if(!l.round)label('יום חמישי · 05 / 11',cx,H*.94,17,theme.muted);
}
function markers(c,cx,cy,r,ink,batons,u){for(let i=0;i<60;i++){const a=i*Math.PI/30-Math.PI/2,len=(i%5?5:batons?23:12)*u;line(c,cx+Math.cos(a)*(r-len),cy+Math.sin(a)*(r-len),cx+Math.cos(a)*r,cy+Math.sin(a)*r,(i%5?1:batons?6:3)*u,i%5?theme.border:ink);}}
