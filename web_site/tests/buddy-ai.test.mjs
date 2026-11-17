import test from 'node:test';
import assert from 'node:assert/strict';
import {BUDDY_MODEL,BUDDY_COLORS,validateBuddyIdea,parseBuddyDesign,buddyMessages,describeDesign} from '../dist/modules/buddy-design.js';
import {buddyAIStatus,generateBuddy,disposeBuddyAI} from '../dist/modules/buddy-ai.js';
import {planLesson} from '../dist/modules/lesson.js';
import {storyState} from '../dist/modules/story.js';
import {designGrammar,designLogitsProcessor} from '../dist/modules/buddy-grammar.js';

const record=()=>({body_type:'robot',head_shape:'round',eyes:'visor',headwear:'antenna',chest:'none',back:'wings',gloves:'none',boots:'round',primary_color:'purple',secondary_color:'yellow',accent_color:'yellow'});
const raw=()=>JSON.stringify(record());
test('the token grammar permits only a complete ordered design and then EOS',()=>{
 const encode=text=>[...text].map(c=>c.charCodeAt(0)),allowed=designGrammar(encode),tokens=encode(raw());
 for(let n=0;n<tokens.length;n++)assert.ok(allowed(tokens.slice(0,n)).includes(tokens[n]));
 assert.equal(allowed(tokens),null);assert.throws(()=>allowed(encode('{"name":')));
 const tokenizer={encode},data=new Float32Array(256).fill(2),processor=designLogitsProcessor(tokenizer,2,1);
 processor([[9,9]],{data});assert.equal(data['{'.charCodeAt(0)],2);assert.equal(data[1],-Infinity);
 data.fill(2);processor([[9,9,...tokens]],{data});assert.equal(data[1],2);assert.equal(data[2],-Infinity);
});
async function fixture(callback,{gpu=true,f16=true,secure=true}={}){
 const keys=['Worker','navigator','isSecureContext'],old=new Map(keys.map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)])),workers=[];
 class FakeWorker{
  constructor(url,options){this.url=url;this.options=options;this.events=new Map();this.messages=[];this.terminated=false;workers.push(this);}
  addEventListener(type,callback){if(!this.events.has(type))this.events.set(type,new Set());this.events.get(type).add(callback);}
  removeEventListener(type,callback){this.events.get(type)?.delete(callback);}
  postMessage(data){this.messages.push(data);}
  terminate(){this.terminated=true;}
  emit(data){for(const callback of this.events.get('message')||[])callback({data});}
  fail(){for(const callback of this.events.get('error')||[])callback({message:'private runtime path'});}
 }
 const values={Worker:FakeWorker,isSecureContext:secure,navigator:gpu?{gpu:{requestAdapter:async()=>({features:new Set(f16?['shader-f16']:[])})}}:{}};
 for(const [k,value] of Object.entries(values))Object.defineProperty(globalThis,k,{value,configurable:true});
 try{await callback(workers);}finally{disposeBuddyAI();for(const k of keys){if(old.get(k))Object.defineProperty(globalThis,k,old.get(k));else delete globalThis[k];}}
}
async function posted(workers,index=0){for(let n=0;n<30;n++){if(workers[index]?.messages.length)return workers[index];await new Promise(setImmediate);}assert.fail('No inference request');}

test('validated AI proposals remain editable jointed characters and preserve lesson object counts',()=>{
 const d=parseBuddyDesign(raw());assert.equal(d.body_type,'robot');assert.equal(d.back,'wings');assert.equal(d.primary_color,BUDDY_COLORS.purple);
 d.primary_color='#123456';d.back='cape';
 const hero={source:'builder',name:'Nova',design:d},plan=planLesson({type:'addition',a:5,b:2});
 for(const s of plan.scenes){const state=storyState(plan,s.start+s.duration*.4,hero);assert.equal(state.items.length,7);assert.equal(new Set(state.items.map(x=>x.id)).size,7);}
 assert.match(describeDesign(d),/Robot/);assert.match(describeDesign(d),/cape/);
});
test('the response contract rejects code, unknown parts, unknown fields, missing keys and duplicate keys',()=>{
 const variants=['Text '+raw(),raw()+'\n'+raw(),raw().replace('"robot"','"dragon"'),raw().replace('"purple"','"javascript:alert(1)"'),raw().replace('"body_type":','"name":'),raw().replace('"body_type":"robot",',''),raw().replace('{','{"back":"cape",'),JSON.stringify({...record(),url:'https://example.com'}),JSON.stringify({...record(),skin_color:'#fff'})];
 for(const text of variants)assert.throws(()=>parseBuddyDesign(text));
 assert.deepEqual(parseBuddyDesign('```json\n'+raw()+'\n```'),parseBuddyDesign(raw()));
});
test('descriptions are bounded, avoid obvious personal information and never become a character name',()=>{
 assert.equal(validateBuddyIdea('  A friendly purple robot  '),'A friendly purple robot');
 for(const text of ['',null,'ab','!@#','x'.repeat(321),'A robot at person@example.com','Call 312-555-0123','https://example.com buddy','A robot with a gun','A nude character'])assert.throws(()=>validateBuddyIdea(text));
 const idea='An emerald mechanical friend with a cape';assert.equal(buddyMessages(idea).at(-1).content,idea);
 assert.equal(parseBuddyDesign(raw()).name,'My buddy');
});
test('checking support never starts a model download or creates a worker',async()=>fixture(async workers=>{
 assert.equal((await buddyAIStatus()).supported,true);assert.equal(workers.length,0);
}));
test('incompatible graphics and insecure contexts retain the manual builder',async()=>{
 for(const options of [{gpu:false},{f16:false},{secure:false}])await fixture(async workers=>{assert.equal((await buddyAIStatus()).supported,false);await assert.rejects(generateBuddy('A green robot'),{code:'UNSUPPORTED'});assert.equal(workers.length,0);},options);
});
test('a deliberate request posts only the idea and returns validated parts',async()=>fixture(async workers=>{
 const progress=[];const promise=generateBuddy('A purple robot',{onProgress:p=>progress.push(p)}),worker=await posted(workers),request=worker.messages[0];
 assert.deepEqual(Object.keys(request).sort(),['device','id','idea','type']);assert.equal(request.device,'webgpu');assert.equal(request.type,'describe');
 worker.emit({type:'progress',id:request.id,stage:'loading',progress:170});worker.emit({type:'result',id:request.id,raw:raw()});
 assert.equal((await promise).back,'wings');assert.equal(progress[0].progress,100);
}));
test('invalid user descriptions are rejected without constructing a worker',async()=>fixture(async workers=>{await assert.rejects(generateBuddy('person@example.com'));assert.equal(workers.length,0);}));
test('busy requests are serialized and late results from cancelled workers cannot replace a new result',async()=>fixture(async workers=>{
 const abort=new AbortController();const first=generateBuddy('A purple robot',{signal:abort.signal}),worker=await posted(workers);const oldId=worker.messages[0].id;
 await assert.rejects(generateBuddy('A blue robot'),{code:'BUSY'});abort.abort();await assert.rejects(first,{name:'AbortError'});assert.equal(worker.terminated,true);
 const second=generateBuddy('A blue robot'),next=await posted(workers,1);worker.emit({type:'result',id:oldId,raw:raw()});next.emit({type:'result',id:next.messages[0].id,raw:JSON.stringify({...record(),primary_color:'blue'})});assert.equal((await second).primary_color,BUDDY_COLORS.blue);
}));
test('cancelling during capability preparation prevents a later download',async()=>fixture(async workers=>{
 let resolve;Object.defineProperty(globalThis,'navigator',{configurable:true,value:{gpu:{requestAdapter:()=>new Promise(r=>resolve=r)}}});
 const promise=generateBuddy('A purple robot');disposeBuddyAI();resolve({features:new Set(['shader-f16'])});await assert.rejects(promise,{name:'AbortError'});assert.equal(workers.length,0);
}));
test('model errors are sanitized, unload the worker and preserve retry',async()=>fixture(async workers=>{
 const first=generateBuddy('A purple robot'),worker=await posted(workers);worker.fail();await assert.rejects(first,error=>error.code==='UNAVAILABLE'&&!error.message.includes('private'));assert.equal(worker.terminated,true);
 const second=generateBuddy('A blue robot'),next=await posted(workers,1);next.emit({type:'result',id:next.messages[0].id,raw:raw()});await second;
}));
test('a malformed model proposal is rejected without showing model prose',async()=>fixture(async workers=>{
 const promise=generateBuddy('A purple robot'),worker=await posted(workers);worker.emit({type:'result',id:worker.messages[0].id,raw:'<script>private text</script>'});await assert.rejects(promise,error=>!error.message.includes('private'));
}));
test('timeout terminates the inference instead of leaving a hidden worker running',async t=>fixture(async workers=>{
 t.mock.timers.enable({apis:['setTimeout']});const promise=generateBuddy('A purple robot'),worker=await posted(workers);t.mock.timers.tick(BUDDY_MODEL.timeoutMs);await assert.rejects(promise,{code:'TIMEOUT'});assert.equal(worker.terminated,true);
}));
