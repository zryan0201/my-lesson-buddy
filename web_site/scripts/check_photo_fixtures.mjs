/** Synthetic camera-condition evidence, not a real phone-photo benchmark. */
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {inflateSync} from 'node:zlib';
import {findPaperQuad,warpPerspective} from '../dist/modules/photo-geometry.js';
import {normalizePaperLighting} from '../dist/modules/lighting.js';
import {findObjectCandidates} from '../dist/modules/objects.js';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const fixtures=path.join(root,'web_site/tests/fixtures/photo');
const output=path.join(root,'output/photo_worksheets');
fs.mkdirSync(output,{recursive:true});
const rows=[];
for(const file of fs.readdirSync(fixtures).filter(file=>file.endsWith('.json')).sort()){
  const f=JSON.parse(fs.readFileSync(path.join(fixtures,file),'utf8'));
  const pixels=new Uint8ClampedArray(inflateSync(Buffer.from(f.pixelsZlibBase64,'base64')));
  const detected=findPaperQuad(pixels,f.width,f.height);
  let selected={pixels,width:f.width,height:f.height};
  if(detected.corners&&!detected.framed)selected=warpPerspective(pixels,f.width,f.height,detected.corners);
  const objectsBefore=findObjectCandidates(selected.pixels,selected.width,selected.height,{expectedCount:f.metadata.expectedCount});
  const light=normalizePaperLighting(selected.pixels,selected.width,selected.height);
  const objects=findObjectCandidates(light.pixels,selected.width,selected.height,{expectedCount:f.metadata.expectedCount});
  const cornerError=f.metadata.paperCorners&&detected.corners?Math.max(...detected.corners.map((p,i)=>Math.hypot(p.x-f.metadata.paperCorners[i].x,p.y-f.metadata.paperCorners[i].y))):null;
  rows.push({fixture:file,metadata:f.metadata,detection:detected,maxNormalizedCornerError:cornerError,output:{width:selected.width,height:selected.height},lighting:{applied:light.applied,stats:light.stats},objectsBeforeLighting:objectsBefore,objects});
  fs.writeFileSync(path.join(output,file.replace('.json','_corrected.rgba')),light.pixels);
  fs.writeFileSync(path.join(output,file.replace('.json','_corrected_size.json')),JSON.stringify({width:selected.width,height:selected.height}));
}
const report={description:'Reproducible synthetic viewpoint, lighting and JPEG cases. These results do not measure real camera accuracy.',cases:rows};
fs.writeFileSync(path.join(output,'pixel_pipeline_report.json'),JSON.stringify(report,null,2)+'\n');
for(const row of rows)console.log(JSON.stringify({fixture:row.fixture,detected:!!row.detection.corners,framed:row.detection.framed,confidence:row.detection.confidence,cornerError:row.maxNormalizedCornerError,lighting:row.lighting.applied,objects:row.objects.boxes.length,complete:row.objects.complete,reason:row.objects.reason}));
