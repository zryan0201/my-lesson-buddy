import {DEFAULT_DESIGN,PRESETS,OPTIONS,normalizeDesign,prepareCharacter,drawCharacter,characterAnchors,characterPreview,DrawingPad} from './modules/character.js';
import {listCharacters,saveCharacter,normalizeName,imageFileToDataURL,readPackage,makePackage,downloadBlob} from './modules/library.js';
import {browserReaderStatus,readWorksheet,disposeWorksheetReader} from './modules/reader.js';
import {planLesson,createLessonPlayer,videoExportSupport,renderLessonFrame} from './modules/lesson.js';
import {PictureLoader,decodeAuthoredPicture} from './modules/picture.js';
import {suggestWorksheetObjects,cropWorksheetObject,normalizeWorksheetObjects,prepareWorksheetObjects} from './modules/objects.js';
import {processWorksheetPhoto} from './modules/photo.js';
import {validateCorners} from './modules/photo-geometry.js';
import {ADVENTURES,suggestAdventure} from './modules/adventures.js';

const $=id=>document.getElementById(id);
const clone=value=>structuredClone(value);
const state={step:'character',mode:'build',design:clone(PRESETS[0]?.design||DEFAULT_DESIGN),name:'Nova',drawing:null,live:null,motion:'idle',library:[],selected:null,picture:null,pictureOrigin:null,pictureLoading:false,pictureVersion:0,readerSupported:false,reading:null,review:null,player:null,preparing:null,exporting:null,savedVideoURL:null,aiLoaded:false,previewVersion:0};
let pad,draftTimer,noticeTimer,cropView=null,photoView=null;
const EXAMPLES={addition:{image:'popsicles.png',spec:{type:'addition',a:5,b:2},label:'Popsicle math · included example'},subtraction:{image:'stars.svg',spec:{type:'subtraction',a:8,b:3},label:'Stars to share · included example'},counting:{image:'counting.svg',spec:{type:'counting',count:6},label:'Count with me · included example'},shape:{image:'triangle.svg',spec:{type:'shape',shape:'triangle',shape_task:'sides'},label:'Shape explorer · included example'},photo:{image:'worksheet-photo-demo.jpg',spec:{type:'addition',a:5,b:2},label:'Simulated worksheet photo · included example',photo:true}};
let adventureChoice='auto',gentleMotion=matchMedia('(prefers-reduced-motion: reduce)').matches;
function previousAdventure(){try{return localStorage.getItem('lesson-buddy-last-adventure-v1');}catch{return null;}}
function lessonPresentation(spec){return{theme:adventureChoice==='auto'?suggestAdventure(spec,previousAdventure()):adventureChoice,motion:gentleMotion?'calm':'story'};}

function notice(message,error=false){clearTimeout(noticeTimer);$('notice').textContent=message;$('notice').classList.toggle('error',error);$('notice').hidden=false;noticeTimer=setTimeout(()=>$('notice').hidden=true,error?18000:9000);}
function safePreviewName(){try{return normalizeName(state.name);}catch{return 'My buddy';}}
function currentDraft(){return state.mode==='build'?{id:'draft-builder',name:safePreviewName(),source:'builder',design:{...state.design,name:safePreviewName()}}:{id:'draft-drawing',name:safePreviewName(),source:'drawing',image:state.drawing};}
function setBusy(button,busy,label){if(!button.dataset.normal)button.dataset.normal=button.textContent;button.disabled=busy;button.textContent=busy?label:button.dataset.normal;}
function invalidateReview(){state.review=null;state.preparing=null;cropView=null;$('object-crop-panel').hidden=true;$('adult-confirm').checked=false;$('make-lesson').disabled=true;if(state.player){void state.player.dispose?.();state.player=null;}if(state.savedVideoURL){URL.revokeObjectURL(state.savedVideoURL);state.savedVideoURL=null;}$('export-status').replaceChildren();$('export-status').hidden=true;}
function watchControls(disabled){for(const id of ['play-video','pause-video','restart-video','lesson-seek','export-video','new-lesson'])$(id).disabled=disabled;}
function rememberDraft(){clearTimeout(draftTimer);draftTimer=setTimeout(()=>{try{localStorage.setItem('lesson-buddy-draft-v1',JSON.stringify({mode:state.mode,design:state.design,name:state.name,drawing:state.drawing}));$('draft-note').textContent='Draft saved on this browser';}catch{$('draft-note').textContent='Save or download your work before closing.';}},350);}
async function updatePreview(){
  const version=++state.previewVersion;const character=currentDraft();
  $('preview-name').textContent=state.name.trim()||'my friend';$('name-count').textContent=`${[...state.name].length} / 32`;
  $('save-use').disabled=state.mode==='draw'&&!state.drawing;
  $('motion-note').textContent=state.mode==='draw'?'Your original drawing moves into the story and carries props. Its lines stay yours.':'Your buddy becomes the hero: moving, carrying, sharing, and exploring.';
  if(!character.image&&character.source==='drawing'){state.live=null;return;}
  try{await prepareCharacter(character);if(version===state.previewVersion)state.live=character;}catch(error){if(version===state.previewVersion){state.live=null;notice(error.message,true);}}
}
function setMode(mode){state.mode=mode;for(const option of ['draw','build']){$(`mode-${option}`).setAttribute('aria-selected',String(option===mode));$(`${option}-panel`).hidden=option!==mode;}void updatePreview();rememberDraft();}
function syncDesignControls(){for(const [field] of Object.entries(OPTIONS))$(`part-${field}`).value=state.design[field];for(const field of ['primary_color','secondary_color','accent_color','skin_color'])$(`color-${field}`).value=state.design[field];$('buddy-name').value=state.name;void updatePreview();}
function populateBuilder(){
  for(const [field,choices] of Object.entries(OPTIONS)){
    const labels={body_type:'Body',head_shape:'Face shape',eyes:'Eyes',headwear:'Head & mask',chest:'Chest symbol',back:'Cape & wings',gloves:'Hands & gloves',boots:'Boots'};
    const label=document.createElement('label');label.className='part-field';label.textContent=labels[field];
    const select=document.createElement('select');select.id=`part-${field}`;select.setAttribute('aria-label',labels[field]);
    for(const choice of choices){const option=document.createElement('option');option.value=choice.value;option.textContent=choice.label;select.append(option);}
    select.addEventListener('change',()=>{state.design[field]=select.value;void updatePreview();rememberDraft();});label.append(select);$('part-controls').append(label);
  }
  for(const [field,labelText] of [['primary_color','Main color'],['secondary_color','Second color'],['accent_color','Little details'],['skin_color','Face color']]){
    const label=document.createElement('label');label.className='color-field';const color=document.createElement('input');color.type='color';color.id=`color-${field}`;color.setAttribute('aria-label',labelText);
    color.addEventListener('input',()=>{state.design[field]=color.value;void updatePreview();rememberDraft();});const span=document.createElement('span');span.textContent=labelText;label.append(color,span);$('color-controls').append(label);
  }
  for(const preset of PRESETS){const button=document.createElement('button');button.className='preset';button.type='button';button.setAttribute('aria-label',`Start with ${preset.name}`);
    const image=document.createElement('img');image.alt='';image.width=73;image.height=83;void characterPreview({source:'builder',design:preset.design,name:preset.design.name},{width:120,height:140}).then(url=>image.src=url);
    const label=document.createElement('span');label.textContent=preset.name;button.append(image,label);button.addEventListener('click',()=>{state.design=clone(preset.design);state.name=state.design.name;syncDesignControls();rememberDraft();});$('presets').append(button);
  }
}
function updateDrawingControls(){
  $('undo').disabled=!pad.canUndo();$('redo').disabled=!pad.canRedo();$('draw-hint').hidden=pad.hasDrawing();
  state.drawing=pad.hasDrawing()?pad.getPNG():null;void updatePreview();rememberDraft();
}
function confirmAction(message,title='Start a fresh drawing?'){
  return new Promise(resolve=>{const dialog=$('confirm-dialog'),previous=document.activeElement;$('confirm-title').textContent=title;$('confirm-message').textContent=message;
    let done=false;const finish=value=>{if(done)return;done=true;dialog.close();$('confirm-cancel').removeEventListener('click',cancel);$('confirm-continue').removeEventListener('click',accept);dialog.removeEventListener('cancel',escape);previous?.focus();resolve(value);};
    const cancel=()=>finish(false),accept=()=>finish(true),escape=event=>{event.preventDefault();finish(false);};
    $('confirm-cancel').addEventListener('click',cancel);$('confirm-continue').addEventListener('click',accept);dialog.addEventListener('cancel',escape);dialog.showModal();$('confirm-cancel').focus();
  });
}
function chosenBuddy(container){
  container.replaceChildren();if(!state.selected)return;
  const image=document.createElement('img');image.src=state.selected.preview||'';image.alt='';
  const content=document.createElement('div');const name=document.createElement('strong');name.textContent=state.selected.name;
  const description=document.createElement('p');description.textContent='Your very own learning buddy';const change=document.createElement('button');change.textContent='Choose a different buddy';change.addEventListener('click',()=>go('character'));
  content.append(name,description,change);container.append(image,content);
}
function go(step){
  if(state.exporting){notice('Finish or cancel the video download before changing steps.');return false;}
  if(state.preparing&&step!=='watch'){notice('Your buddy’s adventure is getting ready. Please wait a moment.');return false;}
  if(step!=='character'&&!state.selected){notice('Create or choose a buddy first.');step='character';}
  if(['review','watch'].includes(step)&&!state.review){notice('Check the worksheet question first.');step='worksheet';}
  if(step==='watch'&&!state.player&&!state.preparing){notice('A grown-up needs to check the lesson before making the video.');step='review';}
  if(step!=='worksheet'){state.reading?.abort();disposeWorksheetReader();}
  if(step!=='watch'&&state.player?.playing)state.player.pause();
  state.step=step;document.querySelectorAll('[data-screen]').forEach(section=>section.hidden=section.dataset.screen!==step);
  const order=['character','worksheet','review','watch'];for(const button of document.querySelectorAll('[data-go]')){button.classList.toggle('active',button.dataset.go===step);button.classList.toggle('done',order.indexOf(button.dataset.go)<order.indexOf(step));if(button.dataset.go===step)button.setAttribute('aria-current','step');else button.removeAttribute('aria-current');}
  if(step==='worksheet')chosenBuddy($('chosen-buddy'));
  if(step==='review')chosenBuddy($('review-buddy'));
  document.querySelector('.journey').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});
  return true;
}
async function selectBuddy(character){const request=state.selectionVersion=(state.selectionVersion||0)+1;invalidateReview();try{await prepareCharacter(character);}catch(error){if(request===state.selectionVersion)throw error;return;}if(request!==state.selectionVersion)return;state.selected=clone(character);go('worksheet');notice(`${character.name} is ready. Add a worksheet or choose an example.`);}
async function refreshLibrary(){
  try{state.library=await listCharacters();renderLibrary();}catch(error){$('library').textContent=error.message;notice(error.message,true);}
}
function renderLibrary(){
  const search=$('library-search').value.toLocaleLowerCase().trim();const matches=state.library.filter(c=>c.name.toLocaleLowerCase().includes(search));const library=$('library');library.replaceChildren();$('library-count').textContent=`${matches.length} of ${state.library.length}`;
  if(!matches.length){const empty=document.createElement('p');empty.className='library-empty';empty.textContent=search?'No buddies with that name yet. Try another name.':'Your story starts here. Save a buddy or import a character package.';library.append(empty);return;}
  for(const character of matches){
    const card=document.createElement('article');card.className='library-card';const image=document.createElement('img');image.src=character.preview;image.alt=character.name;image.loading='lazy';
    const heading=document.createElement('h3');heading.textContent=character.name;const note=document.createElement('p');note.textContent=character.imported?'Imported artwork · original lines preserved':character.source==='builder'?'Mixed & matched by you':'Drawn with imagination';
    const use=document.createElement('button');use.className='button primary';use.textContent='Use in my lesson →';use.setAttribute('aria-label',`Use ${character.name} in a lesson`);use.addEventListener('click',()=>selectBuddy(character).catch(error=>notice(error.message,true)));
    const tools=document.createElement('div');tools.className='library-tools';
    const edit=document.createElement('button');edit.textContent='Edit a copy';edit.addEventListener('click',async()=>{
      if(!await confirmAction('Open an editable copy? Save your current buddy first if you want it in your collection. Your earlier saved characters stay safe.','Open a copy to edit?'))return;
      state.name=character.name;$('buddy-name').value=state.name;
      if(character.design){state.design=normalizeDesign({...character.design,name:state.name});syncDesignControls();setMode('build');}
      else{try{await pad.load(character.image);setMode('draw');}catch(error){notice(error.message,true);return;}}
      go('character');notice('You are editing a copy. Saving will create a new character.');
    });
    const twin=document.createElement('button');twin.textContent='Make a twin';twin.addEventListener('click',async()=>{try{setBusy(twin,true,'Saving…');const saved=await saveCharacter(character);await refreshLibrary();notice(`${saved.name} has a new twin. The original stays safe.`);}catch(error){notice(error.message,true);}finally{setBusy(twin,false);}});
    const download=document.createElement('button');download.textContent='Package ↓';download.addEventListener('click',async()=>{try{setBusy(download,true,'Preparing…');downloadBlob(await makePackage(character),`${character.name.replace(/[^\p{L}\p{N}-]/gu,'_')}.character.zip`);}catch(error){notice(error.message,true);}finally{setBusy(download,false);}});
    tools.append(edit,twin,download);card.append(image,heading,note,use,tools);library.append(card);
  }
}
function updatePictureControls(){
  const busy=state.pictureLoading||state.photoEditorOpen;
  const check=$('question-form').querySelector('button[type="submit"]');
  if(check)check.disabled=busy;
  $('read-picture').disabled=busy||Boolean(state.reading)||!state.readerSupported||!state.picture;
  for(const id of ['photo-auto','photo-corners','photo-use-original','photo-shadows'])$(id).disabled=state.pictureLoading||!state.originalPicture;
  if(!state.reading)$('read-picture').textContent=state.aiLoaded?'Read this picture with AI':'Download AI & read picture';
}
function cancelPictureReading(){
  const controller=state.reading;state.reading=null;controller?.abort();disposeWorksheetReader();
  $('cancel-reading').hidden=true;setBusy($('read-picture'),false);updatePictureControls();
}
const pictureLoader=new PictureLoader({
  onStart(version){
    state.pictureLoading=true;state.pictureVersion=version;cancelPictureReading();
    state.picture=null;state.pictureOrigin=null;state.originalPicture=null;state.photo=null;state.photoEditorOpen=false;state.photoEditVersion=(state.photoEditVersion||0)+1;photoView=null;$('photo-panel').hidden=true;$('photo-corners-panel').hidden=true;invalidateReview();
    $('reader-progress-wrap').hidden=true;
    $('worksheet-image').hidden=true;$('worksheet-image').removeAttribute('src');
    $('worksheet-placeholder').textContent='Getting your new picture ready…';$('worksheet-placeholder').hidden=false;
    $('worksheet-source').textContent='Loading a new worksheet picture…';
    fillQuestion(null,'Getting your new picture ready. The previous question is no longer selected.');
    updatePictureControls();
  },
  onCommit(prepared,{label,spec=null,origin='manual'}){
    const dataURL=typeof prepared==='string'?prepared:prepared.image;
    state.picture=dataURL;state.pictureOrigin=origin;
    state.pictureLabel=label;
    state.originalPicture=typeof prepared==='string'?dataURL:prepared.original;
    state.photo=typeof prepared==='string'?null:prepared.photo;state.photoShadows=typeof prepared==='string'?true:prepared.reduceShadows!==false;
    $('worksheet-image').src=dataURL;$('worksheet-image').hidden=false;$('worksheet-placeholder').hidden=true;$('worksheet-source').textContent=label;
    renderPhotoPanel();
    fillQuestion(spec,origin==='example'?'Included example · please check it together.':'Your picture is ready. Use the optional AI reader, or enter what you see.');
  },
  onError(error){
    $('worksheet-placeholder').textContent='This picture could not be opened. Choose another picture, or enter a question together.';
    $('worksheet-source').textContent='No worksheet picture selected';
    fillQuestion(null,'Choose another picture, or enter the question you want to explore.');
    notice(error.message,true);
  },
  onFinish(version){if(state.pictureVersion===version){state.pictureLoading=false;updatePictureControls();}}
});
const FULL_PAPER=[{x:0,y:0},{x:1,y:0},{x:1,y:1},{x:0,y:1}];
async function preparePhoto(original,{corners=null,reduceShadows=true,signal}={}){
  try{const photo=await processWorksheetPhoto(original,{corners,reduceShadows,signal});return{image:photo.image,original,photo,reduceShadows};}
  catch(error){if(error.name==='AbortError')throw error;return{image:original,original,reduceShadows,photo:{status:'needs-corners',detected:false,corners:clone(FULL_PAPER),image:original,message:'This photo could not be prepared automatically. Adjust the paper edges, use the original, or take a clearer photo.',steps:{cropped:false,perspective:false,shadows:false}}};}
}
function showPhotoVersion(version){
  if(!state.photo||!state.picture)return;
  const original=version==='original';$('worksheet-image').src=original?state.originalPicture:state.picture;
  $('photo-view-original').setAttribute('aria-pressed',String(original));$('photo-view-prepared').setAttribute('aria-pressed',String(!original));
  $('photo-view-note').textContent=original?'Original photo for comparison. Choose “Use original photo” to use this version.':'This worksheet preview is used for reading and extracting the pictures.';
}
function renderPhotoPanel(){
  $('photo-panel').hidden=!state.photo;if(!state.photo)return;
  $('photo-panel').dataset.status=state.photo.status;$('photo-status').textContent=state.photo.message;
  $('photo-shadows').checked=state.photoShadows!==false;$('photo-view-prepared').textContent=state.photo.status==='needs-corners'?'Worksheet preview':'Prepared worksheet';showPhotoVersion('prepared');
}
function photoQuestionSnapshot(){try{return planLesson(getQuestion()).spec;}catch{return null;}}
function runPhotoCorrection({corners=null}={}){
  if(!state.originalPicture||state.pictureLoading)return;
  const original=state.originalPicture,reduceShadows=$('photo-shadows').checked;
  const metadata={label:state.pictureLabel||'Your worksheet photo · check the prepared view',spec:photoQuestionSnapshot(),origin:state.pictureOrigin||'manual'};
  void pictureLoader.load(({signal})=>preparePhoto(original,{corners,reduceShadows,signal}),metadata);
}
function useOriginalPhoto(){
  if(!state.originalPicture||state.pictureLoading)return;
  const original=state.originalPicture,previous=state.photo;
  const prepared={image:original,original,reduceShadows:false,photo:{...previous,image:original,status:'unchanged',message:'You chose the original photo. This version will be used for reading and choosing the worksheet objects.',steps:{cropped:false,perspective:false,shadows:false}}};
  void pictureLoader.load(()=>Promise.resolve(prepared),{label:state.pictureLabel||'Your original worksheet photo',spec:photoQuestionSnapshot(),origin:state.pictureOrigin||'manual'});
}
function closePhotoCorners(){
  state.photoEditVersion=(state.photoEditVersion||0)+1;state.photoEditorOpen=false;photoView=null;$('photo-corners-panel').hidden=true;renderPhotoPanel();updatePictureControls();
}
function paintPhotoCorners(){
  if(!photoView||!state.photoEditorOpen)return;
  const canvas=$('photo-corners-canvas'),ctx=canvas.getContext('2d'),w=canvas.width,h=canvas.height;
  ctx.drawImage(photoView.image,0,0,w,h);ctx.beginPath();ctx.rect(0,0,w,h);photoView.points.forEach((p,i)=>i?ctx.lineTo(p.x*w,p.y*h):ctx.moveTo(p.x*w,p.y*h));ctx.closePath();ctx.fillStyle='#173e3560';ctx.fill('evenodd');
  ctx.beginPath();photoView.points.forEach((p,i)=>i?ctx.lineTo(p.x*w,p.y*h):ctx.moveTo(p.x*w,p.y*h));ctx.closePath();ctx.strokeStyle='#27a68a';ctx.lineWidth=Math.max(2,w/260);ctx.stroke();
  const radius=Math.max(9,w/65);for(const [i,p] of photoView.points.entries()){ctx.beginPath();ctx.arc(p.x*w,p.y*h,radius,0,Math.PI*2);ctx.fillStyle='#fffdf1';ctx.fill();ctx.strokeStyle='#22745f';ctx.lineWidth=Math.max(2,w/340);ctx.stroke();ctx.fillStyle='#245d4d';ctx.font=`700 ${radius*1.25}px system-ui`;ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(String(i+1),p.x*w,p.y*h);for(const axis of ['x','y']){const field=$(`paper-${i}-${axis}`);if(document.activeElement!==field)field.value=String(Math.round(p[axis]*1000)/10);}}
}
async function openPhotoCorners(){
  if(!state.originalPicture||state.pictureLoading)return;
  const original=state.originalPicture,version=state.pictureVersion,request=state.photoEditVersion=(state.photoEditVersion||0)+1;
  const points=clone(state.photo?.corners||FULL_PAPER);state.photoEditorOpen=true;invalidateReview();cancelPictureReading();$('photo-corners-panel').hidden=false;updatePictureControls();
  $('photo-corners-help').textContent='Keep the complete question inside the four corners.';
  try{
    const image=await new Promise((resolve,reject)=>{const i=new Image();i.onload=()=>resolve(i);i.onerror=()=>reject(new Error('The original photo could not open. Choose the picture again.'));i.src=original;});
    if(state.photoEditVersion!==request||state.pictureVersion!==version||!state.photoEditorOpen)return;
    const canvas=$('photo-corners-canvas'),scale=Math.min(1,960/Math.max(image.naturalWidth,image.naturalHeight));canvas.width=Math.round(image.naturalWidth*scale);canvas.height=Math.round(image.naturalHeight*scale);
    photoView={image,points,version,request,drag:null};paintPhotoCorners();canvas.scrollIntoView({behavior:'smooth',block:'center'});
  }catch(error){if(state.photoEditVersion===request){closePhotoCorners();notice(error.message,true);}}
}
function applyPhotoCorners(){
  if(!photoView||!state.photoEditorOpen||photoView.version!==state.pictureVersion)return;
  try{const points=Array.from({length:4},(_,i)=>Object.fromEntries(['x','y'].map(axis=>{const value=$(`paper-${i}-${axis}`).value.trim();if(value==='')throw new Error('Enter every corner position before straightening the paper.');return[axis,Number(value)/100];})));const corners=validateCorners(points,{width:photoView.image.naturalWidth,height:photoView.image.naturalHeight});runPhotoCorrection({corners});}
  catch(error){$('photo-corners-help').textContent=error.message;}
}
async function dataURLForAsset(file,{signal}={}){
  const response=await fetch(new URL(`./assets/${file}`,import.meta.url),{signal});
  if(!response.ok)throw new Error('The example picture could not load.');
  return decodeAuthoredPicture(await response.blob(),{signal});
}

function fillQuestion(spec,message){
  $('question-type').value=spec?.type||'addition';$('number-a').value=spec?.type==='counting'?spec.count??'':spec?.a??'';$('number-b').value=spec?.b??'';
  if(spec?.shape)$('shape-name').value=spec.shape;
  $('shape-task').value=spec?.shape_task||'sides';$('question-origin').textContent=message;questionFields();invalidateReview();
}
function questionFields(){const type=$('question-type').value;$('operand-fields').hidden=type==='shape';$('shape-wrap').hidden=type!=='shape';$('shape-task-wrap').hidden=type!=='shape';$('b-wrap').hidden=type==='counting';$('operand-symbol').hidden=type==='counting';$('operand-symbol').textContent=type==='subtraction'?'−':'+';$('a-label').textContent=type==='counting'?'How many pictures?':'First group';}
function getQuestion(){
  const type=$('question-type').value;const quantity=(id)=>{const value=$(id).value.trim();if(!/^\d{1,2}$/.test(value))throw new Error('Enter the whole-number quantities you see in the worksheet.');return Number(value);};
  if(type==='shape')return{type,shape:$('shape-name').value,shape_task:$('shape-task').value};
  if(type==='counting')return{type,count:quantity('number-a')};return{type,a:quantity('number-a'),b:quantity('number-b')};
}
function reviewQuestion(){
  if(state.pictureLoading||state.photoEditorOpen)throw new Error('Finish preparing the worksheet photo before checking its question.');
  const spec=getQuestion();const plan=planLesson(spec,{presentation:lessonPresentation(spec)});
  const reviewed={plan,character:clone(state.selected),picture:state.picture,originalPhoto:state.photo?state.originalPicture:null,objectsReady:spec.type==='shape'||!state.picture,objectsLoading:false,objectsRequest:0,cropOpen:false,objectKey:`${state.pictureVersion}:${JSON.stringify(plan.spec)}`};state.review=reviewed;
  cropView=null;$('object-crop-panel').hidden=true;$('object-review').hidden=spec.type==='shape'||!state.picture;
  $('adult-confirm').checked=false;
  renderReviewedLesson(reviewed);go('review');
  if(!reviewed.objectsReady){
    if(state.objectChoice?.key===reviewed.objectKey)setReviewedObjects(reviewed,state.objectChoice.pack,state.objectChoice.selection);
    else void autoSelectObjects(reviewed);
  }
}
function objectQuantity(spec){return spec.type==='addition'?spec.a+spec.b:spec.type==='subtraction'?spec.a:spec.type==='counting'?spec.count:0;}
function updateAdultControls(){
  const ready=Boolean(state.review?.objectsReady&&!state.review.objectsLoading&&!state.review.cropOpen);
  $('adult-confirm').disabled=!ready;$('make-lesson').disabled=!ready||!$('adult-confirm').checked;
}
function renderReviewedLesson(reviewed){
  if(state.review!==reviewed)return;
  const {plan}=reviewed,spec=plan.spec;
  $('review-question').textContent=plan.question;$('review-answer').textContent=String(plan.answer);
  $('review-steps').replaceChildren(...(reviewed.objectsReady?plan.steps:['Choose and check the worksheet pictures to preview your buddy’s explanation.']).map(text=>{const li=document.createElement('li');li.textContent=text;return li;}));
  if(reviewed.objectsReady&&spec.type!=='shape'){const note=document.createElement('li');note.textContent=plan.representation;$('review-steps').append(note);}
  $('review-image').parentElement.hidden=!reviewed.picture;if(reviewed.picture)$('review-image').src=reviewed.picture;
  $('review-image').alt=reviewed.originalPhoto?'Prepared worksheet photo':'Original worksheet picture';$('review-photo-original').hidden=!reviewed.originalPhoto;if(reviewed.originalPhoto)$('review-original-image').src=reviewed.originalPhoto;else $('review-original-image').removeAttribute('src');
  $('story-review').hidden=!plan.story||!reviewed.objectsReady;
  if(plan.story&&reviewed.objectsReady){
    $('adventure-style').value=adventureChoice;$('gentle-motion').checked=gentleMotion;
    $('adventure-description').textContent=`${ADVENTURES.find(x=>x.id===plan.presentation.theme).description} ${adventureChoice==='auto'?'A fresh world is suggested for your next lesson.':''}`;
    $('story-review-title').textContent=`${reviewed.character.name} · ${plan.story.title}`;
    $('story-review-goal').textContent=plan.story.goal;
    $('story-review-role').textContent=plan.story.role;
    void renderStoryboard(reviewed);
  }
  updateAdultControls();
}
function setReviewedObjects(reviewed,pack,selection){
  if(state.review!==reviewed)return;
  const quantity=objectQuantity(reviewed.plan.spec);
  const checked=normalizeWorksheetObjects(pack,quantity);
  reviewed.plan=planLesson(reviewed.plan.spec,{objects:checked,presentation:reviewed.plan.presentation});reviewed.objectsReady=true;reviewed.objectsLoading=false;reviewed.cropOpen=false;
  cropView=null;$('object-crop-panel').hidden=true;$('adult-confirm').checked=false;
  state.objectChoice={key:reviewed.objectKey,pack:checked,selection};
  const list=$('object-sprites');list.replaceChildren();
  if(checked)for(const [index,sprite] of checked.sprites.entries()){
    const figure=document.createElement('figure'),image=document.createElement('img'),caption=document.createElement('figcaption');image.src=sprite.image;image.alt=checked.mode==='repeat'?'Original worksheet picture to repeat':`Original worksheet object ${index+1}`;caption.textContent=checked.mode==='repeat'?'Original':String(index+1);figure.append(image,caption);list.append(figure);
  }
  $('object-review').dataset.status='ready';
  $('object-status').textContent=!checked?'You chose story stars to represent the worksheet objects.':quantity===0?'This lesson has no objects to move. Zero stays empty.':checked.mode==='repeat'?`This one original picture will be repeated ${quantity} ${quantity===1?'time':'times'}. Check that it represents the objects in your question.`:`${quantity} original ${quantity===1?'picture is':'pictures are'} ready. Check every cutout against the worksheet; these are the pictures your buddy will move.`;
  renderReviewedLesson(reviewed);
}
async function autoSelectObjects(reviewed){
  if(state.review!==reviewed)return;
  const request=++reviewed.objectsRequest;reviewed.objectsReady=false;reviewed.objectsLoading=true;reviewed.cropOpen=false;cropView=null;
  $('object-crop-panel').hidden=true;$('adult-confirm').checked=false;$('object-sprites').replaceChildren();$('object-review').dataset.status='loading';$('object-status').textContent='Finding separate pictures in your worksheet…';renderReviewedLesson(reviewed);
  const current=()=>state.review===reviewed&&reviewed.objectsRequest===request;
  try{
    const result=await suggestWorksheetObjects(reviewed.picture,objectQuantity(reviewed.plan.spec));
    if(!current())return;
    if(!result.pack)throw new Error(result.reason||'The pictures could not be separated clearly.');
    setReviewedObjects(reviewed,result.pack,'automatic');
  }catch(error){
    if(!current())return;
    reviewed.objectsLoading=false;$('object-review').dataset.status='error';$('object-status').textContent=error.message||'Choose one complete worksheet object below, or choose story stars.';updateAdultControls();
  }
}
function closeObjectCrop(){
  if(state.review){state.review.cropOpen=false;state.review.objectsLoading=false;++state.review.objectsRequest;}cropView=null;$('object-crop-panel').hidden=true;setBusy($('objects-apply-crop'),false);updateAdultControls();
  if(state.review&&!state.review.objectsReady){$('object-review').dataset.status='error';$('object-status').textContent='No worksheet pictures selected yet. Choose one complete object, find separate objects, or choose story stars.';}
}
function paintObjectCrop(){
  if(!cropView||state.review!==cropView.reviewed)return;
  const canvas=$('object-crop-canvas'),ctx=canvas.getContext('2d'),r=cropView.rect,w=canvas.width,h=canvas.height;
  ctx.fillStyle='#fff';ctx.fillRect(0,0,w,h);ctx.drawImage(cropView.image,0,0,w,h);
  ctx.fillStyle='#263e3438';ctx.fillRect(0,0,w,r.y*h);ctx.fillRect(0,(r.y+r.height)*h,w,(1-r.y-r.height)*h);ctx.fillRect(0,r.y*h,r.x*w,r.height*h);ctx.fillRect((r.x+r.width)*w,r.y*h,(1-r.x-r.width)*w,r.height*h);
  ctx.strokeStyle='#267c68';ctx.lineWidth=Math.max(1.5,w/300);ctx.setLineDash([w/100,w/150]);ctx.strokeRect(r.x*w,r.y*h,r.width*w,r.height*h);ctx.setLineDash([]);
  for(const key of ['x','y','width','height']){const field=$(`crop-${key}`);if(document.activeElement!==field)field.value=String(Math.round(r[key]*1000)/10);}
}
async function openObjectCrop(){
  const reviewed=state.review;if(!reviewed?.picture)return;
  const request=++reviewed.objectsRequest;reviewed.objectsLoading=false;reviewed.cropOpen=true;$('adult-confirm').checked=false;updateAdultControls();$('object-crop-panel').hidden=false;
  setBusy($('objects-apply-crop'),false);
  $('object-crop-help').textContent='Include one whole object, without numbers or math symbols. Check the cutout before continuing.';
  try{
    const image=await new Promise((resolve,reject)=>{const i=new Image();i.onload=()=>resolve(i);i.onerror=()=>reject(new Error('This worksheet could not open for selection.'));i.src=reviewed.picture;});
    if(state.review!==reviewed||reviewed.objectsRequest!==request||!reviewed.cropOpen)return;
    const canvas=$('object-crop-canvas'),scale=Math.min(1,960/Math.max(image.naturalWidth,image.naturalHeight));canvas.width=Math.round(image.naturalWidth*scale);canvas.height=Math.round(image.naturalHeight*scale);
    cropView={reviewed,image,rect:{x:.05,y:.1,width:.2,height:.8},drag:null};paintObjectCrop();canvas.scrollIntoView({behavior:'smooth',block:'center'});
  }catch(error){if(state.review===reviewed&&reviewed.objectsRequest===request){closeObjectCrop();notice(error.message,true);}}
}
async function applyObjectCrop(){
  const view=cropView;if(!view||state.review!==view.reviewed)return;
  const reviewed=view.reviewed,request=++reviewed.objectsRequest;reviewed.objectsLoading=true;setBusy($('objects-apply-crop'),true,'Preparing picture…');updateAdultControls();
  try{
    const pack=await cropWorksheetObject(reviewed.picture,{...view.rect});
    if(state.review!==reviewed||reviewed.objectsRequest!==request||cropView!==view)return;
    setReviewedObjects(reviewed,pack,'crop');
  }catch(error){if(state.review===reviewed&&reviewed.objectsRequest===request){reviewed.objectsLoading=false;$('object-crop-help').textContent=error.message;updateAdultControls();}}
  finally{if(state.review===reviewed&&reviewed.objectsRequest===request)setBusy($('objects-apply-crop'),false);}
}
async function renderStoryboard(reviewed){
  const container=$('storyboard');container.replaceChildren();
  const plan=reviewed.plan;
  try{
    await Promise.all([prepareCharacter(reviewed.character),prepareWorksheetObjects(plan.objects)]);if(state.review!==reviewed||reviewed.plan!==plan||!reviewed.objectsReady)return;
    const action=plan.scenes.find(scene=>['count_b','remove_count','count_all','count_side','shape'].includes(scene.phase))||plan.scenes[0];
    const pause=plan.scenes.find(scene=>scene.phase==='pause')||plan.scenes.at(-1);
    const moments=[['Set off on an adventure',Math.min(plan.scenes[0].end-.05,plan.scenes[0].start+.8)],['Your buddy takes action',action.start+action.duration*.5],['Think and answer together',pause.start+pause.duration*.5]];
    for(const [label,time] of moments){
      const figure=document.createElement('figure');const canvas=document.createElement('canvas');canvas.width=640;canvas.height=360;canvas.setAttribute('role','img');canvas.setAttribute('aria-label',label);renderLessonFrame(canvas,plan,reviewed.character,time);
      const caption=document.createElement('figcaption');caption.textContent=label;figure.append(canvas,caption);container.append(figure);
    }
  }catch{container.textContent='The story preview could not load. Your checked math and character are still saved for the lesson.';}
}
function timeLabel(seconds){const n=Math.floor(seconds);return `${Math.floor(n/60)}:${String(n%60).padStart(2,'0')}`;}
async function makeLesson(){
  if(!state.review||!state.review.objectsReady||state.review.objectsLoading||state.review.cropOpen||!$('adult-confirm').checked||state.preparing)return;
  const generation=Symbol('reviewed lesson');state.preparing=generation;watchControls(true);
  setBusy($('make-lesson'),true,'Getting ready…');$('video-loading').hidden=false;
  try{
    const snapshot=clone(state.review);if(state.player){void state.player.dispose();state.player=null;}
    // Create before the first await so AudioContext can unlock on the button gesture.
    const pending=createLessonPlayer($('lesson-canvas'),snapshot.plan,snapshot.character,{onProgress:(fraction,seconds)=>{$('lesson-seek').value=fraction*100;$('lesson-time').textContent=`${timeLabel(seconds)} / ${timeLabel(snapshot.plan.duration)}`;},onEnd:()=>{$('play-video').textContent='▶ Replay lesson';},onError:error=>notice(error.message,true)});
    go('watch');const prepared=await pending;if(state.preparing!==generation){await prepared.dispose();return;}state.player=prepared;state.preparing=null;watchControls(false);try{localStorage.setItem('lesson-buddy-last-adventure-v1',snapshot.plan.presentation.theme);}catch{}$('watch-subtitle').textContent=`${snapshot.character.name} stars in a story about: ${snapshot.plan.question}`;$('lesson-time').textContent=`0:00 / ${timeLabel(snapshot.plan.duration)}`;
    $('watch-mission').hidden=!snapshot.plan.story;if(snapshot.plan.story){$('watch-mission-title').textContent=snapshot.plan.story.title;$('watch-mission-goal').textContent=snapshot.plan.story.goal;}
    const support=videoExportSupport();$('export-video').disabled=!support.supported;if(!support.supported||support.notice){$('export-status').textContent=support.reason||support.notice;$('export-status').hidden=false;}else $('export-status').hidden=true;
    if(state.step==='watch')await state.player.play();
  }catch(error){state.player=null;state.preparing=null;notice(error.message,true);go('review');}finally{if(state.preparing===generation)state.preparing=null;$('video-loading').hidden=true;setBusy($('make-lesson'),false);$('make-lesson').disabled=!$('adult-confirm').checked;}
}
async function exportLesson(){
  if(!state.player||state.exporting)return;
  const controller=new AbortController();state.exporting=controller;$('cancel-export').hidden=false;setBusy($('export-video'),true,'Recording with sound…');$('new-lesson').disabled=true;for(const id of ['play-video','pause-video','restart-video','lesson-seek'])$(id).disabled=true;
  $('export-status').hidden=false;$('export-status').classList.remove('error');$('export-status').textContent='Recording your lesson with narration. Keep this tab visible until it finishes.';
  try{
    const result=await state.player.exportVideo({signal:controller.signal,onProgress:fraction=>{$('export-status').textContent=`Recording with sound… ${Math.round(fraction*100)}%. Keep this tab visible.`;}});
    if(state.savedVideoURL)URL.revokeObjectURL(state.savedVideoURL);state.savedVideoURL=URL.createObjectURL(result.blob);
    $('export-status').replaceChildren();const message=document.createElement('span');message.textContent='Your narrated lesson is ready. ';const link=document.createElement('a');link.href=state.savedVideoURL;link.download=`my-lesson-buddy.${result.extension}`;link.id='finished-download';link.textContent=`Save video (.${result.extension})`;link.className='text-link';$('export-status').append(message,link);
    // A visible link works on browsers that restrict automatic downloads after a long recording.
    link.click();
  }catch(error){$('export-status').textContent=error.message;$('export-status').classList.toggle('error',error.name!=='AbortError');}
  finally{state.exporting=null;$('cancel-export').hidden=true;setBusy($('export-video'),false);$('new-lesson').disabled=false;for(const id of ['play-video','pause-video','restart-video','lesson-seek'])$(id).disabled=false;}
}

function setupEvents(){
  const changeAdventure=()=>{if(!state.review||state.preparing||state.exporting)return;adventureChoice=$('adventure-style').value;gentleMotion=$('gentle-motion').checked;const reviewed=state.review;reviewed.plan=planLesson(reviewed.plan.spec,{objects:reviewed.plan.objects,presentation:lessonPresentation(reviewed.plan.spec)});$('adult-confirm').checked=false;if(state.player){void state.player.dispose();state.player=null;}renderReviewedLesson(reviewed);};
  $('adventure-style').addEventListener('change',changeAdventure);$('gentle-motion').addEventListener('change',changeAdventure);
  $('photo-view-prepared').addEventListener('click',()=>showPhotoVersion('prepared'));$('photo-view-original').addEventListener('click',()=>showPhotoVersion('original'));
  $('photo-auto').addEventListener('click',()=>runPhotoCorrection());$('photo-use-original').addEventListener('click',useOriginalPhoto);$('photo-corners').addEventListener('click',()=>void openPhotoCorners());$('photo-apply-corners').addEventListener('click',applyPhotoCorners);$('photo-cancel-corners').addEventListener('click',closePhotoCorners);
  $('photo-shadows').addEventListener('change',()=>{if(!state.photoEditorOpen)runPhotoCorrection({corners:state.photo?.detected||state.photo?.stats?.manual?state.photo.corners:null});});
  const paperCanvas=$('photo-corners-canvas');
  const paperPoint=event=>{const box=paperCanvas.getBoundingClientRect();return{x:Math.max(0,Math.min(1,(event.clientX-box.left)/box.width)),y:Math.max(0,Math.min(1,(event.clientY-box.top)/box.height))};};
  paperCanvas.addEventListener('pointerdown',event=>{if(!photoView||photoView.drag||event.button!==0)return;const p=paperPoint(event),box=paperCanvas.getBoundingClientRect();let nearest=-1,distance=Infinity;for(const [i,point] of photoView.points.entries()){const d=Math.hypot((p.x-point.x)*box.width,(p.y-point.y)*box.height);if(d<distance){distance=d;nearest=i;}}if(distance>32)return;event.preventDefault();photoView.drag={pointerId:event.pointerId,index:nearest,previous:clone(photoView.points)};paperCanvas.setPointerCapture(event.pointerId);});
  paperCanvas.addEventListener('pointermove',event=>{if(!photoView?.drag||photoView.drag.pointerId!==event.pointerId)return;photoView.points[photoView.drag.index]=paperPoint(event);$('photo-corners-help').textContent='Keep the complete question inside the four corners.';paintPhotoCorners();});
  paperCanvas.addEventListener('pointerup',event=>{if(!photoView?.drag||photoView.drag.pointerId!==event.pointerId)return;photoView.drag=null;if(paperCanvas.hasPointerCapture(event.pointerId))paperCanvas.releasePointerCapture(event.pointerId);paintPhotoCorners();});
  paperCanvas.addEventListener('pointercancel',event=>{if(photoView?.drag?.pointerId===event.pointerId){photoView.points=photoView.drag.previous;photoView.drag=null;paintPhotoCorners();}});
  for(let i=0;i<4;i++)for(const axis of ['x','y'])$(`paper-${i}-${axis}`).addEventListener('input',()=>{if(!photoView)return;const text=$(`paper-${i}-${axis}`).value.trim();if(text==='')return;const value=Number(text);if(Number.isFinite(value))photoView.points[i][axis]=Math.max(0,Math.min(1,value/100));paintPhotoCorners();});
  $('objects-auto').addEventListener('click',()=>{if(state.review)void autoSelectObjects(state.review);});
  $('objects-crop').addEventListener('click',()=>void openObjectCrop());
  $('objects-stars').addEventListener('click',()=>{if(!state.review)return;++state.review.objectsRequest;setReviewedObjects(state.review,null,'stars');});
  $('objects-cancel-crop').addEventListener('click',closeObjectCrop);$('objects-apply-crop').addEventListener('click',()=>void applyObjectCrop());
  const cropCanvas=$('object-crop-canvas');
  const cropPoint=event=>{const box=cropCanvas.getBoundingClientRect();return{x:Math.max(0,Math.min(1,(event.clientX-box.left)/box.width)),y:Math.max(0,Math.min(1,(event.clientY-box.top)/box.height))};};
  cropCanvas.addEventListener('pointerdown',event=>{if(!cropView||cropView.drag||event.button!==0||state.review?.objectsLoading)return;event.preventDefault();cropView.drag={pointerId:event.pointerId,start:cropPoint(event),previous:{...cropView.rect}};cropCanvas.setPointerCapture(event.pointerId);});
  cropCanvas.addEventListener('pointermove',event=>{if(!cropView?.drag||cropView.drag.pointerId!==event.pointerId)return;const start=cropView.drag.start,end=cropPoint(event);cropView.rect={x:Math.min(start.x,end.x),y:Math.min(start.y,end.y),width:Math.abs(start.x-end.x),height:Math.abs(start.y-end.y)};paintObjectCrop();});
  cropCanvas.addEventListener('pointerup',event=>{if(!cropView?.drag||cropView.drag.pointerId!==event.pointerId)return;if(cropView.rect.width<.01||cropView.rect.height<.01)cropView.rect=cropView.drag.previous;cropView.drag=null;if(cropCanvas.hasPointerCapture(event.pointerId))cropCanvas.releasePointerCapture(event.pointerId);paintObjectCrop();});
  cropCanvas.addEventListener('pointercancel',event=>{if(cropView?.drag?.pointerId===event.pointerId){cropView.rect=cropView.drag.previous;cropView.drag=null;paintObjectCrop();}});
  for(const key of ['x','y','width','height'])$(`crop-${key}`).addEventListener('input',()=>{if(!cropView||state.review?.objectsLoading)return;const text=$(`crop-${key}`).value.trim();if(text==='')return;const r={...cropView.rect},value=Number(text)/100;if(!Number.isFinite(value))return;r[key]=Math.max(key==='x'||key==='y'?0:.01,Math.min(key==='x'||key==='y'?.99:1,value));r.width=Math.min(r.width,1-r.x);r.height=Math.min(r.height,1-r.y);cropView.rect=r;paintObjectCrop();});
  for(const mode of ['draw','build'])$(`mode-${mode}`).addEventListener('click',()=>setMode(mode));
  document.querySelectorAll('[data-go]').forEach(button=>button.addEventListener('click',()=>go(button.dataset.go)));
  $('buddy-name').addEventListener('input',event=>{state.name=event.target.value;void updatePreview();rememberDraft();});
  document.querySelectorAll('[data-motion]').forEach(button=>button.addEventListener('click',()=>{state.motion=button.dataset.motion;document.querySelectorAll('[data-motion]').forEach(b=>{b.classList.toggle('selected',b===button);b.setAttribute('aria-pressed',String(b===button));});}));
  document.querySelectorAll('[data-tool]').forEach(button=>button.addEventListener('click',()=>{pad.setTool(button.dataset.tool);document.querySelectorAll('[data-tool]').forEach(b=>{b.classList.toggle('selected',b===button);b.setAttribute('aria-pressed',String(b===button));});}));
  $('mirror').addEventListener('click',()=>{const mirror=$('mirror').getAttribute('aria-pressed')!=='true';$('mirror').setAttribute('aria-pressed',String(mirror));pad.setMirror(mirror);document.querySelector('.draw-paper').classList.toggle('mirrored',mirror);});
  $('ink').addEventListener('input',()=>pad.setColor($('ink').value));$('brush-size').addEventListener('input',()=>pad.setSize(Number($('brush-size').value)));$('undo').addEventListener('click',()=>pad.undo());$('redo').addEventListener('click',()=>pad.redo());
  $('clear-drawing').addEventListener('click',async()=>{if(!pad.hasDrawing()||await confirmAction('You can still use Undo to bring this drawing back.'))pad.clear();});
  document.addEventListener('keydown',event=>{if(event.defaultPrevented||state.mode!=='draw'||state.step!=='character'||$('confirm-dialog').open||$('about-dialog').open||!(event.ctrlKey||event.metaKey)||event.altKey||event.target.closest('input,textarea,select,[contenteditable=true]'))return;if(event.key.toLowerCase()==='z'){event.preventDefault();event.shiftKey?pad.redo():pad.undo();}else if(event.key.toLowerCase()==='y'){event.preventDefault();pad.redo();}});
  $('drawing-upload').addEventListener('change',async event=>{const file=event.target.files[0];try{if(!file)return;if(pad.hasDrawing()&&!await confirmAction('Replace this draft with a drawing file? Undo can bring the current drawing back.','Bring a drawing?'))return;const image=await imageFileToDataURL(file);await pad.load(image);setMode('draw');}catch(error){notice(error.message,true);}finally{event.target.value='';}});
  $('save-use').addEventListener('click',async()=>{try{setBusy($('save-use'),true,'Saving your buddy…');const draft=currentDraft();draft.name=normalizeName(state.name);if(draft.design)draft.design.name=draft.name;const saved=await saveCharacter(draft);await refreshLibrary();await selectBuddy(saved);}catch(error){notice(error.message,true);}finally{setBusy($('save-use'),false);}});
  $('library-search').addEventListener('input',renderLibrary);
  $('package-upload').addEventListener('change',async event=>{try{const file=event.target.files[0];if(!file)return;if(file.size>8*1024*1024)throw new Error('Choose a character ZIP smaller than 8 MB.');const saved=await saveCharacter(await readPackage(file));await refreshLibrary();notice(`${saved.name} joined your collection. Your current draft is safe.`);}catch(error){notice(error.message,true);}finally{event.target.value='';}});
  document.querySelectorAll('[data-example]').forEach(button=>button.addEventListener('click',()=>{
    const example=EXAMPLES[button.dataset.example];
    void pictureLoader.load(async({signal})=>{const image=await dataURLForAsset(example.image,{signal});return example.photo?preparePhoto(image,{signal}):image;},{label:example.label,spec:example.spec,origin:'example'});
  }));
  for(const id of ['worksheet-upload','camera-upload'])$(id).addEventListener('change',event=>{
    const file=event.target.files[0];event.target.value='';
    if(file)void pictureLoader.load(async({signal})=>preparePhoto(await imageFileToDataURL(file),{signal}),{label:'Your worksheet photo · check the prepared view, then read or enter the question'});
  });
  $('question-type').addEventListener('change',()=>{questionFields();invalidateReview();});for(const id of ['number-a','number-b','shape-name','shape-task'])$(id).addEventListener('input',invalidateReview);
  $('question-form').addEventListener('submit',event=>{event.preventDefault();try{reviewQuestion();}catch(error){notice(error.message,true);$('question-form').scrollIntoView({behavior:'smooth',block:'center'});}});
  $('manual-open').addEventListener('click',()=>{cancelPictureReading();$('question-form').scrollIntoView({behavior:'smooth',block:'center'});$('number-a').focus();});
  $('read-picture').addEventListener('click',async()=>{
    if(state.pictureLoading||state.photoEditorOpen){notice('Finish preparing the worksheet photo first.');return;}
    if(!state.picture){notice('Add a picture or choose an example first.');return;}if(state.reading||!state.readerSupported)return;
    const controller=new AbortController(),version=state.pictureVersion,picture=state.picture;
    const current=()=>state.reading===controller&&state.pictureVersion===version&&!state.pictureLoading&&state.step==='worksheet';
    state.reading=controller;setBusy($('read-picture'),true,'Reading on this device…');$('reader-progress-wrap').hidden=false;$('cancel-reading').hidden=false;$('reader-progress').removeAttribute('value');
    try{
      const result=await readWorksheet(picture,{signal:controller.signal,onProgress:event=>{
        if(!current()||controller.signal.aborted)return;
        $('reader-status').textContent=event.message;if(Number.isFinite(event.progress))$('reader-progress').value=event.progress;else $('reader-progress').removeAttribute('value');
      }});
      if(!current()||controller.signal.aborted)return;
      state.aiLoaded=true;fillQuestion(result,'Experimental browser AI reading · check and correct every quantity before continuing.');$('reader-status').textContent='A reading is ready. Check the question on the right before making a lesson.';$('reader-progress').value=100;notice('Check the AI reading against your picture. You can correct any field.');
    }catch(error){
      if(current()){$('reader-status').textContent=error.name==='AbortError'?'Reading cancelled. You can enter the question together.':error.message;notice(error.message,error.name!=='AbortError');}
    }finally{
      if(state.reading===controller){state.reading=null;$('cancel-reading').hidden=true;setBusy($('read-picture'),false);updatePictureControls();}
    }
  });
  $('cancel-reading').addEventListener('click',()=>state.reading?.abort());$('edit-question').addEventListener('click',()=>{closeObjectCrop();go('worksheet');});$('adult-confirm').addEventListener('change',updateAdultControls);$('make-lesson').addEventListener('click',makeLesson);
  $('play-video').addEventListener('click',()=>state.player?.play().catch(error=>notice(error.message,true)));$('pause-video').addEventListener('click',()=>state.player?.pause());$('restart-video').addEventListener('click',()=>{state.player?.stop();state.player?.play().catch(error=>notice(error.message,true));});$('lesson-seek').addEventListener('input',()=>state.player?.seek(state.player.plan.duration*Number($('lesson-seek').value)/100));
  $('export-video').addEventListener('click',exportLesson);$('cancel-export').addEventListener('click',()=>state.exporting?.abort());$('new-lesson').addEventListener('click',()=>{state.player?.stop();invalidateReview();go('worksheet');notice('Choose another example or add a new picture.');});
  $('about-open').addEventListener('click',()=>$('about-dialog').showModal());for(const id of ['about-close','about-done'])$(id).addEventListener('click',()=>$('about-dialog').close());
  window.addEventListener('pagehide',()=>{pictureLoader.cancel();state.reading?.abort();disposeWorksheetReader();state.exporting?.abort();void state.player?.dispose();});
}
async function init(){
  // Keep the requested shape operation explicit, rather than changing a name task into a sides task.
  const label=document.createElement('label');label.id='shape-task-wrap';label.className='field-label';label.hidden=true;label.textContent='What does the worksheet ask?';const select=document.createElement('select');select.id='shape-task';for(const [value,text] of [['sides','Count the straight sides'],['name','Name the shape']]){const option=document.createElement('option');option.value=value;option.textContent=text;select.append(option);}label.append(select);$('shape-wrap').after(label);
  populateBuilder();pad=new DrawingPad($('drawing-canvas'),{onChange:updateDrawingControls});
  try{const draft=JSON.parse(localStorage.getItem('lesson-buddy-draft-v1')||'null');if(draft){state.design=normalizeDesign(draft.design);state.name=typeof draft.name==='string'?draft.name.slice(0,32):state.design.name;if(draft.drawing)await pad.load(draft.drawing);state.mode=['draw','build'].includes(draft.mode)?draft.mode:'build';}}catch{/* A missing/older draft never prevents a new adventure. */}
  syncDesignControls();setMode(state.mode);setupEvents();updateDrawingControls();await refreshLibrary();
  updatePictureControls();const status=await browserReaderStatus();$('reader-support').textContent=status.reason;state.readerSupported=status.supported;updatePictureControls();
  let frame=0;const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;const hero={source:'builder',name:'Nova',design:clone(PRESETS[0]?.design||DEFAULT_DESIGN)};
  function animate(stamp){
    const t=reduced?0:stamp/1000;
    if(document.visibilityState!=='hidden'){
      if(state.step==='character'){
        const canvas=$('buddy-canvas'),ctx=canvas.getContext('2d');ctx.clearRect(0,0,canvas.width,canvas.height);
        if(state.live){
          const w=canvas.width*.9,h=canvas.height*.94;
          const x=(canvas.width-w)/2+(state.motion==='walk'?Math.sin(t*1.7)*14:0),y=(canvas.height-h)/2;
          const facing=state.motion==='walk'&&Math.cos(t*1.7)<0?'left':'right';
          const pose={motion:state.motion,time:t,facing};drawCharacter(ctx,state.live,x,y,w,h,pose);
          if(['carry','give'].includes(state.motion)){
            const anchor=characterAnchors(state.live,x,y,w,h,pose).prop;
            ctx.save();ctx.translate(anchor.x,anchor.y);ctx.rotate(Math.sin(t*1.5)*.1);ctx.beginPath();
            for(let i=0;i<10;i++){const angle=-Math.PI/2+i*Math.PI/5,r=i%2?10:22;i?ctx.lineTo(Math.cos(angle)*r,Math.sin(angle)*r):ctx.moveTo(Math.cos(angle)*r,Math.sin(angle)*r);}
            ctx.closePath();ctx.fillStyle='#F5C666';ctx.fill();ctx.strokeStyle='#B78B42';ctx.lineWidth=2;ctx.stroke();ctx.restore();
          }
        }
      }
      if(++frame%2===0||reduced){const canvas=$('hero-character'),ctx=canvas.getContext('2d');ctx.clearRect(0,0,240,270);drawCharacter(ctx,hero,0,0,240,270,{motion:'wave',time:t});}
    }
    requestAnimationFrame(animate);
  }
  requestAnimationFrame(animate);
}
init().catch(error=>{console.error('Studio initialization failed',error);notice('The studio could not finish loading. Please refresh this page. Your saved characters remain in this browser.',true);});
