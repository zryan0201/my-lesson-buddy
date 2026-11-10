/* Local illumination correction for a rectified white-paper worksheet.
 * This estimates light from neutral paper, never from an object's expected
 * color or shape. RGB channels receive one shared gain; artwork is not redrawn.
 * Ambiguous, colored or very dark backgrounds stay unchanged for manual review. */
const MAX_PIXELS=2_560_000,MAX_GAIN=2.35;
const clamp=(n,low,high)=>Math.max(low,Math.min(high,n));

function percentile(values,fraction){
  if(!values.length)return 0;
  const ordered=[...values].sort((a,b)=>a-b);
  return ordered[Math.min(ordered.length-1,Math.floor((ordered.length-1)*fraction))];
}
function validate(pixels,width,height,strength){
  if(!Number.isInteger(width)||!Number.isInteger(height)||width<1||height<1||width>10000||height>10000||width*height>MAX_PIXELS||!(pixels instanceof Uint8Array||pixels instanceof Uint8ClampedArray)||pixels.length!==width*height*4)throw new Error('Choose a supported worksheet photo for lighting correction.');
  if(!Number.isFinite(strength)||strength<0||strength>1)throw new Error('Choose a lighting correction strength from zero to one.');
}

/** Return new pixels even on a no-op; callers can keep the original photo.
 * Alpha is preserved. Light is estimated only from sufficiently opaque neutral
 * pixels, so colorful illustrations and black printed text are not paper. */
export function normalizePaperLighting(pixels,width,height,{strength=1}={}){
  validate(pixels,width,height,strength);
  const output=new Uint8ClampedArray(pixels),total=width*height;
  const stats={paperFraction:0,fieldRange:0,medianPaper:0,maxGain:1,reason:'already-even'};
  const unchanged=reason=>({pixels:output,applied:false,stats:{...stats,reason}});
  if(strength===0)return unchanged('disabled');
  if(width<16||height<16)return unchanged('too-small');
  const columns=Math.min(32,Math.max(2,Math.ceil(width/40))),rows=Math.min(32,Math.max(2,Math.ceil(height/40)));
  const values=new Float64Array(columns*rows);values.fill(NaN);
  let paperPixels=0;
  for(let ty=0;ty<rows;ty++)for(let tx=0;tx<columns;tx++){
    const left=Math.floor(tx*width/columns),right=Math.floor((tx+1)*width/columns),top=Math.floor(ty*height/rows),bottom=Math.floor((ty+1)*height/rows);
    const neutral=[];
    for(let y=top;y<bottom;y++)for(let x=left;x<right;x++){
      const at=(y*width+x)*4;if(pixels[at+3]<240)continue;
      const r=pixels[at],g=pixels[at+1],b=pixels[at+2],high=Math.max(r,g,b),low=Math.min(r,g,b),luminance=(r+g+b)/3;
      if(luminance>=80&&high-low<=Math.max(18,luminance*.11))neutral.push(luminance);
    }
    paperPixels+=neutral.length;
    if(neutral.length>=Math.max(8,(right-left)*(bottom-top)*.22))values[ty*columns+tx]=percentile(neutral,.72);
  }
  stats.paperFraction=paperPixels/total;
  const known=[];for(let i=0;i<values.length;i++)if(Number.isFinite(values[i]))known.push({i,x:i%columns,y:Math.floor(i/columns),value:values[i]});
  if(stats.paperFraction<.42||known.length<values.length*.32)return unchanged('not-enough-neutral-paper');
  const samples=known.map(p=>p.value),dark=percentile(samples,.1),bright=percentile(samples,.9),median=percentile(samples,.5);
  stats.fieldRange=bright-dark;stats.medianPaper=median;
  if(bright<215||median<110)return unchanged('too-dark-or-uncertain');
  // Uniform gray can be gray paper rather than a shadow. Do not whiten it by
  // assumption. Uniform bright scans also stay bit-for-bit unchanged.
  if(stats.fieldRange<10)return unchanged('already-even');
  if(dark<90||bright/Math.max(dark,1)>2.5)return unchanged('lighting-too-uneven');

  // Interpolate missing cells from nearby paper, rather than estimating light
  // from colorful ink in an object. The grid is bounded to at most 32×32.
  for(let i=0;i<values.length;i++)if(!Number.isFinite(values[i])){
    const x=i%columns,y=Math.floor(i/columns);
    const nearby=known.map(p=>({value:p.value,distance:(x-p.x)**2+(y-p.y)**2})).sort((a,b)=>a.distance-b.distance).slice(0,8);
    let sum=0,weight=0;for(const p of nearby){const w=1/(p.distance+.25);sum+=p.value*w;weight+=w;}
    values[i]=sum/weight;
  }
  const field=new Float64Array(values.length);
  for(let y=0;y<rows;y++)for(let x=0;x<columns;x++){
    let sum=0,weight=0;
    for(let dy=-1;dy<=1;dy++)for(let dx=-1;dx<=1;dx++){
      const xx=x+dx,yy=y+dy;if(xx<0||xx>=columns||yy<0||yy>=rows)continue;
      const w=dx===0&&dy===0?8:dx===0||dy===0?1:.5;sum+=values[yy*columns+xx]*w;weight+=w;
    }
    field[y*columns+x]=sum/weight;
  }
  let maximum=1,changed=0;
  for(let y=0;y<height;y++){
    const fy=clamp((y+.5)*rows/height-.5,0,rows-1),y0=Math.floor(fy),y1=Math.min(rows-1,y0+1),wy=fy-y0;
    for(let x=0;x<width;x++){
      const at=(y*width+x)*4;if(pixels[at+3]===0)continue;
      const fx=clamp((x+.5)*columns/width-.5,0,columns-1),x0=Math.floor(fx),x1=Math.min(columns-1,x0+1),wx=fx-x0;
      const top=field[y0*columns+x0]*(1-wx)+field[y0*columns+x1]*wx,bottom=field[y1*columns+x0]*(1-wx)+field[y1*columns+x1]*wx;
      const illumination=top*(1-wy)+bottom*wy;
      const gain=1+(clamp(255/illumination,1,MAX_GAIN)-1)*strength;maximum=Math.max(maximum,gain);
      for(let c=0;c<3;c++)output[at+c]=pixels[at+c]*gain;
      if(Math.abs(output[at]-pixels[at])+Math.abs(output[at+1]-pixels[at+1])+Math.abs(output[at+2]-pixels[at+2])>2)changed++;
    }
  }
  stats.maxGain=maximum;stats.reason='paper-lighting-normalized';stats.changedFraction=changed/total;
  return {pixels:output,applied:changed>0,stats};
}
