import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {cartoonOptions,cartoonStatus,redrawDrawing} from '../dist/modules/cartoon.js';
import {sourceHasTransparency} from '../dist/modules/character.js';
const png=readFileSync(new URL('../../examples/characters/demo_robot_drawing.png',import.meta.url));
const source='data:image/png;base64,'+png.toString('base64'),hash=createHash('sha256').update(png).digest('hex');
const job={id:'a'.repeat(32),token:'b'.repeat(32),source_sha256:hash};
test('transparent sticker corners preserve supplied alpha while opaque paper still needs extraction',()=>{
 const width=20,height=30,data=new Uint8ClampedArray(width*height*4),rect={left:3,top:4,width:14,height:22};
 for(let y=4;y<26;y++)for(let x=3;x<17;x++)data.set([255,255,255,255],(y*width+x)*4);
 assert.equal(sourceHasTransparency({width,height,data},rect),false);
 for(const [x,y]of [[5,6],[15,6],[5,24],[15,24]])data[(y*width+x)*4+3]=0;
 assert.equal(sourceHasTransparency({width,height,data},rect),true);
});
async function fixture(callback,{local=true,handler}={}){
 const keys=['location','fetch','FileReader'],old=new Map(keys.map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)])),calls=[];
 class Reader{readAsDataURL(blob){blob.arrayBuffer().then(bytes=>{this.result='data:image/png;base64,'+Buffer.from(bytes).toString('base64');this.onload();});}}
 const values={location:{hostname:local?'127.0.0.1':'public.example',protocol:local?'http:':'https:'},FileReader:Reader,fetch:async(url,options={})=>{
  calls.push({url,options});if(handler)return handler(url,options,calls);
  if(url==='/api/cartoon/status')return Response.json({ready:true});
  if(options.method==='POST')return Response.json(job,{status:202});
  if(options.method==='DELETE')return Response.json({state:'cancelling'});
  if(url.endsWith('/image'))return new Response(png,{headers:{'content-type':'image/png'}});
  return Response.json({...job,state:'ready',evidence:{safety_checker_passed:true}});
 }};
 for(const [key,value]of Object.entries(values))Object.defineProperty(globalThis,key,{configurable:true,value});
 try{await callback(calls);}finally{for(const key of keys){if(old.get(key))Object.defineProperty(globalThis,key,old.get(key));else delete globalThis[key];}}
}
test('cartoon settings reject extra model controls, unsafe types and unbounded descriptions',()=>{
 assert.equal(cartoonOptions().style,'soft3d');for(const value of [{model:'remote'},{seed:-1},{seed:1.1},{style:'evil'},{idea:'x'.repeat(241)}])assert.throws(()=>cartoonOptions(value));
});
test('the shared site never probes localhost or transmits drawing pixels to it',async()=>fixture(async calls=>{
 assert.equal((await cartoonStatus()).ready,false);await assert.rejects(redrawDrawing(source),/local cartoon studio/);assert.equal(calls.length,0);
},{local:false}));
test('local capability discovery has no image upload or model generation',async()=>fixture(async calls=>{
 assert.equal((await cartoonStatus()).ready,true);assert.deepEqual(calls.map(x=>x.url),['/api/cartoon/status']);
}));
test('only the matching source can yield a preview and result access uses per-job headers',async()=>fixture(async calls=>{
 const result=await redrawDrawing(source,{idea:'A teal robot'});assert.equal(result.image,source);
 const sent=JSON.parse(calls[0].options.body);assert.equal(sent.image,source);assert.equal(sent.options.style,'soft3d');
 for(const call of calls.slice(1))assert.equal(call.options.headers.Authorization,'Bearer '+job.token);
 assert.ok(calls.every(c=>!c.url.includes(job.token)));assert.equal(calls.filter(c=>c.options.method==='DELETE').length,0);
}));
test('a cancelled submission still cancels its accepted job instead of leaving an orphan',async()=>{
 let resolvePost,posted;const postedPromise=new Promise(resolve=>posted=resolve),controller=new AbortController();
 await fixture(async calls=>{
  const pending=redrawDrawing(source,{}, {signal:controller.signal});await postedPromise;controller.abort();resolvePost(Response.json(job,{status:202}));
  await assert.rejects(pending,{name:'AbortError'});assert.equal(calls.at(-1).options.method,'DELETE');
 },{handler:(url,options)=>{if(options.method==='POST'){posted();return new Promise(resolve=>resolvePost=resolve);}return Response.json({state:'cancelling'});}});
});
test('cancel during polling deletes the job and cannot return a late cartoon',async()=>fixture(async calls=>{
 const controller=new AbortController();await assert.rejects(redrawDrawing(source,{}, {signal:controller.signal,onProgress:()=>controller.abort()}),{name:'AbortError'});
 assert.equal(calls.at(-1).options.method,'DELETE');assert.ok(!calls.some(x=>x.url.endsWith('/image')));
},{handler:(url,options)=>options.method==='POST'?Response.json(job,{status:202}):Response.json({...job,state:'running',stage:'generating',progress:50})}));
test('source mismatch and safety errors never fetch or display a result image',async()=>{
 for(const state of [{...job,source_sha256:'f'.repeat(64),state:'ready'},{...job,state:'error',error:'private path and model text'}])await fixture(async calls=>{
  await assert.rejects(redrawDrawing(source),e=>!e.message.includes('private path'));assert.ok(!calls.some(x=>x.url.endsWith('/image')));assert.equal(calls.at(-1).options.method,'DELETE');
 },{handler:(url,options)=>options.method==='POST'?Response.json(job,{status:202}):Response.json(state)});
});
test('unsupported URLs and already-aborted requests start no model job',async()=>fixture(async calls=>{
 for(const image of ['https://example.com/x.png','data:image/svg+xml;base64,abc'])await assert.rejects(redrawDrawing(image));
 const controller=new AbortController();controller.abort();await assert.rejects(redrawDrawing(source,{}, {signal:controller.signal}),{name:'AbortError'});assert.equal(calls.length,0);
}));
