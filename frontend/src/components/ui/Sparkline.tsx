import React from "react";

interface SparklineProps {
  /** Series of numeric values, oldest first. */
  data: number[];
  /** Value treated as 100% for scaling (e.g. the limit). Defaults to series max. */
  max?: number;
  className?: string;
  strokeClassName?: string;
}

/**
 * Lightweight inline SVG sparkline (24px grid feel, currentColor stroke).
 * Renders a filled area + line; no external chart dependency.
 */
export default function Sparkline({ data, max, className, strokeClassName }: SparklineProps) {
  const W = 100;
  const H = 28;

  if (!data || data.length < 2) {
    return (
      <svg viewBox={`0 0 ${W} ${H}`} className={className} preserveAspectRatio="none" aria-hidden="true">
        <line x1="0" y1={H - 1} x2={W} y2={H - 1} stroke="currentColor" strokeOpacity="0.2" strokeWidth="1" />
      </svg>
    );
  }

  const seriesMax = Math.max(...data, 0.0001);
  const scaleMax = max !== undefined && max > 0 ? max : seriesMax * 1.15;
  const step = W / (data.length - 1);

  const points = data.map((v, i) => {
    const clamped = Math.max(0, Math.min(v, scaleMax));
    const y = H - (clamped / scaleMax) * (H - 2) - 1;
    return `${(i * step).toFixed(2)},${y.toFixed(2)}`;
  });

  const linePath = `M ${points.join(" L ")}`;
  const areaPath = `${linePath} L ${W},${H} L 0,${H} Z`;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className={className} preserveAspectRatio="none" aria-hidden="true">
      <path d={areaPath} fill="currentColor" fillOpacity="0.12" stroke="none" />
      <path
        d={linePath}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinejoin="round"
        strokeLinecap="round"
        className={strokeClassName}
      />
    </svg>
  );
}
