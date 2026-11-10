/** Rasterize only the app's authored example assets. SVG uploads from visitors
 * stay disallowed by the separate imageFileToDataURL upload validator. */
function aborted() {
  const error=new Error('Picture loading was cancelled.');error.name='AbortError';return error;
}

export async function decodeAuthoredPicture(blob,{signal}={}) {
  const type=String(blob?.type||'').split(';',1)[0].trim().toLowerCase();
  if(!blob||!['image/png','image/jpeg','image/webp','image/svg+xml'].includes(type)||blob.size>8*1024*1024)throw new Error('The example picture could not be opened.');
  if(signal?.aborted)throw aborted();
  const url=URL.createObjectURL(blob),image=new Image();
  try {
    await new Promise((resolve,reject)=>{
      const clean=()=>{image.onload=null;image.onerror=null;signal?.removeEventListener('abort',cancel);};
      const cancel=()=>{clean();image.src='';reject(aborted());};
      image.onload=()=>{clean();resolve();};
      image.onerror=()=>{clean();reject(new Error('The example picture could not be decoded. Please try another example.'));};
      signal?.addEventListener('abort',cancel,{once:true});
      if(signal?.aborted){cancel();return;}
      image.src=url;
    });
    if(signal?.aborted)throw aborted();
    const width=image.naturalWidth,height=image.naturalHeight;
    if(!Number.isInteger(width)||!Number.isInteger(height)||width<1||height<1||width*height>12_000_000)throw new Error('The example picture has unsupported dimensions.');
    const scale=Math.min(1,1600/Math.max(width,height));
    const canvas=document.createElement('canvas');canvas.width=Math.max(1,Math.round(width*scale));canvas.height=Math.max(1,Math.round(height*scale));
    const context=canvas.getContext('2d');if(!context)throw new Error('This browser could not prepare the example picture.');
    context.fillStyle='#ffffff';context.fillRect(0,0,canvas.width,canvas.height);
    context.drawImage(image,0,0,canvas.width,canvas.height);
    return canvas.toDataURL('image/png');
  } finally {image.onload=null;image.onerror=null;image.src='';URL.revokeObjectURL(url);}
}

/** One visible picture request owns the form. A slower earlier decoder cannot
 * overwrite a later choice, show an obsolete failure, or unlock its controls. */
export class PictureLoader {
  constructor({onStart=()=>{},onCommit=()=>{},onError=()=>{},onFinish=()=>{}}={}) {
    this.onStart=onStart;this.onCommit=onCommit;this.onError=onError;this.onFinish=onFinish;
    this.version=0;this.active=null;
  }
  get loading(){return this.active!==null;}
  async load(decode,metadata={}) {
    const previous=this.active;const request={version:++this.version,controller:new AbortController()};
    this.active=request;previous?.controller.abort();
    this.onStart(request.version,metadata);
    const current=()=>this.active===request&&!request.controller.signal.aborted;
    try {
      const picture=await decode({signal:request.controller.signal,version:request.version});
      if(!current())return false;
      this.onCommit(picture,metadata,request.version);
      return true;
    } catch(error) {
      if(current()&&error.name!=='AbortError')this.onError(error,metadata,request.version);
      return false;
    } finally {
      if(this.active===request){this.active=null;this.onFinish(request.version,metadata);}
    }
  }
  cancel() {
    const request=this.active;this.active=null;this.version++;
    if(request){request.controller.abort();this.onFinish(request.version);}
  }
}
