/* Exact worksheet artwork, kept on the visitor's device. Automatic extraction
 * proposes separated, repeated colored illustrations; it does not name objects
 * or infer the mathematical question. Every proposal still needs adult review. */
const MAX_SOURCE_PIXELS=12_000_000, MAX_ANALYSIS_PIXELS=4_000_000;
const MAX_SPRITE_SIDE=192, MAX_DATA_URL=270_000, CACHE_LIMIT=48;
const spriteCache=new Map();

const whole=(n,min,max)=>Number.isInteger(n)&&n>=min&&n<=max;
const boxOf=c=>({x:c.x,y:c.y,width:c.width,height:c.height});
const fail=(boxes,reason)=>({boxes,complete:false,reason});

/** Pure, bounded pixel analysis. Uses repetition, color and connectedness rather
 * than a list of recognized object types. Unknown/ambiguous art is not split. */
export function findObjectCandidates(pixels,width,height,{expectedCount}={}) {
  if(!whole(width,1,4096)||!whole(height,1,4096)||width*height>MAX_ANALYSIS_PIXELS||!pixels||pixels.length!==width*height*4)throw new Error('Choose a supported worksheet image.');
  if(!whole(expectedCount,0,10))throw new Error('Check the number of worksheet objects first.');
  const count=width*height,foreground=new Uint8Array(count),colored=new Uint8Array(count),labels=new Uint16Array(count),queue=new Int32Array(count);
  let white=0,ink=0;
  for(let i=0;i<count;i++){
    const a=pixels[i*4+3]/255,r=255+(pixels[i*4]-255)*a,g=255+(pixels[i*4+1]-255)*a,b=255+(pixels[i*4+2]-255)*a;
    const low=Math.min(r,g,b),high=Math.max(r,g,b);
    if(low>=215)white++;
    colored[i]=high-low>=30&&low<225&&high>70?1:0;
    // Keep gray sticks/outlines connected to their colored artwork too. A
    // whole shaded photograph will fail the light-background/ink-area checks.
    foreground[i]=colored[i]||high<220?1:0;ink+=foreground[i];
  }
  if(white/count<.58||ink/count>.40)return fail([],'This picture needs a closer crop around one clear worksheet question.');
  const components=[];let label=0;
  for(let start=0;start<count;start++){
    if(!foreground[start]||labels[start])continue;
    if(++label>2500)return fail([],'There are too many separate marks. Crop one complete object instead.');
    let head=0,tail=1,minX=width,maxX=0,minY=height,maxY=0,color=0,sumR=0,sumG=0,sumB=0;
    queue[0]=start;labels[start]=label;
    while(head<tail){
      const at=queue[head++],x=at%width,y=Math.floor(at/width);
      minX=Math.min(minX,x);maxX=Math.max(maxX,x);minY=Math.min(minY,y);maxY=Math.max(maxY,y);color+=colored[at];
      sumR+=pixels[at*4];sumG+=pixels[at*4+1];sumB+=pixels[at*4+2];
      for(let dy=-1;dy<=1;dy++)for(let dx=-1;dx<=1;dx++){
        const nx=x+dx,ny=y+dy;if((dx===0&&dy===0)||nx<0||nx>=width||ny<0||ny>=height)continue;
        const next=ny*width+nx;if(foreground[next]&&!labels[next]){labels[next]=label;queue[tail++]=next;}
      }
    }
    components.push({label,x:minX,y:minY,width:maxX-minX+1,height:maxY-minY+1,area:tail,color,
      rgb:[sumR/tail,sumG/tail,sumB/tail],edge:minX===0||minY===0||maxX===width-1||maxY===height-1});
  }
  const colorful=c=>c.color>=Math.max(5,c.area*.13);
  const art=components.filter(c=>!c.edge&&colorful(c)&&c.area>=32&&c.width>=8&&c.height>=8&&c.width/c.height<=5&&c.height/c.width<=5);
  const boxes=art.map(boxOf).sort((a,b)=>a.x-b.x||a.y-b.y);
  if(!art.length)return fail([],expectedCount===0?'No objects are needed for this zero lesson.':'No clear separated artwork was found. Select one complete object with the crop tool.');
  if(art.length>10)return fail(boxes,'More than ten pictured objects were found. Crop one question, or select one object to use.');
  for(let i=0;i<art.length;i++)for(let j=i+1;j<art.length;j++){
    const a=art[i],b=art[j];
    if(a.x-2<b.x+b.width+2&&b.x-2<a.x+a.width+2&&a.y-2<b.y+b.height+2&&b.y-2<a.y+a.height+2)return fail(boxes,'The pictured objects are very close together. Crop one complete object so neighboring pieces are not included.');
  }
  const widths=art.map(c=>c.width),heights=art.map(c=>c.height);
  if(Math.max(...widths)/Math.min(...widths)>1.45||Math.max(...heights)/Math.min(...heights)>1.45)return fail(boxes,'The marks differ in size. Select one complete worksheet object instead.');
  const signature=c=>{
    const result=new Uint8Array(24*24);
    for(let y=0;y<24;y++)for(let x=0;x<24;x++){
      const sx=c.x+Math.min(c.width-1,Math.floor((x+.5)*c.width/24)),sy=c.y+Math.min(c.height-1,Math.floor((y+.5)*c.height/24));
      result[y*24+x]=labels[sy*width+sx]===c.label?1:0;
    }
    return result;
  };
  const signatures=art.map(signature);
  for(let i=1;i<art.length;i++){
    let intersection=0,union=0;for(let k=0;k<576;k++){intersection+=signatures[0][k]&signatures[i][k];union+=signatures[0][k]|signatures[i][k];}
    const colorError=art[i].rgb.reduce((sum,value,k)=>sum+Math.abs(value-art[0].rgb[k])/255,0)/3;
    if(intersection/Math.max(1,union)<.66||colorError>.20)return fail(boxes,'The picture may contain different objects or printed marks. Select one complete object instead.');
  }
  // A disconnected colored part (or a nearby separate dark stick/limb) may be
  // part of an illustration. Decline instead of silently cutting it off.
  const chosen=new Set(art.map(c=>c.label)),top=Math.min(...art.map(c=>c.y)),bottom=Math.max(...art.map(c=>c.y+c.height));
  const medianHeight=[...heights].sort((a,b)=>a-b)[Math.floor(heights.length/2)];
  for(const c of components){
    if(chosen.has(c.label)||c.area<8)continue;
    const smallEdgeFragment=c.edge&&c.height<=medianHeight*.35&&(c.y+c.height<top||c.y>bottom);
    if(smallEdgeFragment)continue;
    if(colorful(c)&&c.color>=16)return fail(boxes,'Some artwork may be incomplete or disconnected. Select one whole object with a little space around it.');
    if(c.edge)continue;
    for(const a of art){
      const overlap=Math.max(0,Math.min(c.x+c.width,a.x+a.width)-Math.max(c.x,a.x));
      const gap=c.y>=a.y+a.height?c.y-a.y-a.height:a.y>=c.y+c.height?a.y-c.y-c.height:-1;
      if(overlap>=Math.min(c.width,a.width)*.35&&gap>=0&&gap<=Math.max(5,a.height*.3))return fail(boxes,'An object may have a separate part. Crop the complete object so every part stays in the video.');
    }
  }
  if(boxes.length!==expectedCount)return fail(boxes,`Found ${boxes.length} possible objects; the checked question needs ${expectedCount}. Select one complete object, or correct the question.`);
  return {boxes,complete:true,reason:`Found ${boxes.length} separate matching pictures. Check the cutouts against the worksheet.`};
}

function sourceSize(width,height){if(!whole(width,1,10000)||!whole(height,1,10000)||width*height>MAX_SOURCE_PIXELS)throw new Error('Choose a worksheet image with fewer than 12 million pixels.');}
function pngURL(value){
  if(typeof value!=='string'||value.length>MAX_DATA_URL||!/^data:image\/png;base64,[A-Za-z0-9+/]+={0,2}$/.test(value))throw new Error('Use a prepared PNG cutout from this worksheet.');
  let bytes;try{bytes=atob(value.slice(value.indexOf(',')+1, value.indexOf(',')+1+64));}catch{throw new Error('The worksheet cutout could not be opened.');}
  const signature=[137,80,78,71,13,10,26,10];
  if(bytes.length<24||signature.some((n,i)=>bytes.charCodeAt(i)!==n)||bytes.slice(12,16)!=='IHDR')throw new Error('Use a valid PNG worksheet cutout.');
  const uint=offset=>((bytes.charCodeAt(offset)*0x1000000)+(bytes.charCodeAt(offset+1)<<16)+(bytes.charCodeAt(offset+2)<<8)+bytes.charCodeAt(offset+3))>>>0;
  if(!whole(uint(16),1,MAX_SPRITE_SIDE)||!whole(uint(20),1,MAX_SPRITE_SIDE))throw new Error('Worksheet cutouts must be 192 pixels or smaller.');
  return value;
}

/** Validate pictures separately from question fields; model metadata is never
 * accepted as artwork. Returned data is a fresh, plain serializable value. */
export function normalizeWorksheetObjects(pack,quantity){
  if(!whole(quantity,0,10))throw new Error('Check the whole-number quantity before choosing worksheet objects.');
  if(pack===null||pack===undefined)return null;
  if(!pack||typeof pack!=='object'||Array.isArray(pack)||pack.version!==1||!['individual','repeat'].includes(pack.mode)||!Array.isArray(pack.sprites))throw new Error('Choose worksheet objects again.');
  sourceSize(pack.sourceWidth,pack.sourceHeight);
  if(pack.mode==='individual'?pack.sprites.length!==quantity:quantity===0||pack.sprites.length!==1)throw new Error('The selected worksheet objects do not match the checked question.');
  const sprites=pack.sprites.map(sprite=>{
    const box=sprite?.box;if(!box||!whole(box.x,0,pack.sourceWidth-1)||!whole(box.y,0,pack.sourceHeight-1)||!whole(box.width,1,pack.sourceWidth)||!whole(box.height,1,pack.sourceHeight)||box.x+box.width>pack.sourceWidth||box.y+box.height>pack.sourceHeight)throw new Error('Choose a complete object inside the worksheet picture.');
    return {image:pngURL(sprite.image),box:{x:box.x,y:box.y,width:box.width,height:box.height}};
  });
  return {version:1,mode:pack.mode,sourceWidth:pack.sourceWidth,sourceHeight:pack.sourceHeight,sprites};
}

function canvas(width,height){const value=document.createElement('canvas');value.width=width;value.height=height;if(!value.getContext('2d'))throw new Error('This browser cannot prepare worksheet objects.');return value;}
function decode(source,sprite=false){
  if(sprite)pngURL(source);
  else if(typeof source!=='string'||source.length>12_000_000||!/^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/]+={0,2}$/.test(source))throw new Error('Choose a PNG or JPEG worksheet picture.');
  return new Promise((resolve,reject)=>{
    const image=new Image();image.onload=()=>{try{sourceSize(image.naturalWidth,image.naturalHeight);resolve(image);}catch(error){reject(error);}};
    image.onerror=()=>reject(new Error('The worksheet picture could not be decoded. Try another PNG or JPEG.'));image.src=source;
  });
}

/** Remove only near-white paper connected to a crop edge. Enclosed white eyes,
 * highlights and details remain; the original worksheet is never modified. */
export function clearBorderPaper(pixels,width,height){
  if(!whole(width,1,MAX_SPRITE_SIDE)||!whole(height,1,MAX_SPRITE_SIDE)||!pixels||pixels.length!==width*height*4)throw new Error('Choose a supported worksheet cutout.');
  const result=new Uint8ClampedArray(pixels),seen=new Uint8Array(width*height),queue=new Int32Array(width*height);let head=0,tail=0;
  const add=index=>{if(seen[index])return;seen[index]=1;const i=index*4,r=result[i],g=result[i+1],b=result[i+2];if(result[i+3]<8||(Math.min(r,g,b)>235&&Math.max(r,g,b)-Math.min(r,g,b)<22))queue[tail++]=index;};
  for(let x=0;x<width;x++){add(x);add((height-1)*width+x);}for(let y=0;y<height;y++){add(y*width);add(y*width+width-1);}
  while(head<tail){const at=queue[head++],x=at%width,y=Math.floor(at/width);result[at*4+3]=0;if(x)add(at-1);if(x+1<width)add(at+1);if(y)add(at-width);if(y+1<height)add(at+width);}
  return result;
}
function extract(image,box){
  const scale=Math.min(1,MAX_SPRITE_SIDE/Math.max(box.width,box.height)),width=Math.max(1,Math.round(box.width*scale)),height=Math.max(1,Math.round(box.height*scale));
  const out=canvas(width,height),ctx=out.getContext('2d',{willReadFrequently:true});ctx.drawImage(image,box.x,box.y,box.width,box.height,0,0,width,height);
  const data=ctx.getImageData(0,0,width,height);data.data.set(clearBorderPaper(data.data,width,height));
  let ink=0;for(let i=3;i<data.data.length;i+=4)if(data.data[i]>8)ink++;
  if(ink<Math.max(12,width*height*.015))throw new Error('This selection is empty. Include one complete worksheet object.');
  ctx.putImageData(data,0,0);return {image:out.toDataURL('image/png'),box:{...box}};
}

export async function suggestWorksheetObjects(pictureDataURL,quantity){
  if(!whole(quantity,0,10))throw new Error('Check the question before selecting its objects.');
  const image=await decode(pictureDataURL),sourceWidth=image.naturalWidth,sourceHeight=image.naturalHeight;
  if(quantity===0)return {pack:{version:1,mode:'individual',sourceWidth,sourceHeight,sprites:[]},candidates:[],reason:'No objects are needed for this zero lesson.'};
  const scale=Math.min(1,1200/Math.max(sourceWidth,sourceHeight)),w=Math.max(1,Math.round(sourceWidth*scale)),h=Math.max(1,Math.round(sourceHeight*scale));
  const analysis=canvas(w,h),ctx=analysis.getContext('2d',{willReadFrequently:true});ctx.fillStyle='#ffffff';ctx.fillRect(0,0,w,h);ctx.drawImage(image,0,0,w,h);
  const result=findObjectCandidates(ctx.getImageData(0,0,w,h).data,w,h,{expectedCount:quantity});
  const boxes=result.boxes.map(box=>{const x=Math.max(0,Math.floor(box.x/scale)-2),y=Math.max(0,Math.floor(box.y/scale)-2);return {x,y,width:Math.min(sourceWidth-x,Math.ceil((box.x+box.width)/scale)+2-x),height:Math.min(sourceHeight-y,Math.ceil((box.y+box.height)/scale)+2-y)};});
  if(!result.complete)return {pack:null,candidates:boxes,reason:result.reason};
  const pack={version:1,mode:'individual',sourceWidth,sourceHeight,sprites:boxes.map(box=>extract(image,box))};
  return {pack:normalizeWorksheetObjects(pack,quantity),candidates:boxes,reason:result.reason};
}

export async function cropWorksheetObject(pictureDataURL,normalizedRect){
  const r=normalizedRect;if(!r||!['x','y','width','height'].every(k=>Number.isFinite(r[k]))||r.x<0||r.y<0||r.width<=0||r.height<=0||r.x+r.width>1.000001||r.y+r.height>1.000001)throw new Error('Select one whole object inside the worksheet.');
  const image=await decode(pictureDataURL),sourceWidth=image.naturalWidth,sourceHeight=image.naturalHeight;
  const x=Math.floor(r.x*sourceWidth),y=Math.floor(r.y*sourceHeight),width=Math.min(sourceWidth-x,Math.ceil(r.width*sourceWidth)),height=Math.min(sourceHeight-y,Math.ceil(r.height*sourceHeight));
  if(width<6||height<6)throw new Error('Make the selection larger so it includes the whole object.');
  return normalizeWorksheetObjects({version:1,mode:'repeat',sourceWidth,sourceHeight,sprites:[extract(image,{x,y,width,height})]},1);
}

export async function prepareWorksheetObjects(pack){
  if(!pack)return;
  const quantity=pack.mode==='individual'?pack.sprites?.length:1,checked=normalizeWorksheetObjects(pack,quantity);
  await Promise.all(checked.sprites.map(async sprite=>{
    const key=sprite.image;if(spriteCache.has(key)){const value=spriteCache.get(key);spriteCache.delete(key);spriteCache.set(key,value);return;}
    const image=await decode(key,true);if(image.naturalWidth>MAX_SPRITE_SIDE||image.naturalHeight>MAX_SPRITE_SIDE)throw new Error('Choose a smaller worksheet cutout.');
    spriteCache.set(key,image);while(spriteCache.size>CACHE_LIMIT)spriteCache.delete(spriteCache.keys().next().value);
  }));
}

export function drawWorksheetObject(ctx,pack,index,x,y,size){
  if(!pack||!whole(index,0,9)||![x,y,size].every(Number.isFinite)||size<=0||size>2048)return false;
  const sprite=pack.sprites?.[pack.mode==='repeat'?0:index],image=sprite&&spriteCache.get(sprite.image);if(!image)return false;
  const scale=size/Math.max(image.naturalWidth,image.naturalHeight),w=image.naturalWidth*scale,h=image.naturalHeight*scale;
  ctx.drawImage(image,x-w/2,y-h/2,w,h);return true;
}
