import test from 'node:test';
import assert from 'node:assert/strict';
import {normalizePaperLighting} from '../dist/modules/lighting.js';

function image(width=320,height=200,color=[255,255,255]){
  const pixels=new Uint8ClampedArray(width*height*4);
  for(let i=0;i<width*height;i++)pixels.set([...color,255],i*4);
  return {pixels,width,height};
}
function rectangle(p,x,y,w,h,color){for(let yy=y;yy<y+h;yy++)for(let xx=x;xx<x+w;xx++)p.pixels.set([...color,255],(yy*p.width+xx)*4);}
function shade(p,light){const copy=p.pixels.slice();for(let y=0;y<p.height;y++)for(let x=0;x<p.width;x++){const gain=light(x/p.width,y/p.height),at=(y*p.width+x)*4;for(let c=0;c<3;c++)copy[at+c]=p.pixels[at+c]*gain;}return copy;}
function sample(pixels,width,x,y){return [...pixels.slice((y*width+x)*4,(y*width+x)*4+3)];}

test('a paper light gradient is reduced without modifying source pixels or drawing replacement objects',()=>{
  const p=image();rectangle(p,30,70,30,55,[232,132,25]);rectangle(p,135,70,30,55,[232,132,25]);rectangle(p,235,70,30,55,[232,132,25]);rectangle(p,90,110,20,4,[12,12,12]);
  const photographed=shade(p,(x)=>.65+.35*x),before=photographed.slice();
  const result=normalizePaperLighting(photographed,p.width,p.height);
  assert.equal(result.applied,true);assert.deepEqual(photographed,before);
  assert.ok(Math.min(...sample(result.pixels,p.width,8,25))>=237,'dark paper becomes light enough to separate ink');
  assert.ok(Math.min(...sample(result.pixels,p.width,250,25))>=244);
  const object=sample(result.pixels,p.width,42,92);assert.ok(object[0]>195&&object[1]>100&&object[2]<38,'orange artwork stays orange');
  assert.ok(object[0]/object[1]>1.65&&object[0]/object[1]<1.85,'one shared gain retains the color ratio');
  assert.ok(Math.max(...sample(result.pixels,p.width,98,111))<24,'black print remains black');
  for(let i=3;i<result.pixels.length;i+=4)assert.equal(result.pixels[i],photographed[i]);
});
test('a broad soft shadow is reduced while colorful ink stays distinct from paper',()=>{
  const p=image(400,240);rectangle(p,145,90,35,55,[20,130,220]);
  const photographed=shade(p,(x,y)=>1-.32*Math.exp(-((x-.35)**2+(y-.5)**2)/.07));
  const result=normalizePaperLighting(photographed,p.width,p.height);
  assert.equal(result.applied,true);
  assert.ok(Math.min(...sample(result.pixels,p.width,120,60))>230);
  const blue=sample(result.pixels,p.width,160,115);assert.ok(blue[0]<35&&blue[1]>100&&blue[2]>180);
  assert.ok(result.stats.maxGain>1&&result.stats.maxGain<=2.35);
});
test('uniform clean artwork and uniform gray or very dark paper are not whitened by assumption',()=>{
  for(const color of [[255,255,255],[245,245,245],[185,185,185],[65,65,65]]){
    const p=image(160,120,color);rectangle(p,30,40,30,35,[210,80,35]);
    const result=normalizePaperLighting(p.pixels,p.width,p.height);assert.equal(result.applied,false);assert.deepEqual(result.pixels,p.pixels);assert.notEqual(result.pixels,p.pixels);
  }
});
test('colored paper, insufficient paper evidence and disabled correction remain unchanged',()=>{
  const colored=image(160,120,[235,210,160]),dark=image(160,120,[40,40,40]);rectangle(dark,10,10,15,15,[255,255,255]);
  for(const p of [colored,dark]){const result=normalizePaperLighting(p.pixels,p.width,p.height);assert.equal(result.applied,false);assert.deepEqual(result.pixels,p.pixels);}
  const p=image(),photographed=shade(p,x=>.65+.35*x),disabled=normalizePaperLighting(photographed,p.width,p.height,{strength:0});assert.equal(disabled.applied,false);assert.deepEqual(disabled.pixels,photographed);
});
test('correction strength blends a bounded gain and preserves transparent pixels',()=>{
  const p=image(),photographed=shade(p,x=>.65+.35*x);photographed.set([80,110,150,0],0);
  const full=normalizePaperLighting(photographed,p.width,p.height),half=normalizePaperLighting(photographed,p.width,p.height,{strength:.5});
  assert.deepEqual([...full.pixels.slice(0,4)],[80,110,150,0]);
  const at=(25*p.width+8)*4;assert.ok(half.pixels[at]>photographed[at]&&half.pixels[at]<full.pixels[at]);
});
test('invalid or excessive image inputs and strength values fail before allocating image work',()=>{
  for(const [pixels,w,h,options] of [[new Uint8ClampedArray(4),0,1,{}],[new Uint8ClampedArray(4),1,2,{}],[[],1,1,{}],[new Uint8ClampedArray(4),2000,2000,{}],[new Uint8ClampedArray(4),1,1,{strength:NaN}],[new Uint8ClampedArray(4),1,1,{strength:1.1}]])assert.throws(()=>normalizePaperLighting(pixels,w,h,options));
});
