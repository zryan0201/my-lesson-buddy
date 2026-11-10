import test from 'node:test';
import assert from 'node:assert/strict';
import { DEFAULT_DESIGN, PRESETS, OPTIONS, normalizeDesign, prepareCharacter, drawCharacter, characterAnchors, drawingInkBounds, DrawingPad } from '../dist/modules/character.js';

function fakeCanvas(width = 12, height = 10) {
  let pixels = new Uint8ClampedArray(width * height * 4).fill(255);
  const events = new Map(), commands = [], pointer = { value: null };
  const context = {
    commands, save() { commands.push(['save']); }, restore() { commands.push(['restore']); },
    setTransform(...args) { commands.push(['setTransform', ...args]); },
    translate(...args) { commands.push(['translate', ...args]); }, scale(...args) { commands.push(['scale', ...args]); }, rotate(...args) { commands.push(['rotate', ...args]); },
    beginPath() { commands.push(['begin']); }, closePath() { commands.push(['close']); },
    moveTo(...args) { commands.push(['moveTo', ...args]); }, lineTo(...args) { commands.push(['lineTo', ...args]); },
    quadraticCurveTo(...args) { commands.push(['quadraticCurveTo', ...args]); },
    ellipse(...args) { commands.push(['ellipse', ...args]); }, arc(...args) { commands.push(['arc', ...args]); }, rect(...args) { commands.push(['rect', ...args]); },
    stroke() { commands.push(['stroke', this.strokeStyle, this.lineWidth]); pixels[0] = (pixels[0] + 1) % 255; },
    fill() { commands.push(['fill', this.fillStyle]); pixels[0] = (pixels[0] + 1) % 255; },
    fillRect() { pixels.fill(255); }, drawImage(...args) { commands.push(['drawImage',...args.slice(1)]);pixels[0] = 0; },
    getImageData() { return { data: pixels.slice(), width, height }; },
    putImageData(image) { pixels = image.data.slice(); },
  };
  const canvas = {
    width, height, style: {}, getContext() { return context; },
    addEventListener(name, callback) { events.set(name, callback); }, removeEventListener(name) { events.delete(name); },
    getBoundingClientRect() { return { left: 0, top: 0, width, height }; },
    setPointerCapture(id) { pointer.value = id; }, hasPointerCapture(id) { return pointer.value === id; }, releasePointerCapture() { pointer.value = null; },
    toDataURL() { return 'data:image/png;base64,' + Buffer.from(pixels).toString('base64'); },
  };
  return { canvas, context, events, pixels: () => pixels, setPixels(value) { pixels = new Uint8ClampedArray(value); } };
}
const pointer = (x, y, id = 1, type = 'pointerdown') => ({ clientX: x, clientY: y, pointerId: id, pointerType: 'mouse', button: 0, type, preventDefault() {} });

// Track actual Canvas transforms to measure drawn hand centers and shoe soles.
// This observes renderer output rather than recreating its pose coordinates.
function trackedRender(character,options,frame=[12,23,205,305]) {
  const {context}=fakeCanvas(),stack=[],palms=[],soles=[];
  let matrix=[1,0,0,1,0,0],lastTranslate=null;
  const point=(x,y)=>({x:matrix[0]*x+matrix[2]*y+matrix[4],y:matrix[1]*x+matrix[3]*y+matrix[5]});
  for(const name of ['save','restore','translate','scale','rotate']) {
    const prior=context[name];
    context[name]=(...args)=>{
      prior.apply(context,args);
      if(name==='save')stack.push(matrix.slice());
      if(name==='restore')matrix=stack.pop();
      if(name==='translate'){const[x,y]=args;matrix[4]+=matrix[0]*x+matrix[2]*y;matrix[5]+=matrix[1]*x+matrix[3]*y;lastTranslate=args;}
      if(name==='scale'){const[x,y]=args;matrix[0]*=x;matrix[1]*=x;matrix[2]*=y;matrix[3]*=y;}
      if(name==='rotate'){const c=Math.cos(args[0]),s=Math.sin(args[0]),[a,b,u,d,e,f]=matrix;matrix=[a*c+u*s,b*c+d*s,-a*s+u*c,-b*s+d*c,e,f];
        if(lastTranslate?.[1]>=200&&lastTranslate[1]<=500)palms.push(point(0,14));
        if(lastTranslate?.[1]>500&&lastTranslate[1]<550)soles.push(point(0,215));
      }
    };
  }
  drawCharacter(context,character,...frame,options);
  return {context,palms,soles,balanced:stack.length===0};
}
const closePoint=(actual,expected)=>{assert.ok(Math.abs(actual.x-expected.x)<1e-8,`${actual.x} differs from ${expected.x}`);assert.ok(Math.abs(actual.y-expected.y)<1e-8,`${actual.y} differs from ${expected.y}`);};

test('canonical designs normalize names and colors without mutating originals', () => {
  const input = { name: "  Cafe\u0301  Hero ", primary_color: '#b49add', back: 'wings' };
  const result = normalizeDesign(input);
  assert.equal(result.name, 'Café Hero');
  assert.equal(result.primary_color, '#B49ADD');
  assert.equal(result.back, 'wings');
  assert.equal(input.name, "  Cafe\u0301  Hero ");
  assert.equal(DEFAULT_DESIGN.name, 'Spark');
  assert.equal(normalizeDesign({ name: '小星星' }).name, '小星星');
});

test('design imports reject scripts, unknown parts, invalid versions and colors', () => {
  for (const input of [null, [], { version: true }, { headwear: 'javascript:alert(1)' }, { name: '<script>' }, { name: 'Hero\nName' }, { primary_color: 'red' }, { image: '/etc/passwd' }, { name: ' '.repeat(33) }]) {
    assert.throws(() => normalizeDesign(input));
  }
  assert.throws(() => normalizeDesign({ name: 'A'.repeat(33) }));
});

test('all presets remain canonical, independently selectable original heroes', () => {
  assert.equal(PRESETS.length, 4);
  assert.equal(new Set(PRESETS.map(value => value.id)).size, 4);
  for (const preset of PRESETS) {
    assert.deepEqual(normalizeDesign(preset.design), preset.design);
    for (const [field, options] of Object.entries(OPTIONS)) assert.ok(options.some(option => option.value === preset.design[field]));
  }
});

test('renderer supports every part in every pose with finite canvas coordinates', () => {
  const examples = [...PRESETS.map(preset => preset.design), ...Object.entries(OPTIONS).flatMap(([field, options]) => options.map(option => ({ [field]: option.value })))];
  for (const design of examples) for (const motion of ['idle', 'wave', 'talk', 'celebrate','walk','point','carry','give','think']) {
    const { context } = fakeCanvas();
    drawCharacter(context, { source: 'builder', design }, 12, 23, 205, 305, { motion, time: .8 });
    assert.ok(context.commands.length > 100);
    assert.equal(context.commands.filter(command => command[0] === 'save').length, context.commands.filter(command => command[0] === 'restore').length);
    assert.ok(context.commands.flat().filter(value => typeof value === 'number').every(Number.isFinite));
  }
});

test('poses move the joints and talking mouth deterministically', () => {
  const hero = { source: 'builder', design: PRESETS[1].design };
  const render = (motion, time = .3) => { const { context } = fakeCanvas(); drawCharacter(context, hero, 0, 0, 600, 800, { motion, time }); return context.commands; };
  assert.notDeepEqual(render('wave'), render('idle'));
  assert.notDeepEqual(render('talk'), render('idle'));
  assert.notDeepEqual(render('celebrate'), render('wave'));
  assert.deepEqual(render('talk'), render('talk'));
  assert.throws(() => render('dance'));
  assert.throws(() => render('idle', Infinity));
});

test('new interaction anchors coincide with drawn palms for both facing directions and every pose',()=>{
  const hero={source:'builder',design:PRESETS[1].design};
  for(const motion of ['idle','wave','talk','celebrate','walk','point','carry','give','think'])for(const facing of ['left','right'])for(const time of [0,.4,1.3]){
    const options={motion,facing,time},render=trackedRender(hero,options),anchors=characterAnchors(hero,12,23,205,305,options);
    assert.equal(render.palms.length,2);assert.equal(render.balanced,true);
    closePoint(anchors.leftHand,render.palms[0]);closePoint(anchors.rightHand,render.palms[1]);
    for(const value of Object.values(anchors))assert.ok(Number.isFinite(value.x)&&Number.isFinite(value.y));
  }
});

test('facing mirrors the actor and its prop around the same fitted frame center',()=>{
  const hero={source:'builder',design:DEFAULT_DESIGN},frame=[100,70,200,220];
  const right=characterAnchors(hero,...frame,{motion:'give',time:.3}),left=characterAnchors(hero,...frame,{motion:'give',time:.3,facing:'left'});
  for(const key of ['leftHand','rightHand','head','feet','prop','body']){assert.ok(Math.abs(right[key].x+left[key].x-400)<1e-8);assert.equal(right[key].y,left[key].y);}
  const render=trackedRender(hero,{motion:'point',time:.3,facing:'left'});
  assert.equal(render.context.commands.filter(command=>command[0]==='scale'&&command[1]===-1&&command[2]===1).length,1);
  assert.equal(render.balanced,true);
});

test('point reaches out, carry grips a prop, give extends it, and think brings the palm to the face',()=>{
  const hero={source:'builder',design:DEFAULT_DESIGN},at=motion=>characterAnchors(hero,0,0,600,800,{motion,time:.4});
  const idle=at('idle'),point=at('point'),carry=at('carry'),give=at('give'),think=at('think');
  assert.ok(point.rightHand.x>idle.rightHand.x+50);assert.ok(point.rightHand.y<idle.rightHand.y-100);closePoint(point.prop,point.rightHand);
  for(const pose of [carry,give]){assert.ok(pose.prop.x>Math.min(pose.leftHand.x,pose.rightHand.x));assert.ok(pose.prop.x<Math.max(pose.leftHand.x,pose.rightHand.x));assert.ok(pose.prop.y<Math.min(pose.leftHand.y,pose.rightHand.y));}
  assert.ok(give.prop.x>carry.prop.x+30);
  const distance=(a,b)=>Math.hypot(a.x-b.x,a.y-b.y);assert.ok(distance(think.rightHand,think.head)<distance(idle.rightHand,idle.head)/2);
});

test('walking swings arms opposite to feet, while carrying can keep its grip and still walk',()=>{
  const hero={source:'builder',design:PRESETS[0].design};
  const idle=characterAnchors(hero,0,0,600,800,{motion:'idle'}),walk=trackedRender(hero,{motion:'walk',time:.4},[0,0,600,800]);
  assert.equal(walk.soles.length,2);
  assert.ok((walk.palms[1].x-idle.rightHand.x)*(walk.soles[1].x-345)<0);
  assert.ok((walk.palms[0].x-idle.leftHand.x)*(walk.soles[0].x-255)<0);
  const still=characterAnchors(hero,0,0,600,800,{motion:'carry',time:.4});
  const moving=characterAnchors(hero,0,0,600,800,{motion:'carry',time:.4,walking:true});
  assert.equal(still.leftHand.x,moving.leftHand.x);assert.equal(still.rightHand.x,moving.rightHand.x);
  const render=trackedRender(hero,{motion:'carry',time:.4,walking:true},[0,0,600,800]);
  assert.equal(render.soles.length,2);closePoint(moving.leftHand,render.palms[0]);closePoint(moving.rightHand,render.palms[1]);
});

test('characters can speak while carrying without replacing their grip with a talking pose',()=>{
  const hero={source:'builder',design:DEFAULT_DESIGN};
  const options={motion:'carry',walking:true,time:.3};
  const quiet=trackedRender(hero,options),talking=trackedRender(hero,{...options,speaking:true});
  assert.notDeepEqual(quiet.context.commands,talking.context.commands);
  assert.deepEqual(quiet.palms,talking.palms);
  assert.deepEqual(characterAnchors(hero,0,0,600,800,options),characterAnchors(hero,0,0,600,800,{...options,speaking:true}));
});

test('invalid or unbounded action geometry fails before drawing',()=>{
  const hero={source:'builder',design:DEFAULT_DESIGN};
  for(const frame of [[-1,0,600,800],[0,-1,600,800],[0,0,-1,800],[0,0,600,0],[0,0,Infinity,800],[0,0,600,10000]])assert.throws(()=>characterAnchors(hero,...frame));
  for(const options of [{time:-1},{time:Infinity},{time:1e15},{motion:'fly'},{facing:'up'},{speaking:'true'},{walking:'yes'}])assert.throws(()=>characterAnchors(hero,0,0,600,800,options));
  assert.throws(()=>drawCharacter(fakeCanvas().context,hero,0,0,600,800,{time:-1}));
});

test('ink bounds ignore transparent margins without modifying a single source pixel',()=>{
  const data=new Uint8ClampedArray(8*9*4),image={width:8,height:9,data};
  for(let y=2;y<7;y++)for(let x=1;x<3;x++)data.set([35,45,55,255],(y*8+x)*4);
  data.set([0,0,0,8],(8*8+7)*4);const original=data.slice();
  assert.deepEqual(drawingInkBounds(image),{left:1,top:2,right:3,bottom:7,width:2,height:5,centerX:2,centerY:4.5});
  assert.deepEqual(data,original);
  assert.equal(drawingInkBounds({width:2,height:2,data:new Uint8ClampedArray(16)}),null);
  for(const input of [null,{width:-1,height:2,data},{width:8,height:9,data:new Uint8ClampedArray(1)},{width:1,height:1,data:[0,0,0,255]}])assert.throws(()=>drawingInkBounds(input));
});

test('prepared off-center sketches carry props next to real ink rather than empty canvas space',async()=>{
  const oldDocument=globalThis.document,oldImage=globalThis.Image;
  globalThis.document={createElement:()=>{const fake=fakeCanvas(600,800);fake.context.drawImage=()=>{const pixels=fake.pixels();for(let y=250;y<430;y++)for(let x=90;x<120;x++)pixels.set([30,40,50,255],(y*600+x)*4);};return fake.canvas;}};
  globalThis.Image=class{constructor(){this.naturalWidth=100;this.naturalHeight=400;}set src(value){this.onload?.();}};
  try{
    const drawing={source:'drawing',image:'data:image/png;base64,AQ=='};const original=drawing.image;
    await prepareCharacter(drawing);
    const right=characterAnchors(drawing,0,0,600,800,{motion:'carry',time:0});
    closePoint(right.body,{x:105,y:358});closePoint(right.prop,{x:138,y:358});
    assert.equal(right.prop.x-120,18);assert.equal(right.feet.y,430);
    const left=characterAnchors(drawing,0,0,600,800,{motion:'carry',time:0,facing:'left'});
    assert.equal(left.body.x+right.body.x,600);assert.equal(left.body.y,right.body.y);
    assert.ok(left.prop.x<left.body.x);assert.ok(Math.hypot(left.prop.x-left.body.x,left.prop.y-left.body.y)<40);
    assert.equal(drawing.image,original);
  }finally{if(oldDocument===undefined)delete globalThis.document;else globalThis.document=oldDocument;if(oldImage===undefined)delete globalThis.Image;else globalThis.Image=oldImage;}
});

test('drawn characters participate through whole-sticker actions without invented limb paths',async()=>{
  const oldDocument=globalThis.document,oldImage=globalThis.Image;
  globalThis.document={createElement:()=>fakeCanvas(600,800).canvas};
  globalThis.Image=class{constructor(){this.naturalWidth=50;this.naturalHeight=60;}set src(value){this.onload?.();}};
  try{
    const character={source:'drawing',image:'data:image/png;base64,AA=='};await prepareCharacter(character);
    for(const motion of ['walk','point','carry','give','think']){
      const {context}=fakeCanvas();drawCharacter(context,character,12,23,140,200,{motion,time:.4,facing:'left',walking:true,speaking:true});
      assert.equal(context.commands.filter(command=>command[0]==='drawImage').length,1);
      assert.equal(context.commands.filter(command=>['begin','lineTo','stroke','fill'].includes(command[0])).length,0);
      const anchors=characterAnchors(character,12,23,140,200,{motion,time:.4,facing:'left',walking:true});
      assert.ok(anchors.prop.x<anchors.head.x);assert.ok(anchors.feet.y>anchors.head.y);
    }
  }finally{if(oldDocument===undefined)delete globalThis.document;else globalThis.document=oldDocument;if(oldImage===undefined)delete globalThis.Image;else globalThis.Image=oldImage;}
});

test('preparing builders is DOM-free and drawings cannot fetch external URLs', async () => {
  await prepareCharacter({ source: 'builder', design: DEFAULT_DESIGN });
  await assert.rejects(prepareCharacter({ source: 'drawing', image: 'https://example.com/child.png' }), /PNG or JPEG/);
  await assert.rejects(prepareCharacter({ source: 'drawing', image: 'data:image/svg+xml;base64,PHN2Zz4=' }), /PNG or JPEG/);
  await assert.rejects(prepareCharacter({ source: 'drawing', image: 'data:image/png;base64,' + 'A'.repeat(12 * 1024 * 1024) }), /8 MB/);
  await assert.rejects(prepareCharacter({ source: 'unknown' }), /saved character/);
  const { context } = fakeCanvas();
  assert.throws(() => drawCharacter(context, { source: 'drawing', image: 'not-prepared' }, 0, 0, 100, 100), /Prepare/);
  assert.equal(context.commands.filter(command => command[0] === 'save').length, context.commands.filter(command => command[0] === 'restore').length);
});

test('fill stays inside closed borders and a matching second fill is a no-op', () => {
  const fake = fakeCanvas(7, 7), pad = new DrawingPad(fake.canvas), pixels = fake.pixels().slice();
  for (let y = 1; y < 6; y += 1) for (let x = 1; x < 6; x += 1) if (x === 1 || x === 5 || y === 1 || y === 5) pixels.set([0, 0, 0, 255], (y * 7 + x) * 4);
  fake.setPixels(pixels); pad.setColor('#E77676');
  assert.equal(pad._floodFill({ x: 3, y: 3 }), true);
  assert.deepEqual(Array.from(fake.pixels().slice((3 * 7 + 3) * 4, (3 * 7 + 3) * 4 + 4)), [231, 118, 118, 255]);
  assert.deepEqual(Array.from(fake.pixels().slice(0, 4)), [255, 255, 255, 255]);
  assert.equal(pad._floodFill({ x: 3, y: 3 }), false);
});

test('full-size fill is iterative and covers all 604800 pixels', () => {
  const fake = fakeCanvas(720, 840), pad = new DrawingPad(fake.canvas); pad.setColor('#363249');
  assert.equal(pad._floodFill({ x: 719, y: 839 }), true);
  assert.deepEqual(Array.from(fake.pixels().slice(0, 4)), [54, 50, 73, 255]);
  assert.deepEqual(Array.from(fake.pixels().slice(-4)), [54, 50, 73, 255]);
});

test('shape previews commit one undo entry and a second touch is ignored', () => {
  const fake = fakeCanvas(), pad = new DrawingPad(fake.canvas);
  assert.equal(pad._history.length, 1);
  pad.setTool('rectangle'); pad._start(pointer(1, 1));
  pad._start(pointer(3, 3, 2)); assert.equal(pad._gesture.pointerId, 1);
  for (let i = 2; i < 8; i += 1) pad._move(pointer(i, i, 1, 'pointermove'));
  pad._end(pointer(4, 4, 2, 'pointerup')); assert.ok(pad._gesture);
  assert.equal(pad._history.length, 1);
  pad._end(pointer(7, 7, 1, 'pointerup'));
  assert.equal(pad._history.length, 2); assert.equal(pad.hasDrawing(), true);
  assert.equal(pad.undo(), true); assert.equal(pad.hasDrawing(), false);
  assert.equal(pad.redo(), true); assert.equal(pad.hasDrawing(), true);
});

test('cancelled gestures restore exact prior pixels and drawing state', () => {
  const fake = fakeCanvas(), pad = new DrawingPad(fake.canvas), before = fake.pixels().slice();
  pad.setTool('fill'); pad._start(pointer(3, 3)); pad._end(pointer(3, 3, 1, 'pointercancel'));
  assert.deepEqual(fake.pixels(), before); assert.equal(pad.hasDrawing(), false); assert.equal(pad._history.length, 1);
});

test('mirror draws paired strokes and clear can be undone without losing pixels', () => {
  const fake = fakeCanvas(), pad = new DrawingPad(fake.canvas); pad.setMirror(true);
  pad._start(pointer(1, 1)); pad._move(pointer(3, 4, 1, 'pointermove')); pad._end(pointer(3, 4, 1, 'pointerup'));
  const segments = fake.context.commands.filter(command => command[0] === 'lineTo');
  assert.ok(segments.some(command => command[1] === 3 && command[2] === 4));
  assert.ok(segments.some(command => command[1] === 8 && command[2] === 4));
  const before = fake.pixels().slice(); pad.clear(); assert.equal(pad.hasDrawing(), false);
  assert.equal(pad.undo(), true); assert.deepEqual(fake.pixels(), before); assert.equal(pad.hasDrawing(), true);
});

test('history is bounded and a new stroke safely replaces only redo history', () => {
  const fake = fakeCanvas(), pad = new DrawingPad(fake.canvas);
  for (let i = 0; i < 40; i += 1) { pad._start(pointer(1, 1)); pad._end(pointer(1, 1, 1, 'pointerup')); }
  assert.equal(pad._history.length, 24); assert.equal(pad._index, 23);
  pad.undo(); assert.equal(pad.canRedo(), true);
  pad._start(pointer(2, 2)); pad._end(pointer(2, 2, 1, 'pointerup'));
  assert.equal(pad.canRedo(), false); assert.equal(pad._history.length, 24);
});

test('constructor does not call an unassigned pad callback and disposal removes handlers', () => {
  const fake = fakeCanvas(); let changes = 0;
  const pad = new DrawingPad(fake.canvas, { onChange: () => { changes += 1; assert.ok(pad); } });
  assert.equal(changes, 0); assert.equal(fake.events.size, 5);
  pad._start(pointer(2, 2)); pad._end(pointer(2, 2, 1, 'pointerup')); assert.equal(changes, 1);
  pad.dispose(); assert.equal(fake.events.size, 0); assert.equal(pad._history.length, 0);
  pad._start(pointer(2, 2)); assert.equal(pad._gesture, null);
});
