import test from 'node:test';
import assert from 'node:assert/strict';
import {POLISH_MODEL,blendPolish,checkPolishPixels,polishTiles,polishTilePixels,placePolishTile,reflectPixel} from '../dist/modules/drawing-polish-core.js';
import {polishStatus,enhanceDrawingPixels,disposeDrawingPolish,prepareDrawingPolish} from '../dist/modules/drawing-polish.js';
const pixels=(width=2,height=2,color=[80,120,160,255])=>({width,height,data:new Uint8ClampedArray(Array.from({length:width*height},()=>color).flat())});

test('zero strength is pixel-exact; bounded enhancement retains alpha, white paper, and input buffers',()=>{
 const original=pixels(2,1);original.data.set([255,255,255,127],4);const copy=original.data.slice(),learned=pixels(2,1,[255,0,255,0]);
 assert.deepEqual(blendPolish(original,learned,0).data,copy);
 const strong=blendPolish(original,learned,1);assert.deepEqual([...strong.data],[120,80,200,255,255,255,255,127]);assert.deepEqual(original.data,copy);
 const gentle=blendPolish(original,learned,.5);assert.deepEqual([...gentle.data.slice(0,4)],[100,100,180,255]);
 const transparent=pixels(1,1,[3,44,99,0]);assert.deepEqual(blendPolish(transparent,pixels(1,1),1).data,transparent.data);
 for(const value of [-1,1.1,NaN,'0.5'])assert.throws(()=>blendPolish(original,learned,value));assert.throws(()=>blendPolish(original,pixels(1,1),.5));
});
test('tiled reconstruction covers each output pixel exactly once, including partial edge tiles',()=>{
 const width=273,height=259,coverage=new Uint8Array(width*height*4),target=pixels(width*2,height*2,[0,0,0,0]);
 const edge=(POLISH_MODEL.tile+POLISH_MODEL.halo*2)*2,patch={width:edge,height:edge,channels:3,data:new Uint8Array(edge*edge*3).fill(90)};
 for(const tile of polishTiles(width,height)){
  for(let y=0;y<tile.height*2;y++)for(let x=0;x<tile.width*2;x++)coverage[(tile.y*2+y)*width*2+tile.x*2+x]++;
  placePolishTile(target,patch,tile);
 }assert.ok(coverage.every(value=>value===1));assert.ok(target.data.every((value,index)=>value===(index%4===3?255:90)));
 assert.throws(()=>placePolishTile(target,{...patch,width:3},polishTiles(width,height)[0]));
});
test('halo pixels reflect at the drawing edge and transparency is white-composited only for inference',()=>{
 const image=pixels(1,1,[200,0,0,128]),copy=image.data.slice(),tile=polishTiles(1,1)[0],patch=polishTilePixels(image,tile);
 assert.equal(patch.channels,3);assert.deepEqual([...patch.data.slice(0,3)],[227,127,127]);assert.deepEqual(image.data,copy);
 for(let size=1;size<9;size++)for(let value=-400;value<400;value++)assert.ok(reflectPixel(value,size)>=0&&reflectPixel(value,size)<size);
});
test('unbounded buffers and external or executable image sources are rejected before inference',async()=>{
 for(const image of [null,pixels(0,2),{width:9999,height:1,data:new Uint8Array(4)},{width:1,height:1,data:new Float32Array(4)}])assert.throws(()=>checkPolishPixels(image));
 for(const url of ['https://example.com/drawing.png','data:image/svg+xml;base64,abc','javascript:alert(1)'])await assert.rejects(prepareDrawingPolish(url));
});

async function fixture(callback,{supported=true}={}){
 const keys=['Worker','isSecureContext'],old=new Map(keys.map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)])),workers=[];
 class FakeWorker{
  constructor(){this.events=new Map();this.messages=[];workers.push(this);}
  addEventListener(type,fn){if(!this.events.has(type))this.events.set(type,new Set());this.events.get(type).add(fn);}
  removeEventListener(type,fn){this.events.get(type)?.delete(fn);}
  postMessage(data){this.messages.push(data);}
  terminate(){this.terminated=true;}
  emit(data){for(const fn of this.events.get('message')||[])fn({data});}
  fail(){for(const fn of this.events.get('error')||[])fn({message:'private runtime path'});}
 }
 Object.defineProperty(globalThis,'Worker',{configurable:true,value:FakeWorker});Object.defineProperty(globalThis,'isSecureContext',{configurable:true,value:supported});
 try{await callback(workers);}finally{disposeDrawingPolish();for(const key of keys){if(old.get(key))Object.defineProperty(globalThis,key,old.get(key));else delete globalThis[key];}}
}
test('support checks start no worker or download and unsupported devices keep the original path',async()=>{
 await fixture(async workers=>{assert.equal(polishStatus().supported,true);assert.equal(workers.length,0);});
 await fixture(async workers=>{assert.equal(polishStatus().supported,false);await assert.rejects(enhanceDrawingPixels(pixels()));assert.equal(workers.length,0);},{supported:false});
});
test('a deliberate request copies original pixels and only accepts the matching 2x result',async()=>fixture(async workers=>{
 const source=pixels(),progress=[],promise=enhanceDrawingPixels(source,{onProgress:x=>progress.push(x)}),worker=workers[0],request=worker.messages[0];
 assert.notEqual(request.image.data.buffer,source.data.buffer);assert.deepEqual(request.image.data,source.data);assert.deepEqual(Object.keys(request).sort(),['id','image','type']);
 worker.emit({type:'result',id:'other',image:pixels(4,4)});worker.emit({type:'progress',id:request.id,stage:'bad',progress:120,message:'untrusted text'});assert.deepEqual(progress,[{stage:'loading',progress:100}]);
 worker.emit({type:'result',id:request.id,image:pixels(4,4)});assert.equal((await promise).width,4);assert.equal(source.data.length,16);
}));
test('cancel and stale results cannot replace the next drawing; jobs are serialized',async()=>fixture(async workers=>{
 const controller=new AbortController(),first=enhanceDrawingPixels(pixels(),{signal:controller.signal}),old=workers[0],oldId=old.messages[0].id;
 await assert.rejects(enhanceDrawingPixels(pixels()),/One drawing/);controller.abort();await assert.rejects(first,{name:'AbortError'});assert.equal(old.terminated,true);
 const second=enhanceDrawingPixels(pixels()),next=workers[1];old.emit({type:'result',id:oldId,image:pixels(4,4)});next.emit({type:'result',id:next.messages[0].id,image:pixels(4,4)});await second;
}));
test('malformed results and runtime failures terminate the worker with a safe retry',async()=>fixture(async workers=>{
 const first=enhanceDrawingPixels(pixels()),one=workers[0];one.emit({type:'result',id:one.messages[0].id,image:pixels(1,1)});await assert.rejects(first,/original is safe/);assert.equal(one.terminated,true);
 const second=enhanceDrawingPixels(pixels()),two=workers[1];two.fail();await assert.rejects(second,error=>!error.message.includes('private runtime'));assert.equal(two.terminated,true);
}));
test('timeout cancels expensive inference and already-aborted requests never start a worker',async t=>fixture(async workers=>{
 const abort=new AbortController();abort.abort();await assert.rejects(enhanceDrawingPixels(pixels(),{signal:abort.signal}),{name:'AbortError'});assert.equal(workers.length,0);
 t.mock.timers.enable({apis:['setTimeout']});const pending=enhanceDrawingPixels(pixels());t.mock.timers.tick(POLISH_MODEL.timeoutMs);await assert.rejects(pending,/too long/);assert.equal(workers[0].terminated,true);
}));
