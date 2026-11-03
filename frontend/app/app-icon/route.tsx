import { ImageResponse } from "next/og";
export const dynamic = "force-static";
// The same projected ribbon geometry as the live orb, rendered once for iOS.
export function GET() {
  const point=(angle:number,across:number,band:number)=>{
    const latitude=across*.48+Math.sin(angle*2+band*1.7)*.19;
    const radius=151*(1+.065*Math.sin(angle+band*2.1));
    const x=radius*Math.cos(latitude)*Math.cos(angle),y=radius*Math.cos(latitude)*Math.sin(angle),z=radius*Math.sin(latitude);
    const tilt=[.95,-.85,.3][band],rotation=[-.5,.65,1.8][band];
    const yy=y*Math.cos(tilt)-z*Math.sin(tilt),depth=y*Math.sin(tilt)+z*Math.cos(tilt),perspective=1+depth/1800;
    return [(256+(x*Math.cos(rotation)-yy*Math.sin(rotation))*perspective).toFixed(1),(256+(x*Math.sin(rotation)+yy*Math.cos(rotation))*perspective).toFixed(1),depth] as const;
  };
  let paths="";
  for(const front of [false,true])for(let band=0;band<3;band++){
    for(let strip=0;strip<20;strip++){
      const u=-1+strip/10,v=u+.106;let upper:string[]=[],lower:string[]=[];
      const fill=()=>{if(upper.length)paths+=`<path d="M${upper.join('L')}L${lower.reverse().join('L')}Z" fill="url(#${band===1?'lilac':'blue'})" opacity="${front?1:.5}"/>`;upper=[];lower=[];};
      for(let segment=0;segment<=120;segment++){
        const a=segment/120*Math.PI*2,p=point(a,u,band),q=point(a,v,band);
        if((p[2]+q[2]>0)!==front){fill();continue;}upper.push(`${p[0]},${p[1]}`);lower.push(`${q[0]},${q[1]}`);
      }fill();
    }
    for(const edge of [-1,1]){
      let path="",pen=false;
      for(let segment=0;segment<=160;segment++){const [x,y,z]=point(segment/160*Math.PI*2,edge,band);if((z>0)!==front){pen=false;continue;}path+=`${pen?'L':'M'}${x},${y}`;pen=true;}
      paths+=`<path d="${path}" fill="none" stroke="${band===1?'#d5c5ff':'#c9f0ff'}" stroke-width="1.2" opacity="${front?.9:.3}"/>`;
    }
  }
  const svg=`<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512"><defs><radialGradient id="halo"><stop stop-color="#93a8ed" stop-opacity=".17"/><stop offset="1" stop-color="#121116" stop-opacity="0"/></radialGradient><linearGradient id="blue" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#bbf2ff" stop-opacity=".33"/><stop offset=".5" stop-color="#81cefa" stop-opacity=".1"/><stop offset="1" stop-color="#e7eeff" stop-opacity=".3"/></linearGradient><linearGradient id="lilac"><stop stop-color="#c3c6ff" stop-opacity=".18"/><stop offset="1" stop-color="#e5c3ff" stop-opacity=".3"/></linearGradient></defs><rect width="512" height="512" fill="#121116"/><circle cx="256" cy="256" r="235" fill="url(#halo)"/>${paths}</svg>`;
  return new ImageResponse(<img src={`data:image/svg+xml;base64,${Buffer.from(svg).toString("base64")}`} width={512} height={512}/>,{width:512,height:512});
}
