/** No model, worker, or network download begins just by importing this module. */
import {BUDDY_MODEL,validateBuddyIdea,parseBuddyDesign,BuddyDesignError} from './buddy-design.js';
let worker=null,active=null,sequence=0;
function abortError(){const e=new Error('Buddy creation cancelled. Your earlier character is safe.');e.name='AbortError';return e;}
export async function buddyAIStatus(){
  if(globalThis.isSecureContext===false||typeof globalThis.Worker!=='function')return {supported:false,reason:'Local AI is unavailable here. You can still build or draw a buddy.'};
  try{const adapter=await globalThis.navigator?.gpu?.requestAdapter?.();if(adapter?.features?.has('shader-f16'))return {supported:true,device:'webgpu',reason:'This browser can run local character AI. Check the proposal and change any parts you like.'};}catch{}
  return {supported:false,reason:'This device cannot run this optional local AI model. Try a compatible Chrome or Edge browser, or use Build it and Draw it here.'};
}
export function disposeBuddyAI(){active?.cancel();worker?.terminate();worker=null;}
export async function generateBuddy(idea,{signal,onProgress}={}){
  const text=validateBuddyIdea(idea);
  if(active)throw new BuddyDesignError('A buddy is already being imagined. Finish or cancel it first.','BUSY');
  if(signal?.aborted)throw abortError();
  const request={cancelled:false,cancel(){this.cancelled=true;}};active=request;
  try{
    const status=await buddyAIStatus();
    if(signal?.aborted||request.cancelled)throw abortError();
    if(!status.supported)throw new BuddyDesignError(status.reason,'UNSUPPORTED');
    if(!worker)worker=new Worker(new URL('./buddy-worker.js',import.meta.url),{type:'module',name:'buddy-designer'});
    const current=worker,id=`buddy-${++sequence}`;
    return await new Promise((resolve,reject)=>{
      let finished=false;
      const clean=()=>{clearTimeout(timer);signal?.removeEventListener('abort',cancel);for(const type of ['error','messageerror'])current.removeEventListener(type,failed);current.removeEventListener('message',message);};
      const settle=(error,result,terminate=false)=>{
        if(finished)return;finished=true;clean();
        if(terminate){current.terminate();if(worker===current)worker=null;}
        if(error)reject(error);else resolve(result);
      };
      const cancel=()=>settle(abortError(),null,true);request.cancel=cancel;
      const failed=()=>settle(new BuddyDesignError('Local AI could not finish. Try again, or use Build it.','UNAVAILABLE'),null,true);
      const message=({data})=>{
        if(!data||data.id!==id)return;
        if(data.type==='progress'){
          const progress={stage:data.stage==='generating'?'generating':'loading',message:data.stage==='generating'?'Imagining an editable buddy on this device…':'Downloading or preparing local AI…'};
          for(const key of ['progress','loaded','total'])if(Number.isFinite(data[key])&&data[key]>=0)progress[key]=key==='progress'?Math.min(100,data[key]):data[key];
          try{onProgress?.(progress);}catch{}
        }else if(data.type==='result'){
          try{settle(null,parseBuddyDesign(data.raw));}catch(error){settle(error);}
        }else if(data.type==='error')failed();
      };
      const timer=setTimeout(()=>settle(new BuddyDesignError('Local AI took too long. Try fewer words, or use Build it.','TIMEOUT'),null,true),BUDDY_MODEL.timeoutMs);
      current.addEventListener('message',message);for(const type of ['error','messageerror'])current.addEventListener(type,failed);
      signal?.addEventListener('abort',cancel,{once:true});
      if(signal?.aborted){cancel();return;}
      try{current.postMessage({type:'describe',id,idea:text,device:status.device});}catch{failed();}
    });
  }finally{if(active===request)active=null;}
}
