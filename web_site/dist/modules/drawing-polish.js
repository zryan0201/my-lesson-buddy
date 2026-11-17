/** Browser-local restoration client. No worker or download until requested. */
import {POLISH_MODEL,checkPolishPixels,blendPolish} from './drawing-polish-core.js';
let worker=null,active=null,sequence=0;
function abortError(){return new DOMException('Enhancement cancelled. Your original drawing is safe.','AbortError');}
export function polishStatus(){return globalThis.isSecureContext!==false&&typeof Worker==='function'&&typeof WebAssembly==='object'?{supported:true,reason:'Local AI is ready to try. Your drawing stays on this device.'}:{supported:false,reason:'Local AI is unavailable in this browser. Your original drawing can still star in a lesson.'};}
export function disposeDrawingPolish(){active?.cancel();worker?.terminate();worker=null;}
export async function enhanceDrawingPixels(image,{signal,onProgress}={}){
  checkPolishPixels(image);if(signal?.aborted)throw abortError();
  if(!polishStatus().supported)throw new Error(polishStatus().reason);
  if(active)throw new Error('One drawing at a time. Finish or cancel the current enhancement.');
  if(!worker)worker=new Worker(new URL('./drawing-polish-worker.js',import.meta.url),{type:'module',name:'drawing-polish'});
  const current=worker,id=`polish-${++sequence}`;
  return await new Promise((resolve,reject)=>{
    let finished=false;
    const clean=()=>{clearTimeout(timer);signal?.removeEventListener('abort',cancel);for(const type of ['error','messageerror'])current.removeEventListener(type,failed);current.removeEventListener('message',message);if(active?.id===id)active=null;};
    const settle=(error,result,terminate=false)=>{if(finished)return;finished=true;clean();if(terminate){current.terminate();if(worker===current)worker=null;}error?reject(error):resolve(result);};
    const cancel=()=>settle(abortError(),null,true),failed=()=>settle(new Error('Local AI could not finish. Your original is safe. Try again or use your drawing as it is.'),null,true);
    const message=({data})=>{
      if(!data||data.id!==id)return;
      if(data.type==='progress'){try{onProgress?.({stage:data.stage==='enhancing'?'enhancing':'loading',progress:Number.isFinite(data.progress)?Math.max(0,Math.min(100,data.progress)):undefined});}catch{}}
      else if(data.type==='result'){
        try{checkPolishPixels(data.image,{output:true});if(data.image.width!==image.width*2||data.image.height!==image.height*2)throw new Error();settle(null,data.image);}catch{failed();}
      }else if(data.type==='error')failed();
    };
    const timer=setTimeout(()=>settle(new Error('Local AI took too long. Your original is safe. Try again or keep drawing.'),null,true),POLISH_MODEL.timeoutMs);
    active={id,cancel};current.addEventListener('message',message);for(const type of ['error','messageerror'])current.addEventListener(type,failed);signal?.addEventListener('abort',cancel,{once:true});
    if(signal?.aborted){cancel();return;}
    try{current.postMessage({type:'polish',id,image:{width:image.width,height:image.height,data:new Uint8ClampedArray(image.data)}});}catch{failed();}
  });
}
export function composePolish(original,learned,strength){return blendPolish(original,learned,strength);}
export async function readPolishPNG(source,{maxEdge=POLISH_MODEL.maxEdge*2}={}){
  if(typeof source!=='string'||source.length>12*1024*1024||!/^data:image\/png;base64,[a-z0-9+/]+=*$/i.test(source))throw new Error('Draw or import a PNG in the studio first.');
  const image=await new Promise((resolve,reject)=>{const img=new Image();img.onload=()=>resolve(img);img.onerror=()=>reject(new Error('This drawing could not be opened.'));img.src=source;});
  if(image.naturalWidth<1||image.naturalHeight<1||image.naturalWidth>maxEdge||image.naturalHeight>maxEdge)throw new Error('Use the studio canvas for local enhancement.');
  const canvas=document.createElement('canvas');canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;const ctx=canvas.getContext('2d',{willReadFrequently:true});ctx.drawImage(image,0,0);
  return ctx.getImageData(0,0,canvas.width,canvas.height);
}
export async function prepareDrawingPolish(source){
  const pixels=await readPolishPNG(source,{maxEdge:POLISH_MODEL.maxEdge});
  let hasInk=false;for(let n=0;n<pixels.data.length;n+=4)if(pixels.data[n+3]>8&&Math.min(pixels.data[n],pixels.data[n+1],pixels.data[n+2])<235){hasInk=true;break;}
  if(!hasInk)throw new Error('Add a few visible lines or colors before trying AI polish.');
  const canvas=document.createElement('canvas');canvas.width=pixels.width;canvas.height=pixels.height;canvas.getContext('2d').putImageData(pixels,0,0);
  const larger=document.createElement('canvas');larger.width=canvas.width*2;larger.height=canvas.height*2;const out=larger.getContext('2d',{willReadFrequently:true});out.imageSmoothingEnabled=true;out.imageSmoothingQuality='high';out.drawImage(canvas,0,0,larger.width,larger.height);
  return{image:pixels,baseline:out.getImageData(0,0,larger.width,larger.height)};
}
export function polishPNG(pixels){
  checkPolishPixels(pixels,{output:true});const canvas=document.createElement('canvas');canvas.width=pixels.width;canvas.height=pixels.height;
  canvas.getContext('2d').putImageData(new ImageData(new Uint8ClampedArray(pixels.data),pixels.width,pixels.height),0,0);return canvas.toDataURL('image/png');
}
