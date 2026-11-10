import test from 'node:test';
import assert from 'node:assert/strict';
import {PictureLoader,decodeAuthoredPicture} from '../dist/modules/picture.js';
import {imageFileToDataURL} from '../dist/modules/library.js';

test('authored SVG uses HTML image decoding, produces PNG, and releases its temporary URL',async t=>{
  const old={Image:globalThis.Image,document:globalThis.document,createImageBitmap:globalThis.createImageBitmap,create:URL.createObjectURL,revoke:URL.revokeObjectURL};
  t.after(()=>{for(const key of ['Image','document','createImageBitmap'])if(old[key]===undefined)delete globalThis[key];else globalThis[key]=old[key];URL.createObjectURL=old.create;URL.revokeObjectURL=old.revoke;});
  const revoked=[],drawn=[];let output;
  URL.createObjectURL=()=> 'blob:authored-example';URL.revokeObjectURL=url=>revoked.push(url);
  globalThis.createImageBitmap=()=>{throw new Error('SVG bitmap decoding is deliberately unavailable.');};
  globalThis.Image=class{naturalWidth=900;naturalHeight=300;set src(value){this.value=value;if(value)queueMicrotask(()=>this.onload?.());}};
  globalThis.document={createElement:()=>output={width:0,height:0,getContext:()=>({fillRect(){},drawImage(...args){drawn.push(args);}}),toDataURL:type=>`data:${type};base64,example`}};
  assert.equal(await decodeAuthoredPicture(new Blob(['<svg/>'],{type:'image/svg+xml;charset=utf-8'})),'data:image/png;base64,example');
  assert.equal(output.width,900);assert.equal(output.height,300);assert.equal(drawn.length,1);assert.deepEqual(revoked,['blob:authored-example']);
});

test('authored PNG and image failures release URLs; visitor SVG uploads remain rejected',async t=>{
  const old={Image:globalThis.Image,create:URL.createObjectURL,revoke:URL.revokeObjectURL};
  t.after(()=>{if(old.Image===undefined)delete globalThis.Image;else globalThis.Image=old.Image;URL.createObjectURL=old.create;URL.revokeObjectURL=old.revoke;});
  const revoked=[];URL.createObjectURL=()=> 'blob:bad-picture';URL.revokeObjectURL=url=>revoked.push(url);
  globalThis.Image=class{set src(value){if(value)queueMicrotask(()=>this.onerror?.());}};
  await assert.rejects(decodeAuthoredPicture(new Blob(['broken'],{type:'image/png'})),/could not be decoded/);
  assert.deepEqual(revoked,['blob:bad-picture']);
  await assert.rejects(imageFileToDataURL({type:'image/svg+xml',size:20}),/PNG, JPEG, or WebP/);
});

test('a newer picture wins even if an older decoder finishes later',async()=>{
  const events=[];let firstResolve,secondResolve,firstSignal;
  const loader=new PictureLoader({onStart:id=>events.push(['start',id]),onCommit:(image,meta,id)=>events.push(['commit',id,image]),onFinish:id=>events.push(['finish',id])});
  const first=loader.load(({signal})=>{firstSignal=signal;return new Promise(resolve=>firstResolve=resolve);});
  assert.equal(loader.loading,true);
  const second=loader.load(()=>new Promise(resolve=>secondResolve=resolve));assert.equal(firstSignal.aborted,true);
  secondResolve('new');assert.equal(await second,true);assert.equal(loader.loading,false);
  firstResolve('old');assert.equal(await first,false);
  assert.deepEqual(events,[['start',1],['start',2],['commit',2,'new'],['finish',2]]);
});

test('an obsolete error cannot show a failure or unlock the active newer request',async()=>{
  const events=[];let rejectOld,resolveNew;
  const loader=new PictureLoader({onError:error=>events.push(error.message),onFinish:id=>events.push(['finish',id])});
  const first=loader.load(()=>new Promise((resolve,reject)=>rejectOld=reject));
  const second=loader.load(()=>new Promise(resolve=>resolveNew=resolve));
  rejectOld(new Error('Old decode failed'));await first;assert.equal(loader.loading,true);assert.deepEqual(events,[]);
  resolveNew('new');await second;assert.deepEqual(events,[['finish',2]]);
});

test('cancelling a picture prevents late commits and leaves the next request usable',async()=>{
  const commits=[];let resolveOld;const loader=new PictureLoader({onCommit:value=>commits.push(value)});
  const old=loader.load(()=>new Promise(resolve=>resolveOld=resolve));loader.cancel();assert.equal(loader.loading,false);
  await loader.load(async()=> 'fresh');resolveOld('obsolete');assert.equal(await old,false);assert.deepEqual(commits,['fresh']);
});
