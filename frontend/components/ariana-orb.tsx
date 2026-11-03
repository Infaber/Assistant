"use client";
import { useEffect, useRef } from "react";
import LegacyOrb from "./legacy-ariana-orb";
export const orbStyles = ["Silk ribbons", "Glass bubble", "Crystal burst", "Shard vortex", "Wireframe globe", "Particle swirl"] as const;
export type OrbState = "idle" | "listening" | "thinking" | "speaking";
const TAU = Math.PI * 2;

/** Transparent, twisted spherical sheets. No bitmap or prerecorded animation. */
function RibbonOrb({mode = "normal", theme = mode, style = 0, state = "idle", level = 0}: {
  mode?: "normal" | "local"; theme?: "normal" | "local"; style?: number; state?: OrbState; level?: number;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const current = useRef({theme, style, state, level});
  current.current = {theme, style, state, level};
  useEffect(() => {
    const element = canvas.current!;
    const ctx = element.getContext("2d");
    if (!ctx) return;
    const motion = matchMedia("(prefers-reduced-motion: reduce)");
    let frame = 0, previous = 0, time = 0, energy = 0;
    const resize = () => {
      const size = Math.round(element.clientWidth * Math.min(devicePixelRatio || 1, 2));
      element.width = size; element.height = size;
    };
    const observer = new ResizeObserver(resize); observer.observe(element); resize();
    function draw(now: number) {
      if (!motion.matches && previous && now - previous < 1000 / 30) {
        frame = requestAnimationFrame(draw); return;
      }
      if (!element.width || !element.height) {
        if (!document.hidden) frame=requestAnimationFrame(draw);
        return;
      }
      const context = ctx!;
      const dt = Math.min((now - previous) / 1000 || .016, .05); previous = now;
      const props = current.current;
      const target = props.state === "thinking" ? .35 : props.state === "idle" ? 0 : Math.min(1, props.level * 3);
      energy += (target - energy) * (1 - Math.exp(-dt * 8));
      if (!motion.matches) time += dt * (props.state === "thinking" ? .22 : .09);
      context.setTransform(element.width, 0, 0, element.height, element.width / 2, element.height / 2);
      context.clearRect(-.5, -.5, 1, 1);
      const red = props.theme === "local";
      const cyan = red ? "255,91,107" : "142,222,255";
      const pearl = red ? "255,202,188" : "218,238,255";
      const lavender = red ? "241,65,91" : "198,177,244";
      const halo = context.createRadialGradient(0, .06, .12, 0, .04, .49);
      halo.addColorStop(0, `rgba(${cyan},.025)`); halo.addColorStop(.55, `rgba(${lavender},.075)`); halo.addColorStop(1, `rgba(${cyan},0)`);
      context.fillStyle = halo; context.fillRect(-.5,-.5,1,1);
      context.save();
      const breath = motion.matches ? 1 : 1 + Math.sin(time * 2) * .012 + energy * .025;
      context.scale(breath, breath);
      // Three broad bands wrap a hollow volume. Their latitude twists as they orbit.
      const project = (angle: number, across: number, band: number) => {
        const latitude = across * .48 + Math.sin(angle * 2 + time * .6 + band * 1.7) * .19;
        const r = .345 * (1 + .065 * Math.sin(angle + band * 2.1));
        let x = r * Math.cos(latitude) * Math.cos(angle);
        const y = r * Math.cos(latitude) * Math.sin(angle);
        let z = r * Math.sin(latitude);
        const tilt = [.95, -.85, .3][band] + Math.sin(time * .4) * .09;
        const yy = y * Math.cos(tilt) - z * Math.sin(tilt);
        z = y * Math.sin(tilt) + z * Math.cos(tilt);
        const rotation = [-.5, .65, 1.8][band] + time * .13 + (props.style > 1 ? props.style * .1 : 0);
        const xx = x * Math.cos(rotation) - yy * Math.sin(rotation);
        const py = x * Math.sin(rotation) + yy * Math.cos(rotation);
        x = xx;
        const perspective = 1 + z * .25;
        return [x * perspective * 1.04, py * perspective, z];
      };
      context.globalCompositeOperation = "screen";
      // Draw the rear halves first, then the front, keeping the sheets translucent.
      for (const front of [false, true]) {
        for (let band = 0; band < 3; band++) {
          const color = band === 1 ? lavender : cyan;
          for (let strip = 0; strip < 36; strip++) {
            const u = -1 + strip / 18, v = u + 1.06 / 18;
            const edge = Math.pow(Math.abs((u + v) / 2), 5);
            const gradient = context.createLinearGradient(-.3,-.3,.32,.3);
            gradient.addColorStop(0, `rgba(${cyan},${.18 + edge * .25})`);
            gradient.addColorStop(.35, `rgba(${color},${.06 + edge * .15})`);
            gradient.addColorStop(.7, `rgba(${color},${.10 + edge * .23})`);
            gradient.addColorStop(1, `rgba(${pearl},${.22 + edge * .28})`);
            context.fillStyle = gradient; context.globalAlpha = front ? 1 : .5;
            let upper: number[][] = [], lower: number[][] = [];
            const fill = () => {
              if (!upper.length) return;
              context.beginPath();
              [...upper,...lower.reverse()].forEach(([x,y],i)=>i ? context.lineTo(x,y) : context.moveTo(x,y));
              context.closePath(); context.fill(); upper=[];lower=[];
            };
            for (let segment = 0; segment <= 180; segment++) {
              const a = segment / 180 * TAU;
              const p = project(a,u,band), q = project(a,v,band);
              if (((p[2]+q[2]) > 0) !== front) { fill(); continue; }
              upper.push(p);lower.push(q);
            }
            fill();context.globalAlpha=1;
          }
          for (const edge of [-1,1]) {
            context.beginPath();
            let pen = false;
            for(let segment=0;segment<=192;segment++) {
              const [x,y,z] = project(segment/192*TAU,edge,band);
              if ((z > 0) !== front) {pen=false;continue;}
              if (pen) context.lineTo(x,y); else context.moveTo(x,y); pen=true;
            }
            context.strokeStyle = `rgba(${pearl},${front ? .9 : .38})`;
            context.lineWidth = .00115; context.shadowColor=`rgba(${color},.6)`;context.shadowBlur=8;context.stroke();context.shadowBlur=0;
          }
        }
      }
      context.restore();
      if (!document.hidden && !motion.matches) frame = requestAnimationFrame(draw);
    }
    const resume = () => { cancelAnimationFrame(frame);previous=0;frame=requestAnimationFrame(draw); };
    document.addEventListener("visibilitychange",resume);motion.addEventListener("change",resume);
    resume();
    // Reduced motion still reflects state and palette changes without continuous motion.
    const still = setInterval(()=>{if(motion.matches && !document.hidden) resume();},250);
    return ()=>{cancelAnimationFrame(frame);clearInterval(still);observer.disconnect();document.removeEventListener("visibilitychange",resume);motion.removeEventListener("change",resume);};
  }, []);
  return <canvas ref={canvas} className="ariana-orb" aria-hidden="true" data-mode={mode} data-theme={theme} data-style={style} data-state={state}/>;
}

export default function ArianaOrb(props: Parameters<typeof RibbonOrb>[0]) {
  return (props.style || 0) >= 2 ? <LegacyOrb {...props}/> : <RibbonOrb {...props}/>;
}
