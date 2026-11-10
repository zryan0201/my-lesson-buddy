import test from 'node:test';
import assert from 'node:assert/strict';
import {processWorksheetPhoto} from '../dist/modules/photo.js';
const DATA='data:image/png;base64,aGVsbG8=';
const full=[{x:0,y:0},{x:1,y:0},{x:1,y:1},{x:0,y:1}];
function pixels(width,height,color){const out=new Uint8ClampedArray(width*height*4);for(let i=0;i<out.length;i+=4)out.set([...color,255],i);return out;}
function browser(t,{width=120,height=80,data=pixels(width,height,[255,255,255]),defer=false}={}){
  const old={Image:globalThis.Image,document:globalThis.document},canvases=[],images=[];
  t.after(()=>{for(const key of ['Image','document'])if(old[key]===undefined)delete globalThis[key];else globalThis[key]=old[key];});
  globalThis.Image=class{naturalWidth=width;naturalHeight=height;pixels=data;constructor(){images.push(this);}set src(value){this.url=value;if(value&&!defer)queueMicrotask(()=>this.onload?.());}};
  globalThis.document={createElement:()=>{const canvas={width:0,height:0,buffer:null,getContext(){return ctx;},toDataURL(){return `data:image/png;base64,output${canvases.indexOf(canvas)}`;}};const ctx={fillRect(){canvas.buffer=new Uint8ClampedArray(canvas.width*canvas.height*4).fill(255);},drawImage(image){canvas.buffer=new Uint8ClampedArray(canvas.width*canvas.height*4);for(let y=0;y<canvas.height;y++)for(let x=0;x<canvas.width;x++){const sx=Math.min(width-1,Math.floor(x*width/canvas.width)),sy=Math.min(height-1,Math.floor(y*height/canvas.height));canvas.buffer.set(image.pixels.subarray((sy*width+sx)*4,(sy*width+sx)*4+4),(y*canvas.width+x)*4);}},getImageData(){return{data:canvas.buffer.slice()};},createImageData(w,h){return{data:new Uint8ClampedArray(w*h*4)};},putImageData(image){canvas.buffer=image.data.slice();}};canvases.push(canvas);return canvas;}};
  return{canvases,images,data};
}

test('photo preparation rejects executable or remote pictures and invalid options before decoding',async t=>{
  const mocked=browser(t);
  for(const dataURL of ['https://example.com/private.jpg','data:image/svg+xml;base64,aGVsbG8=',null])await assert.rejects(processWorksheetPhoto(dataURL),/PNG, JPEG, or WebP/);
  await assert.rejects(processWorksheetPhoto(DATA,{corners:[{x:0,y:0}]}),/four paper corners/);
  await assert.rejects(processWorksheetPhoto(DATA,{reduceShadows:'yes'}),/whether/);assert.equal(mocked.images.length,0);
});

test('a clean already-framed worksheet keeps its geometry and original pixels',async t=>{
  const data=pixels(120,80,[255,255,255]);for(let y=28;y<50;y++)for(let x=40;x<52;x++)data.set([240,160,20,255],(y*120+x)*4);const mocked=browser(t,{data});
  const result=await processWorksheetPhoto(DATA);assert.equal(result.status,'unchanged');assert.equal(result.detected,true);assert.deepEqual(result.corners,full);assert.deepEqual(result.steps,{cropped:false,perspective:false,shadows:false});assert.deepEqual(mocked.canvases.at(-1).buffer,data);
});

test('manual corners are applied to a fresh source and can disable lighting changes',async t=>{
  const mocked=browser(t,{width:200,height:160});const corners=[{x:.1,y:.1},{x:.9,y:.15},{x:.85,y:.9},{x:.15,y:.8}];
  const result=await processWorksheetPhoto(DATA,{corners,reduceShadows:false});assert.equal(result.status,'corrected');assert.equal(result.detected,false);assert.equal(result.stats.manual,true);assert.equal(result.steps.cropped,true);assert.equal(result.steps.perspective,true);assert.equal(result.steps.shadows,false);assert.ok(result.stats.outputWidth<200&&result.stats.outputHeight<160);assert.notEqual(result.corners,corners);assert.equal(mocked.images.length,1);
});

test('uncertain paper edges return the original full photo without silently applying a crop or lighting',async t=>{
  const mocked=browser(t,{data:pixels(120,80,[100,100,100])});const result=await processWorksheetPhoto(DATA);assert.equal(result.status,'needs-corners');assert.equal(result.detected,false);assert.deepEqual(result.corners,full);assert.deepEqual(result.steps,{cropped:false,perspective:false,shadows:false});assert.deepEqual(mocked.canvases[0].buffer,mocked.data);assert.equal(mocked.canvases.length,1);
});

test('a cancelled photo decode cannot produce a prepared image',async t=>{
  const mocked=browser(t,{defer:true}),controller=new AbortController();const pending=processWorksheetPhoto(DATA,{signal:controller.signal});controller.abort();await assert.rejects(pending,{name:'AbortError'});assert.equal(mocked.images[0].url,'');assert.equal(mocked.canvases.length,0);
  const before=mocked.images.length;await assert.rejects(processWorksheetPhoto(DATA,{signal:controller.signal}),{name:'AbortError'});assert.equal(mocked.images.length,before);
});
