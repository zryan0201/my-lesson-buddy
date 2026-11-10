/* A character-led mathematical story. Every displayed star has one stable ID;
 * transfers move it between places instead of duplicating a hand-held prop.
 * State is deterministic, so review frames, playback, seeking, and export agree. */
import {AUDIO} from '../audio/manifest.js';
import {DEFAULT_DESIGN, drawCharacter, characterAnchors} from './character.js';
import {drawWorksheetObject} from './objects.js';
import {adventureFor,drawAdventureBackground,sceneDirection} from './adventures.js';

const INK='#293E38', TEAL='#367970', GOLD='#E8B657';
const FINAL=new Set(['answer','celebration']);
const AFTER_ADD=new Set(['your_turn','pause','answer','celebration']);
const AFTER_TAKE=new Set(['remaining','count_remaining','your_turn','pause','answer','celebration']);
const CHAR={source:'builder',name:'Buddy',design:DEFAULT_DESIGN};
const HOME={x:130,y:338,w:440,h:136,kind:'container'};
const SOURCE={x:859,y:338,w:292,h:136,kind:'container'};
const GIFT={x:884,y:338,w:261,h:136,kind:'container'};
const TOKEN_RADIUS=23;
const clamp=(value,min=0,max=1)=>Math.max(min,Math.min(max,value));
const mix=(a,b,t)=>a+(b-a)*t;
const smooth=t=>{const p=clamp(t);return p*p*(3-2*p);};
const point=(a,b,t)=>({x:mix(a.x,b.x,t),y:mix(a.y,b.y,t)});

function validatePlan(plan){
  if(!plan||!plan.spec||!Array.isArray(plan.scenes)||!plan.scenes.length||!Number.isFinite(plan.duration)||plan.duration<=0)throw new Error('Choose a reviewed story lesson.');
  const s=plan.spec;
  if(!['addition','subtraction','counting','shape'].includes(s.type))throw new Error('Choose a supported story lesson.');
  const whole=n=>Number.isInteger(n)&&n>=0&&n<=10;
  if(['addition','subtraction'].includes(s.type)&&(!whole(s.a)||!whole(s.b)||(s.type==='addition'?s.a+s.b>10:s.b>s.a)))throw new Error('Choose supported story quantities.');
  if(s.type==='counting'&&!whole(s.count))throw new Error('Choose a supported story count.');
  if(s.type==='shape'&&!['circle','triangle','square','rectangle'].includes(s.shape))throw new Error('Choose a supported story shape.');
}

function slots(quantity,area){
  if(!quantity)return [];
  const columns=Math.min(quantity,5),rows=Math.ceil(quantity/columns);
  const gap=Math.min(73,(area.w-(area.kind==='container'?64:54))/Math.max(columns-1,1));
  const first=area.x+area.w/2-(columns-1)*gap/2;
  const middle=area.y+area.h*(area.kind==='container' ? .5 : .45),rowGap=area.kind==='container'?64:52;
  return Array.from({length:quantity},(_,i)=>({x:first+(i%columns)*gap,y:middle+(Math.floor(i/columns)-(rows-1)/2)*rowGap}));
}

function actorAt(x,motion='idle',facing='right',extra={}){
  return {x:clamp(x,60,1080),y:227,width:180,height:240,motion,facing,walking:false,...extra};
}

function homePointActor(item,previous,p){
  const target=clamp(item.x-122,70,580),from=clamp(previous?previous.x-122:600,70,680);
  return actorAt(mix(from,target,smooth(p/.43)),p<.43?'walk':'point','right',{walking:p<.43});
}

function transferState(kind,scene,p,character,from,to,previousTo){
  const adding=kind==='addition';
  const sourceFacing=adding?'right':'left',destinationFacing=adding?'left':'right';
  const pickupOffset=characterAnchors(character,0,0,180,240,{motion:'carry',facing:sourceFacing,time:0}).prop.x;
  const dropOffset=characterAnchors(character,0,0,180,240,{motion:'give',facing:destinationFacing,time:0}).prop.x;
  const sourceX=clamp(from.x-pickupOffset,60,1080),finishX=clamp(to.x-dropOffset,60,1080);
  // Each delivery reaches the actual receiving slot. Reusing the previous
  // slot endpoint avoids both teleporting and a long cross-wagon prop fling.
  const beginX=previousTo?clamp(previousTo.x-dropOffset,60,1080):650;
  let actor;
  if(p<.12)actor=actorAt(mix(beginX,sourceX,smooth(p/.12)),'walk',adding?'right':'left',{walking:true});
  else if(p<.23)actor=actorAt(sourceX,'carry',adding?'right':'left');
  else if(p<.57)actor=actorAt(mix(sourceX,finishX,smooth((p-.23)/.34)),'carry',adding?'left':'right',{walking:true});
  else if(p<.64)actor=actorAt(finishX,'give',adding?'left':'right');
  else actor=actorAt(finishX,'point',adding?'left':'right');
  const anchors=characterAnchors(character,actor.x,actor.y,actor.width,actor.height,{...actor,time:scene.start+p*scene.duration});
  let location,status;
  if(p<.12){location=from;status=adding?'source':'home';}
  else if(p<.23){location=point(from,anchors.prop,smooth((p-.12)/.11));status='moving';}
  else if(p<.29){
    const previous=characterAnchors(character,sourceX,227,180,240,{motion:'carry',facing:sourceFacing,time:scene.start+.23*scene.duration}).prop;
    location=point(previous,anchors.prop,smooth((p-.23)/.06));status='moving';
  }
  else if(p<.57){location=anchors.prop;status='moving';}
  else if(p<.64){
    const previous=characterAnchors(character,finishX,227,180,240,{motion:'carry',facing:destinationFacing,walking:true,time:scene.start+.57*scene.duration}).prop;
    const q=smooth((p-.57)/.07);location=point(previous,to,q);location.y-=Math.sin(q*Math.PI)*28;status='moving';
  }
  else{location=to;status=adding?'home':'delivered';}
  return {actor,location,status};
}

export function shapeGeometry(name){
  if(name==='circle')return {center:{x:655,y:322},radius:135,vertices:[]};
  if(name==='triangle')return {vertices:[{x:650,y:170},{x:908,y:435},{x:392,y:435}]};
  if(name==='square')return {vertices:[{x:505,y:170},{x:805,y:170},{x:805,y:470},{x:505,y:470}]};
  if(name==='rectangle')return {vertices:[{x:410,y:205},{x:910,y:205},{x:910,y:435},{x:410,y:435}]};
  throw new Error('Choose a supported shape gate.');
}

function routePoint(geometry,progress){
  const p=clamp(progress);
  if(geometry.radius){const angle=-Math.PI/2+p*Math.PI*2;return {x:geometry.center.x+Math.cos(angle)*geometry.radius,y:geometry.center.y+Math.sin(angle)*geometry.radius};}
  const count=geometry.vertices.length,index=Math.min(count-1,Math.floor(p*count));
  return point(geometry.vertices[index],geometry.vertices[(index+1)%count],p===1?1:p*count-index);
}

/** Pure scene state. Optional character input makes carrying anchors exact for
 * both modular heroes and original, unrigged drawings. Nothing is saved here. */
export function storyState(plan,time,character=CHAR){
  validatePlan(plan);
  const t=clamp(Number.isFinite(time)?time:0,0,plan.duration);
  const scene=plan.scenes.find(s=>t<s.end)||plan.scenes.at(-1);
  const p=clamp((t-scene.start)/Math.max(.001,scene.duration));
  const phase=scene.phase,s=plan.spec,final=FINAL.has(phase),worksheet=Boolean(plan.objects);
  let actor=actorAt(620),items=[],focus=null,geometry=null,trace=null;
  const total=s.type==='addition'?s.a+s.b:s.type==='subtraction'?s.a:s.type==='counting'?s.count:0;
  const homeSlots=slots(s.type==='addition'?total:s.type==='subtraction'?s.a:0,HOME);
  const sourceSlots=slots(s.type==='addition'?s.b:0,SOURCE);
  const deliveredSlots=slots(s.type==='subtraction'?s.b:0,GIFT);
  if(s.type==='addition'){
    for(let i=0;i<s.a;i++)items.push({id:`base-${i}`,origin:'home',status:'home',...homeSlots[i],active:false,label:null});
    let completed=AFTER_ADD.has(phase)?s.b:phase==='count_b'?Math.max(0,scene.count-1):0;
    for(let i=0;i<s.b;i++)items.push({id:`extra-${i}`,origin:'source',status:i<completed?'home':'source',...(i<completed?homeSlots[s.a+i]:sourceSlots[i]),active:false,label:null});
    if(phase==='count_a'){
      const i=clamp(scene.count-1,0,Math.max(0,s.a-1));focus=items[i];
      if(focus){actor=homePointActor(focus,items[i-1],p);focus.active=p>=.43;focus.label=p>=.55?scene.count:null;}
    }else if(phase==='count_b'){
      const i=clamp(scene.count-1,0,Math.max(0,s.b-1)),item=items[s.a+i];
      if(item){const transfer=transferState(s.type,scene,p,character,sourceSlots[i],homeSlots[s.a+i],i?homeSlots[s.a+i-1]:null);actor=transfer.actor;Object.assign(item,transfer.location,{status:transfer.status,active:true,label:p>=.66?scene.spokenCount??s.a+scene.count:null});focus=item;}
    }else if(['add','count_on'].includes(phase))actor=actorAt(650,'point','right');
    else if(phase==='first')actor=actorAt(580,'point','left');
  }else if(s.type==='subtraction'){
    const completed=AFTER_TAKE.has(phase)?s.b:phase==='remove_count'?Math.max(0,scene.count-1):0;
    for(let i=0;i<s.a;i++){
      const shared=i>=s.a-completed,sharedIndex=s.a-1-i;
      items.push({id:`base-${i}`,origin:'home',status:shared?'delivered':'home',...(shared?deliveredSlots[sharedIndex]:homeSlots[i]),active:false,label:null});
    }
    if(phase==='count_a'||phase==='count_remaining'){
      const i=scene.count-1;focus=items[i];if(focus&&focus.status==='home'){actor=homePointActor(focus,items[i-1],p);focus.active=p>=.43;focus.label=p>=.55?scene.count:null;}
    }else if(phase==='remove_count'){
      const i=clamp(scene.count-1,0,Math.max(0,s.b-1)),item=items[s.a-1-i];
      if(item){const transfer=transferState(s.type,scene,p,character,homeSlots[s.a-1-i],deliveredSlots[i],i?deliveredSlots[i-1]:null);actor=transfer.actor;Object.assign(item,transfer.location,{status:transfer.status,active:true,label:p>=.66?scene.count:null});focus=item;}
    }else if(phase==='take')actor=actorAt(650,'point','left');
    else if(phase==='remaining')actor=actorAt(590,'point','left');
  }else if(s.type==='counting'){
    const coordinates=slots(s.count,{x:135,y:382,w:1000,h:95});
    for(let i=0;i<s.count;i++){
      const visited=phase==='count_all'?i<scene.count-1:AFTER_ADD.has(phase);
      items.push({id:`trail-${i}`,origin:'trail',status:'home',...coordinates[i],active:false,label:visited?i+1:null});
    }
    if(phase==='count_all'){
      const i=scene.count-1;focus=items[i];if(focus){actor=homePointActor(focus,items[i-1],p);actor.x=clamp(mix(i?coordinates[i-1].x-100:80,coordinates[i].x-100,smooth(p/.43)),70,1055);focus.active=p>=.43;if(p>=.55)focus.label=scene.count;}
    }else if(AFTER_ADD.has(phase))actor=actorAt(s.count?clamp(coordinates.at(-1).x-110,85,1055):575,'point','left');
  }else{
    geometry=shapeGeometry(s.shape);
    if(phase==='count_side'){
      const index=clamp(scene.highlightSide??scene.count-1,0,geometry.vertices.length-1);
      const target=point(geometry.vertices[index],geometry.vertices[(index+1)%geometry.vertices.length],smooth(p));
      trace={target,edge:index,progress:smooth(p),completedEdges:index};
      actor=actorAt(clamp(target.x-160,170,900),'point','right',{y:clamp(target.y-105,155,270),walking:p<.9});focus={...target,active:true};
    }else if(phase==='shape'){
      const target=routePoint(geometry,p);trace={target,edge:null,progress:p,completedEdges:0,preview:true};
      actor=actorAt(clamp(target.x-160,170,900),'point','right',{y:clamp(target.y-105,155,270),walking:true});focus={...target,active:true};
    }else actor=actorAt(220,'point','right');
  }
  if(phase==='intro')actor=actorAt(mix(65,620,smooth(p)),'walk','right',{walking:true});
  if(['question','your_turn'].includes(phase))actor=actorAt(s.type==='shape'?230:620,'point','right');
  if(phase==='pause')actor=actorAt(s.type==='shape'?230:620,'think','right');
  if(phase==='answer')actor=s.type==='shape'?actorAt(mix(230,460,smooth(p)),'walk','right',{walking:true}):actorAt(620,'point',s.type==='subtraction'?'left':'right');
  if(phase==='celebration')actor=s.type==='shape'?actorAt(mix(460,850,smooth(p/.7)),p<.7?'walk':'celebrate','right',{walking:p<.7}):actorAt(620,'celebrate','right');
  const sceneIndex=plan.scenes.indexOf(scene);
  if(sceneIndex>0&&p<.43&&!['count_b','remove_count'].includes(phase)){
    // Narrative and counting shots inherit the preceding endpoint. This is a
    // one-step lookup: the earlier time is at progress≈1 and never recurses here.
    // Character location therefore remains continuous when a new spoken step
    // begins, rather than cutting back to an arbitrary presenter position.
    const previous=storyState(plan,Math.max(0,scene.start-.000001),character).actor;
    if(Math.hypot(actor.x-previous.x,actor.y-previous.y)>1){
      const q=smooth(p/.43),target=actor;
      actor={...target,x:mix(previous.x,target.x,q),y:mix(previous.y,target.y,q),motion:'walk',walking:true,facing:target.x>=previous.x?'right':'left'};
    }
  }
  const audioOffset=scene.audioOffset||0,audioDuration=scene.audioDuration??AUDIO[scene.audioKey]?.duration??0;
  actor.speaking=Boolean(scene.audioKey&&t-scene.start>=audioOffset&&t-scene.start<audioOffset+audioDuration);
  actor.time=t;
  const direction=sceneDirection(plan,t);
  if(phase==='question'&&p<.42)actor.motion='wave';
  if(phase==='celebration'&&direction.presentation.motion!=='calm')actor.y-=Math.sin(p*Math.PI*3)**2*9;
  const counts={home:0,source:0,moving:0,delivered:0,total};for(const item of items)counts[item.status]++;
  for(const item of items)item.objectIndex=item.id.startsWith('extra-')?s.a+Number(item.id.slice(6)):Number(item.id.slice(item.id.indexOf('-')+1));
  const equation=final?plan.answerText:s.type==='addition'?`${s.a} + ${s.b} = ?`:s.type==='subtraction'?`${s.a} − ${s.b} = ?`:s.type==='counting'?(worksheet?'One picture. One count.':'One star. One count.'):s.shape_task==='name'?'Which shape makes this gate?':'Trace each straight side once.';
  const noun=worksheet?'picture':'star';
  const actionCaption=phase==='count_b'?`Bring one ${noun} to the wagon…`:phase==='remove_count'?`Share one ${noun} with our friend…`:phase==='count_side'?'Follow this straight side…':`Visit one ${noun} at a time…`;
  const caption=audioOffset>0&&t-scene.start<audioOffset?actionCaption:scene.caption||'Take your time. Think and count!';
  const gateOpen=s.type==='shape'?(phase==='answer'?smooth((p-.15)/.7):phase==='celebration'?1:0):0;
  let connection=null;
  const carried=items.find(item=>item.status==='moving');
  if(character.source==='drawing'&&carried&&['carry','give'].includes(actor.motion)){
    const anchors=characterAnchors(character,actor.x,actor.y,actor.width,actor.height,actor);
    const from=anchors.body||{x:mix(anchors.head.x,anchors.feet.x,.5),y:mix(anchors.head.y,anchors.feet.y,.5)},to={x:carried.x,y:carried.y};
    connection={kind:'magic-ribbon',from,to,control:{x:(from.x+to.x)/2,y:Math.min(from.y,to.y)-16}};
  }
  return {version:1,usesWorksheetObjects:worksheet,presentation:direction.presentation,camera:direction.camera,time:t,phase,scene,progress:p,actor,items,counts,focus,geometry,trace,gateOpen,connection,answerVisible:final,equation,
    containers:{home:{...HOME},source:{...SOURCE},delivered:{...GIFT}},tokenRadius:TOKEN_RADIUS,
    homeLabel:s.type==='subtraction'?(final?(worksheet?'PICTURES LEFT':'STARS LEFT'):'OUR WAGON'):'OUR WAGON',
    otherLabel:s.type==='subtraction'?'SHARED WITH OUR FRIEND':worksheet?'WORKSHEET PICTURES':'STARS IN THE GARDEN',
    storyTitle:plan.story?.title||'The Starlight Garden',
    question:plan.question,caption,
    representation:s.type==='shape'?'Follow your buddy’s path around the gate.':worksheet?plan.representation:'Story stars stand for the pictures on your worksheet.'};
}

function rounded(ctx,x,y,w,h,r,fill,stroke,width=2){ctx.beginPath();ctx.roundRect(x,y,w,h,r);if(fill){ctx.fillStyle=fill;ctx.fill();}if(stroke){ctx.strokeStyle=stroke;ctx.lineWidth=width;ctx.stroke();}}
function line(ctx,points,color,width=3){ctx.beginPath();points.forEach((p,i)=>i?ctx.lineTo(p.x,p.y):ctx.moveTo(p.x,p.y));ctx.strokeStyle=color;ctx.lineWidth=width;ctx.lineCap='round';ctx.lineJoin='round';ctx.stroke();}
function text(ctx,value,x,y,size=24,color=INK,align='left',maxWidth=1120,weight=700){let font=size;ctx.textAlign=align;ctx.textBaseline='middle';ctx.font=`${weight} ${font}px system-ui, -apple-system, sans-serif`;while(ctx.measureText(String(value)).width>maxWidth&&font>12){font--;ctx.font=`${weight} ${font}px system-ui, -apple-system, sans-serif`;}ctx.fillStyle=color;ctx.fillText(String(value),x,y);}
function ellipse(ctx,x,y,rx,ry,fill,stroke,width=2){ctx.beginPath();ctx.ellipse(x,y,rx,ry,0,0,Math.PI*2);if(fill){ctx.fillStyle=fill;ctx.fill();}if(stroke){ctx.strokeStyle=stroke;ctx.lineWidth=width;ctx.stroke();}}
function wrapped(ctx,value,x,y,maxWidth,size=23){ctx.font=`600 ${size}px system-ui, -apple-system, sans-serif`;const lines=[];let current='';for(const word of String(value).split(' ')){const candidate=current?`${current} ${word}`:word;if(current&&ctx.measureText(candidate).width>maxWidth){lines.push(current);current=word;}else current=candidate;}if(current)lines.push(current);lines.slice(0,2).forEach((value,i)=>text(ctx,value,x,y+(lines.length>1?-13+i*27:0),size,INK,'center',maxWidth,600));}

function background(ctx,shapeLesson){
  ctx.fillStyle='#FAF8EE';ctx.fillRect(0,0,1280,720);
  rounded(ctx,34,112,1212,391,30,'#EDF4DF','#DBE6CF');
  ctx.save();ctx.beginPath();ctx.roundRect(35,113,1210,389,29);ctx.clip();
  ctx.fillStyle='#DDEBCC';ctx.beginPath();ctx.ellipse(300,493,490,173,0,Math.PI,Math.PI*2);ctx.fill();
  ctx.fillStyle='#D1E4C4';ctx.beginPath();ctx.ellipse(1105,527,560,175,0,Math.PI,Math.PI*2);ctx.fill();
  if(!shapeLesson){
    for(const c of [{x:108,y:152,s:1},{x:1060,y:159,s:.8}]){ellipse(ctx,c.x,c.y,55*c.s,15*c.s,'#FFFFFF80');ellipse(ctx,c.x+38*c.s,c.y-7*c.s,39*c.s,18*c.s,'#FFFFFF80');}
    // Rounded foliage is deliberately unlike the countable star tokens.
    rounded(ctx,83,292,16,127,8,'#AFBD88');ellipse(ctx,89,264,49,62,'#A9C99A');ellipse(ctx,55,282,34,43,'#B8D3A5');ellipse(ctx,121,284,35,46,'#B8D3A5');
  }
  ctx.fillStyle='#EBDCC0';ctx.beginPath();ctx.ellipse(659,491,652,53,0,Math.PI,Math.PI*2);ctx.fill();
  line(ctx,[{x:100,y:476},{x:1182,y:476}],'#DCCAA7',2);
  ctx.restore();
}

function wagon(ctx,area,label,{source=false,dim=false,empty=false,theme=null}={}){
  ctx.save();if(dim)ctx.globalAlpha=.67;
  text(ctx,label,area.x+area.w/2,216,15,theme?.id==='moon'?'#DBE7FA':theme?.accent||'#496D60','center',area.w+100,800);
  if(!source){
    const wheelY=area.y+area.h+12;
    ellipse(ctx,area.x+68,wheelY,16,16,'#667C6B','#405B4E',3);ellipse(ctx,area.x+area.w-68,wheelY,16,16,'#667C6B','#405B4E',3);
    ellipse(ctx,area.x+68,wheelY,6,6,'#D9D9BB');ellipse(ctx,area.x+area.w-68,wheelY,6,6,'#D9D9BB');
  }
  rounded(ctx,area.x,area.y,area.w,area.h,theme?.id==='moon'?10:16,theme?.cart||(source?'#E7D4AD':'#D6B986'),theme?.trim||'#9D855D',3);
  // A tall open counting window visibly contains both rows. The wooden base
  // and wheels are below every star, never used as a second row of slots.
  rounded(ctx,area.x+10,area.y+13,area.w-20,area.h-28,11,theme?.inside||(source?'#FAEED3':'#F7E8C9'),null);
  line(ctx,[{x:area.x+12,y:area.y+area.h-9},{x:area.x+area.w-12,y:area.y+area.h-9}],'#B99E70',3);
  if(!source)line(ctx,[{x:area.x+area.w,y:area.y+20},{x:area.x+area.w+28,y:area.y-5},{x:area.x+area.w+51,y:area.y-5}],'#9D855D',5);
  if(empty)text(ctx,'Empty',area.x+area.w/2,area.y+area.h/2,20,'#A18F6D','center',area.w-20,600);
  ctx.restore();
}

function token(ctx,item,time,{dim=false,objects=null,calm=false}={}){
  ctx.save();if(dim)ctx.globalAlpha=.5;
  if(item.active){ellipse(ctx,item.x,item.y,31+(calm?0:Math.sin(time*3)*2),31+(calm?0:Math.sin(time*3)*2),'#FFF8CC');ellipse(ctx,item.x,item.y,34,34,null,'#DAB34F',2);}
  if(objects){
    if(!drawWorksheetObject(ctx,objects,item.objectIndex,item.x,item.y,TOKEN_RADIUS*2))throw new Error('A worksheet picture could not be prepared. Please make this lesson again.');
  }else{
  const radius=TOKEN_RADIUS,inner=10;
  ctx.beginPath();for(let i=0;i<10;i++){const angle=-Math.PI/2+i*Math.PI/5,r=i%2?inner:radius,x=item.x+Math.cos(angle)*r,y=item.y+Math.sin(angle)*r;if(!i)ctx.moveTo(x,y);else ctx.lineTo(x,y);}ctx.closePath();ctx.fillStyle='#F4C45E';ctx.fill();ctx.lineWidth=2.5;ctx.strokeStyle='#AE853E';ctx.stroke();
  }
  ctx.restore();
  // Put its count on the star itself: an above-star badge can cover another
  // countable object when a container needs two rows.
  if(!objects&&item.label!==null&&item.label!==undefined)text(ctx,item.label,item.x,item.y+1,16,'#375D45','center',23,800);
}

function helper(ctx,time,{receiving=false,celebrate=false}={}){
  const x=1175,y=357;
  ellipse(ctx,x,y+94,34,8,'#B7CDB0');
  line(ctx,[{x:x-26,y:y+39},{x:x-43,y:y+56}],'#4E7768',15);line(ctx,[{x:x+25,y:y+39},{x:x+39,y:y+(celebrate?2:receiving?20:53)}],'#4E7768',15);
  rounded(ctx,x-30,y+33,60,49,23,'#80B79B','#496D60',3);
  ellipse(ctx,x-15,y+86,15,9,'#5F8E76');ellipse(ctx,x+15,y+86,15,9,'#5F8E76');
  ellipse(ctx,x,y+10,39,37,'#A7D0AC','#496D60',3);
  ellipse(ctx,x-24,y-16,12,18,'#A7D0AC','#496D60',3);ellipse(ctx,x+24,y-16,12,18,'#A7D0AC','#496D60',3);
  ellipse(ctx,x-12,y+7,4,6,'#293E38');ellipse(ctx,x+12,y+7,4,6,'#293E38');
  ctx.beginPath();ctx.arc(x,y+17,11,.08,Math.PI-.08);ctx.strokeStyle='#496D60';ctx.lineWidth=3;ctx.stroke();
  if(receiving){rounded(ctx,1088,235,130,42,16,'#FFFFFF','#D8E5CE');text(ctx,'Thank you!',1153,256,18,TEAL,'center',120);}
  else if(celebrate){text(ctx,'A kind friend!',1158,257,17,TEAL,'center',142);}
}

function shapeGate(ctx,state,theme){
  const g=state.geometry,s=state.scene,final=state.answerVisible;
  const outline=()=>{ctx.beginPath();if(g.radius)ctx.ellipse(g.center.x,g.center.y,g.radius,g.radius,0,0,Math.PI*2);else{g.vertices.forEach((p,i)=>i?ctx.lineTo(p.x,p.y):ctx.moveTo(p.x,p.y));ctx.closePath();}};
  outline();ctx.fillStyle=theme?.id==='moon'?'#D8E4FF':theme?.soft||'#DCE9D8';ctx.fill();
  if(state.gateOpen>0){
    const minX=g.radius?g.center.x-g.radius:Math.min(...g.vertices.map(p=>p.x)),maxX=g.radius?g.center.x+g.radius:Math.max(...g.vertices.map(p=>p.x));
    const minY=g.radius?g.center.y-g.radius:Math.min(...g.vertices.map(p=>p.y)),maxY=g.radius?g.center.y+g.radius:Math.max(...g.vertices.map(p=>p.y));
    const width=maxX-minX,height=maxY-minY,center=(minX+maxX)/2,slide=state.gateOpen*(width*.58);
    ctx.save();outline();ctx.clip();ctx.fillStyle='#FFF3CD';ctx.fillRect(minX,minY,width,height);
    ellipse(ctx,center,(minY+maxY)/2,width*.44,height*.56,'#FFFEED');
    // Two moving panels actually part after the answer. The original outer
    // outline remains fixed and visible, preserving the mathematics of the gate.
    rounded(ctx,minX-slide-12,minY-16,width/2+13,height+32,24,'#BED5B5');
    rounded(ctx,center+slide-1,minY-16,width/2+13,height+32,24,'#BED5B5');
    ctx.restore();
  }
  outline();ctx.strokeStyle=final?'#C6AA63':theme?.id==='moon'?'#B2CAF5':theme?.accent||'#79A285';ctx.lineWidth=10;ctx.lineJoin='round';ctx.stroke();
  if(state.trace){
    if(g.radius){const end=-Math.PI/2+state.trace.progress*Math.PI*2;ctx.beginPath();ctx.arc(g.center.x,g.center.y,g.radius,-Math.PI/2,end);ctx.strokeStyle=GOLD;ctx.lineWidth=13;ctx.stroke();}
    else if(state.trace.preview){const n=g.vertices.length,full=state.trace.progress*n;for(let i=0;i<Math.ceil(full);i++)line(ctx,[g.vertices[i],point(g.vertices[i],g.vertices[(i+1)%n],clamp(full-i))],GOLD,13);}
    else{for(let i=0;i<state.trace.completedEdges;i++)line(ctx,[g.vertices[i],g.vertices[(i+1)%g.vertices.length]],'#E3C885',11);const edge=state.trace.edge;line(ctx,[g.vertices[edge],state.trace.target],GOLD,14);}
    ellipse(ctx,state.trace.target.x,state.trace.target.y,10,10,'#FFF4BB','#C6A764',2);
  }
  if(final){rounded(ctx,883,143,304,45,18,'#FFFFFFDD');text(ctx,'The gate is opening!',1035,166,21,TEAL,'center',282);}
}

/** Entire 1280×720 scene, with the selected character inside the action. */
export function renderStoryFrame(canvas,plan,character,time){
  const ctx=canvas?.getContext?.('2d');if(!ctx)throw new Error('This browser could not open the story canvas.');
  const state=storyState(plan,time,character),spec=plan.spec,shapeLesson=spec.type==='shape';
  const theme=adventureFor(plan),calm=state.presentation.motion==='calm';
  ctx.save();try{
    ctx.setTransform(canvas.width/1280,0,0,canvas.height/720,0,0);ctx.lineCap='round';ctx.lineJoin='round';drawAdventureBackground(ctx,state,theme);
    text(ctx,state.phase==='celebration'?'You made the story happen!':plan.question,51,56,35,theme.ink,'left',1063);
    rounded(ctx,1097,35,133,42,21,theme.badge);text(ctx,{addition:'COLLECT',subtraction:'SHARE',counting:'EXPLORE',shape:'SHAPE QUEST'}[spec.type],1163,57,15,theme.accent,'center',121,800);
    text(ctx,state.storyTitle.toUpperCase(),61,103,13,theme.accent,'left',680,800);
    text(ctx,character.name||'Your buddy',1205,103,14,theme.accent,'right',380,700);
    ctx.save();try{ctx.beginPath();ctx.roundRect(35,113,1210,389,29);ctx.clip();
    ctx.translate(640+state.camera.x,315);ctx.scale(state.camera.scale,state.camera.scale);ctx.translate(-640,-315);
    if(shapeLesson)shapeGate(ctx,state,theme);
    else if(spec.type==='addition'){
      wagon(ctx,HOME,state.homeLabel,{empty:state.counts.home===0,theme});wagon(ctx,SOURCE,state.otherLabel,{source:true,empty:state.counts.source===0,theme});
    }else if(spec.type==='subtraction'){
      wagon(ctx,HOME,state.homeLabel,{empty:state.counts.home===0,theme});wagon(ctx,GIFT,state.otherLabel,{source:true,dim:state.answerVisible,empty:state.counts.delivered===0,theme});
      helper(ctx,state.time,{receiving:state.phase==='remove_count'&&state.progress>.57,celebrate:state.phase==='celebration'});
    }else{
      text(ctx,plan.objects?'THE PICTURE TRAIL':'THE STAR TRAIL',650,171,17,theme.id==='moon'?'#DBE7FA':theme.accent,'center',850,800);
      if(!spec.count){rounded(ctx,381,363,480,89,23,'#FFFFFF70');text(ctx,plan.objects?'No pictures on the trail today.':'No stars on the trail today.',621,407,26,'#839173','center',450,600);}
      else for(const item of state.items)ellipse(ctx,item.x,item.y+41,34,8,'#C7D3B2');
    }
    const actor=state.actor;
    const anchors=characterAnchors(character,actor.x,actor.y,actor.width,actor.height,actor);
    ellipse(ctx,anchors.feet.x,anchors.feet.y+4,45,8,'#8FAA7D40');
    drawCharacter(ctx,character,actor.x,actor.y,actor.width,actor.height,actor);
    if(state.connection){
      const {from,to,control}=state.connection;
      ctx.save();ctx.globalAlpha=.8;ctx.beginPath();ctx.moveTo(from.x,from.y);ctx.quadraticCurveTo(control.x,control.y,to.x,to.y);
      ctx.strokeStyle='#B898C9';ctx.lineWidth=5;ctx.stroke();ctx.strokeStyle='#FFF7D8';ctx.lineWidth=1.5;ctx.stroke();
      ellipse(ctx,from.x,from.y,3.5,3.5,'#FFF4C9','#AF92BF',1);ctx.restore();
    }
    // A visible hand-to-object touch path makes even a preserved drawing an
    // actor in the lesson. This is not an additional countable object.
    if(state.focus?.active&&actor.motion==='point'&&state.phase!=='pause'){
      ctx.save();ctx.setLineDash([4,7]);line(ctx,[anchors.prop,{x:state.focus.x,y:state.focus.y}],'#C9AB5B',2.5);ctx.restore();
    }
    for(const item of state.items)token(ctx,item,state.time,{objects:plan.objects,calm,dim:spec.type==='subtraction'&&state.answerVisible&&item.status==='delivered'});
    if(state.focus?.active&&['count_b','remove_count'].includes(state.phase)&&state.progress>=.64&&state.progress<.83&&!calm){const q=(state.progress-.64)/.19;ellipse(ctx,state.focus.x,state.focus.y,29+q*13,29+q*13,null,theme.accent+'88',2*(1-q));}
    if(state.phase==='pause'){
      rounded(ctx,883,139,315,62,21,'#FFFFFFDD','#DCE6D2');text(ctx,'Your turn. Take your time!',1041,162,18,TEAL,'center',290,700);
      const fraction=clamp((state.scene.end-state.time)/Math.max(.001,state.scene.duration));rounded(ctx,913,181,255,4,2,'#E4E7D5');rounded(ctx,913,181,255*fraction,4,2,'#B29ECC');
    }
    if(state.phase==='celebration'&&!calm)for(let i=0;i<16;i++){const x=65+(i*151)%1150,y=130+((state.time-state.scene.start)*48+i*39)%330;ctx.fillStyle=[theme.accent,theme.edge,'#DDBE6A'][i%3];ctx.fillRect(x,y,5,8);}
    }finally{ctx.restore();}
    rounded(ctx,166,521,948,61,24,state.answerVisible?'#FFF0AC':'#FFFFFF','#DDE4D1');
    text(ctx,state.equation,640,552,state.answerVisible?34:29,theme.accent,'center',900);
    text(ctx,state.representation,640,599,13,'#829274','center',1160,500);
    const progress=clamp(state.time/plan.duration);rounded(ctx,53,612,1174,4,2,theme.edge);rounded(ctx,53,612,1174*progress,4,2,theme.accent);
    rounded(ctx,53,631,1174,65,22,'#FFFFFF');wrapped(ctx,state.caption,640,663,1108,23);
  }finally{ctx.restore();}
  return state;
}
