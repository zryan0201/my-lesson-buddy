/* These fixed original-art fixtures simulate camera conditions. They are not
 * real phone photographs or a measured classroom accuracy benchmark. */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {inflateSync} from 'node:zlib';
import {findPaperQuad,validateCorners,warpPerspective} from '../dist/modules/photo-geometry.js';
import {normalizePaperLighting} from '../dist/modules/lighting.js';
import {findObjectCandidates} from '../dist/modules/objects.js';

function fixture(name){
  const file=new URL(`./fixtures/photo/${name}.json`,import.meta.url),value=JSON.parse(fs.readFileSync(file,'utf8'));
  return{...value,pixels:new Uint8ClampedArray(inflateSync(Buffer.from(value.pixelsZlibBase64,'base64')))};
}
function prepare(value){
  const geometry=findPaperQuad(value.pixels,value.width,value.height);
  const selected=geometry.corners&&!geometry.framed?warpPerspective(value.pixels,value.width,value.height,geometry.corners):value;
  const lighting=normalizePaperLighting(selected.pixels,selected.width,selected.height);
  const objects=findObjectCandidates(lighting.pixels,selected.width,selected.height,{expectedCount:value.metadata.expectedCount});
  return{geometry,selected,lighting,objects};
}

test('original clean worksheet pixels are not cropped or relit and keep every original object',()=>{
  for(const name of ['clean_popsicles','clean_yellow_dots']){
    const source=fixture(name),original=source.pixels.slice(),result=prepare(source);
    assert.equal(result.geometry.framed,true);assert.equal(result.lighting.applied,false);
    assert.deepEqual(result.lighting.pixels,original);assert.deepEqual(source.pixels,original);
    assert.equal(result.objects.complete,true);assert.equal(result.objects.boxes.length,source.metadata.expectedCount);
  }
});

test('synthetic perspective photograph rectifies the full paper and retains seven original popsicles',()=>{
  const source=fixture('popsicle_perspective'),original=source.pixels.slice(),result=prepare(source);
  assert.equal(source.metadata.realPhonePhoto,false);assert.ok(result.geometry.corners);assert.ok(result.geometry.confidence>.75);
  const error=Math.max(...result.geometry.corners.map((p,i)=>Math.hypot(p.x-source.metadata.paperCorners[i].x,p.y-source.metadata.paperCorners[i].y)));
  assert.ok(error<.035,'paper corners stay close to the known synthetic page corners');
  assert.equal(result.objects.complete,true);assert.equal(result.objects.boxes.length,7);
  assert.ok(result.selected.width<source.width&&result.selected.height<source.height);
  assert.deepEqual(source.pixels,original,'correction never changes the source photograph');
});

test('synthetic shadow photograph becomes extractable after local paper-light correction',()=>{
  const source=fixture('popsicle_shadow'),result=prepare(source);
  const before=findObjectCandidates(result.selected.pixels,result.selected.width,result.selected.height,{expectedCount:7});
  assert.equal(before.complete,false,'the shadowed paper fails the existing extraction gate before lighting correction');
  assert.equal(result.lighting.applied,true);assert.ok(result.lighting.stats.fieldRange>20);
  assert.equal(result.objects.complete,true);assert.equal(result.objects.boxes.length,7);
  assert.ok(result.objects.boxes.every(box=>box.width>15&&box.height>25),'real artwork remains large enough to see');
});

test('synthetic yellow-dot photo preserves its different original art and five-object count',()=>{
  const source=fixture('yellow_dots_photo'),result=prepare(source);
  assert.ok(result.geometry.corners);assert.equal(result.lighting.applied,true);
  assert.equal(result.objects.complete,true);assert.equal(result.objects.boxes.length,5);
  assert.ok(result.objects.boxes.every(box=>Math.max(box.width,box.height)/Math.min(box.width,box.height)<1.15),'circular source art remains approximately circular after rectification');
});

test('clipped paper is left for manual corner review instead of proposing a smaller misleading crop',()=>{
  const source=fixture('clipped_paper'),result=prepare(source);
  assert.equal(result.geometry.corners,null);assert.equal(result.objects.complete,false);
  assert.throws(()=>validateCorners(source.metadata.paperCorners,{width:source.width,height:source.height}));
});

test('very dark synthetic photographs are not brightened by guessing colors or inventing objects',()=>{
  const source=fixture('low_light'),result=prepare(source);
  assert.equal(result.lighting.applied,false);assert.equal(result.objects.complete,false);
  assert.equal(result.objects.boxes.length,0);assert.equal(result.lighting.stats.reason,'too-dark-or-uncertain');
});

test('reviewed math only validates extraction and never forces a photographed object count',()=>{
  const source=fixture('popsicle_shadow'),result=prepare(source);
  const wrong=findObjectCandidates(result.lighting.pixels,result.selected.width,result.selected.height,{expectedCount:6});
  assert.equal(wrong.complete,false);assert.equal(wrong.boxes.length,7);assert.match(wrong.reason,/needs 6/);
});
