import {ADVENTURES} from './modules/adventures.js';
import {planLesson,renderLessonFrame,createLessonPlayer,videoExportSupport} from './modules/lesson.js';
import {PRESETS,prepareCharacter} from './modules/character.js';
import {decodeAuthoredPicture} from './modules/picture.js';
import {suggestWorksheetObjects,prepareWorksheetObjects} from './modules/objects.js';
const $=id=>document.getElementById(id),hero={source:'builder',name:'Nova',design:PRESETS[0].design};
const examples=[{theme:'garden',spec:{type:'addition',a:5,b:2},label:'5 + 2 · original worksheet popsicles'},{theme:'workshop',spec:{type:'subtraction',a:5,b:2},label:'5 − 2 · sharing with a friend'},{theme:'ocean',spec:{type:'counting',count:6},label:'Count six · visit each story star once'},{theme:'moon',spec:{type:'shape',shape:'triangle',shape_task:'sides'},label:'Triangle · trace the shape gate'}];
let player=null,active=null,controller=null,generation=0,savedURL=null,objectPack=null;
const stamp=t=>`${Math.floor(t/60)}:${String(Math.floor(t%60)).padStart(2,'0')}`;
function controls(disabled){for(const id of ['demo-play','demo-pause','demo-restart','demo-download','demo-seek','demo-calm'])$(id).disabled=disabled;for(const button of document.querySelectorAll('[data-example]'))button.disabled=disabled;}
function buildPlan(example){return planLesson(example.spec,{objects:example.theme==='garden'?objectPack:null,presentation:{theme:example.theme,motion:$('demo-calm').checked?'calm':'story'}});}
async function openExample(example){
  if(controller)return;active=example;const request=++generation;const plan=buildPlan(example);if(player)void player.dispose();player=null;controls(true);$('demo-status').textContent='Preparing the narrated adventure…';$('demo-watch').hidden=false;
  const pending=createLessonPlayer($('demo-canvas'),plan,hero,{onProgress:(fraction,seconds)=>{$('demo-seek').value=fraction*100;$('demo-time').textContent=`${stamp(seconds)} / ${stamp(plan.duration)}`;},onError:error=>$('demo-status').textContent=error.message});
  try{const ready=await pending;if(request!==generation){await ready.dispose();return;}player=ready;$('demo-title').textContent=plan.story.title;$('demo-goal').textContent=plan.story.goal;$('demo-time').textContent=`0:00 / ${stamp(plan.duration)}`;controls(false);$('demo-download').disabled=!videoExportSupport().supported;$('demo-status').textContent='The question, objects and spoken counts stay consistent in this world.';$('demo-watch').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});await player.play();}
  catch(error){$('demo-status').textContent=error.message;controls(false);}
}
async function record(){
  if(!player||controller)return;const current=player;controller=new AbortController();controls(true);$('demo-cancel').hidden=false;$('demo-status').textContent='Recording with sound. Keep this tab visible.';
  try{const result=await current.exportVideo({signal:controller.signal,onProgress:p=>$('demo-status').textContent=`Recording with sound… ${Math.round(p*100)}%. Keep this tab visible.`});if(savedURL)URL.revokeObjectURL(savedURL);savedURL=URL.createObjectURL(result.blob);const a=document.createElement('a');a.href=savedURL;a.download=`lesson-buddy-${active.theme}.${result.extension}`;a.textContent=`Save ${ADVENTURES.find(x=>x.id===active.theme).name} video`;a.id='demo-finished-download';$('demo-status').replaceChildren('Your narrated video is ready. ',a);a.click();}
  catch(error){$('demo-status').textContent=error.message;}finally{controller=null;controls(false);$('demo-cancel').hidden=true;}
}
async function init(){
  $('demo-calm').checked=matchMedia('(prefers-reduced-motion: reduce)').matches;await prepareCharacter(hero);
  const response=await fetch('assets/popsicles.png');if(!response.ok)throw new Error('The original worksheet could not load.');const image=await decodeAuthoredPicture(await response.blob());const extracted=await suggestWorksheetObjects(image,7);if(!extracted.pack)throw new Error('The example source objects could not be prepared.');objectPack=extracted.pack;await prepareWorksheetObjects(objectPack);
  for(const example of examples){const world=ADVENTURES.find(x=>x.id===example.theme),plan=buildPlan(example),article=document.createElement('article');article.className='adventure-example';const canvas=document.createElement('canvas');canvas.width=960;canvas.height=540;canvas.setAttribute('aria-label',`${world.name}: ${example.label}`);canvas.setAttribute('role','img');const scene=plan.scenes.find(s=>['count_b','remove_count','count_all','count_side'].includes(s.phase))||plan.scenes[0];renderLessonFrame(canvas,plan,hero,scene.start+scene.duration*.45);const content=document.createElement('div'),heading=document.createElement('h2'),copy=document.createElement('p'),button=document.createElement('button');heading.textContent=world.name;copy.textContent=example.label;button.type='button';button.className='button primary small';button.dataset.example=example.theme;button.textContent=`Play ${world.name}`;button.addEventListener('click',()=>void openExample(example));content.append(heading,copy,button);article.append(canvas,content);$('adventure-examples').append(article);}
  $('demo-loading').hidden=true;
  $('demo-play').addEventListener('click',()=>player?.play().catch(e=>$('demo-status').textContent=e.message));$('demo-pause').addEventListener('click',()=>player?.pause());$('demo-restart').addEventListener('click',()=>{if(player){player.seek(0);void player.play();}});$('demo-seek').addEventListener('input',()=>{if(player)player.seek(player.plan.duration*Number($('demo-seek').value)/100);});$('demo-download').addEventListener('click',()=>void record());$('demo-cancel').addEventListener('click',()=>controller?.abort());$('demo-calm').addEventListener('change',()=>{if(active)void openExample(active);});
}
init().catch(error=>{$('demo-loading').textContent=error.message;});
