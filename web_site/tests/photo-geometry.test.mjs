import test from 'node:test';
import assert from 'node:assert/strict';
import {findPaperQuad,validateCorners,warpPerspective} from '../dist/modules/photo-geometry.js';
const full=[{x:0,y:0},{x:1,y:0},{x:1,y:1},{x:0,y:1}];
function raster(width,height,color){const pixels=new Uint8ClampedArray(width*height*4);for(let i=0;i<pixels.length;i+=4)pixels.set([...color,255],i);return pixels;}
function polygon(pixels,width,height,quad,color){for(let y=0;y<height;y++)for(let x=0;x<width;x++){if(quad.every((p,i)=>{const q=quad[(i+1)%quad.length];return(q.x-p.x)*(y-p.y)-(q.y-p.y)*(x-p.x)>=0;}))pixels.set([...color,255],(y*width+x)*4);}}

test('corner validation rejects crossings, wrong order, outside points and unreadable slivers',()=>{
  const copy=validateCorners(full,{width:640,height:480});assert.deepEqual(copy,full);assert.notEqual(copy,full);assert.notEqual(copy[0],full[0]);
  for(const corners of [null,[],[full[0],full[2],full[1],full[3]],full.map(p=>({x:p.x*1.1,y:p.y})),[{x:0,y:0},{x:1,y:0},{x:1,y:.001},{x:0,y:.001}],full.slice().reverse()])assert.throws(()=>validateCorners(corners,{width:640,height:480}));
});

test('light scan keeps its full image and an ambiguous uniform dark photograph has no proposed crop',()=>{
  const scan=raster(300,150,[255,255,255]);for(let y=50;y<90;y++)for(let x=110;x<130;x++)scan.set([235,140,30,255],(y*300+x)*4);
  const found=findPaperQuad(scan,300,150);assert.deepEqual(found.corners,full);assert.equal(found.framed,true);
  assert.equal(findPaperQuad(raster(300,200,[90,90,90]),300,200).corners,null);
});

test('paper detection fits contrasting rotated perspective edges rather than a light-object bounding box',()=>{
  const width=320,height=240,pixels=raster(width,height,[94,62,39]),quad=[{x:39,y:26},{x:289,y:43},{x:272,y:215},{x:49,y:201}];polygon(pixels,width,height,quad,[235,235,230]);
  for(let y=100;y<125;y++)for(let x=110;x<145;x++)pixels.set([245,141,28,255],(y*width+x)*4);
  const found=findPaperQuad(pixels,width,height);assert.ok(found.confidence>.8);assert.ok(found.corners);
  for(let i=0;i<4;i++)assert.ok(Math.hypot(found.corners[i].x*(width-1)-quad[i].x,found.corners[i].y*(height-1)-quad[i].y)<3);
});

test('an image-edge-clipped sheet is declined instead of inventing its missing corner',()=>{
  const width=320,height=240,pixels=raster(width,height,[94,62,39]);polygon(pixels,width,height,[{x:-12,y:20},{x:289,y:40},{x:270,y:215},{x:-10,y:200}],[235,235,230]);assert.equal(findPaperQuad(pixels,width,height).corners,null);
});

test('identity warp preserves every source channel exactly and leaves its input untouched',()=>{
  const width=23,height=17,pixels=raster(width,height,[0,0,0]);for(let y=0;y<height;y++)for(let x=0;x<width;x++)pixels.set([x*9,y*13,(x+y)*5,255],(y*width+x)*4);const original=pixels.slice();
  const result=warpPerspective(pixels,width,height,full);assert.equal(result.width,width);assert.equal(result.height,height);assert.deepEqual(result.pixels,pixels);assert.deepEqual(pixels,original);
});

test('manual projective crop samples its actual four source corners and stays size bounded',()=>{
  const width=100,height=80,pixels=raster(width,height,[0,0,0]),points=[{x:10,y:10},{x:85,y:15},{x:80,y:68},{x:15,y:65}],colors=[[250,20,30],[20,240,40],[30,40,230],[220,210,25]];
  for(let i=0;i<4;i++)for(let y=points[i].y-1;y<=points[i].y+1;y++)for(let x=points[i].x-1;x<=points[i].x+1;x++)pixels.set([...colors[i],255],(y*width+x)*4);
  const result=warpPerspective(pixels,width,height,points.map(p=>({x:p.x/(width-1),y:p.y/(height-1)})),{maxSide:64});assert.ok(Math.max(result.width,result.height)<=64);
  for(const [i,[x,y]]of [[0,[0,0]],[1,[result.width-1,0]],[2,[result.width-1,result.height-1]],[3,[0,result.height-1]]])assert.deepEqual([...result.pixels.slice((y*result.width+x)*4,(y*result.width+x)*4+3)],colors[i]);
});
