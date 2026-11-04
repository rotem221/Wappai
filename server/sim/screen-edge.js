// Screen-edge animation follows the display outline, at constant perimeter speed.
export function screenEdge(c,shape,width,height,start=0,fraction=1,color='#61dcb2',thickness=5){
 const inset=Math.min(width,height)*.035,r=Math.min(width,height)*.12;
 c.save();c.strokeStyle=color;c.lineWidth=thickness;c.lineCap='round';
 const p=new Path2D();let length;
 if(shape==='round'){
  const radius=Math.min(width,height)/2-inset;
  p.arc(width/2,height/2,radius,-Math.PI/2,Math.PI*1.5);length=2*Math.PI*radius;
 }else{
  const left=inset,top=inset,right=width-inset,bottom=height-inset;
  p.moveTo(width/2,top);p.lineTo(right-r,top);p.arcTo(right,top,right,top+r,r);
  p.lineTo(right,bottom-r);p.arcTo(right,bottom,right-r,bottom,r);
  p.lineTo(left+r,bottom);p.arcTo(left,bottom,left,bottom-r,r);
  p.lineTo(left,top+r);p.arcTo(left,top,left+r,top,r);p.lineTo(width/2,top);
  length=2*(width+height-4*inset-4*r)+2*Math.PI*r;
 }
 if(fraction>0){if(fraction<1){c.setLineDash([fraction*length,(1-fraction)*length]);c.lineDashOffset=-((start%1+1)%1)*length;}c.stroke(p);}
 c.restore();
}
