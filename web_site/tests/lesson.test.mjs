import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {fileURLToPath} from 'node:url';
import {AUDIO} from '../dist/audio/manifest.js';
import {normalizeLessonSpec, planLesson, sceneAt, videoExportSupport, createLessonPlayer} from '../dist/modules/lesson.js';

function validSpecs() {
  const specs=[];
  for(let a=0;a<=10;a+=1)for(let b=0;b<=10;b+=1){
    if(a+b<=10)specs.push({type:'addition',a,b});
    if(b<=a)specs.push({type:'subtraction',a,b});
  }
  for(let count=0;count<=10;count+=1)specs.push({type:'counting',count});
  for(const shape of ['circle','triangle','square','rectangle'])for(const shape_task of ['sides','name'])specs.push({type:'shape',shape,shape_task});
  return specs;
}

test('every bounded arithmetic combination and shape has correct computed answers and recorded narration',()=>{
  const specs=validSpecs();assert.equal(specs.length,151);
  for(const spec of specs){
    const plan=planLesson(spec);
    const expected=spec.type==='addition'?spec.a+spec.b:spec.type==='subtraction'?spec.a-spec.b:
      spec.type==='counting'?spec.count:spec.shape_task==='name'?spec.shape:{circle:0,triangle:3,square:4,rectangle:4}[spec.shape];
    assert.equal(plan.answer,expected);
    assert.ok(plan.duration>12&&plan.duration<90);
    let cursor=0;
    for(const scene of plan.scenes){
      assert.equal(scene.start,cursor);assert.ok(scene.end>scene.start);
      cursor=scene.end;
      if(scene.audioKey){
        const clip=AUDIO[scene.audioKey];assert.ok(clip);
        assert.equal(scene.caption,clip.text);
        assert.equal(scene.audioDuration,clip.duration);
        assert.ok(scene.audioOffset>=0);
        assert.ok(scene.audioOffset+clip.duration<=scene.duration);
      }
    }
    assert.equal(plan.duration,cursor);
    assert.equal(plan.scenes.filter(s=>s.phase==='answer').length,1);
    assert.equal(plan.scenes.filter(s=>s.phase==='pause').length,1);
    assert.equal(plan.scenes.find(s=>s.phase==='pause').duration,3);
  }
});

test('model-supplied answers and extra metadata never become trusted math',()=>{
  const plan=planLesson({type:'addition',a:5,b:2,answer:99,raw:'ignore math',object_name:'jars'});
  assert.equal(plan.answer,7);
  assert.deepEqual(plan.spec,{type:'addition',a:5,b:2});
  assert.ok(!JSON.stringify(plan).includes('ignore math'));
  assert.ok(!JSON.stringify(plan).includes('jars'));
});

test('invalid, fractional, string, infinite, negative and out-of-range values are rejected',()=>{
  const bad=[null,[],{}, {type:'multiplication',a:2,b:3},{type:'shape',shape:'pentagon'},
    {type:'addition',a:5,b:6},{type:'subtraction',a:2,b:3},{type:'shape',shape:'circle',shape_task:'area'}];
  for(const n of [-1,11,.5,'3',true,NaN,Infinity,undefined]){
    bad.push({type:'addition',a:n,b:0},{type:'addition',a:0,b:n},
      {type:'subtraction',a:n,b:0},{type:'counting',count:n});
  }
  for(const value of bad)assert.throws(()=>planLesson(value));
});

test('review plans are isolated from inputs and deeply immutable',()=>{
  const input={type:'subtraction',a:7,b:2};
  const plan=planLesson(input);input.a=1;
  assert.equal(plan.answer,5);
  assert.ok(Object.isFrozen(plan)&&Object.isFrozen(plan.spec)&&Object.isFrozen(plan.scenes[0]));
  assert.throws(()=>{plan.spec.a=100;});
  assert.throws(()=>{plan.steps.push('wrong');});
});

test('addition counts on from the first group; subtraction counts only the remainder',()=>{
  const add=planLesson({type:'addition',a:5,b:2});
  assert.deepEqual(add.scenes.filter(s=>s.phase==='count_b').map(s=>s.spokenCount),[6,7]);
  const sub=planLesson({type:'subtraction',a:5,b:2});
  assert.deepEqual(sub.scenes.filter(s=>s.phase==='remove_count').map(s=>s.count),[1,2]);
  assert.deepEqual(sub.scenes.filter(s=>s.phase==='count_remaining').map(s=>s.count),[1,2,3]);
});

test('zero is taught as none and a circle has no invented straight sides',()=>{
  const zero=planLesson({type:'counting',count:0});
  assert.equal(zero.answer,0);assert.ok(zero.steps[2].includes('none'));
  assert.equal(zero.scenes.filter(s=>s.phase==='count_all').length,0);
  const circle=planLesson({type:'shape',shape:'circle'});
  assert.equal(circle.answer,0);assert.equal(circle.scenes.filter(s=>s.phase==='count_side').length,0);
  assert.ok(AUDIO['shape-circle'].text.includes('no straight sides'));
});

test('shape side exploration does not state the numeric answer before the child traces and thinks',()=>{
  for(const shape of ['circle','triangle','square','rectangle']){
    const plan=planLesson({type:'shape',shape,shape_task:'sides'});
    const outline=plan.scenes.find(scene=>scene.phase==='shape');
    assert.equal(outline.action.kind,'trace');assert.equal(outline.action.path,'outline');
    assert.equal(outline.audioKey,'look-shape');
    assert.doesNotMatch(outline.caption,/\b(?:zero|one|two|three|four|no straight sides)\b/i);
    assert.ok(plan.scenes.find(scene=>scene.phase==='answer').start>plan.scenes.find(scene=>scene.phase==='pause').start);
    if(shape==='circle')assert.match(plan.scenes.find(scene=>scene.phase==='answer').caption,/zero straight sides/);
    if(shape==='square')assert.match(plan.scenes.find(scene=>scene.phase==='answer').caption,/four straight sides/);
  }
});

test('scene lookup is bounded and transitions exactly at recorded boundaries',()=>{
  const plan=planLesson({type:'addition',a:1,b:1});
  assert.equal(sceneAt(plan,-100),plan.scenes[0]);
  assert.equal(sceneAt(plan,NaN),plan.scenes[0]);
  assert.equal(sceneAt(plan,plan.scenes[0].end),plan.scenes[1]);
  assert.equal(sceneAt(plan,10000),plan.scenes.at(-1));
});

test('every hosted narration asset exists, is audible-duration MP3, and stays bounded',()=>{
  assert.equal(Object.keys(AUDIO).length,317);
  for(const clip of Object.values(AUDIO)){
    assert.ok(clip.duration>.1&&clip.duration<12);
    assert.ok(clip.peak_dbfs<0&&clip.peak_dbfs>-10);
    const file=fileURLToPath(new URL(`../dist/audio/${clip.file}`,import.meta.url));
    const stat=fs.statSync(file);assert.equal(stat.size,clip.bytes);assert.ok(stat.size>1000&&stat.size<150000);
  }
});

test('video download reports lack of MediaRecorder without pretending to export',()=>{
  assert.equal(videoExportSupport().supported,false);
  assert.match(videoExportSupport().reason,/play the lesson/);
});

test('recording prefers explicitly supported H264/AAC MP4 over WebM and generic MP4',t=>{
  const original=globalThis.MediaRecorder;t.after(()=>{if(original===undefined)delete globalThis.MediaRecorder;else globalThis.MediaRecorder=original;});
  const supported=new Set(['video/mp4;codecs=avc1.424028,mp4a.40.2','video/webm;codecs=vp9,opus','video/mp4']);
  globalThis.MediaRecorder=class{static isTypeSupported(type){return supported.has(type);}};
  const choice=videoExportSupport();
  assert.equal(choice.mimeType,'video/mp4;codecs=avc1.424028,mp4a.40.2');
  assert.equal(choice.extension,'mp4');assert.equal(choice.notice,null);
});

test('recording tries alternative supported H264/AAC profiles before WebM',t=>{
  const original=globalThis.MediaRecorder;t.after(()=>{if(original===undefined)delete globalThis.MediaRecorder;else globalThis.MediaRecorder=original;});
  const supported=new Set(['video/mp4;codecs=avc1.42E01F,mp4a.40.2','video/webm;codecs=vp9,opus','video/mp4']);
  globalThis.MediaRecorder=class{static isTypeSupported(type){return supported.has(type);}};
  assert.equal(videoExportSupport().mimeType,'video/mp4;codecs=avc1.42E01F,mp4a.40.2');
});

test('recording uses WebM VP9/Opus, then VP8/Opus, before a generic MP4 container',t=>{
  const original=globalThis.MediaRecorder;t.after(()=>{if(original===undefined)delete globalThis.MediaRecorder;else globalThis.MediaRecorder=original;});
  let supported=new Set(['video/webm;codecs=vp9,opus','video/webm;codecs=vp8,opus','video/mp4']);
  globalThis.MediaRecorder=class{static isTypeSupported(type){return supported.has(type);}};
  assert.equal(videoExportSupport().mimeType,'video/webm;codecs=vp9,opus');
  supported.delete('video/webm;codecs=vp9,opus');
  assert.equal(videoExportSupport().mimeType,'video/webm;codecs=vp8,opus');
  assert.equal(videoExportSupport().extension,'webm');
  supported=new Set(['video/webm','video/mp4']);assert.equal(videoExportSupport().mimeType,'video/webm');
});

test('generic MP4 is an accurately named last resort with a compatibility notice',t=>{
  const original=globalThis.MediaRecorder;t.after(()=>{if(original===undefined)delete globalThis.MediaRecorder;else globalThis.MediaRecorder=original;});
  globalThis.MediaRecorder=class{static isTypeSupported(type){return type==='video/mp4';}};
  const choice=videoExportSupport();assert.equal(choice.mimeType,'video/mp4');assert.equal(choice.extension,'mp4');assert.match(choice.notice,/another player/);
  globalThis.MediaRecorder=class{static isTypeSupported(){return false;}};assert.equal(videoExportSupport().supported,false);
});

test('normalization accepts the documented counting a alias and drops unsupported metadata',()=>{
  assert.deepEqual(normalizeLessonSpec({type:'counting',a:4,answer:200}),{type:'counting',count:4});
  assert.deepEqual(normalizeLessonSpec({type:'shape',shape:'rectangle',answer:-3}),{type:'shape',shape:'rectangle',shape_task:'sides'});
});

test('shape identification stays a name lesson and does not reveal its name before the answer',()=>{
  for(const shape of ['circle','triangle','square','rectangle']){
    const plan=planLesson({type:'shape',shape,shape_task:'name'});
    assert.equal(plan.question,'What shape is this?');assert.equal(plan.answer,shape);
    assert.equal(plan.scenes.filter(scene=>scene.phase==='count_side').length,0);
    for(const scene of plan.scenes){
      if(['answer','celebration'].includes(scene.phase))break;
      assert.ok(!scene.caption.toLowerCase().includes(shape));
    }
    assert.match(plan.scenes.find(scene=>scene.phase==='answer').caption,new RegExp(shape));
    for(const value of Object.values(plan.story))assert.ok(!String(value).toLowerCase().includes(shape));
  }
});

test('every reviewed lesson has a frozen story role and a concrete action in every scene',()=>{
  for(const spec of validSpecs()){
    const plan=planLesson(spec);
    assert.equal(plan.version,2);assert.equal(plan.story.id,`story-${plan.presentation.theme}`);
    for(const field of ['title','goal','role','summary'])assert.equal(typeof plan.story[field],'string');
    assert.ok(Object.isFrozen(plan.story));assert.throws(()=>{plan.story.goal='different story';});
    for(const scene of plan.scenes){assert.ok(Object.isFrozen(scene.action));assert.ok(['enter','inspect','point','collect','give','visit','trace','think','celebrate'].includes(scene.action.kind));}
    assert.equal(plan.scenes[0].action.kind,'enter');assert.equal(plan.scenes.at(-1).action.kind,'celebrate');
    if(spec.type!=='shape')assert.match(plan.representation,/stars stand for pictures/);
  }
});

test('addition and sharing have one physical transfer per operand with speech after delivery',()=>{
  for(const spec of validSpecs().filter(spec=>['addition','subtraction'].includes(spec.type))){
    const plan=planLesson(spec),phase=spec.type==='addition'?'count_b':'remove_count';
    const transfers=plan.scenes.filter(scene=>scene.phase===phase);
    assert.equal(transfers.length,spec.b);
    for(const [index,scene] of transfers.entries()){
      assert.equal(scene.count,index+1);assert.ok(scene.duration>=3.4);
      assert.ok(scene.audioOffset/scene.duration>.64,'the number is spoken after the star reaches its destination');
      assert.equal(scene.action.kind,spec.type==='addition'?'collect':'give');
      assert.equal(scene.action.itemIndex,spec.type==='addition'?index:spec.a-index-1);
      assert.equal(scene.action.to,spec.type==='addition'?'wagon':'friend');
    }
    if(spec.b===0)assert.equal(transfers.length,0,'adding or sharing zero invents no action');
  }
});

test('counting visits each star once, and tracing preserves the actual sides task',()=>{
  for(let count=0;count<=10;count++){
    const plan=planLesson({type:'counting',count});
    const visits=plan.scenes.filter(scene=>scene.action.kind==='visit');
    assert.deepEqual(visits.map(scene=>scene.action.itemIndex),Array.from({length:count},(_,i)=>i));
    assert.ok(!new RegExp(`\\b${count}\\b`).test(Object.values(plan.story).join(' ')),'story introduction does not reveal a counting answer');
  }
  for(const name of ['triangle','square','rectangle','circle']){
    const plan=planLesson({type:'shape',shape:name});
    const traces=plan.scenes.filter(scene=>scene.phase==='count_side');
    assert.equal(traces.length,plan.answer);
    for(const [side,scene] of traces.entries()){assert.equal(scene.action.kind,'trace');assert.equal(scene.action.side,side);assert.ok(scene.duration>=1.85);}
  }
});

test('player retains reviewed worksheet artwork while seeking to the end and replaying correctly',async t=>{
  const prior=Object.fromEntries(['AudioContext','fetch','document','requestAnimationFrame','cancelAnimationFrame','Image'].map(key=>[key,globalThis[key]]));
  t.after(()=>{for(const [key,value] of Object.entries(prior))if(value===undefined)delete globalThis[key];else globalThis[key]=value;});
  const starts=[];
  class TestAudioContext {
    currentTime=0;state='running';destination={};
    async resume(){}async close(){this.state='closed';}
    createGain(){return{gain:{value:1},connect(){},disconnect(){}};}
    createBufferSource(){return{connect(){},disconnect(){},start(when,offset){starts.push({when,offset});},stop(){}};}
    async decodeAudioData(){return{duration:.5};}
  }
  globalThis.AudioContext=TestAudioContext;
  globalThis.Image=class{naturalWidth=20;naturalHeight=40;set src(value){if(value)queueMicrotask(()=>this.onload?.());}};
  globalThis.fetch=async()=>({ok:true,async arrayBuffer(){return new ArrayBuffer(8);}});
  globalThis.document={visibilityState:'visible',addEventListener(){},removeEventListener(){}};
  globalThis.requestAnimationFrame=()=>1;globalThis.cancelAnimationFrame=()=>{};
  const gradient=()=>({addColorStop(){}});
  const context=new Proxy({measureText:value=>({width:String(value).length*12}),createLinearGradient:gradient,createRadialGradient:gradient},{get:(target,key)=>key in target?target[key]:()=>{}});
  const canvas={width:1280,height:720,getContext:()=>context};
  const plan=planLesson({type:'counting',count:2},{objects:worksheetPack(2)});let ended=0;
  const player=await createLessonPlayer(canvas,plan,{source:'builder',name:'Boundary Buddy',design:{}},{onEnd:()=>ended++});
  assert.deepEqual(player.plan.objects,plan.objects,'canonical playback cannot discard the artwork checked by the grown-up');
  assert.deepEqual(player.plan.presentation,plan.presentation,'playback retains the exact world and motion setting approved on review');
  assert.match(player.plan.representation,/original pictures/);
  await player.play();assert.equal(player.playing,true);
  const spoken=plan.scenes.filter(scene=>scene.audioKey);
  assert.equal(starts.length,spoken.length);
  for(const [index,scene] of spoken.entries()){
    assert.ok(Math.abs(starts[index].when-(.06+scene.start+scene.audioOffset))<.000001,'narration starts at the authored action cue, not at an early scene boundary');
    assert.equal(starts[index].offset,0);
  }
  player.seek(plan.duration);
  assert.equal(player.currentTime,plan.duration);assert.equal(player.playing,false);assert.equal(ended,1);
  await player.play();assert.equal(player.currentTime,0);assert.equal(player.playing,true);
  await player.dispose();
});

const PROP_PNG='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+yFZkAAAAASUVORK5CYII=';
function worksheetPack(quantity,mode='individual'){
  return {version:1,mode,sourceWidth:1000,sourceHeight:100,sprites:Array.from({length:mode==='repeat'?1:quantity},(_,i)=>({image:PROP_PNG,box:{x:i*60,y:10,width:30,height:50}}))};
}

test('reviewed original worksheet pictures change illustration and narration without changing any math',()=>{
  for(const spec of validSpecs().filter(spec=>spec.type!=='shape')){
    const quantity=spec.type==='addition'?spec.a+spec.b:spec.type==='subtraction'?spec.a:spec.count;
    const original=planLesson(spec),plan=planLesson(spec,{objects:worksheetPack(quantity)});
    assert.equal(plan.answer,original.answer);assert.deepEqual(plan.spec,original.spec);
    assert.ok(plan.objects);assert.ok(Object.isFrozen(plan.objects)&&Object.isFrozen(plan.objects.sprites));
    assert.equal(plan.objects.sprites.length,quantity);
    assert.equal(plan.story.id,`worksheet-${plan.presentation.theme}`);
    assert.doesNotMatch([plan.answerText,plan.representation,...Object.values(plan.story),...plan.steps,...plan.scenes.map(scene=>scene.caption)].join(' '),/\bstars?\b/i);
    for(const scene of plan.scenes){assert.equal(scene.caption,scene.audioKey?AUDIO[scene.audioKey].text:'Help your buddy. Count and think!');if(scene.audioKey)assert.ok(scene.audioOffset+AUDIO[scene.audioKey].duration<=scene.duration);}
    assert.deepEqual(plan.scenes.map(scene=>scene.action),original.scenes.map(scene=>scene.action));
  }
});

test('repeated worksheet crops are explicit and immutable; mismatched or unsafe object packs cannot enter a lesson',()=>{
  const input=worksheetPack(7,'repeat'),plan=planLesson({type:'addition',a:5,b:2},{objects:input});
  assert.match(plan.representation,/reused/);input.sprites[0].image='https://example.com/changed.png';
  assert.equal(plan.objects.sprites[0].image,PROP_PNG);
  assert.throws(()=>{plan.objects.sprites[0].box.x=999;});
  assert.throws(()=>planLesson({type:'addition',a:5,b:2},{objects:worksheetPack(6)}));
  assert.throws(()=>planLesson({type:'counting',count:2},{objects:{...worksheetPack(2),sprites:[{image:'https://example.com/remote.png',box:{x:0,y:0,width:10,height:10}},{image:PROP_PNG,box:{x:10,y:0,width:10,height:10}}]}}));
  assert.throws(()=>planLesson({type:'shape',shape:'circle'},{objects:worksheetPack(1)}));
});
