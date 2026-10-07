"use client";
import { useEffect, useRef } from "react";
export const orbStyles = [
  "Flowing mesh",
  "Glass bubble",
  "Crystal burst",
  "Shard vortex",
  "Wireframe globe",
  "Particle swirl",
] as const;
export type OrbState = "idle" | "listening" | "thinking" | "speaking";
const TAU = Math.PI * 2;
export default function ArianaOrb({
  style = 0,
  state = "idle",
  level = 0,
}: {
  style?: number;
  state?: OrbState;
  level?: number;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const current = useRef({ style, state, level });
  current.current = { style, state, level };
  useEffect(() => {
    const element = canvas.current!;
    const context = element.getContext("2d", { alpha: false });
    if (!context) return;
    const ctx: CanvasRenderingContext2D = context;
    const motion = matchMedia("(prefers-reduced-motion: reduce)");
    let frame = 0,
      previous = 0,
      time = 0,
      energy = 0,
      speed = 0.18,
      tightness = 0,
      size = 0;
    let lastStyle = current.current.style,
      oldStyle = lastStyle,
      blend = 1;
    const resize = () => {
      size = element.clientWidth;
      const dpr = Math.min(devicePixelRatio || 1, 2);
      element.width = Math.round(size * dpr);
      element.height = element.width;
    };
    const observer = new ResizeObserver(resize);
    observer.observe(element);
    resize();
    const line = (points: number[][], color: string, width = 0.001) => {
      ctx.strokeStyle = color;
      ctx.lineWidth = width;
      ctx.beginPath();
      points.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
      ctx.stroke();
    };
    function inner(kind: number, alpha: number) {
      ctx.save();
      ctx.globalAlpha = alpha;
      const t = time,
        e = energy;
      if (kind === 0) {
        ctx.rotate(Math.sin(t * 0.12) * 0.18);
        for (let j = 0; j < 40; j++) {
          const points = [];
          for (let i = 0; i <= 80; i++) {
            const u = i / 80,
              a = u * TAU;
            const r = 0.23 + 0.045 * Math.sin(a * 2 + j * 0.11 + t * 0.6);
            points.push([
              Math.sin(a + j * 0.055) * r * (0.55 + Math.sin(j * 0.075) * 0.35),
              Math.cos(a) * r +
                Math.sin(a * 3 + t + j * 0.09) * (0.024 + e * 0.04),
            ]);
          }
          line(
            points,
            `rgba(${148 + j * 1.8},${208 + j * 0.4},${247 - j * 2},${0.3 + j * 0.003})`,
            0.0009,
          );
        }
      } else if (kind === 1 || kind === 5) {
        const glass = ctx.createRadialGradient(
          -0.075,
          -0.095,
          0.01,
          0,
          0,
          0.255,
        );
        glass.addColorStop(0, "rgba(169,219,255,.045)");
        glass.addColorStop(0.65, "rgba(5,21,35,.04)");
        glass.addColorStop(0.85, "rgba(54,139,184,.13)");
        glass.addColorStop(0.94, "rgba(93,189,231,.25)");
        glass.addColorStop(1, "rgba(23,40,76,.02)");
        ctx.fillStyle = glass;
        ctx.beginPath();
        ctx.arc(0, 0, 0.255, 0, TAU);
        ctx.fill();
        for (let j = 0; j < 18; j++) {
          const points = [];
          for (let i = 0; i <= 80; i++) {
            const a = (i / 80) * TAU;
            const r =
              0.245 + j * 0.0004 + Math.sin(a * 3 + t + j * 0.1) * 0.003;
            points.push([Math.cos(a) * r, Math.sin(a) * r]);
          }
          line(points, `rgba(131,213,248,${0.008 + j * 0.0007})`, 0.001);
        }
        ctx.save();
        ctx.rotate(-0.6 + Math.sin(t * 0.2) * 0.08);
        ctx.scale(1, 0.83);
        ctx.strokeStyle = "rgba(180,230,255,.23)";
        ctx.lineWidth = 0.003;
        ctx.beginPath();
        ctx.arc(0, 0, 0.246, 3.5, 4.8);
        ctx.stroke();
        ctx.restore();
        if (kind === 5)
          for (let i = 0; i < 600; i++) {
            const a = i * 2.399 + t * (0.12 + (i % 7) * 0.005),
              r = 0.05 + Math.sqrt(i / 600) * 0.19;
            const y = Math.sin(a) * r * 0.7;
            ctx.fillStyle = `rgba(91,233,250,${0.15 + (0.6 * (Math.sin(a) + 1)) / 2})`;
            ctx.beginPath();
            ctx.arc(
              Math.cos(a) * r,
              y + Math.sin(r * 15 + t) * 0.025,
              0.0006 + (i % 4) * 0.0003,
              0,
              TAU,
            );
            ctx.fill();
          }
      } else if (kind === 2) {
        for (let i = 0; i < 350; i++) {
          const a = i * 2.399 + t * 0.04,
            r = 0.12 + (0.5 + 0.5 * Math.sin(i * 71.17)) * (0.16 + e * 0.06);
          const x = Math.cos(a),
            y = Math.sin(a);
          const grad = ctx.createLinearGradient(
            x * 0.08,
            y * 0.08,
            x * r,
            y * r,
          );
          grad.addColorStop(0, "rgba(17,24,89,0)");
          grad.addColorStop(0.7, "rgba(45,92,238,.4)");
          grad.addColorStop(
            1,
            `rgba(${i % 8 === 0 ? "216,238,239" : "127,163,255"},.85)`,
          );
          ctx.fillStyle = grad;
          ctx.beginPath();
          ctx.moveTo(x * 0.08, y * 0.08);
          ctx.lineTo(x * r - y * 0.003, y * r + x * 0.003);
          ctx.lineTo(x * (r * 0.72) + y * 0.004, y * (r * 0.72) - x * 0.004);
          ctx.closePath();
          ctx.fill();
        }
      } else if (kind === 3) {
        for (let i = 0; i < 270; i++) {
          const u = i / 270,
            a = i * 2.399 + t * (0.16 + u * 0.18),
            r = 0.06 + u * 0.19,
            w = 0.001 + u * 0.005;
          ctx.save();
          ctx.translate(Math.cos(a) * r, Math.sin(a) * r * 0.85);
          ctx.rotate(a + t * 0.12);
          ctx.fillStyle = `rgba(${180 + (i % 60)},${180 + (i % 60)},${125 + (i % 60)},${0.2 + u * 0.45})`;
          ctx.beginPath();
          ctx.moveTo(-w, -w * 0.3);
          ctx.lineTo(w * 2, -w);
          ctx.lineTo(w * 0.3, w * 2.8);
          ctx.closePath();
          ctx.fill();
          ctx.restore();
        }
      } else {
        const rotate = t * 0.12,
          tilt = 0.35;
        const project = (lat: number, lon: number) => {
          const x = Math.cos(lat) * Math.cos(lon + rotate),
            z = Math.cos(lat) * Math.sin(lon + rotate),
            y = Math.sin(lat);
          return [
            x * 0.24,
            (y * Math.cos(tilt) - z * Math.sin(tilt)) * 0.24,
            z,
          ];
        };
        for (let j = 0; j < 24; j++) {
          const lat = -Math.PI / 2 + (j / 23) * Math.PI,
            points = [];
          for (let i = 0; i <= 90; i++) {
            const p = project(lat, (i / 90) * TAU);
            points.push(p);
          }
          line(
            points,
            `rgba(${132 + j * 4},${113 + j * 4},${201 - j * 2},.33)`,
            0.0008,
          );
        }
        for (let j = 0; j < 36; j++) {
          const points = [];
          for (let i = 0; i <= 55; i++)
            points.push(
              project(-Math.PI / 2 + (i / 55) * Math.PI, (j / 36) * TAU),
            );
          line(
            points,
            `rgba(${132 + j * 2.7},${113 + j * 3},${201 - j * 1.8},.3)`,
            0.0008,
          );
        }
      }
      ctx.restore();
    }
    function draw(now: number) {
      const dt = Math.min((now - previous) / 1000 || 0.016, 0.05);
      previous = now;
      const props = current.current;
      const target =
        props.state === "thinking"
          ? 0.5
          : props.state === "speaking" || props.state === "listening"
            ? Math.min(1, props.level * 3)
            : 0;
      tightness +=
        ((props.state === "listening" ? 0.007 : 0) - tightness) *
        (1 - Math.exp(-dt * 8));
      energy += (target - energy) * (1 - Math.exp(-dt * 9));
      speed +=
        ((props.state === "thinking"
          ? 1.25
          : props.state === "speaking"
            ? 0.45
            : 0.18) -
          speed) *
        (1 - Math.exp(-dt * 7));
      if (!motion.matches) time += dt * speed;
      if (props.style !== lastStyle) {
        oldStyle = lastStyle;
        lastStyle = props.style;
        blend = 0;
      }
      blend = Math.min(1, blend + dt * 2.5);
      ctx.setTransform(
        element.width,
        0,
        0,
        element.height,
        element.width / 2,
        element.height / 2,
      );
      ctx.fillStyle = "#000";
      ctx.fillRect(-0.5, -0.5, 1, 1);
      const breathing = motion.matches ? 1 : 1 + Math.sin(time * 1.5) * 0.012;
      ctx.scale(
        breathing * (1 + energy * 0.025),
        breathing * (1 + energy * 0.025),
      );
      const halo = ctx.createRadialGradient(0, 0, 0.27, 0, 0, 0.47);
      halo.addColorStop(0, "rgba(0,8,28,0)");
      halo.addColorStop(0.6, `rgba(0,58,173,${0.055 + energy * 0.03})`);
      halo.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = halo;
      ctx.fillRect(-0.5, -0.5, 1, 1);
      ctx.save();
      ctx.rotate(time * 0.12);
      // Tapered, overlapping light ribbons form two asymmetric crescents.
      ctx.globalCompositeOperation = "screen";
      for (let j = 0; j < 9; j++) {
        const radius = 0.35 + j * 0.003 - tightness,
          offset = j * 0.014;
        for (let side = 0; side < 2; side++)
          for (let i = 0; i < 95; i++) {
            const u = i / 95,
              a = -1.7 + u * 2.55 + side * Math.PI + offset;
            const envelope = Math.pow(Math.sin(u * Math.PI), 1.8),
              width = (0.004 + 0.017 * envelope) * (1 - j * 0.065);
            ctx.strokeStyle = `hsla(${233 - 40 * envelope - j * 1.3},100%,${25 + envelope * 24 + j}%,${envelope * (0.14 + energy * 0.05)})`;
            ctx.lineWidth = width;
            ctx.lineCap = "round";
            ctx.beginPath();
            ctx.arc(
              Math.sin(time * 0.3 + j) * 0.002,
              Math.cos(j) * 0.002,
              radius,
              a,
              a + 0.029,
            );
            ctx.stroke();
          }
      }
      ctx.restore();
      const eased = blend * blend * (3 - 2 * blend);
      if (blend < 1) inner(oldStyle, 1 - eased);
      inner(lastStyle, eased);
      if (!document.hidden) frame = requestAnimationFrame(draw);
    }
    const resume = () => {
      cancelAnimationFrame(frame);
      previous = 0;
      frame = requestAnimationFrame(draw);
    };
    document.addEventListener("visibilitychange", resume);
    motion.addEventListener("change", resume);
    resume();
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      document.removeEventListener("visibilitychange", resume);
      motion.removeEventListener("change", resume);
    };
  }, []);
  return (
    <canvas
      ref={canvas}
      className="ariana-orb"
      aria-hidden="true"
      data-style={style}
      data-state={state}
    />
  );
}
