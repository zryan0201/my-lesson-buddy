/** Conservative restoration: learned 2× detail, bounded against the original. */
export const POLISH_MODEL=Object.freeze({modelId:'Xenova/swin2SR-lightweight-x2-64',revision:'92a21aca5713f20faf9a87590cdfbdce2e34112c',dtype:'fp32',weightBytes:8078888,tile:128,halo:16,maxEdge:960,maxPixels:921600,timeoutMs:8*60*1000});
export function checkPolishPixels(image,{output=false}={}){
  const limit=output?POLISH_MODEL.maxEdge*2:POLISH_MODEL.maxEdge;
  if(!image||!Number.isInteger(image.width)||!Number.isInteger(image.height)||image.width<1||image.height<1||image.width>limit||image.height>limit||!ArrayBuffer.isView(image.data)||image.data.BYTES_PER_ELEMENT!==1||image.data.length!==image.width*image.height*4)throw new Error('Choose a supported drawing pixel buffer.');
  return image;
}
export function polishTiles(width,height){
  if(!Number.isInteger(width)||!Number.isInteger(height)||width<1||height<1||width>POLISH_MODEL.maxEdge||height>POLISH_MODEL.maxEdge)throw new Error('Drawing dimensions are outside the local model limit.');
  const tiles=[];for(let y=0;y<height;y+=POLISH_MODEL.tile)for(let x=0;x<width;x+=POLISH_MODEL.tile)tiles.push({x,y,width:Math.min(POLISH_MODEL.tile,width-x),height:Math.min(POLISH_MODEL.tile,height-y)});return tiles;
}
export function reflectPixel(value,size){if(size===1)return 0;const period=2*size-2,n=((value%period)+period)%period;return n<size?n:period-n;}
export function polishTilePixels(image,tile){
  checkPolishPixels(image);const edge=POLISH_MODEL.tile+2*POLISH_MODEL.halo,data=new Uint8Array(edge*edge*3);
  for(let y=0;y<edge;y++)for(let x=0;x<edge;x++){
    const sx=reflectPixel(tile.x+x-POLISH_MODEL.halo,image.width),sy=reflectPixel(tile.y+y-POLISH_MODEL.halo,image.height),from=(sy*image.width+sx)*4,to=(y*edge+x)*3,a=image.data[from+3]/255;
    for(let c=0;c<3;c++)data[to+c]=Math.round(image.data[from+c]*a+255*(1-a));
  }return{data,width:edge,height:edge,channels:3};
}
export function placePolishTile(target,image,tile){
  checkPolishPixels(target,{output:true});const edge=(POLISH_MODEL.tile+2*POLISH_MODEL.halo)*2;
  if(image?.width!==edge||image?.height!==edge||image.channels!==3||!(image.data instanceof Uint8Array||image.data instanceof Uint8ClampedArray)||image.data.length!==edge*edge*3)throw new Error('Local AI returned an unusable image.');
  for(let y=0;y<tile.height*2;y++)for(let x=0;x<tile.width*2;x++){
    const from=((y+POLISH_MODEL.halo*2)*edge+x+POLISH_MODEL.halo*2)*3,to=((tile.y*2+y)*target.width+tile.x*2+x)*4;
    target.data[to]=image.data[from];target.data[to+1]=image.data[from+1];target.data[to+2]=image.data[from+2];target.data[to+3]=255;
  }
}
/** Input buffers remain untouched. White paper and transparency stay exact. */
export function blendPolish(original,learned,strength=.6){
  checkPolishPixels(original,{output:true});checkPolishPixels(learned,{output:true});
  if(original.width!==learned.width||original.height!==learned.height||!Number.isFinite(strength)||strength<0||strength>1)throw new Error('Choose an enhancement strength from zero to one.');
  const data=new Uint8ClampedArray(original.data.length);
  for(let n=0;n<data.length;n+=4){
    const paper=original.data[n]>=248&&original.data[n+1]>=248&&original.data[n+2]>=248;
    for(let c=0;c<3;c++){const v=original.data[n+c];data[n+c]=paper||original.data[n+3]===0?v:v+strength*Math.max(-40,Math.min(40,learned.data[n+c]-v));}
    data[n+3]=original.data[n+3];
  }return{data,width:original.width,height:original.height};
}
