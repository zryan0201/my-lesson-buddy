/** Optional real local inference. Imported only after a deliberate generation action. */
import {BUDDY_MODEL,buddyMessages} from './buddy-design.js';
import {designLogitsProcessor} from './buddy-grammar.js';
// The pinned ONNX runtime uses Uint16 storage for half tensors. Keep this
// compatibility setting inside this dedicated worker, away from the app.
globalThis.Float16Array=undefined;
let runtimePromise=null,generator=null,busy=false,activeId=null;
function runtime(){
  if(!runtimePromise)runtimePromise=import('../vendor/transformers.js').then(api=>{
    api.env.allowLocalModels=false;api.env.useBrowserCache=true;
    api.env.backends.onnx.wasm.wasmPaths=new URL('../vendor/ort/',import.meta.url).href;
    api.env.backends.onnx.wasm.numThreads=1;api.env.backends.onnx.wasm.proxy=false;return api;
  });
  return runtimePromise;
}
self.addEventListener('message',async({data})=>{
  if(!data||data.type!=='describe'||!/^buddy-\d+$/.test(data.id)||!['webgpu','wasm'].includes(data.device))return;
  if(busy){self.postMessage({type:'error',id:data.id});return;}
  busy=true;activeId=data.id;
  try{
    const messages=buddyMessages(data.idea);
    self.postMessage({type:'progress',id:data.id,stage:'loading'});
    const {AutoTokenizer,AutoModelForCausalLM}=await runtime();
    if(!generator){
      const options={revision:BUDDY_MODEL.revision,progress_callback:event=>{
        const progress={type:'progress',id:activeId,stage:'loading'};
        for(const key of ['progress','loaded','total'])if(Number.isFinite(event[key]))progress[key]=event[key];
        self.postMessage(progress);
      }};
      generator=await Promise.all([AutoTokenizer.from_pretrained(BUDDY_MODEL.modelId,options),AutoModelForCausalLM.from_pretrained(BUDDY_MODEL.modelId,{...options,dtype:BUDDY_MODEL.dtype,device:data.device})]);
    }
    self.postMessage({type:'progress',id:data.id,stage:'generating'});
    const [tokenizer,model]=generator;
    const prompt=tokenizer.apply_chat_template(messages,{tokenize:false,add_generation_prompt:true,enable_thinking:false});
    const inputs=tokenizer(prompt,{add_special_tokens:false});const promptLength=inputs.input_ids.dims.at(-1);
    const processor=designLogitsProcessor(tokenizer,promptLength,model.generation_config.eos_token_id);
    const output=await model.generate({...inputs,max_new_tokens:BUDDY_MODEL.maxNewTokens,do_sample:false,logits_processor:[processor]});
    const raw=tokenizer.decode(output.tolist()[0].slice(promptLength).map(Number),{skip_special_tokens:true});
    if(typeof raw!=='string'||raw.length>4000)throw new Error('Unusable design');
    self.postMessage({type:'result',id:data.id,raw});
  }catch{self.postMessage({type:'error',id:data.id});}
  finally{busy=false;activeId=null;}
});
