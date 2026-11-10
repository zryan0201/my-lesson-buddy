/* A real browser-native lesson renderer. The same PCM audio reaches speakers
 * and the exported video; no microphone, desktop capture, or speech API is used. */
import {AUDIO} from '../audio/manifest.js';
import {prepareCharacter} from './character.js';
import {renderStoryFrame} from './story.js';
import {normalizeWorksheetObjects,prepareWorksheetObjects} from './objects.js';
import {normalizePresentation,adventureStory,adventureAudioKey} from './adventures.js';

const SHAPES = Object.freeze({circle: 0, triangle: 3, square: 4, rectangle: 4});

function freeze(value) {
  if (value && typeof value === 'object' && !Object.isFrozen(value)) {
    Object.values(value).forEach(freeze);
    Object.freeze(value);
  }
  return value;
}

function number(value, label) {
  if (!Number.isInteger(value) || value < 0 || value > 10) throw new Error(`${label} must be a whole number from 0 to 10.`);
  return value;
}

/** Validate and calculate locally. A model-proposed answer is never trusted. */
export function normalizeLessonSpec(spec) {
  if (!spec || typeof spec !== 'object' || Array.isArray(spec)) throw new Error('Choose a supported math question.');
  const type = spec.type;
  if (type === 'addition' || type === 'subtraction') {
    const a = number(spec.a, 'The first number');
    const b = number(spec.b, 'The second number');
    if (type === 'addition' && a + b > 10) throw new Error('For this first version, choose an addition total of 10 or less.');
    if (type === 'subtraction' && b > a) throw new Error('For this first version, take away no more than the starting number.');
    return {type, a, b};
  }
  if (type === 'counting') return {type, count: number(spec.count ?? spec.a, 'The count')};
  if (type === 'shape' && Object.hasOwn(SHAPES, spec.shape)) {
    const shape_task=spec.shape_task??'sides';
    if(!['name','sides'].includes(shape_task))throw new Error('Choose identifying the shape or counting its straight sides.');
    return {type, shape: spec.shape, shape_task};
  }
  throw new Error('Choose addition, subtraction, counting, or a circle, triangle, square, or rectangle.');
}

/** A frozen story and teaching plan, inspected before any playback or recording. */
export function planLesson(input, {objects: requestedObjects = null, presentation: requestedPresentation = null} = {}) {
  const spec = normalizeLessonSpec(input);
  const presentation=normalizePresentation(spec,requestedPresentation);
  if (spec.type === 'shape' && requestedObjects !== null) throw new Error('Worksheet picture props are for addition, subtraction, and counting lessons.');
  const quantity = spec.type === 'addition' ? spec.a + spec.b : spec.type === 'subtraction' ? spec.a : spec.type === 'counting' ? spec.count : 0;
  const objects = normalizeWorksheetObjects(requestedObjects, quantity);
  // A reviewed crop changes the illustration, never the checked quantities.
  const objectAudioKey = key => {
    if (!objects || !key) return key;
    const direct = {'story-intro':'object-story-intro','story-add-goal':'object-add-goal','story-sub-goal':'object-sub-goal',
      'story-count-goal':'object-count-goal','story-remaining':'object-remaining','story-turn-add':'object-turn-add',
      'story-turn-sub':'object-turn-sub','story-turn-count':'object-turn-count'};
    if (direct[key]) return direct[key];
    return key.replace(/^story-first-/, 'first-').replace(/^story-collect-/, 'add-')
      .replace(/^story-give-/, 'take-').replace(/^story-answer-count-/, 'answer-count-');
  };
  const scenes = [];
  let cursor = 0;
  const add = (phase, audioKey, extra = {}) => {
    audioKey = objectAudioKey(audioKey);
    audioKey = adventureAudioKey(audioKey,{objects,presentation});
    const clip = audioKey ? AUDIO[audioKey] : null;
    if (audioKey && !clip) throw new Error(`A narration asset is missing (${audioKey}). Please reload the page.`);
    const transfer = phase === 'count_b' || phase === 'remove_count';
    const visit = ['count_a', 'count_remaining', 'count_all'].includes(phase);
    const trace = phase === 'count_side';
    const minimum = transfer ? 3.4 : trace ? 1.85 : visit ? 1.8 : phase === 'shape' ? 3.6 : 1.15;
    const fraction = transfer ? .66 : trace ? .5 : visit ? .55 : 0;
    const duration = phase === 'pause' ? 3 : Math.max(minimum, ((clip?.duration || 0) + .2) / (1 - fraction));
    const audioOffset = audioKey ? duration * fraction : 0;
    scenes.push({phase, audioKey, audioOffset, audioDuration: clip?.duration || 0,
      caption: clip?.text || 'Help your buddy. Count and think!', start: cursor, end: cursor + duration, duration, ...extra});
    cursor += duration;
  };
  const action = (kind, fields = {}) => ({kind, ...fields});
  let question, answer, answerText, story;
  const steps = [];
  add('intro', 'story-intro', {action: action('enter')});
  if (spec.type === 'addition') {
    const {a, b} = spec;
    answer = a + b;
    question = `What is ${a} + ${b}?`;
    answerText = `${a} + ${b} = ${answer}`;
    story = {id: 'starlight-garden', title: 'The Starlight Picnic',
      goal: 'Help your buddy collect stars for a garden picnic.', role: 'Star collector and wagon helper',
      summary: `Your buddy starts with ${a} stars in a wagon and carries ${b} more stars from the garden into it, one at a time.`};
    steps.push(`Use one story star for each worksheet picture. Start with ${a} stars in the wagon.`,
      `Your buddy carries ${b} more stars into the wagon, one at a time.`,
      b ? `Count on from ${a} as each new star arrives. There are ${answer} altogether.` : `No stars are added. The wagon still has ${answer}.`);
    add('question', 'story-add-goal', {action: action('inspect')});
    add('first', `story-first-${a}`, {action: action('point', {target: 'wagon'})});
    for (let i = 1; i <= a; i += 1) add('count_a', `number-${i}`, {count: i, action: action('point', {itemIndex: i-1, target: 'wagon'})});
    add('add', `story-collect-${b}`, {action: action('point', {target: 'garden'})});
    if (b) add('count_on', `on-${a}`, {action: action('think')});
    for (let i = 1; i <= b; i += 1) add('count_b', `number-${a+i}`, {
      count: i, spokenCount: a+i, action: action('collect', {itemIndex: i-1, from: 'garden', to: 'wagon'})});
    add('your_turn', 'story-turn-add', {action: action('think')}); add('pause', null, {action: action('think')});
    add('answer', `answer-add-${a}-${b}`, {action: action('point', {target: 'wagon'})});
  } else if (spec.type === 'subtraction') {
    const {a, b} = spec;
    answer = a - b;
    question = `What is ${a} − ${b}?`;
    answerText = `${a} − ${b} = ${answer}`;
    story = {id: 'starlight-garden', title: 'A Gift for a Garden Friend',
      goal: 'Help your buddy share stars with a garden friend.', role: 'Star giver and careful counter',
      summary: `Your buddy starts with ${a} stars, gives ${b} to a garden friend one at a time, then checks the wagon for the stars that remain.`};
    steps.push(`Use one story star for each worksheet picture. Start with ${a} stars in the wagon.`,
      `Your buddy gives ${b} stars to a friend. Those stars leave the wagon.`,
      `Count only the ${answer} stars that are still in the wagon.`);
    add('question', 'story-sub-goal', {action: action('inspect')});
    add('first', `story-first-${a}`, {action: action('point', {target: 'wagon'})});
    for (let i = 1; i <= a; i += 1) add('count_a', `number-${i}`, {count: i, action: action('point', {itemIndex: i-1, target: 'wagon'})});
    add('take', `story-give-${b}`, {action: action('point', {target: 'friend'})});
    for (let i = 1; i <= b; i += 1) add('remove_count', `number-${i}`, {
      count: i, action: action('give', {itemIndex: a-i, from: 'wagon', to: 'friend'})});
    add('remaining', 'story-remaining', {action: action('point', {target: 'wagon'})});
    for (let i = 1; i <= answer; i += 1) add('count_remaining', `number-${i}`, {count: i, action: action('point', {itemIndex: i-1, target: 'wagon'})});
    add('your_turn', 'story-turn-sub', {action: action('think')}); add('pause', null, {action: action('think')});
    add('answer', `answer-sub-${a}-${b}`, {action: action('point', {target: 'wagon'})});
  } else if (spec.type === 'counting') {
    answer = spec.count;
    question = 'How many pictures can you count?';
    answerText = `${answer} ${answer === 1 ? 'star' : 'stars'}`;
    story = {id: 'starlight-garden', title: 'The Garden Star Hunt',
      goal: 'Help your buddy find every star without counting one twice.', role: 'Garden explorer and star counter',
      summary: 'Your buddy visits the garden stars and points to each one once. The final count tells how many were found.'};
    if (answer === 0) steps.push('Explore with your buddy.', 'There are no stars to visit.', 'Zero means there are none.');
    else steps.push('Use one story star for each worksheet picture.', 'Your buddy visits and points to one star at a time.', `Say each number once. The last number tells us there are ${answer} stars.`);
    add('question', 'story-count-goal', {action: action('inspect')});
    for (let i = 1; i <= answer; i += 1) add('count_all', `number-${i}`, {count: i, action: action('visit', {itemIndex: i-1, target: 'garden'})});
    add('your_turn', 'story-turn-count', {action: action('think')}); add('pause', null, {action: action('think')});
    add('answer', `story-answer-count-${answer}`, {action: action('point', {target: 'garden'})});
  } else {
    story = {id: 'starlight-garden', title: 'The Shape Gate',
      goal: spec.shape_task === 'name' ? 'Help your buddy name the shape to open the garden gate.' : 'Help your buddy trace and count the gate’s straight sides.',
      role: 'Shape explorer and gate opener', summary: spec.shape_task === 'name' ?
        'Your buddy follows the gate outline, notices its features, and waits for the child to name the shape before the gate opens.' :
        'Your buddy follows each straight side of the gate. The child counts along, then the gate opens after the answer.'};
    if (spec.shape_task === 'name') {
      answer = spec.shape; question = 'What shape is this?'; answerText = `A ${spec.shape}`;
      steps.push('Your buddy explores the gate outline.', AUDIO[`feature-${spec.shape}`].text, `Name the shape to open the gate: ${spec.shape}.`);
      add('question', 'story-shape-name-goal', {action: action('inspect')});
      add('shape', `feature-${spec.shape}`, {action: action('trace', {path: 'outline'})});
      add('your_turn', 'story-turn-name', {action: action('think')}); add('pause', null, {action: action('think')});
      add('answer', `answer-name-${spec.shape}`, {action: action('point', {target: 'gate'})});
    } else {
      answer = SHAPES[spec.shape];
      question = `How many straight sides does a ${spec.shape} have?`;
      answerText = `${answer} straight ${answer === 1 ? 'side' : 'sides'}`;
      steps.push('Your buddy explores the shape gate.', 'Follow and count each straight side once.', `${spec.shape[0].toUpperCase()+spec.shape.slice(1)}: ${answer} straight sides.`);
      add('question', 'story-shape-goal', {action: action('inspect')});
      // Explore the outline without stating the side-count answer before the
      // child's thinking pause. Number clips accompany the later traced sides.
      add('shape', 'look-shape', {action: action('trace', {path: 'outline'})});
      for (let i = 1; i <= answer; i += 1) add('count_side', `number-${i}`, {count: i, highlightSide: i-1, action: action('trace', {side: i-1})});
      add('your_turn', 'story-turn-shape', {action: action('think')}); add('pause', null, {action: action('think')});
      add('answer', `answer-${spec.shape}`, {action: action('point', {target: 'gate'})});
    }
  }
  if (objects) {
    // The original worksheet artwork is the cast of objects, not a star stand-in.
    if (spec.type === 'addition') {
      story = {id:'worksheet-garden', title:'The Garden Picnic',
        goal:'Help your buddy collect the pictures from your worksheet for a garden picnic.',
        role:'Picture collector and wagon helper',
        summary:`Your buddy starts with ${spec.a} worksheet pictures and carries ${spec.b} more into the wagon, one at a time.`};
      steps.splice(0, steps.length, `Start with ${spec.a} pictures from your worksheet in the wagon.`,
        `Your buddy carries ${spec.b} more worksheet pictures into the wagon, one at a time.`,
        spec.b ? `Count on from ${spec.a} as each new picture arrives. There are ${answer} altogether.` : `No pictures are added. The wagon still has ${answer}.`);
    } else if (spec.type === 'subtraction') {
      story = {id:'worksheet-garden', title:'A Gift for a Garden Friend',
        goal:'Help your buddy share the pictures from your worksheet with a garden friend.',
        role:'Picture giver and careful counter',
        summary:`Your buddy starts with ${spec.a} worksheet pictures, gives ${spec.b} to a friend one at a time, then checks the wagon for the pictures that remain.`};
      steps.splice(0, steps.length, `Start with ${spec.a} pictures from your worksheet in the wagon.`,
        `Your buddy gives ${spec.b} worksheet pictures to a friend. Those pictures leave the wagon.`,
        `Count only the ${answer} pictures that are still in the wagon.`);
    } else if (spec.type === 'counting') {
      answerText = `${answer} ${answer === 1 ? 'picture' : 'pictures'}`;
      story = {id:'worksheet-garden', title:'The Garden Picture Hunt',
        goal:'Help your buddy find every worksheet picture without counting one twice.',
        role:'Garden explorer and picture counter',
        summary:'Your buddy visits the worksheet pictures and points to each one once. The final count tells how many were found.'};
      steps.splice(0, steps.length, ...(answer === 0 ? ['Explore with your buddy.', 'There are no pictures to visit.', 'Zero means there are none.'] :
        ['Use the pictures from your worksheet.', 'Your buddy visits and points to one picture at a time.', `Say each number once. The last number tells us there are ${answer} pictures.`]));
    }
  }
  add('celebration', 'story-celebrate', {action: action('celebrate')});
  story=adventureStory(spec,objects,presentation);
  return freeze({version: 2, spec, objects, presentation, question, answer, answerText, steps, scenes, story, duration: cursor,
    representation: spec.type === 'shape' ? 'The shape gate represents the worksheet shape.' : objects ? (objects.mode === 'repeat' ? 'Your chosen worksheet picture is reused for each counted object.' : 'These are the original pictures from your worksheet.') : 'Story stars stand for pictures on the worksheet.',
    narration: 'Recorded English story narration; no microphone or paid speech API.'});
}

export function sceneAt(plan, time) {
  const t = Math.max(0, Math.min(plan.duration, Number.isFinite(time) ? time : 0));
  return plan.scenes.find(scene => t < scene.end) || plan.scenes[plan.scenes.length - 1];
}

/** Characters enact the mathematics in a shared story world. */
export function renderLessonFrame(canvas, plan, character, time) {
  return renderStoryFrame(canvas, plan, character, time);
}

export function videoExportSupport() {
  if(typeof globalThis.MediaRecorder!=='function'||typeof globalThis.MediaRecorder.isTypeSupported!=='function') return {supported:false,reason:'This browser can play the lesson, but video download needs a browser with MediaRecorder. Try a current Chrome, Edge, or Safari.'};
  // Request both video and audio codecs explicitly. A generic MP4 request can
  // otherwise choose VP9/Opus inside MP4, which some ordinary players reject.
  // AVC/AAC syntax: developer.mozilla.org/en-US/docs/Web/API/MediaRecorder/mimeType
  const types=[
    'video/mp4;codecs=avc1.424028,mp4a.40.2',
    'video/mp4;codecs=avc1.42E01F,mp4a.40.2',
    'video/mp4;codecs=avc1.4D401F,mp4a.40.2',
    'video/mp4;codecs=avc1,mp4a.40.2',
    'video/webm;codecs=vp9,opus',
    'video/webm;codecs=vp8,opus',
    'video/webm',
    'video/mp4',
  ];
  const mimeType=types.find(type=>globalThis.MediaRecorder.isTypeSupported(type));
  return mimeType?{supported:true,mimeType,extension:mimeType.startsWith('video/mp4')?'mp4':'webm',
    notice:mimeType==='video/mp4'?'This browser chooses its MP4 recording format. If another player cannot open it, play the file in your browser.':null}:
    {supported:false,reason:'This browser can play the lesson but cannot record a supported video format.'};
}

function abortError(message='Video generation was cancelled. Your character and worksheet are still here.') {
  const error=new Error(message);error.name='AbortError';return error;
}

/** Load actual PCM narration, then play/record the exact frozen reviewed plan. */
export async function createLessonPlayer(canvas, plan, character, callbacks={}) {
  const canonical=planLesson(plan?.spec,{objects:plan?.objects??null,presentation:plan?.presentation??null});
  if(!canvas||typeof canvas.getContext!=='function')throw new Error('Choose a lesson canvas before playing.');
  const friend=JSON.parse(JSON.stringify(character));
  canvas.width=1280;canvas.height=720;
  const AudioContextClass=globalThis.AudioContext||globalThis.webkitAudioContext;
  if(!AudioContextClass)throw new Error('This browser does not support narrated lessons. Try a current browser.');
  const audio=new AudioContextClass();
  // Start unlocking synchronously in the user's button event, before image work
  // or network awaits can consume a mobile browser's transient activation.
  const unlocking=audio.resume();
  const gain=audio.createGain();gain.gain.value=.88;gain.connect(audio.destination);
  const buffers=new Map();
  try {
    await unlocking;await prepareCharacter(friend);await prepareWorksheetObjects(canonical.objects);
    const keys=[...new Set(canonical.scenes.map(s=>s.audioKey).filter(Boolean))];
    await Promise.all(keys.map(async key=>{
      const response=await fetch(new URL(`../audio/${AUDIO[key].file}`,import.meta.url));
      if(!response.ok)throw new Error('A narration clip could not load. Check your connection and try again.');
      const bytes=await response.arrayBuffer();
      if(bytes.byteLength>2*1024*1024)throw new Error('A narration clip was too large to load safely.');
      buffers.set(key,await audio.decodeAudioData(bytes));
    }));
  } catch(error){await audio.close();throw error;}
  let offset=0,startAt=0,playing=false,disposed=false,animation=0,recording=null;
  const sources=new Set();
  function stopAudio(){for(const source of sources){try{source.stop();}catch{}source.disconnect();}sources.clear();}
  function notify(name,...args){try{callbacks[name]?.(...args);}catch(error){console.error('Lesson display callback failed',error);}}
  function position(){return playing?Math.min(canonical.duration,offset+Math.max(0,audio.currentTime-startAt)):offset;}
  function paint(t){renderLessonFrame(canvas,canonical,friend,t);}
  function cancelAnimation(){if(animation)cancelAnimationFrame(animation);animation=0;}
  function halt(){offset=position();playing=false;stopAudio();cancelAnimation();}
  function tick(){
    if(!playing||disposed)return;
    const t=position();paint(t);notify('onProgress',t/canonical.duration,t);
    if(recording)try{recording.onProgress?.(t/canonical.duration,t);}catch(error){console.error('Video progress callback failed',error);}
    if(t>=canonical.duration){
      halt();offset=canonical.duration;paint(offset);notify('onEnd');
      if(recording)recording.finish();
      return;
    }
    animation=requestAnimationFrame(tick);
  }
  function startPlayback(from){
    halt();offset=from>=canonical.duration?0:Math.max(0,from);startAt=audio.currentTime+.06;playing=true;
    for(const scene of canonical.scenes){
      if(!scene.audioKey)continue;
      const audioStart=scene.start+(scene.audioOffset||0);
      const buffer=buffers.get(scene.audioKey),passed=Math.max(0,offset-audioStart);
      if(!buffer||passed>=buffer.duration)continue;
      const source=audio.createBufferSource();source.buffer=buffer;source.connect(gain);
      sources.add(source);source.onended=()=>{sources.delete(source);source.disconnect();};
      source.start(startAt+Math.max(0,audioStart-offset),passed);
    }
    paint(offset);animation=requestAnimationFrame(tick);
  }
  function ensure(){if(disposed)throw new Error('This lesson player has closed. Generate the lesson again.');}
  const onVisibility=()=>{
    if(document.visibilityState==='hidden'){
      if(recording)recording.cancel(abortError('Video generation stopped because this tab was hidden. Keep this tab visible and try again.'));
      else if(playing){halt();notify('onProgress',offset/canonical.duration,offset);}
    }
  };
  document.addEventListener('visibilitychange',onVisibility);
  audio.onstatechange=()=>{
    if(audio.state==='suspended'&&recording)recording.cancel(abortError('Audio was interrupted. Keep this tab active and try creating the video again.'));
  };
  paint(0);
  return {
    plan:canonical,
    get currentTime(){return position();},get playing(){return playing;},get exporting(){return Boolean(recording);},
    async play(){ensure();if(recording)throw new Error('Wait for the video download to finish.');await audio.resume();startPlayback(offset);},
    pause(){ensure();if(recording)throw new Error('Cancel video generation before pausing.');halt();paint(offset);},
    stop(){ensure();if(recording)recording.cancel(abortError());else{halt();offset=0;paint(0);notify('onProgress',0,0);}},
    seek(seconds){ensure();if(recording)throw new Error('Cancel video generation before moving through the lesson.');
      if(!Number.isFinite(seconds))throw new Error('Choose a valid lesson time.');
      const resume=playing;halt();offset=Math.max(0,Math.min(canonical.duration,seconds));paint(offset);
      notify('onProgress',offset/canonical.duration,offset);
      // Seeking to the last frame should stay there. Only an explicit Replay
      // action restarts a completed lesson from zero.
      if(resume&&offset<canonical.duration)startPlayback(offset);
      else if(offset===canonical.duration)notify('onEnd');},
    async exportVideo({onProgress,signal}={}){
      ensure();if(recording)throw new Error('A video is already being created.');
      const support=videoExportSupport();if(!support.supported)throw new Error(support.reason);
      if(typeof canvas.captureStream!=='function')throw new Error('This browser can play the lesson but cannot record its canvas. Try Chrome or Edge.');
      if(document.visibilityState==='hidden')throw new Error('Keep the lesson tab visible while creating the video.');
      if(signal?.aborted)throw abortError();
      await audio.resume();
      // Check again after the await to prevent two export requests racing.
      if(recording)throw new Error('A video is already being created.');
      if(signal?.aborted)throw abortError();
      halt();offset=0;paint(0);
      const videoStream=canvas.captureStream(24);
      const destination=audio.createMediaStreamDestination();gain.connect(destination);
      const stream=new MediaStream([...videoStream.getVideoTracks(),...destination.stream.getAudioTracks()]);
      const chunks=[];let recorder;
      try{recorder=new MediaRecorder(stream,{mimeType:support.mimeType,videoBitsPerSecond:2800000,audioBitsPerSecond:96000});}
      catch(error){gain.disconnect(destination);stream.getTracks().forEach(track=>track.stop());throw new Error('This browser could not start video recording. Try a current Chrome or Edge.');}
      return await new Promise((resolve,reject)=>{
        let failure=null,ended=false;
        const cleanup=()=>{
          signal?.removeEventListener('abort',onAbort);try{gain.disconnect(destination);}catch{}
          stream.getTracks().forEach(track=>track.stop());recording=null;
        };
        const finish=()=>{if(ended)return;ended=true;halt();if(recorder.state!=='inactive')recorder.stop();};
        const cancel=(error)=>{failure=error;finish();};
        const onAbort=()=>cancel(abortError());
        recorder.ondataavailable=event=>{if(event.data?.size)chunks.push(event.data);};
        recorder.onerror=()=>cancel(new Error('The browser could not finish recording. Your lesson is still available to play.'));
        recorder.onstop=()=>{
          cleanup();if(failure){reject(failure);return;}
          const mimeType=recorder.mimeType||support.mimeType;
          const blob=new Blob(chunks,{type:mimeType});
          if(!blob.size){reject(new Error('The browser returned an empty video. Please try again.'));return;}
          try{onProgress?.(1,canonical.duration);}catch{}resolve({blob,mimeType,extension:mimeType.startsWith('video/mp4')?'mp4':'webm'});
        };
        recording={onProgress,finish,cancel};signal?.addEventListener('abort',onAbort,{once:true});
        try{recorder.start(250);startPlayback(0);}catch(error){failure=error;finish();if(recorder.state==='inactive'){cleanup();reject(error);}}
      });
    },
    async dispose(){if(disposed)return;if(recording)recording.cancel(abortError());halt();disposed=true;
      document.removeEventListener('visibilitychange',onVisibility);audio.onstatechange=null;gain.disconnect();await audio.close();},
  };
}
