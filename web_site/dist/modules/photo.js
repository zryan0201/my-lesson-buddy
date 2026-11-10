/* Browser-only scan preparation: retain the original; correct pixels locally. */
import {findPaperQuad,validateCorners,warpPerspective} from './photo-geometry.js';
import {normalizePaperLighting} from './lighting.js';
const fullCorners=()=>[{x:0,y:0},{x:1,y:0},{x:1,y:1},{x:0,y:1}];
function cancelled(){const error=new Error('Photo preparation was cancelled.');error.name='AbortError';return error;}
function check(signal){if(signal?.aborted)throw cancelled();}
function makeCanvas(width,height){const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;const ctx=canvas.getContext('2d',{willReadFrequently:true});if(!ctx)throw new Error('This browser could not prepare the worksheet photograph.');return{canvas,ctx};}
async function decode(dataURL,signal){
  if(typeof dataURL!=='string'||dataURL.length>16_000_000||!/^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/]+={0,2}$/.test(dataURL))throw new Error('Choose a PNG, JPEG, or WebP worksheet photograph.');
  check(signal);const image=new Image();
  await new Promise((resolve,reject)=>{const clean=()=>{image.onload=null;image.onerror=null;signal?.removeEventListener('abort',abort);};const abort=()=>{clean();image.src='';reject(cancelled());};image.onload=()=>{clean();resolve();};image.onerror=()=>{clean();reject(new Error('This worksheet photograph could not be opened.'));};signal?.addEventListener('abort',abort,{once:true});if(signal?.aborted){abort();return;}image.src=dataURL;});
  check(signal);if(!image.naturalWidth||!image.naturalHeight||image.naturalWidth*image.naturalHeight>12_000_000)throw new Error('Choose a worksheet photograph with fewer than 12 million pixels.');return image;
}

export async function processWorksheetPhoto(dataURL,{corners=null,reduceShadows=true,signal}={}){
  if(typeof reduceShadows!=='boolean')throw new Error('Choose whether to reduce shadows.');
  if(corners!==null)validateCorners(corners);check(signal);
  const image=await decode(dataURL,signal),scale=Math.min(1,1600/Math.max(image.naturalWidth,image.naturalHeight)),source=makeCanvas(Math.max(2,Math.round(image.naturalWidth*scale)),Math.max(2,Math.round(image.naturalHeight*scale)));
  source.ctx.fillStyle='#fff';source.ctx.fillRect(0,0,source.canvas.width,source.canvas.height);source.ctx.drawImage(image,0,0,source.canvas.width,source.canvas.height);const sourceWidth=source.canvas.width,sourceHeight=source.canvas.height,original=source.ctx.getImageData(0,0,sourceWidth,sourceHeight);check(signal);
  const found=corners?{corners:validateCorners(corners,{width:sourceWidth,height:sourceHeight}),confidence:1,framed:false}:findPaperQuad(original.data,sourceWidth,sourceHeight);
  if(!found.corners)return{image:source.canvas.toDataURL('image/png'),corners:fullCorners(),detected:false,status:'needs-corners',message:found.reason,stats:{sourceWidth,sourceHeight,outputWidth:sourceWidth,outputHeight:sourceHeight,detectionConfidence:found.confidence,manual:false},steps:{cropped:false,perspective:false,shadows:false}};
  const selected=found.corners,full=fullCorners(),geometryChanged=selected.some((p,i)=>Math.hypot(p.x-full[i].x,p.y-full[i].y)>.003);
  const perspective=geometryChanged&&(Math.abs(selected[0].y-selected[1].y)>.005||Math.abs(selected[2].y-selected[3].y)>.005||Math.abs(selected[0].x-selected[3].x)>.005||Math.abs(selected[1].x-selected[2].x)>.005);
  const warped=geometryChanged?warpPerspective(original.data,sourceWidth,sourceHeight,selected):{pixels:original.data,width:sourceWidth,height:sourceHeight};check(signal);
  const lighting=reduceShadows?normalizePaperLighting(warped.pixels,warped.width,warped.height):{pixels:warped.pixels,applied:false,stats:{reason:'Shadow reduction is off.'}};check(signal);
  const out=makeCanvas(warped.width,warped.height),output=out.ctx.createImageData(warped.width,warped.height);output.data.set(lighting.pixels);out.ctx.putImageData(output,0,0);
  const changed=geometryChanged||lighting.applied;
  const lightingWarning=reduceShadows&&['too-dark-or-uncertain','lighting-too-uneven','not-enough-neutral-paper'].includes(lighting.stats?.reason);
  const message=lightingWarning?'The paper area was kept, but its lighting could not be corrected reliably. Try a brighter, evenly lit photo, or check the original and select objects manually.':changed?'The worksheet is straightened and ready to check. Keep every object and symbol in the preview.':'The worksheet already looks clear. Check the picture before reading or selecting its objects.';
  return{image:out.canvas.toDataURL('image/png'),corners:selected.map(p=>({...p})),detected:!corners,status:changed?'corrected':'unchanged',message,stats:{sourceWidth,sourceHeight,outputWidth:warped.width,outputHeight:warped.height,detectionConfidence:found.confidence,manual:corners!==null,lighting:lighting.stats,lightingWarning},steps:{cropped:geometryChanged,perspective,shadows:lighting.applied}};
}
