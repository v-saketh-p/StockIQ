"use client";

import { useEffect, useRef, useState } from "react";

interface Props {
  value: number;
  duration?: number;         // ms
  decimals?: number;
  prefix?: string;
  suffix?: string;
  className?: string;
}

function easeOutExpo(t: number) {
  return t === 1 ? 1 : 1 - Math.pow(2, -10 * t);
}

export default function NumberTicker({
  value,
  duration = 800,
  decimals = 2,
  prefix = "",
  suffix = "",
  className = "",
}: Props) {
  const [display, setDisplay] = useState(0);
  const startRef  = useRef<number | null>(null);
  const fromRef   = useRef(0);
  const rafRef    = useRef<number | null>(null);
  const prevValue = useRef(value);

  useEffect(() => {
    fromRef.current  = prevValue.current;
    prevValue.current = value;
    startRef.current  = null;

    if (rafRef.current) cancelAnimationFrame(rafRef.current);

    function tick(ts: number) {
      if (startRef.current === null) startRef.current = ts;
      const elapsed = ts - startRef.current;
      const progress = Math.min(elapsed / duration, 1);
      const eased    = easeOutExpo(progress);
      setDisplay(fromRef.current + (value - fromRef.current) * eased);
      if (progress < 1) rafRef.current = requestAnimationFrame(tick);
    }

    rafRef.current = requestAnimationFrame(tick);
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current); };
  }, [value, duration]);

  const formatted = display.toFixed(decimals);

  return (
    <span className={`tabular-nums ${className}`}>
      {prefix}{formatted}{suffix}
    </span>
  );
}
