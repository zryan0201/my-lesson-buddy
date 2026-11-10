import test from 'node:test';
import assert from 'node:assert/strict';
import {planLesson} from '../dist/modules/lesson.js';
import {storyState,renderStoryFrame,shapeGeometry} from '../dist/modules/story.js';
import {PRESETS,characterAnchors} from '../dist/modules/character.js';
import {prepareWorksheetObjects} from '../dist/modules/objects.js';

const hero={source:'builder',name:'Comet',design:PRESETS[3].design};
function allSpecs(){const specs=[];for(let a=0;a<=10;a++)for(let b=0;b<=10;b++){if(a+b<=10)specs.push({type:'addition',a,b});if(b<=a)specs.push({type:'subtraction',a,b});}for(let count=0;count<=10;count++)specs.push({type:'counting',count});for(const shape of ['circle','triangle','square','rectangle'])for(const shape_task of ['name','sides'])specs.push({type:'shape',shape,shape_task});return specs;}
const sample=(plan,phase,count=undefined,fraction=.5)=>{const scene=plan.scenes.find(s=>s.phase===phase&&(count===undefined||s.count===count));assert.ok(scene,`${phase}/${count} exists`);return storyState(plan,scene.start+scene.duration*fraction,hero);};
function finite(value){if(typeof value==='number')assert.ok(Number.isFinite(value),'all rendered geometry is finite');else if(Array.isArray(value))value.forEach(finite);else if(value&&typeof value==='object')Object.values(value).forEach(finite);}

test('all 151 supported lessons conserve stable object IDs at every scene boundary and transfer interval',()=>{
  assert.equal(allSpecs().length,151);
  for(const spec of allSpecs()){
    const plan=planLesson(spec),quantity=spec.type==='addition'?spec.a+spec.b:spec.type==='subtraction'?spec.a:spec.type==='counting'?spec.count:0;
    const expectedIDs=new Set(storyState(plan,0,hero).items.map(item=>item.id));
    for(const scene of plan.scenes)for(const f of [0,.119,.12,.23,.4,.57,.6399,.64,.66,.99999]){
      const state=storyState(plan,scene.start+scene.duration*f,hero);
      assert.equal(state.items.length,quantity);assert.equal(new Set(state.items.map(item=>item.id)).size,quantity);
      assert.deepEqual(new Set(state.items.map(item=>item.id)),expectedIDs);
      assert.equal(state.counts.home+state.counts.source+state.counts.moving+state.counts.delivered,quantity);
      assert.ok(state.counts.moving<=1);finite(state.actor);finite(state.items);
      for(const item of state.items)assert.ok(['home','source','moving','delivered'].includes(item.status));
      assert.ok(state.actor.x>=0&&state.actor.x+state.actor.width<=1280);
      assert.ok(state.actor.y>=100&&state.actor.y+state.actor.height<=510);
    }
  }
});

test('collecting moves each addend star out of the garden, through the hands, and into the wagon',()=>{
  const plan=planLesson({type:'addition',a:5,b:2});
  for(let count=1;count<=2;count++){
    const start=sample(plan,'count_b',count,.05),carry=sample(plan,'count_b',count,.4),placed=sample(plan,'count_b',count,.8);
    assert.equal(start.counts.home,5+count-1);assert.equal(start.counts.source,2-count+1);
    assert.equal(carry.counts.home,5+count-1);assert.equal(carry.counts.source,2-count);assert.equal(carry.counts.moving,1);
    assert.equal(placed.counts.home,5+count);assert.equal(placed.counts.source,2-count);assert.equal(placed.counts.moving,0);
    const moving=carry.items.find(item=>item.status==='moving');const hand=characterAnchors(hero,carry.actor.x,carry.actor.y,carry.actor.width,carry.actor.height,carry.actor).prop;
    assert.ok(Math.abs(moving.x-hand.x)<1e-8);assert.ok(Math.abs(moving.y-hand.y)<1e-8);
    assert.ok(Math.abs(sample(plan,'count_b',count,.25).actor.x-sample(plan,'count_b',count,.56).actor.x)>100);
    assert.equal(carry.actor.motion,'carry');assert.equal(carry.actor.walking,true);
  }
  assert.equal(sample(plan,'answer').counts.home,7);assert.equal(sample(plan,'answer').counts.source,0);
});

test('sharing removes the same star from the wagon and gives it to the helper without cancelling or duplicating it',()=>{
  const plan=planLesson({type:'subtraction',a:5,b:2});
  for(let count=1;count<=2;count++){
    const carry=sample(plan,'remove_count',count,.4),shared=sample(plan,'remove_count',count,.8);
    assert.equal(carry.counts.home,5-count);assert.equal(carry.counts.delivered,count-1);assert.equal(carry.counts.moving,1);
    assert.equal(shared.counts.home,5-count);assert.equal(shared.counts.delivered,count);assert.equal(shared.counts.moving,0);
  }
  const final=sample(plan,'answer');assert.equal(final.counts.home,3);assert.equal(final.counts.delivered,2);assert.equal(final.homeLabel,'STARS LEFT');
});

test('successive deliveries start where the previous action finished instead of teleporting back',()=>{
  for(const spec of [{type:'addition',a:3,b:3},{type:'subtraction',a:5,b:3}]){
    const plan=planLesson(spec),phase=spec.type==='addition'?'count_b':'remove_count';
    for(let count=1;count<3;count++){const before=sample(plan,phase,count,.999999),after=sample(plan,phase,count+1,0);assert.ok(Math.abs(before.actor.x-after.actor.x)<1e-8);assert.equal(before.actor.y,after.actor.y);}
  }
});

test('the character walks continuously between spoken steps for all supported story types',()=>{
  for(const spec of allSpecs()){
    const plan=planLesson(spec);for(let i=1;i<plan.scenes.length;i++){
      const scene=plan.scenes[i],before=storyState(plan,scene.start-.000001,hero),after=storyState(plan,scene.start,hero);
      assert.ok(Math.abs(before.actor.x-after.actor.x)<.001,`${spec.type} ${scene.phase} keeps its horizontal endpoint`);
      assert.ok(Math.abs(before.actor.y-after.actor.y)<.001,`${spec.type} ${scene.phase} keeps its vertical endpoint`);
    }
  }
});

test('zero tasks stay empty and taking every star away leaves a truly empty wagon',()=>{
  for(const spec of [{type:'addition',a:0,b:0},{type:'subtraction',a:0,b:0},{type:'counting',count:0}]){
    const plan=planLesson(spec);for(const scene of plan.scenes)assert.equal(storyState(plan,scene.start+scene.duration*.5,hero).items.length,0);
  }
  const state=sample(planLesson({type:'subtraction',a:10,b:10}),'answer');assert.equal(state.counts.home,0);assert.equal(state.counts.delivered,10);
});

test('both rows of up to ten stars fit inside every wagon or basket, clear of other stars and wheels',()=>{
  const cases=[
    {spec:{type:'addition',a:10,b:0},phase:'answer',status:'home'},
    {spec:{type:'addition',a:0,b:10},phase:'intro',status:'source'},
    {spec:{type:'subtraction',a:10,b:10},phase:'answer',status:'delivered'},
  ];
  for(const {spec,phase,status} of cases){
    const state=sample(planLesson(spec),phase),box=state.containers[status],r=state.tokenRadius,items=state.items.filter(item=>item.status===status);
    assert.equal(items.length,10);
    for(const item of items){assert.ok(item.x-r>=box.x+8);assert.ok(item.x+r<=box.x+box.w-8);assert.ok(item.y-r>=box.y+8);assert.ok(item.y+r<=box.y+box.h-8);if(status==='home')assert.ok(item.y+r<box.y+box.h+12-16,'every token is above the wheel tops');}
    for(let i=0;i<items.length;i++)for(let j=i+1;j<items.length;j++)assert.ok(Math.hypot(items[i].x-items[j].x,items[i].y-items[j].y)>=r*2+2,'stars do not overlap');
  }
  const counting=sample(planLesson({type:'counting',count:10}),'answer');
  for(let i=0;i<counting.items.length;i++)for(let j=i+1;j<counting.items.length;j++)assert.ok(Math.hypot(counting.items[i].x-counting.items[j].x,counting.items[i].y-counting.items[j].y)>=counting.tokenRadius*2+2);
});

test('a carried star stays continuous through pickup, turn, and release instead of snapping between palms',()=>{
  for(const spec of [{type:'addition',a:5,b:2},{type:'subtraction',a:5,b:2}]){
    const plan=planLesson(spec),phase=spec.type==='addition'?'count_b':'remove_count',scene=plan.scenes.find(s=>s.phase===phase&&s.count===1);
    for(const boundary of [.12,.17,.23,.29,.57,.64]){
      const before=storyState(plan,scene.start+scene.duration*(boundary-.00000001),hero),after=storyState(plan,scene.start+scene.duration*boundary,hero);
      const id=phase==='count_b'?'extra-0':'base-4',a=before.items.find(i=>i.id===id),b=after.items.find(i=>i.id===id);
      assert.ok(Math.hypot(a.x-b.x,a.y-b.y)<.001,`the ${phase} token stays continuous at ${boundary}`);
    }
  }
});

test('counting physically visits and touches one original object at a time, without moving the objects',()=>{
  const plan=planLesson({type:'counting',count:6}),positions=new Map(storyState(plan,0).items.map(item=>[item.id,{x:item.x,y:item.y}]));
  const actorPositions=[];
  for(let count=1;count<=6;count++){
    const state=sample(plan,'count_all',count,.8);actorPositions.push(state.actor.x);
    assert.equal(state.items.filter(item=>item.active).length,1);assert.equal(state.items.find(item=>item.active).id,`trail-${count-1}`);
    assert.equal(state.items.filter(item=>item.label!==null).length,count);
    for(const item of state.items)assert.deepEqual({x:item.x,y:item.y},positions.get(item.id));
  }
  assert.ok(Math.max(...actorPositions)-Math.min(...actorPositions)>200);
});

test('shape gates preserve real geometry and the hero traces the requested edge',()=>{
  const distance=(a,b)=>Math.hypot(a.x-b.x,a.y-b.y);
  const square=shapeGeometry('square').vertices;const lengths=square.map((p,i)=>distance(p,square[(i+1)%4]));assert.ok(lengths.every(n=>Math.abs(n-lengths[0])<1e-10));
  const rectangle=shapeGeometry('rectangle').vertices;assert.equal(distance(rectangle[0],rectangle[1]),distance(rectangle[2],rectangle[3]));assert.notEqual(distance(rectangle[0],rectangle[1]),distance(rectangle[1],rectangle[2]));
  assert.equal(shapeGeometry('triangle').vertices.length,3);assert.equal(shapeGeometry('circle').vertices.length,0);
  const plan=planLesson({type:'shape',shape:'triangle',shape_task:'sides'});
  for(let count=1;count<=3;count++){const state=sample(plan,'count_side',count,.5);assert.equal(state.trace.edge,count-1);assert.equal(state.trace.completedEdges,count-1);assert.equal(state.actor.motion,'point');const a=state.geometry.vertices[count-1],b=state.geometry.vertices[count%3];assert.ok(Math.abs(state.trace.target.x-(a.x+b.x)/2)<1e-8);assert.ok(Math.abs(state.trace.target.y-(a.y+b.y)/2)<1e-8);}
});

test('the shape gate opens only after the answer and the chosen hero walks through it',()=>{
  for(const shape of ['circle','triangle','square','rectangle'])for(const shape_task of ['name','sides']){
    const plan=planLesson({type:'shape',shape,shape_task});assert.equal(sample(plan,'pause').gateOpen,0);
    const answering=sample(plan,'answer',undefined,.6),entering=sample(plan,'celebration',undefined,.2),through=sample(plan,'celebration',undefined,.85);
    assert.ok(answering.gateOpen>0);assert.equal(entering.gateOpen,1);assert.ok(entering.actor.x<655);assert.ok(through.actor.x>655);assert.equal(through.actor.motion,'celebrate');
  }
});

test('the equation reveals its result only after the thinking pause and shape names stay hidden until the answer',()=>{
  for(const spec of [{type:'addition',a:5,b:2},{type:'subtraction',a:8,b:3},{type:'shape',shape:'triangle',shape_task:'name'}]){
    const plan=planLesson(spec);for(const scene of plan.scenes){const state=storyState(plan,scene.start+scene.duration*.5,hero);if(!['answer','celebration'].includes(scene.phase)){assert.equal(state.answerVisible,false);if(spec.type==='shape')assert.ok(!state.equation.includes('triangle'));else assert.ok(state.equation.endsWith('= ?'));}else assert.equal(state.answerVisible,true);}
  }
});

test('count words, numeric badges and speaking arrive after transfer, not while approaching a future object',()=>{
  const plan=planLesson({type:'addition',a:5,b:2}),early=sample(plan,'count_b',1,.3),late=sample(plan,'count_b',1,.7);
  assert.equal(early.caption,'Bring one star to the wagon…');assert.equal(early.actor.speaking,false);assert.equal(early.items.find(item=>item.active).label,null);
  assert.equal(late.caption,late.scene.caption);assert.equal(late.actor.speaking,true);assert.equal(late.items.find(item=>item.active).label,6);
});

test('preserved drawings use the same action path and their own prop anchor without invented limbs',()=>{
  const drawing={source:'drawing',name:'My drawing',image:'data:image/png;base64,AA=='},plan=planLesson({type:'addition',a:2,b:1}),scene=plan.scenes.find(s=>s.phase==='count_b');
  const state=storyState(plan,scene.start+scene.duration*.4,drawing),prop=characterAnchors(drawing,state.actor.x,state.actor.y,state.actor.width,state.actor.height,state.actor).prop;
  assert.equal(state.actor.motion,'carry');assert.equal(state.actor.walking,true);assert.deepEqual({x:state.items.find(i=>i.status==='moving').x,y:state.items.find(i=>i.status==='moving').y},prop);
  assert.equal(state.connection.kind,'magic-ribbon');assert.deepEqual(state.connection.to,prop);finite(state.connection);
  assert.equal(storyState(plan,scene.start+scene.duration*.4,hero).connection,null,'modular characters keep their real gripping hands');
  assert.equal(storyState(plan,scene.start+scene.duration*.8,drawing).connection,null,'the ribbon disappears after delivery without leaving a ghost object');
});

function context(){
  const texts=[];const base={font:'',globalAlpha:1,measureText:value=>({width:String(value).length*12}),fillText(value,...args){finite(args);texts.push(String(value));}};
  return {texts,ctx:new Proxy(base,{get(target,key){if(key in target)return target[key];return(...args)=>{finite(args);};},set(target,key,value){if(typeof value==='number')finite(value);target[key]=value;return true;}})};
}
test('all lesson kinds render safely in the same frame layout and name-shape rendering does not expose an answer label',()=>{
  for(const spec of allSpecs()){
    const plan=planLesson(spec);for(const phase of ['intro','pause','answer','celebration']){const scene=plan.scenes.find(s=>s.phase===phase),fake=context();const state=renderStoryFrame({width:1280,height:720,getContext:()=>fake.ctx},plan,hero,scene.start+scene.duration*.5);assert.equal(state.phase,phase);assert.ok(fake.texts.includes(state.caption)||fake.texts.some(text=>state.caption.includes(text)));if(spec.type==='shape'&&spec.shape_task==='name'&&!state.answerVisible){assert.ok(!fake.texts.some(text=>text.toLowerCase().includes(spec.shape)));}}
  }
});

test('seeking is deterministic and does not mutate a frozen reviewed plan',()=>{
  const plan=planLesson({type:'addition',a:3,b:4}),before=JSON.stringify(plan),t=plan.scenes.find(s=>s.phase==='count_b'&&s.count===3).start+1;
  const first=storyState(plan,t,hero);storyState(plan,plan.duration,hero);assert.deepEqual(storyState(plan,t,hero),first);assert.equal(JSON.stringify(plan),before);
});

const PROP_PNG='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+yFZkAAAAASUVORK5CYII=';
function worksheetPack(quantity,mode='individual'){
  return {version:1,mode,sourceWidth:1000,sourceHeight:100,sprites:Array.from({length:mode==='repeat'?1:quantity},(_,i)=>({image:PROP_PNG,box:{x:i*60,y:10,width:30,height:50}}))};
}

test('original worksheet objects keep their stable sprite identity through every transfer and remain conserved',()=>{
  for(const spec of allSpecs().filter(spec=>spec.type!=='shape')){
    const quantity=spec.type==='addition'?spec.a+spec.b:spec.type==='subtraction'?spec.a:spec.count;
    const plan=planLesson(spec,{objects:worksheetPack(quantity)});
    for(const scene of plan.scenes)for(const progress of [.01,.4,.7,.999]){
      const state=storyState(plan,scene.start+scene.duration*progress,hero);
      assert.equal(state.usesWorksheetObjects,true);assert.equal(state.items.length,quantity);
      assert.deepEqual(state.items.map(item=>item.objectIndex).sort((a,b)=>a-b),Array.from({length:quantity},(_,i)=>i));
      assert.equal(state.counts.home+state.counts.source+state.counts.moving+state.counts.delivered,quantity);
      assert.doesNotMatch([state.caption,state.equation,state.homeLabel,state.otherLabel,state.representation].join(' '),/\bstars?\b/i);
      if(spec.type==='addition')for(const item of state.items)assert.equal(item.objectIndex,item.id.startsWith('extra-')?spec.a+Number(item.id.slice(6)):Number(item.id.slice(5)));
    }
  }
});

test('exact worksheet rendering draws only the prepared artwork, preserves aspect, and leaves its pixels unobscured',async t=>{
  const previous=globalThis.Image;
  t.after(()=>{if(previous===undefined)delete globalThis.Image;else globalThis.Image=previous;});
  globalThis.Image=class{naturalWidth=20;naturalHeight=40;set src(value){this.currentSrc=value;if(value)queueMicrotask(()=>this.onload?.());}};
  const objects=worksheetPack(7),plan=planLesson({type:'addition',a:5,b:2},{objects});
  await prepareWorksheetObjects(plan.objects);
  const fake=context(),images=[],starShapes=[],texts=fake.texts;
  fake.ctx.drawImage=(...args)=>images.push(args);
  const scene=plan.scenes.find(scene=>scene.phase==='count_b');
  const state=renderStoryFrame({width:1280,height:720,getContext:()=>fake.ctx},plan,hero,scene.start+scene.duration*.7);
  assert.equal(images.length,7,'each reviewed source sprite is drawn exactly once');
  for(const [index,args] of images.entries()){
    const [,x,y,width,height]=args;assert.equal(width/height,.5,'original artwork aspect ratio is retained');
    assert.ok(width<=46&&height<=46,'every object fits its original stable counting slot');
    assert.ok(Math.abs(x+width/2-state.items[index].x)<1e-6);assert.ok(Math.abs(y+height/2-state.items[index].y)<1e-6);
  }
  assert.ok(!texts.includes('6'),'the numeric count never covers the original object artwork');
  assert.doesNotMatch(texts.join(' '),/\bstars?\b/i);
});
