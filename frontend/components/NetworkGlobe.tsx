"use client";

import { useEffect, useRef } from "react";

interface P3 { x: number; y: number; z: number }
interface P2 { x: number; y: number; z: number }

function rotateY(p: P3, a: number): P3 {
  return {
    x: p.x * Math.cos(a) - p.z * Math.sin(a),
    y: p.y,
    z: p.x * Math.sin(a) + p.z * Math.cos(a),
  };
}

function project(p: P3): P2 {
  const fov = 900;
  const s   = fov / (fov + p.z);
  return { x: p.x * s, y: p.y * s, z: p.z };
}

function spherePt(r: number, lat: number, lon: number): P3 {
  const phi   = (lat - 0.5) * Math.PI;
  const theta = lon * Math.PI * 2;
  return {
    x: r * Math.cos(phi) * Math.cos(theta),
    y: r * Math.sin(phi),
    z: r * Math.cos(phi) * Math.sin(theta),
  };
}

export default function NetworkGlobe() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const angleRef  = useRef(0);
  const rafRef    = useRef<number | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const LATS  = 10;
    const LONS  = 14;
    const SEGS  = 60;

    function resize() {
      canvas!.width  = canvas!.offsetWidth;
      canvas!.height = canvas!.offsetHeight;
    }
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);

    function draw() {
      if (!canvas || !ctx) return;
      const W = canvas.width;
      const H = canvas.height;
      const R = Math.min(W, H) * 0.44;
      const a = angleRef.current;

      ctx.clearRect(0, 0, W, H);
      ctx.save();
      ctx.translate(W / 2, H / 2);

      /* latitude rings */
      for (let li = 1; li < LATS; li++) {
        const lat = li / LATS;
        const phi = (lat - 0.5) * Math.PI;
        const ry  = R * Math.sin(phi);
        const rx  = R * Math.cos(phi);

        for (let si = 0; si < SEGS; si++) {
          const t0 = (si / SEGS) * Math.PI * 2;
          const t1 = ((si + 1) / SEGS) * Math.PI * 2;

          const q0 = rotateY({ x: rx * Math.cos(t0), y: ry, z: rx * Math.sin(t0) }, a);
          const q1 = rotateY({ x: rx * Math.cos(t1), y: ry, z: rx * Math.sin(t1) }, a);
          const p0 = project(q0);
          const p1 = project(q1);

          const depth = ((q0.z + q1.z) / 2 / R + 1) / 2;
          ctx.beginPath();
          ctx.moveTo(p0.x, p0.y);
          ctx.lineTo(p1.x, p1.y);
          ctx.strokeStyle = `rgba(59,130,246,${depth * 0.14})`;
          ctx.lineWidth = 0.6;
          ctx.stroke();
        }
      }

      /* longitude arcs */
      for (let lo = 0; lo < LONS; lo++) {
        const theta = (lo / LONS) * Math.PI * 2;

        for (let si = 0; si < SEGS; si++) {
          const lat0 = si / SEGS;
          const lat1 = (si + 1) / SEGS;
          const q0 = rotateY(spherePt(R, lat0, lo / LONS), a);
          const q1 = rotateY(spherePt(R, lat1, lo / LONS), a);
          const p0 = project(q0);
          const p1 = project(q1);

          const depth = ((q0.z + q1.z) / 2 / R + 1) / 2;
          ctx.beginPath();
          ctx.moveTo(p0.x, p0.y);
          ctx.lineTo(p1.x, p1.y);
          ctx.strokeStyle = `rgba(139,92,246,${depth * 0.11})`;
          ctx.lineWidth = 0.6;
          ctx.stroke();
        }
      }

      /* glowing nodes at intersections */
      for (let li = 0; li <= LATS; li++) {
        for (let lo = 0; lo < LONS; lo++) {
          const q  = rotateY(spherePt(R, li / LATS, lo / LONS), a);
          const p  = project(q);
          const depth = (q.z / R + 1) / 2;
          if (depth < 0.42) continue; // skip back-facing

          const pulse = (Math.sin(angleRef.current * 3 + li * 0.7 + lo * 0.5) + 1) / 2;
          const r = 1.2 + pulse * 1.2;

          /* glow */
          const grd = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, r * 4);
          grd.addColorStop(0, `rgba(99,102,241,${depth * 0.55})`);
          grd.addColorStop(1, `rgba(99,102,241,0)`);
          ctx.beginPath();
          ctx.arc(p.x, p.y, r * 4, 0, Math.PI * 2);
          ctx.fillStyle = grd;
          ctx.fill();

          /* dot */
          ctx.beginPath();
          ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(139,92,246,${depth * 0.7})`;
          ctx.fill();
        }
      }

      ctx.restore();
      angleRef.current += 0.0035;
      rafRef.current = requestAnimationFrame(draw);
    }

    draw();
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      ro.disconnect();
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: "absolute",
        inset: 0,
        width: "100%",
        height: "100%",
        pointerEvents: "none",
        opacity: 0.75,
      }}
    />
  );
}
