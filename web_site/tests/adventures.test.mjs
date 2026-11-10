import test from 'node:test';
import assert from 'node:assert/strict';
import {ADVENTURES,suggestAdventure} from '../dist/modules/adventures.js';
import {planLesson} from '../dist/modules/lesson.js';
import {storyState,renderStoryFrame} from '../dist/modules/story.js';
import {PRESETS} from '../dist/modules/character.js';
const hero={source:'builder',name:'Nova',design:PRESETS[0].design};
const specs=[];for(let a=0;a<=10;a++)for(let b=0;b<=10;b++){if(a+b<=10)specs.push({type:'addition',a,b});if(b<=a)specs.push({type:'subtraction',a,b});}for(let count=0;count<=10;count++)specs.push({type:'counting',count});for(const shape of ['circle','triangle','square','rectangle'])for(const shape_task of ['name','sides'])specs.push({type:'shape',shape,shape_task});

test('auto world recommendations are deterministic and avoid the last played world for every supported question',()=>{
  const chosen=new Set();for(const spec of specs){assert.equal(suggestAdventure(spec),suggestAdventure({...spec}));chosen.add(suggestAdventure(spec));for(const world of ADVENTURES)assert.notEqual(suggestAdventure(spec,world.id),world.id);}
  assert.equal(chosen.size,4);
});
test('every world preserves every question answer, action sequence, token identity and quantity',()=>{
  for(const spec of specs){const base=planLesson(spec),quantity=spec.type==='addition'?spec.a+spec.b:spec.type==='subtraction'?spec.a:spec.type==='counting'?spec.count:0;
    for(const world of ADVENTURES){const plan=planLesson(spec,{presentation:{theme:world.id}});assert.equal(plan.answer,base.answer);assert.deepEqual(plan.scenes.map(s=>s.action),base.scenes.map(s=>s.action));
      const ids=new Set(storyState(plan,0,hero).items.map(i=>i.id));
      for(const scene of plan.scenes)for(const fraction of [0,.23,.4,.64,.66,.99999]){const state=storyState(plan,scene.start+scene.duration*fraction,hero);assert.equal(state.items.length,quantity);assert.deepEqual(new Set(state.items.map(i=>i.id)),ids);assert.equal(state.counts.home+state.counts.source+state.counts.moving+state.counts.delivered,quantity);assert.ok(state.camera.scale>=1&&state.camera.scale<=1.0211);}
    }
  }
});
test('world selection cannot enter through model metadata and unsupported visual controls are rejected',()=>{
  const spec={type:'addition',a:5,b:2};const base=planLesson(spec);assert.deepEqual(planLesson({...spec,presentation:{theme:'evil',url:'https://example.com'}}).presentation,base.presentation);
  for(const presentation of [{theme:'unknown'},'moon',{motion:'flash'},[]])assert.throws(()=>planLesson(spec,{presentation}));
  const plan=planLesson(spec,{presentation:{theme:'moon',motion:'calm'}});assert.ok(Object.isFrozen(plan.presentation));assert.throws(()=>{plan.presentation.theme='garden';});
});
test('all non-garden narration is location-consistent and every speech clip fits the action timeline',()=>{
  for(const theme of ['workshop','ocean','moon'])for(const spec of specs){const plan=planLesson(spec,{presentation:{theme}});for(const scene of plan.scenes){assert.doesNotMatch(scene.caption,/\bgarden\b|\bpicnic\b/i);assert.ok(scene.audioOffset+scene.audioDuration<=scene.duration);}}
});
test('gentle motion stops camera drift while preserving the teaching action and original phase timings',()=>{
  const spec={type:'addition',a:5,b:2};const rich=planLesson(spec,{presentation:{theme:'ocean'}}),calm=planLesson(spec,{presentation:{theme:'ocean',motion:'calm'}});assert.equal(calm.duration,rich.duration);
  for(const scene of calm.scenes){const t=scene.start+scene.duration*.4,a=storyState(rich,t,hero),b=storyState(calm,t,hero);assert.deepEqual(a.items,b.items);assert.deepEqual(b.camera,{scale:1,x:0,y:0});assert.deepEqual(a.counts,b.counts);}
});
test('each visual world has its own actual rendered palette without adding countable story objects',()=>{
  const palettes=[];
  for(const world of ADVENTURES){const colors=[],ctx=new Proxy({measureText:s=>({width:String(s).length*12})},{get:(o,k)=>k in o?o[k]:()=>{},set(o,k,v){if(k==='fillStyle')colors.push(v);o[k]=v;return true;}});const plan=planLesson({type:'counting',count:0},{presentation:{theme:world.id}});const state=renderStoryFrame({width:1280,height:720,getContext:()=>ctx},plan,hero,2);assert.equal(state.items.length,0);assert.ok(colors.includes(world.sky));palettes.push(colors.join('|'));}
  assert.equal(new Set(palettes).size,4);
});
