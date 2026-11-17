/** Token-level grammar: the model chooses values, never keys or executable text. */
import {BUDDY_FIELDS} from './buddy-design.js';

export function designGrammar(encode){
 const entries=Object.entries(BUDDY_FIELDS),roots=entries.map(([key,values],index)=>{
  const root={next:new Map(),end:false};
  for(const value of values){
   const text=(index===0?'{':',')+JSON.stringify(key)+':'+JSON.stringify(value)+(index===entries.length-1?'}':'');
   let node=root;
   for(const token of encode(text)){const id=Number(token);if(!node.next.has(id))node.next.set(id,{next:new Map(),end:false});node=node.next.get(id);}
   node.end=true;
  }
  return root;
 });
 return prefix=>{
  let field=0,node=roots[0];
  for(const token of prefix){
   if(node.end){field++;node=roots[field];}
   if(!node?.next.has(Number(token)))throw new Error('The generated token sequence left the design grammar.');
   node=node.next.get(Number(token));
  }
  if(node.end&&field===roots.length-1)return null;
  if(node.end)node=roots[field+1];
  return [...node.next.keys()];
 };
}

export function designLogitsProcessor(tokenizer,promptLength,eosToken){
 const allowedAfter=designGrammar(text=>tokenizer.encode(text,{add_special_tokens:false}));
 const eos=Array.isArray(eosToken)?eosToken:[eosToken];
 return (inputIds,logits)=>{
  if(inputIds.length!==1)throw new Error('One buddy description at a time.');
  const allowed=allowedAfter(inputIds[0].slice(promptLength))??eos;
  if(!allowed.length||allowed.some(x=>!Number.isInteger(x)||x<0||x>=logits.data.length))throw new Error('Unsupported character-model vocabulary.');
  const values=allowed.map(id=>logits.data[id]);logits.data.fill(-Infinity);
  allowed.forEach((id,i)=>{logits.data[id]=values[i];});return logits;
 };
}
