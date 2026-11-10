/* Local document geometry. Coordinates are normalized TL, TR, BR, BL.
 * Detection is conservative; an uncertain photograph is left for corner review.
 * Warping only resamples source pixels. No text or objects are synthesized. */
const FULL=()=>[{x:0,y:0},{x:1,y:0},{x:1,y:1},{x:0,y:1}];
const cross=(a,b,c)=>(b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x);
const distance=(a,b)=>Math.hypot(a.x-b.x,a.y-b.y);
const area=points=>Math.abs(points.reduce((sum,p,i)=>sum+p.x*points[(i+1)%points.length].y-p.y*points[(i+1)%points.length].x,0))/2;
function input(pixels,width,height){if(!Number.isInteger(width)||!Number.isInteger(height)||width<2||height<2||width>4096||height>4096||width*height>12_000_000||!pixels||pixels.length!==width*height*4)throw new Error('Choose a supported worksheet photograph.');}

/** Validate rather than silently reorder the corner controls. */
export function validateCorners(corners,{width=1600,height=1600}={}){
  if(!Number.isFinite(width)||!Number.isFinite(height)||width<2||height<2||!Array.isArray(corners)||corners.length!==4)throw new Error('Mark the four paper corners in order: top left, top right, bottom right, bottom left.');
  const result=corners.map(p=>{if(!p||!Number.isFinite(p.x)||!Number.isFinite(p.y)||p.x<0||p.x>1||p.y<0||p.y>1)throw new Error('Keep every paper corner inside the photograph.');return{x:p.x,y:p.y};});
  if(result.some((p,i)=>cross(p,result[(i+1)%4],result[(i+2)%4])<=.0002)||area(result)<.015)throw new Error('Choose a complete paper area without crossing its corner lines.');
  const actual=result.map(p=>({x:p.x*(width-1),y:p.y*(height-1)}));
  if(actual.some((p,i)=>distance(p,actual[(i+1)%4])<6))throw new Error('Move the corners farther apart to include a readable paper area.');
  if(result[0].y+result[1].y>=result[2].y+result[3].y||result[0].x+result[3].x>=result[1].x+result[2].x)throw new Error('Keep top corners above bottom corners and left corners to the left.');
  return result;
}

function hull(points){
  const sorted=points.slice().sort((a,b)=>a.x-b.x||a.y-b.y),unique=sorted.filter((p,i)=>!i||p.x!==sorted[i-1].x||p.y!==sorted[i-1].y);
  if(unique.length<4)return unique;
  const lower=[],upper=[];
  for(const p of unique){while(lower.length>1&&cross(lower.at(-2),lower.at(-1),p)<=0)lower.pop();lower.push(p);}
  for(const p of unique.slice().reverse()){while(upper.length>1&&cross(upper.at(-2),upper.at(-1),p)<=0)upper.pop();upper.push(p);}
  return lower.slice(0,-1).concat(upper.slice(0,-1));
}
function reduceQuad(polygon){const result=polygon.slice();while(result.length>4){let selected=0,minimum=Infinity;for(let i=0;i<result.length;i++){const a=result[(i+result.length-1)%result.length],b=result[i],c=result[(i+1)%result.length],cost=Math.abs(cross(a,b,c));if(cost<minimum){minimum=cost;selected=i;}}result.splice(selected,1);}if(result.length!==4)return null;let first=0;for(let i=1;i<4;i++)if(result[i].x+result[i].y<result[first].x+result[first].y)first=i;return result.slice(first).concat(result.slice(0,first));}
function segmentDistance(p,a,b){const dx=b.x-a.x,dy=b.y-a.y,q=Math.max(0,Math.min(1,((p.x-a.x)*dx+(p.y-a.y)*dy)/(dx*dx+dy*dy)));return Math.hypot(p.x-a.x-q*dx,p.y-a.y-q*dy);}
const median=values=>values.slice().sort((a,b)=>a-b)[Math.floor(values.length/2)]||0;
function fitEdges(quad,points,size){
  const lines=quad.map((a,i)=>{const b=quad[(i+1)%4],dx=b.x-a.x,dy=b.y-a.y,length2=dx*dx+dy*dy;const selected=points.filter(p=>{const q=((p.x-a.x)*dx+(p.y-a.y)*dy)/length2;return q>.09&&q<.91&&segmentDistance(p,a,b)<size*.023;});if(selected.length<4)return null;const cx=selected.reduce((s,p)=>s+p.x,0)/selected.length,cy=selected.reduce((s,p)=>s+p.y,0)/selected.length;let xx=0,yy=0,xy=0;for(const p of selected){xx+=(p.x-cx)**2;yy+=(p.y-cy)**2;xy+=(p.x-cx)*(p.y-cy);}const angle=.5*Math.atan2(2*xy,xx-yy);return{x:cx,y:cy,dx:Math.cos(angle),dy:Math.sin(angle)};});
  if(lines.some(l=>!l))return quad;
  const result=lines.map((line,i)=>{const previous=lines[(i+3)%4],denominator=previous.dx*line.dy-previous.dy*line.dx;if(Math.abs(denominator)<.1)return null;const t=((line.x-previous.x)*line.dy-(line.y-previous.y)*line.dx)/denominator;return{x:previous.x+t*previous.dx,y:previous.y+t*previous.dy};});
  return result.some((p,i)=>!p||distance(p,quad[i])>size*.04)?quad:result;
}

/** Find a large light-paper quadrilateral against a contrasting background.
 * A safe full-frame result is allowed for an already framed light worksheet.
 * A failed result never proposes a smaller crop to satisfy a desired answer. */
export function findPaperQuad(pixels,width,height){
  input(pixels,width,height);
  const scale=Math.min(1,420/Math.max(width,height)),w=Math.max(2,Math.round(width*scale)),h=Math.max(2,Math.round(height*scale)),n=w*h;
  const light=new Float32Array(n),chroma=new Float32Array(n),border=[];let lightCount=0,inkCount=0;
  for(let y=0;y<h;y++)for(let x=0;x<w;x++){
    const sx=Math.min(width-1,Math.round(x*(width-1)/(w-1))),sy=Math.min(height-1,Math.round(y*(height-1)/(h-1))),at=(sy*width+sx)*4,alpha=pixels[at+3]/255;
    const r=255+(pixels[at]-255)*alpha,g=255+(pixels[at+1]-255)*alpha,b=255+(pixels[at+2]-255)*alpha,index=y*w+x;
    light[index]=Math.min(r,g,b);chroma[index]=Math.max(r,g,b)-light[index];if(light[index]>205&&chroma[index]<40)lightCount++;if(light[index]<180)inkCount++;
    if(x<2||y<2||x>=w-2||y>=h-2)border.push(light[index]>205&&chroma[index]<40?1:0);
  }
  if(border.reduce((a,b)=>a+b,0)/border.length>.88&&lightCount/n>.57&&inkCount/n<.38)return{corners:FULL(),confidence:.94,reason:'The light worksheet already fills the picture.',framed:true};
  const queue=new Int32Array(n),seen=new Uint8Array(n),candidates=[];
  for(const threshold of [85,110,140,170,200,225]){
    seen.fill(0);
    for(let start=0;start<n;start++){
      if(seen[start]||light[start]<threshold||chroma[start]>65)continue;
      let head=0,tail=1,minX=w,maxX=0,minY=h,maxY=0,touches=false;queue[0]=start;seen[start]=1;const rows=new Map();
      while(head<tail){const at=queue[head++],x=at%w,y=Math.floor(at/w);minX=Math.min(minX,x);maxX=Math.max(maxX,x);minY=Math.min(minY,y);maxY=Math.max(maxY,y);if(x<2||y<2||x>w-3||y>h-3)touches=true;const row=rows.get(y);if(row){row[0]=Math.min(row[0],x);row[1]=Math.max(row[1],x);}else rows.set(y,[x,x]);
        for(const next of [x?at-1:-1,x<w-1?at+1:-1,y?at-w:-1,y<h-1?at+w:-1])if(next>=0&&!seen[next]&&light[next]>=threshold&&chroma[next]<=65){seen[next]=1;queue[tail++]=next;}
      }
      if(touches||tail<n*.13||(maxX-minX)<w*.22||(maxY-minY)<h*.17)continue;
      const points=[];for(const[y,[left,right]]of rows){points.push({x:left,y},{x:right,y});}const outline=hull(points),rough=reduceQuad(outline);if(!rough)continue;const quad=fitEdges(rough,points,Math.max(w,h));
      const polygonArea=area(outline),quadArea=area(quad),coverage=quadArea/n;
      if(coverage<.15||coverage>.96||quadArea/polygonArea<.955||tail/polygonArea<.67)continue;
      const error=Math.max(...outline.map(p=>Math.min(...quad.map((a,i)=>segmentDistance(p,a,quad[(i+1)%4])))))/Math.max(w,h);if(error>.018)continue;
      const sample=(x,y)=>light[Math.max(0,Math.min(h-1,Math.round(y)))*w+Math.max(0,Math.min(w-1,Math.round(x)))];
      const contrasts=quad.map((a,i)=>{const b=quad[(i+1)%4],dx=b.x-a.x,dy=b.y-a.y,length=Math.hypot(dx,dy),offset=Math.max(3,Math.max(w,h)*.012),nx=dy/length,ny=-dx/length;return median([.2,.35,.5,.65,.8].map(f=>{const x=a.x+dx*f,y=a.y+dy*f;return sample(x-nx*offset,y-ny*offset)-sample(x+nx*offset,y+ny*offset);}));});
      if(Math.min(...contrasts)<13||contrasts.reduce((a,b)=>a+b,0)/4<22)continue;
      const normalized=quad.map(p=>({x:p.x/(w-1),y:p.y/(h-1)}));try{validateCorners(normalized,{width,height});}catch{continue;}
      candidates.push({corners:normalized,coverage,confidence:Math.min(.99,.72+Math.min(.18,Math.min(...contrasts)/400)+Math.max(0,.08-error*3)),reason:'Four contrasting paper edges were found.'});
    }
  }
  candidates.sort((a,b)=>b.coverage-a.coverage||b.confidence-a.confidence);
  if(!candidates.length)return{corners:null,confidence:0,reason:'The paper edges are not clear enough. Adjust the four corners, or keep the original picture.'};
  const best=candidates[0];return{corners:best.corners,confidence:best.confidence,reason:best.reason,framed:false};
}

function solve(matrix,values){const a=matrix.map((row,i)=>row.concat(values[i])),size=values.length;for(let column=0;column<size;column++){let pivot=column;for(let row=column+1;row<size;row++)if(Math.abs(a[row][column])>Math.abs(a[pivot][column]))pivot=row;if(Math.abs(a[pivot][column])<1e-10)throw new Error('The paper corners are too close together to straighten.');[a[pivot],a[column]]=[a[column],a[pivot]];const divisor=a[column][column];for(let k=column;k<=size;k++)a[column][k]/=divisor;for(let row=0;row<size;row++)if(row!==column){const factor=a[row][column];for(let k=column;k<=size;k++)a[row][k]-=factor*a[column][k];}}return a.map(row=>row[size]);}

/** Rectify the selected source quadrilateral using inverse homography and
 * bilinear sampling. Output size follows mean opposing edge lengths. */
export function warpPerspective(pixels,width,height,corners,{maxSide=1600}={}){
  input(pixels,width,height);const c=validateCorners(corners,{width,height}).map(p=>({x:p.x*(width-1),y:p.y*(height-1)}));if(!Number.isInteger(maxSide)||maxSide<16||maxSide>1600)throw new Error('Choose a supported worksheet output size.');
  const rawWidth=Math.max(2,Math.round((distance(c[0],c[1])+distance(c[3],c[2]))/2)+1),rawHeight=Math.max(2,Math.round((distance(c[0],c[3])+distance(c[1],c[2]))/2)+1),scale=Math.min(1,maxSide/Math.max(rawWidth,rawHeight));
  const outWidth=Math.max(2,Math.round(rawWidth*scale)),outHeight=Math.max(2,Math.round(rawHeight*scale)),destination=[{x:0,y:0},{x:1,y:0},{x:1,y:1},{x:0,y:1}],matrix=[],values=[];
  for(let i=0;i<4;i++){const u=destination[i].x,v=destination[i].y,x=c[i].x,y=c[i].y;matrix.push([u,v,1,0,0,0,-x*u,-x*v]);values.push(x);matrix.push([0,0,0,u,v,1,-y*u,-y*v]);values.push(y);}
  const m=solve(matrix,values),out=new Uint8ClampedArray(outWidth*outHeight*4);
  for(let y=0;y<outHeight;y++)for(let x=0;x<outWidth;x++){
    const u=x/(outWidth-1),v=y/(outHeight-1),d=m[6]*u+m[7]*v+1,sx=Math.max(0,Math.min(width-1,(m[0]*u+m[1]*v+m[2])/d)),sy=Math.max(0,Math.min(height-1,(m[3]*u+m[4]*v+m[5])/d)),x0=Math.floor(sx),y0=Math.floor(sy),x1=Math.min(width-1,x0+1),y1=Math.min(height-1,y0+1),fx=sx-x0,fy=sy-y0,at=(y*outWidth+x)*4;
    for(let channel=0;channel<4;channel++)out[at+channel]=pixels[(y0*width+x0)*4+channel]*(1-fx)*(1-fy)+pixels[(y0*width+x1)*4+channel]*fx*(1-fy)+pixels[(y1*width+x0)*4+channel]*(1-fx)*fy+pixels[(y1*width+x1)*4+channel]*fx*fy;
  }
  return{pixels:out,width:outWidth,height:outHeight};
}
