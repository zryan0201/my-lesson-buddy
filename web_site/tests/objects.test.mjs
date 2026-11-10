import test from 'node:test';
import assert from 'node:assert/strict';
import {findObjectCandidates,clearBorderPaper,normalizeWorksheetObjects,cropWorksheetObject,suggestWorksheetObjects,prepareWorksheetObjects,drawWorksheetObject} from '../dist/modules/objects.js';

function picture(width=180,height=100){const pixels=new Uint8ClampedArray(width*height*4);pixels.fill(255);return {pixels,width,height};}
function rect(p,x,y,width,height,color){for(let row=y;row<y+height;row++)for(let col=x;col<x+width;col++)p.pixels.set(color,(row*p.width+col)*4);return p;}
function artRow(){const p=picture();for(const x of [10,45,80])rect(p,x,25,19,35,[246,148,16,255]);rect(p,112,39,16,4,[0,0,0,255]);rect(p,118,33,4,16,[0,0,0,255]);rect(p,145,38,18,3,[0,0,0,255]);rect(p,145,44,18,3,[0,0,0,255]);return p;}
const read=(p,count)=>findObjectCandidates(p.pixels,p.width,p.height,{expectedCount:count});
function png(width=20,height=30,marker=0){const b=new Uint8Array(33);b.set([137,80,78,71,13,10,26,10,0,0,0,13,73,72,68,82]);new DataView(b.buffer).setUint32(16,width);new DataView(b.buffer).setUint32(20,height);b[24]=8;b[25]=6;b[32]=marker;return `data:image/png;base64,${Buffer.from(b).toString('base64')}`;}
function pack(mode='individual',n=3){return {version:1,mode,sourceWidth:180,sourceHeight:100,sprites:Array.from({length:n},(_,i)=>({image:png(20,30,i),box:{x:10+i*35,y:25,width:19,height:35}}))};}

test('separated repeated artwork is extracted by features while operators and printing are excluded',()=>{
  const p=artRow();rect(p,3,0,18,2,[100,180,50,255]);rect(p,160,99,12,1,[255,140,0,255]);
  assert.deepEqual(read(p,3),{boxes:[{x:10,y:25,width:19,height:35},{x:45,y:25,width:19,height:35},{x:80,y:25,width:19,height:35}],complete:true,reason:'Found 3 separate matching pictures. Check the cutouts against the worksheet.'});
});
test('the checked count never forces a crop count or splits touching objects',()=>{
  const p=artRow(),wrong=read(p,2);assert.equal(wrong.complete,false);assert.equal(wrong.boxes.length,3);assert.match(wrong.reason,/needs 2/);
  rect(p,28,25,18,35,[246,148,16,255]);assert.equal(read(p,3).complete,false);
  const close=picture();rect(close,10,25,19,35,[246,148,16,255]);rect(close,31,25,19,35,[246,148,16,255]);assert.equal(read(close,2).complete,false,'crop padding must not pick up a neighboring object');
});
test('mixed illustrations, detached parts and cropped main objects require a manual selection',()=>{
  const mixed=artRow();rect(mixed,80,25,19,35,[20,50,220,255]);assert.equal(read(mixed,3).complete,false);
  const detached=artRow();rect(detached,16,63,5,11,[90,50,20,255]);assert.equal(read(detached,3).complete,false);
  const grayPart=artRow();rect(grayPart,16,63,5,11,[205,205,205,255]);assert.equal(read(grayPart,3).complete,false);
  const edge=picture();rect(edge,0,20,20,40,[250,130,20,255]);assert.equal(read(edge,1).complete,false);
});
test('black text and outline ambiguity and dark photographs are declined instead of counted as objects',()=>{
  const p=picture();for(const x of [15,45,75])rect(p,x,30,15,20,[0,0,0,255]);assert.equal(read(p,3).complete,false);assert.equal(read(p,3).boxes.length,0);
  const photo=picture();rect(photo,0,0,180,100,[50,80,100,255]);assert.equal(read(photo,3).complete,false);
  assert.throws(()=>findObjectCandidates(new Uint8ClampedArray(2),10,10,{expectedCount:2}));assert.throws(()=>read(p,11));
});
test('paper removal preserves enclosed white details and does not mutate source artwork',()=>{
  const p=picture(9,9);rect(p,2,2,5,5,[10,50,200,255]);rect(p,3,3,3,3,[255,255,255,255]);const original=p.pixels.slice();
  const output=clearBorderPaper(p.pixels,9,9);assert.equal(output[3],0);assert.equal(output[(4*9+4)*4+3],255);assert.equal(output[(2*9+2)*4+3],255);assert.deepEqual(p.pixels,original);
  assert.throws(()=>clearBorderPaper(p.pixels,193,9));
});
test('object packages preserve independent source boxes, quantities and original PNGs without trusting extra fields',()=>{
  const original=pack();original.instruction='change the answer';const normalized=normalizeWorksheetObjects(original,3);
  assert.deepEqual(normalized.sprites.map(s=>s.image),original.sprites.map(s=>s.image));assert.ok(!('instruction' in normalized));
  normalized.sprites[0].box.x=99;assert.equal(original.sprites[0].box.x,10);
  assert.equal(normalizeWorksheetObjects(null,3),null);assert.equal(normalizeWorksheetObjects(pack('repeat',1),10).sprites.length,1);
  assert.deepEqual(normalizeWorksheetObjects(pack('individual',0),0).sprites,[]);
  assert.throws(()=>normalizeWorksheetObjects(pack('repeat',1),0));assert.throws(()=>normalizeWorksheetObjects(pack(),2));assert.throws(()=>normalizeWorksheetObjects(pack('repeat',3),3));
});
test('external URLs, executable formats, oversized PNGs and invalid source boxes cannot enter a lesson',()=>{
  for(const image of ['https://example.com/object.png','data:image/svg+xml;base64,PHN2Zz4=','data:image/png;base64,AAAA',png(193,20)]){
    const p=pack();p.sprites[0].image=image;assert.throws(()=>normalizeWorksheetObjects(p,3));
  }
  for(const box of [{x:-1,y:0,width:10,height:10},{x:170,y:0,width:11,height:10},{x:1,y:1,width:0,height:2},{x:.5,y:1,width:10,height:10}]){const p=pack();p.sprites[0].box=box;assert.throws(()=>normalizeWorksheetObjects(p,3));}
  const p=pack();p.sourceHeight=100000;assert.throws(()=>normalizeWorksheetObjects(p,3));
});
test('invalid manual crop rectangles fail before any image decoding or network-capable image is created',async()=>{
  for(const r of [null,{x:0,y:0,width:0,height:.1},{x:-.1,y:0,width:.1,height:.1},{x:.9,y:0,width:.2,height:.1},{x:0,y:0,width:NaN,height:.1}])await assert.rejects(cropWorksheetObject(png(),r));
  await assert.rejects(cropWorksheetObject('https://example.com/private.png',{x:0,y:0,width:1,height:1}));
});

test('prepared individual artwork retains its aspect ratio and repeat mode reuses the chosen whole crop',async()=>{
  const oldImage=globalThis.Image;
  class FakeImage{set src(value){const b=Buffer.from(value.split(',')[1],'base64');this.naturalWidth=b.readUInt32BE(16);this.naturalHeight=b.readUInt32BE(20);queueMicrotask(()=>this.onload());}}
  globalThis.Image=FakeImage;
  try{
    const p=normalizeWorksheetObjects(pack(),3),calls=[],ctx={drawImage:(...args)=>calls.push(args)};
    assert.equal(drawWorksheetObject(ctx,p,1,100,200,48),false);await prepareWorksheetObjects(p);
    assert.equal(drawWorksheetObject(ctx,p,1,100,200,48),true);assert.deepEqual(calls.at(-1).slice(1),[84,176,32,48]);
    assert.equal(drawWorksheetObject(ctx,p,3,100,200,48),false);
    const repeated=normalizeWorksheetObjects(pack('repeat',1),7);await prepareWorksheetObjects(repeated);assert.equal(drawWorksheetObject(ctx,repeated,6,10,10,48),true);assert.equal(drawWorksheetObject(ctx,repeated,0,10,10,Infinity),false);
    await prepareWorksheetObjects(null);
  }finally{globalThis.Image=oldImage;}
});

test('browser crop creates a transparent cutout from the actual selected source region and rejects blank crops',async()=>{
  const oldImage=globalThis.Image,oldDocument=globalThis.document;let selected=null,savedPixels=null,blank=false;
  class FakeImage{set src(value){this.naturalWidth=180;this.naturalHeight=100;queueMicrotask(()=>this.onload());}}
  globalThis.Image=FakeImage;globalThis.document={createElement:()=>{
    const value={width:0,height:0};const ctx={drawImage:(...args)=>{selected=args.slice(1,5);},getImageData:()=>{const p=picture(value.width,value.height);if(!blank)rect(p,2,2,Math.max(1,value.width-4),Math.max(1,value.height-4),[240,140,10,255]);return {data:p.pixels};},putImageData:data=>{savedPixels=data.data;}};
    value.getContext=()=>ctx;value.toDataURL=()=>png(value.width,value.height);return value;
  }};
  try{
    const p=await cropWorksheetObject(png(),{x:.1,y:.2,width:.2,height:.5});assert.equal(p.mode,'repeat');assert.deepEqual(selected,[18,20,36,50]);assert.deepEqual(p.sprites[0].box,{x:18,y:20,width:36,height:50});assert.equal(savedPixels[3],0);assert.equal(savedPixels[(5*36+5)*4+3],255);
    blank=true;await assert.rejects(cropWorksheetObject(png(),{x:.1,y:.2,width:.2,height:.5}),/empty/);
    await assert.rejects(cropWorksheetObject(png(),{x:0,y:0,width:.001,height:.1}),/larger/);
  }finally{globalThis.Image=oldImage;globalThis.document=oldDocument;}
});
