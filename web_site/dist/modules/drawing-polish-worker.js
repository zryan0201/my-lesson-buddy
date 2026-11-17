import {POLISH_MODEL,checkPolishPixels,polishTiles,polishTilePixels,placePolishTile} from './drawing-polish-core.js';
let runtimePromise=null,upscaler=null,busy=false,activeId=null,backend='wasm';
function runtime(){
  if(!runtimePromise)runtimePromise=import('../vendor/transformers.js').then(api=>{
    api.env.allowLocalModels=false;api.env.useBrowserCache=true;
    api.env.backends.onnx.wasm.wasmPaths=new URL('../vendor/ort/',import.meta.url).href;
    api.env.backends.onnx.wasm.numThreads=1;api.env.backends.onnx.wasm.proxy=false;return api;
  });return runtimePromise;
}
self.addEventListener('message',async({data})=>{
  if(!data||data.type!=='polish'||!/^polish-\d+$/.test(data.id)||busy)return;
  busy=true;activeId=data.id;
  try{
    const source=checkPolishPixels(data.image),{pipeline,RawImage}=await runtime();
    const load=async device=>pipeline('image-to-image',POLISH_MODEL.modelId,{revision:POLISH_MODEL.revision,dtype:POLISH_MODEL.dtype,device,progress_callback:event=>{
      const message={type:'progress',id:activeId,stage:'loading'};if(Number.isFinite(event.progress))message.progress=event.progress;self.postMessage(message);
    }});
    if(!upscaler){
      try{if(await self.navigator?.gpu?.requestAdapter?.()){upscaler=await load('webgpu');backend='webgpu';}}catch{/* CPU restoration stays available on unsupported graphics. */}
      if(!upscaler){upscaler=await load('wasm');backend='wasm';}
    }
    const target={width:source.width*2,height:source.height*2,data:new Uint8ClampedArray(source.width*source.height*16)},tiles=polishTiles(source.width,source.height);
    for(let i=0;i<tiles.length;i++){
      self.postMessage({type:'progress',id:data.id,stage:'enhancing',progress:100*i/tiles.length});
      const patch=polishTilePixels(source,tiles[i]);let result;
      try{result=await upscaler(new RawImage(patch.data,patch.width,patch.height,3));}
      catch(error){
        if(backend!=='webgpu')throw error;
        await upscaler.dispose().catch(()=>{});upscaler=null;backend='wasm';upscaler=await load('wasm');
        result=await upscaler(new RawImage(patch.data,patch.width,patch.height,3));
      }
      placePolishTile(target,result,tiles[i]);
    }
    self.postMessage({type:'result',id:data.id,image:target},[target.data.buffer]);
  }catch{self.postMessage({type:'error',id:data.id});}
  finally{busy=false;activeId=null;}
});
