/** Optional same-origin companion. Public hosting never sends images to localhost. */
const LOCAL_HOSTS=new Set(['127.0.0.1','localhost']);
const styles=new Set(['soft3d','storybook','comic']),strengths=new Set(['gentle','balanced','creative']);
let active=false;
function aborted(){return new DOMException('Cartoon makeover cancelled. Your original is safe.','AbortError');}
export function cartoonOptions(value={}){
  if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).some(key=>!['idea','style','strength','seed'].includes(key)))throw new Error('Choose the displayed cartoon options.');
  const out={idea:value.idea??'',style:value.style??'soft3d',strength:value.strength??'balanced',seed:value.seed??24};
  if(typeof out.idea!=='string'||out.idea.length>240||/[\x00-\x1f\x7f]/.test(out.idea)||!styles.has(out.style)||!strengths.has(out.strength)||!Number.isInteger(out.seed)||out.seed<0||out.seed>=2**31)throw new Error('Choose a supported character idea, style, change level, and seed.');
  return out;
}
function local(){return globalThis.location?.protocol==='http:'&&LOCAL_HOSTS.has(globalThis.location?.hostname);}
export async function cartoonStatus(){
  if(!local())return{ready:false,localStudio:false,message:'Cartoon redraw runs in the local studio on your computer. The shared site can use its exported character packages.'};
  try{const r=await fetch('/api/cartoon/status',{cache:'no-store'});if(!r.ok)throw new Error();const d=await r.json();return{ready:d.ready===true,localStudio:true,message:d.ready===true?'The local cartoon model is ready. Your drawing stays on this computer.':'A grown-up needs to run local cartoon setup first (about 3.5 GB).'};}
  catch{return{ready:false,localStudio:false,message:'Open the local cartoon studio after setup to use this feature.'};}
}
function sleep(ms,signal){return new Promise((resolve,reject)=>{if(signal?.aborted){reject(aborted());return;}const abort=()=>{clearTimeout(timer);reject(aborted());};const timer=setTimeout(()=>{signal?.removeEventListener('abort',abort);resolve();},ms);signal?.addEventListener('abort',abort,{once:true});});}
async function imageHash(source){const raw=atob(source.split(',')[1]),bytes=Uint8Array.from(raw,ch=>ch.charCodeAt(0));return[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(n=>n.toString(16).padStart(2,'0')).join('');}
export async function redrawDrawing(source,options={}, {signal,onProgress}={}){
  options=cartoonOptions(options);
  if(typeof source!=='string'||source.length>11*1024*1024||!/^data:image\/(?:png|jpeg);base64,[a-z0-9+/]+=*$/i.test(source))throw new Error('Draw or import a bounded PNG or JPEG first.');
  if(!local())throw new Error('Use the local cartoon studio to redraw a character.');
  if(active)throw new Error('One cartoon at a time. Finish or cancel the current makeover.');
  if(signal?.aborted)throw aborted();active=true;
  let job=null,complete=false;
  const headers=()=>({'X-Lesson-Buddy-Local':'1',...(job?{'Authorization':`Bearer ${job.token}`}:{})});
  try{
    const hash=await imageHash(source);if(signal?.aborted)throw aborted();
    // Receive the job token even if cancelled during submission, then cancel it.
    const response=await fetch('/api/cartoon/jobs',{method:'POST',headers:{...headers(),'Content-Type':'application/json'},body:JSON.stringify({image:source,options})});
    if(!response.ok)throw new Error(response.status===409?'Another local makeover is still running. Wait a moment and try again.':'The local model could not start. Check setup and try again.');
    job=await response.json();
    if(!/^[a-f0-9]{32}$/.test(job.id)||typeof job.token!=='string'||!/^[A-Za-z0-9_-]{24,80}$/.test(job.token)||job.source_sha256!==hash)throw new Error('The local job did not match this drawing.');
    const deadline=Date.now()+8*60*1000;
    while(true){
      if(signal?.aborted)throw aborted();if(Date.now()>deadline)throw new Error('The cartoon took too long. Your original is safe.');
      const result=await fetch(`/api/cartoon/jobs/${job.id}`,{headers:headers(),cache:'no-store',signal});if(!result.ok)throw new Error('The local makeover is no longer available.');
      const current=await result.json();if(current.source_sha256!==hash)throw new Error('The cartoon no longer matches this drawing.');
      if(current.state==='ready'){
        const image=await fetch(`/api/cartoon/jobs/${job.id}/image`,{headers:headers(),cache:'no-store',signal});if(!image.ok||!image.headers.get('content-type')?.startsWith('image/png'))throw new Error('The local model returned an unusable character.');
        const blob=await image.blob();if(blob.size>8*1024*1024)throw new Error('The cartoon is too large to use. Try again.');
        const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(new Error('The cartoon preview could not open.'));reader.readAsDataURL(blob);});
        if(signal?.aborted)throw aborted();complete=true;return{image:data,evidence:current.evidence};
      }
      if(current.state==='cancelled')throw aborted();
      if(current.state==='error')throw new Error('This version could not pass the model or drawing checks. Try Gentle or a clearer description. Your original is safe.');
      onProgress?.({stage:['loading','generating','checking'].includes(current.stage)?current.stage:'loading',progress:Number.isFinite(current.progress)?Math.min(100,Math.max(0,current.progress)):0});
      await sleep(700,signal);
    }
  }finally{
    if(job&&!complete&&/^[a-f0-9]{32}$/.test(job.id))try{await fetch(`/api/cartoon/jobs/${job.id}`,{method:'DELETE',headers:headers()});}catch{}
    active=false;
  }
}
