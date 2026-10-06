'use client';

import { useEffect, useRef } from 'react';
import { useTrackVolume } from '@livekit/components-react';

type CoreState = 'standby' | 'connecting' | 'ready' | 'listening' | 'thinking' | 'speaking' | 'error';

// A procedural point globe: no textures, network requests, or synthetic telemetry.
export default function IntelligenceCore({ state, track }: { state: CoreState; track: Parameters<typeof useTrackVolume>[0] }) {
  const volume = useTrackVolume(track);
  const canvas = useRef<HTMLCanvasElement>(null);
  const signal = useRef({ state, volume });
  useEffect(() => { signal.current = { state, volume }; }, [state, volume]);

  useEffect(() => {
    const element = canvas.current;
    const ctx = element?.getContext('2d');
    if (!element || !ctx) return;
    const motion = matchMedia('(prefers-reduced-motion: reduce)');
    let frame = 0;
    let previous = 0;
    let rotation = 0;
    let energy = 0;
    let size = 440;
    const points = Array.from({ length: 950 }, (_, i) => {
      const y = 1 - (i / 949) * 2;
      const radius = Math.sqrt(1 - y * y);
      const angle = i * Math.PI * (3 - Math.sqrt(5));
      return { x: Math.cos(angle) * radius, y, z: Math.sin(angle) * radius };
    });
    function resize() {
      size = element!.getBoundingClientRect().width;
      const ratio = Math.min(devicePixelRatio || 1, 2);
      element!.width = size * ratio;
      element!.height = size * ratio;
      ctx!.setTransform(ratio, 0, 0, ratio, 0, 0);
      previous = 0;
    }
    const observer = new ResizeObserver(resize);
    observer.observe(element);
    resize();

    function draw(now: number) {
      frame = requestAnimationFrame(draw);
      // Render at 30fps; slow/static refresh for reduced motion and hidden tabs.
      if (document.hidden || now - previous < (motion.matches ? 250 : 33)) return;
      const delta = Math.min(now - previous, 100);
      previous = now;
      const { state: current, volume: amplitude } = signal.current;
      const thinking = current === 'thinking' || current === 'connecting';
      const colour = current === 'error' ? '255, 111, 112' : thinking ? '255, 182, 107' : '108, 231, 247';
      energy += (Math.min(amplitude * 3, 1) - energy) * .15;
      if (!motion.matches) rotation += delta * (thinking ? .0003 : .00009);
      const radius = size * (.275 + (motion.matches ? 0 : energy * .028));
      const centre = size / 2;
      ctx!.clearRect(0, 0, size, size);
      const glow = ctx!.createRadialGradient(centre, centre, 0, centre, centre, radius * 1.6);
      glow.addColorStop(0, `rgba(${colour},.07)`);
      glow.addColorStop(.65, `rgba(${colour},.035)`);
      glow.addColorStop(1, `rgba(${colour},0)`);
      ctx!.fillStyle = glow;
      ctx!.fillRect(0, 0, size, size);
      const sin = Math.sin(rotation), cos = Math.cos(rotation);
      const projected = points.map((point) => {
        const x = point.x * cos - point.z * sin;
        const z = point.x * sin + point.z * cos;
        const y = point.y * .96 - z * .28;
        const depth = z * .96 + point.y * .28;
        const perspective = 3 / (3 - depth * .3);
        return { x: centre + x * radius * perspective, y: centre + y * radius * perspective, z: depth };
      }).sort((a, b) => a.z - b.z);
      for (const point of projected) {
        const opacity = .14 + (point.z + 1) * .32;
        ctx!.fillStyle = `rgba(${colour},${opacity})`;
        ctx!.beginPath();
        ctx!.arc(point.x, point.y, (.65 + (point.z + 1) * .5) * size / 440, 0, Math.PI * 2);
        ctx!.fill();
      }
      for (let meridian = 0; meridian < 5; meridian++) {
        ctx!.beginPath();
        for (let i = 0; i <= 80; i++) {
          const a = i / 80 * Math.PI * 2;
          const longitude = rotation + meridian / 5 * Math.PI;
          const x = Math.cos(a) * Math.cos(longitude);
          const z = Math.cos(a) * Math.sin(longitude);
          const y = Math.sin(a);
          const px = centre + x * radius;
          const py = centre + (y * .96 - z * .28) * radius;
          if (i === 0) ctx!.moveTo(px, py); else ctx!.lineTo(px, py);
        }
        ctx!.strokeStyle = `rgba(${colour},.08)`;
        ctx!.lineWidth = .6;
        ctx!.stroke();
      }
      // Latitude filaments make the moving globe legible at every screen size.
      for (let band = -2; band <= 2; band++) {
        ctx!.beginPath();
        for (let i = 0; i <= 100; i++) {
          const a = i / 100 * Math.PI * 2;
          const y = band * .27;
          const r = Math.sqrt(1 - y * y);
          const x = Math.cos(a + rotation) * r;
          const z = Math.sin(a + rotation) * r;
          const px = centre + x * radius;
          const py = centre + (y * .96 - z * .28) * radius;
          if (i === 0) ctx!.moveTo(px, py); else ctx!.lineTo(px, py);
        }
        ctx!.strokeStyle = `rgba(${colour},.13)`;
        ctx!.lineWidth = .6;
        ctx!.stroke();
      }
    }
    frame = requestAnimationFrame(draw);
    return () => { cancelAnimationFrame(frame); observer.disconnect(); };
  }, []);

  return <div className="intelligence-core" data-state={state} aria-hidden="true">
    <div className="core-aura" />
    <svg className="core-grid" viewBox="0 0 480 480" fill="none">
      <path d="M240 0v66m0 348v66M0 240h66m348 0h66" />
      <circle cx="240" cy="240" r="228" strokeDasharray="1 11" />
      <circle cx="240" cy="240" r="211" />
      <path d="M80 70H62v18m338-18h18v18M62 392v18h18m338-18v18h-18" />
      <path d="M74 74 103 103m274 274 29 29M74 406l29-29M377 103l29-29" />
    </svg>
    <svg className="core-ring outer-ring" viewBox="0 0 480 480" fill="none">
      <circle cx="240" cy="240" r="198" strokeDasharray="240 71 90 43 320 480" />
      <circle className="ring-detail" cx="240" cy="240" r="190" strokeDasharray="2 7" />
      <circle className="ring-accent" cx="240" cy="240" r="198" strokeDasharray="56 1188" transform="rotate(72 240 240)" />
    </svg>
    <svg className="core-ring inner-ring" viewBox="0 0 480 480" fill="none">
      <circle cx="240" cy="240" r="171" strokeDasharray="165 36 50 116 220 488" />
      <circle className="ring-fine" cx="240" cy="240" r="163" strokeDasharray="310 205" />
    </svg>
    <canvas ref={canvas} className="particle-globe" />
    <div className="core-heart"><span /><span /><span /></div>
    <div className="core-axis axis-top">N</div><div className="core-axis axis-bottom">S</div>
    <div className="core-cross cross-left">+</div><div className="core-cross cross-right">+</div>
  </div>;
}
