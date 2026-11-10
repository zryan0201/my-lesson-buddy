/* Authored visual worlds. Presentation is frozen with the reviewed lesson;
 * it never changes quantities, source pixels or the mathematical action. */
export const ADVENTURES=Object.freeze([
  {id:'garden',name:'Garden Picnic',description:'Paper-cut hills and a picnic delivery.',sky:'#EAF4DD',floor:'#E9D8B4',ink:'#293E38',accent:'#367970',soft:'#D8E9CA',edge:'#B7CDA9',cart:'#D6B986',inside:'#FFF2D4',trim:'#967A4D',paper:'#FAF8EE',badge:'#E9E1F3'},
  {id:'workshop',name:'Maker Workshop',description:'A cozy making room and a sharing cart.',sky:'#F6E6D2',floor:'#D9B792',ink:'#443A35',accent:'#A2563F',soft:'#EDD5B6',edge:'#D8B28B',cart:'#B77D62',inside:'#FFF1DB',trim:'#825543',paper:'#FFF9EF',badge:'#F1DDD3'},
  {id:'ocean',name:'Ocean Discovery',description:'Flowing water and an underwater picture trail.',sky:'#DAF2F3',floor:'#E8DABB',ink:'#24454E',accent:'#277D8D',soft:'#B5DFDE',edge:'#99CED0',cart:'#79AFAD',inside:'#F4F4D8',trim:'#477E84',paper:'#F3FBFA',badge:'#D5EAF3'},
  {id:'moon',name:'Moon Station',description:'A moon base, a rover cart and a shape portal.',sky:'#263C63',floor:'#8291AE',ink:'#223651',accent:'#476DA1',soft:'#455D86',edge:'#6984AC',cart:'#90A6C9',inside:'#F2F5FD',trim:'#4A638A',paper:'#F4F6FD',badge:'#DDE3F5'}
].map(x=>Object.freeze(x)));
const ids=ADVENTURES.map(x=>x.id);
const preferred={addition:['garden','workshop','moon','ocean'],subtraction:['workshop','garden','ocean','moon'],counting:['ocean','garden','workshop','moon'],shape:['moon','workshop','ocean','garden']};
export function questionSeed(spec){const value=JSON.stringify([spec.type,spec.a??spec.count??spec.shape,spec.b??spec.shape_task??'']);let h=2166136261;for(const c of value)h=Math.imul(h^c.charCodeAt(0),16777619);return h>>>0;}
export function suggestAdventure(spec,previous=null){const list=preferred[spec.type];if(!list)throw new Error('Choose a supported lesson before its adventure.');const seed=questionSeed(spec),index=seed%4<2?0:1+seed%3;const chosen=list[index];return chosen===previous?list.find(id=>id!==previous):chosen;}
export function normalizePresentation(spec,value=null){
  if(value!==null&&(!value||typeof value!=='object'||Array.isArray(value)))throw new Error('Choose a supported adventure.');
  const theme=value?.theme??'auto',motion=value?.motion??'story';
  if(theme!=='auto'&&!ids.includes(theme))throw new Error('Choose one of the four story worlds.');
  if(!['story','calm'].includes(motion))throw new Error('Choose story motion or gentle motion.');
  return {version:1,theme:theme==='auto'?suggestAdventure(spec):theme,motion,seed:questionSeed(spec)};
}
export function adventureFor(plan){const presentation=normalizePresentation(plan.spec,plan.presentation??null);return ADVENTURES.find(x=>x.id===presentation.theme);}
export function adventureStory(spec,objects,presentation){
  const world=ADVENTURES.find(x=>x.id===presentation.theme),noun=objects?'worksheet pictures':'story stars';
  const action={addition:'Delivery',subtraction:'Sharing',counting:'Discovery',shape:'Shape Gate'}[spec.type];
  const goal=spec.type==='addition'?`Help your buddy collect ${noun} for a delivery in ${world.name}.`:
    spec.type==='subtraction'?`Help your buddy share ${noun} with a friend, then count what remains.`:
    spec.type==='counting'?`Explore ${world.name} and visit each ${objects?'worksheet picture':'story star'} exactly once.`:
    `Explore the ${world.name.toLowerCase()} gate. ${spec.shape_task==='name'?'Name its shape':spec.shape==='circle'?'Inspect its curved outline':'Follow its straight sides'} to open it.`;
  return {id:`${objects?'worksheet':'story'}-${world.id}`,title:`${world.name}: ${action}`,goal,
    role:{addition:'Collector and careful counter',subtraction:'Sharing helper and careful counter',counting:'Explorer and picture counter',shape:'Shape explorer and gate opener'}[spec.type],
    summary:spec.type==='addition'?`Start with ${spec.a} ${noun}. Carry ${spec.b} more into the wagon, one at a time.`:
      spec.type==='subtraction'?`Start with ${spec.a} ${noun}. Give ${spec.b} to a friend, then count only those left.`:goal};
}
export function adventureAudioKey(key,plan){
  const theme=plan.presentation.theme,objects=plan.objects;
  if(key==='story-intro'||key==='object-story-intro')return `adventure-${theme}-intro`;
  const map={'story-add-goal':'adventure-add-goal','story-sub-goal':'adventure-sub-goal','story-count-goal':'adventure-count-goal',
    'story-shape-goal':'adventure-shape-goal','story-shape-name-goal':'adventure-shape-name-goal','story-turn-count':'adventure-turn-count','story-turn-name':'adventure-turn-name',
    'object-add-goal':'adventure-object-add-goal','object-count-goal':'adventure-object-count-goal','object-turn-count':'adventure-object-turn-count'};
  if(map[key])return map[key];
  if(!objects&&key?.startsWith('story-answer-count-'))return key.replace('story-answer-count-','adventure-answer-count-');
  return key;
}

function oval(ctx,x,y,rx,ry,fill){ctx.beginPath();ctx.ellipse(x,y,rx,ry,0,0,Math.PI*2);ctx.fillStyle=fill;ctx.fill();}
function box(ctx,x,y,w,h,r,fill,stroke=null){ctx.beginPath();ctx.roundRect(x,y,w,h,r);ctx.fillStyle=fill;ctx.fill();if(stroke){ctx.strokeStyle=stroke;ctx.lineWidth=2;ctx.stroke();}}
/* Scenery deliberately avoids spare countable tokens inside the lesson area. */
export function drawAdventureBackground(ctx,state,theme){
  const calm=state.presentation.motion==='calm',time=calm?0:state.phase==='pause'?state.scene.start:state.time;
  ctx.fillStyle=theme.paper;ctx.fillRect(0,0,1280,720);
  box(ctx,34,112,1212,391,30,theme.sky,theme.edge);
  ctx.save();ctx.beginPath();ctx.roundRect(35,113,1210,389,29);ctx.clip();
  if(theme.id==='garden'){
    oval(ctx,300+Math.sin(time*.13)*5,493,490,173,theme.soft);oval(ctx,1105,527,560,175,'#CAE1BD');
    oval(ctx,136+Math.sin(time*.17)*9,157,92,18,'#FFFFFFA0');oval(ctx,1020-Math.sin(time*.14)*8,162,113,20,'#FFFFFF90');
    box(ctx,82,289,16,137,8,'#A5BC83');oval(ctx,89,262,49,62,'#A0C294');oval(ctx,54,281,35,43,'#B8D2A2');oval(ctx,123,285,34,45,'#B8D2A2');
  }else if(theme.id==='workshop'){
    box(ctx,66,138,154,159,24,'#FFF8E8','#CDA878');box(ctx,79,151,128,133,18,'#E1EBDA');
    ctx.strokeStyle='#C9AC87';ctx.lineWidth=9;ctx.beginPath();ctx.moveTo(144,148);ctx.lineTo(144,287);ctx.moveTo(77,216);ctx.lineTo(210,216);ctx.stroke();
    box(ctx,253,139,795,48,16,'#E2C6A4');box(ctx,1082,138,118,154,20,'#F8EDD9','#D6B58C');
    ctx.strokeStyle='#D9BC98';ctx.lineWidth=3;for(const y of [202,218,234]){ctx.beginPath();ctx.moveTo(1102,y);ctx.lineTo(1181,y);ctx.stroke();}
    box(ctx,47,314,1200,190,12,'#EACAA7');
  }else if(theme.id==='ocean'){
    ctx.fillStyle='#EFFDFB70';ctx.beginPath();ctx.moveTo(199,113);ctx.lineTo(336,113);ctx.lineTo(586,480);ctx.lineTo(371,480);ctx.closePath();ctx.fill();
    ctx.strokeStyle='#A0D7D8';ctx.lineWidth=5;ctx.beginPath();for(let x=40;x<=1250;x+=10){const y=210+Math.sin(x/155+time*.18)*12;x===40?ctx.moveTo(x,y):ctx.lineTo(x,y);}ctx.stroke();
    oval(ctx,250,520,500,122,'#C3E5DC');oval(ctx,1058,511,560,110,'#AAD7D3');
    ctx.strokeStyle='#67AAA1';ctx.lineWidth=15;ctx.lineCap='round';for(const x of [74,1200]){ctx.beginPath();ctx.moveTo(x,478);ctx.bezierCurveTo(x-27,405,x+22,367,x+Math.sin(time*.7)*6,307);ctx.stroke();}
  }else{
    oval(ctx,1080,181,196,94,'#405983');oval(ctx,1109,167,114,67,'#7790B5');oval(ctx,1082,155,27,14,'#647FA4');
    ctx.strokeStyle='#728CAE';ctx.lineWidth=2;ctx.beginPath();ctx.ellipse(1080,181,221,66,-.23,0,Math.PI*2);ctx.stroke();
    ctx.strokeStyle='#45608A';ctx.lineWidth=1;for(let x=80;x<1230;x+=110){ctx.beginPath();ctx.moveTo(x,300);ctx.lineTo(640+(x-640)*1.7,505);ctx.stroke();}
    box(ctx,61,143,153,126,23,'#3D567B','#7D96B8');box(ctx,75,157,125,98,17,'#AEC4D9');
    oval(ctx,640,520,730,93,'#6E809F');
  }
  oval(ctx,659,513,687,59,theme.floor);
  ctx.strokeStyle=theme.trim+'65';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(55,477);ctx.lineTo(1230,477);ctx.stroke();ctx.restore();
}

export function sceneDirection(plan,time){
  const presentation=normalizePresentation(plan.spec,plan.presentation??null),scene=plan.scenes.find(s=>time<s.end)||plan.scenes.at(-1);
  const t=scene.phase==='pause'?scene.start:time,fade=Math.min(1,Math.max(0,t/3));
  return {presentation,camera:{scale:presentation.motion==='calm'?1:1+fade*(.016+.005*Math.sin(t*.22)),x:presentation.motion==='calm'?0:Math.sin(t*.14)*1.5,y:0}};
}
