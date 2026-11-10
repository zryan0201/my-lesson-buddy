import {normalizeDesign, characterPreview, DEFAULT_DESIGN} from './character.js';
const MAX_BYTES=8*1024*1024;
export function normalizeName(value){
  if(typeof value!=='string')throw new Error('Give your buddy a name.');
  const name=value.normalize('NFC').trim().replace(/\s+/g,' ');
  if(!name||[...name].length>32||!/[\p{L}\p{N}]/u.test(name)||!/^[\p{L}\p{N}\p{M} '\u2019-]+$/u.test(name))throw new Error('Use 1–32 letters, numbers, spaces, apostrophes, or hyphens.');
  return name;
}
const clone=value=>structuredClone(value);
let database;
async function db(){
  if(!globalThis.indexedDB)throw new Error('This browser cannot save a collection. Download your character to keep it.');
  if(!database)database=new Promise((resolve,reject)=>{
    const request=indexedDB.open('my-lesson-buddy',1);
    request.onupgradeneeded=()=>request.result.createObjectStore('characters',{keyPath:'id'});
    request.onsuccess=()=>resolve(request.result);
    request.onerror=()=>{database=null;reject(new Error('Your collection could not be opened. Browser storage may be disabled.'));};
  });
  return database;
}
async function transaction(mode,operation){
  const connection=await db();
  return new Promise((resolve,reject)=>{
    const tx=connection.transaction('characters',mode);const request=operation(tx.objectStore('characters'));
    let result;request.onsuccess=()=>{result=request.result;};
    tx.oncomplete=()=>resolve(result);tx.onerror=()=>reject(new Error('Your collection could not be saved. Download a character package before closing this page.'));
    tx.onabort=()=>reject(new Error('There is not enough browser storage. Download a character package to keep your work.'));
  });
}
export async function listCharacters(){return(await transaction('readonly',store=>store.getAll())).sort((a,b)=>b.created_at.localeCompare(a.created_at));}
export async function saveCharacter(value){
  const name=normalizeName(value.name);
  const character={id:crypto.randomUUID().replaceAll('-',''),name,source:value.source==='builder'?'builder':'drawing',created_at:new Date().toISOString()};
  if(value.design)character.design=normalizeDesign({...value.design,name});
  if(character.source==='builder'&&!character.design)throw new Error('Choose some parts for your buddy.');
  if(character.source==='drawing'){
    if(typeof value.image!=='string'||!/^data:image\/(png|jpeg);base64,/.test(value.image)||value.image.length>MAX_BYTES*1.4)throw new Error('Choose a PNG or JPEG drawing smaller than 8 MB.');
    character.image=value.image;
  }
  if(value.imported)character.imported=true;
  character.preview=await characterPreview(character,{width:180,height:240});
  await transaction('readwrite',store=>store.add(clone(character)));
  return clone(character);
}
export async function imageFileToDataURL(file){
  if(!file||!['image/png','image/jpeg','image/webp'].includes(file.type)||file.size>MAX_BYTES)throw new Error('Choose a PNG, JPEG, or WebP picture smaller than 8 MB.');
  const bitmap=await createImageBitmap(file);
  try{
    if(bitmap.width*bitmap.height>12000000)throw new Error('Choose a picture smaller than 12 megapixels, or crop it to one question.');
    const scale=Math.min(1,1600/Math.max(bitmap.width,bitmap.height));
    const canvas=document.createElement('canvas');canvas.width=Math.round(bitmap.width*scale);canvas.height=Math.round(bitmap.height*scale);
    canvas.getContext('2d').drawImage(bitmap,0,0,canvas.width,canvas.height);
    return canvas.toDataURL('image/png');
  }finally{bitmap.close();}
}
function pngDimensions(bytes){
  if(bytes.length<33||![137,80,78,71,13,10,26,10].every((b,i)=>bytes[i]===b))throw new Error('The package needs a PNG character picture.');
  const view=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);
  if(view.getUint32(16)!==600||view.getUint32(20)!==800)throw new Error('The saved character picture must be 600 × 800 pixels.');
}
export function inspectPackage(raw){
  if(!(raw instanceof Uint8Array)||!raw.length||raw.length>MAX_BYTES)throw new Error('Choose a character ZIP smaller than 8 MB.');
  const view=new DataView(raw.buffer,raw.byteOffset,raw.byteLength);let eocd=-1;
  for(let i=raw.length-22;i>=Math.max(0,raw.length-65557);i--){if(view.getUint32(i,true)===0x06054b50){eocd=i;break;}}
  if(eocd<0)throw new Error('This character ZIP could not be opened.');
  const count=view.getUint16(eocd+10,true),start=view.getUint32(eocd+16,true),size=view.getUint32(eocd+12,true);
  if(view.getUint16(eocd+4,true)||view.getUint16(eocd+6,true)||view.getUint16(eocd+8,true)!==count||count<2||count>3||start+size!==eocd||eocd+22+view.getUint16(eocd+20,true)!==raw.length||count===65535)throw new Error('Choose a supported Character Studio package.');
  const allowed=new Set(['character.json','character.png','README.txt']);const names=new Set();let cursor=start,total=0;
  for(let i=0;i<count;i++){
    if(cursor+46>eocd||view.getUint32(cursor,true)!==0x02014b50)throw new Error('The package index is incomplete.');
    const flags=view.getUint16(cursor+8,true),compression=view.getUint16(cursor+10,true),length=view.getUint32(cursor+24,true),nameLength=view.getUint16(cursor+28,true),extra=view.getUint16(cursor+30,true),comment=view.getUint16(cursor+32,true);
    const end=cursor+46+nameLength+extra+comment;if(end>start+size)throw new Error('The package index is incomplete.');
    const name=new TextDecoder('utf-8',{fatal:true}).decode(raw.subarray(cursor+46,cursor+46+nameLength));
    if(!allowed.has(name)||names.has(name)||flags&1||![0,8].includes(compression)||length>MAX_BYTES||length===0xffffffff||(name==='character.json'&&length>65536))throw new Error('The package contains an unsupported file.');
    total+=length;if(total>12*1024*1024)throw new Error('The character package expands beyond 12 MB.');
    names.add(name);cursor=end;
  }
  if(!names.has('character.json')||!names.has('character.png')||cursor!==start+size)throw new Error('The package is missing its character picture or details.');
  return [...names];
}
function toDataURL(raw){let str='';for(let i=0;i<raw.length;i+=8192)str+=String.fromCharCode(...raw.subarray(i,i+8192));return 'data:image/png;base64,'+btoa(str);}
async function sha(raw){return [...new Uint8Array(await crypto.subtle.digest('SHA-256',raw))].map(v=>v.toString(16).padStart(2,'0')).join('');}
export async function readPackage(file){
  const raw=new Uint8Array(await file.arrayBuffer());const names=inspectPackage(raw);
  const {unzipSync}=await import('../vendor/fflate.js');
  const files=unzipSync(raw);
  if(Object.keys(files).length!==names.length||Object.keys(files).some(name=>!names.includes(name))||Object.values(files).reduce((sum,value)=>sum+value.length,0)>12*1024*1024||files['character.json'].length>65536)throw new Error('The decompressed package does not match its index.');
  const png=files['character.png'];pngDimensions(png);
  const manifest=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(files['character.json']));
  if(manifest.version!==1||!['builder','drawing'].includes(manifest.source))throw new Error('Choose a version 1 Character Studio package.');
  const name=normalizeName(manifest.name);
  if(typeof manifest.sha256!=='string'||await sha(png)!==manifest.sha256)throw new Error('The picture does not match this package.');
  // Imported pixels remain the source of truth. Editing its parts creates a new picture.
  const record={name,source:'drawing',image:toDataURL(png),imported:true};
  if(manifest.source==='builder'){
    if(!manifest.design||typeof manifest.design!=='object'||Array.isArray(manifest.design)||Object.keys(DEFAULT_DESIGN).some(key=>!Object.hasOwn(manifest.design,key)))throw new Error('This parts character is missing its saved design.');
    record.design=normalizeDesign({...manifest.design,name});
  }
  return record;
}
export async function makePackage(character){
  const {zipSync,strToU8}=await import('../vendor/fflate.js');
  let image=await characterPreview(character,{width:600,height:800});
  if(character.source==='drawing'&&character.image?.startsWith('data:image/png;base64,')){
    const original=Uint8Array.from(atob(character.image.split(',')[1]),c=>c.charCodeAt(0));
    try{pngDimensions(original);image=character.image;}catch{/* A canvas draft is fitted to the portable 600×800 format. */}
  }
  const raw=Uint8Array.from(atob(image.split(',')[1]),c=>c.charCodeAt(0));
  const source=character.design?'builder':'drawing';
  const manifest={version:1,id:character.id,name:normalizeName(character.name),source,created_at:character.created_at||new Date().toISOString(),sha256:await sha(raw),design:source==='builder'?normalizeDesign({...character.design,name:character.name}):null};
  const bytes=zipSync({'character.json':strToU8(JSON.stringify(manifest,null,2)),'character.png':raw,'README.txt':strToU8('My Lesson Buddy · Character Studio\nYour saved character picture and editable parts. No executable code.\n')});
  return new Blob([bytes],{type:'application/zip'});
}
export function downloadBlob(blob,name){
  const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=name;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);
}
