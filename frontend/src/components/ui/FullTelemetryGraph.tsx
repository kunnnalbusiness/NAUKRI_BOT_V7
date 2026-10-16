import React, { useId, useMemo, useState } from "react";
import { cn } from "@/lib/utils";

interface FullTelemetryGraphProps {
  title: string;
  data: number[];
  unit?: string;
  max?: number;
  color?: "emerald" | "cyan" | "amber" | "rose" | "purple";
  threshold?: number | null;
  thresholdLabel?: string;
  className?: string;
  height?: number;
}

const COLOR_MAP = {
  emerald: {
    stroke: "#10b981",
    fill: "#10b981",
    text: "text-emerald-400",
    bg: "bg-emerald-500/10",
    border: "border-emerald-500/20",
    glow: "shadow-emerald-500/20",
  },
  cyan: {
    stroke: "#06b6d4",
    fill: "#06b6d4",
    text: "text-cyan-400",
    bg: "bg-cyan-500/10",
    border: "border-cyan-500/20",
    glow: "shadow-cyan-500/20",
  },
  amber: {
    stroke: "#f59e0b",
    fill: "#f59e0b",
    text: "text-amber-400",
    bg: "bg-amber-500/10",
    border: "border-amber-500/20",
    glow: "shadow-amber-500/20",
  },
  rose: {
    stroke: "#f43f5e",
    fill: "#f43f5e",
    text: "text-rose-400",
    bg: "bg-rose-500/10",
    border: "border-rose-500/20",
    glow: "shadow-rose-500/20",
  },
  purple: {
    stroke: "#a855f7",
    fill: "#a855f7",
    text: "text-purple-400",
    bg: "bg-purple-500/10",
    border: "border-purple-500/20",
    glow: "shadow-purple-500/20",
  },
};

export default function FullTelemetryGraph({
  title,
  data,
  unit = "%",
  max,
  color = "emerald",
  threshold,
  thresholdLabel,
  className,
  height = 140,
}: FullTelemetryGraphProps) {
  const gradId = useId();
  const theme = COLOR_MAP[color] || COLOR_MAP.emerald;
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const cleanData = useMemo(() => {
    if (!data || data.length === 0) return [0, 0];
    if (data.length === 1) return [data[0], data[0]];
    return data;
  }, [data]);

  const currentVal = cleanData[cleanData.length - 1] ?? 0;
  const peakVal = Math.max(...cleanData);
  const minVal = Math.min(...cleanData);
  const avgVal = cleanData.reduce((a, b) => a + b, 0) / cleanData.length;

  const seriesMax = Math.max(peakVal, 0.001);
  const scaleMax = max !== undefined && max > 0 ? max : Math.max(seriesMax * 1.15, 10);

  // SVG coordinate geometry
  const SVG_W = 600;
  const SVG_H = height;
  const PAD_TOP = 14;
  const PAD_BOTTOM = 24;
  const PAD_LEFT = 36;
  const PAD_RIGHT = 12;

  const plotW = SVG_W - PAD_LEFT - PAD_RIGHT;
  const plotH = SVG_H - PAD_TOP - PAD_BOTTOM;

  const points = useMemo(() => {
    return cleanData.map((v, i) => {
      const x = PAD_LEFT + (i / (cleanData.length - 1)) * plotW;
      const clamped = Math.max(0, Math.min(v, scaleMax));
      const y = PAD_TOP + plotH - (clamped / scaleMax) * plotH;
      return { x, y, v };
    });
  }, [cleanData, scaleMax, plotW, plotH, PAD_LEFT, PAD_TOP]);

  const linePath = useMemo(() => {
    if (points.length < 2) return "";
    return `M ${points.map((p) => `${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(" L ")}`;
  }, [points]);

  const areaPath = useMemo(() => {
    if (points.length < 2) return "";
    const first = points[0];
    const last = points[points.length - 1];
    const baseLine = (PAD_TOP + plotH).toFixed(2);
    return `${linePath} L ${last.x.toFixed(2)},${baseLine} L ${first.x.toFixed(2)},${baseLine} Z`;
  }, [linePath, points, PAD_TOP, plotH]);

  const latestPoint = points[points.length - 1];
  const activePoint = hoverIndex !== null && points[hoverIndex] ? points[hoverIndex] : latestPoint;

  // Threshold line coordinate if specified
  const thresholdY =
    threshold !== undefined && threshold !== null && threshold > 0
      ? PAD_TOP + plotH - (Math.min(threshold, scaleMax) / scaleMax) * plotH
      : null;

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const clientX = e.clientX - rect.left;
    const ratio = Math.max(0, Math.min(1, (clientX - (PAD_LEFT / SVG_W) * rect.width) / ((plotW / SVG_W) * rect.width)));
    const targetIdx = Math.round(ratio * (points.length - 1));
    setHoverIndex(Math.max(0, Math.min(points.length - 1, targetIdx)));
  };

  return (
    <div className={cn("rounded-xl border border-slate-800 bg-slate-950/80 p-3 flex flex-col gap-2.5", className)}>
      {/* Chart Header & Stats Pills */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-slate-200">{title}</span>
          <span className="text-[10px] text-slate-500 font-mono">15m Window ({cleanData.length} samples)</span>
        </div>

        <div className="flex items-center gap-1.5 text-[11px] font-mono">
          <span className={cn("rounded px-2 py-0.5 border font-semibold", theme.bg, theme.border, theme.text)}>
            Cur: {currentVal.toFixed(1)}
            {unit}
          </span>
          <span className="rounded px-1.5 py-0.5 bg-slate-900 border border-slate-800 text-slate-400">
            Avg: {avgVal.toFixed(1)}
            {unit}
          </span>
          <span className="rounded px-1.5 py-0.5 bg-slate-900 border border-slate-800 text-slate-400">
            Max: {peakVal.toFixed(1)}
            {unit}
          </span>
          <span className="rounded px-1.5 py-0.5 bg-slate-900 border border-slate-800 text-slate-400">
            Min: {minVal.toFixed(1)}
            {unit}
          </span>
        </div>
      </div>

      {/* SVG Canvas */}
      <div className="relative w-full overflow-hidden rounded-lg bg-slate-950/90 border border-slate-900/80">
        <svg
          viewBox={`0 0 ${SVG_W} ${SVG_H}`}
          className="w-full h-auto cursor-crosshair select-none"
          preserveAspectRatio="none"
          onMouseMove={handleMouseMove}
          onMouseLeave={() => setHoverIndex(null)}
        >
          <defs>
            <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={theme.fill} stopOpacity="0.32" />
              <stop offset="60%" stopColor={theme.fill} stopOpacity="0.08" />
              <stop offset="100%" stopColor={theme.fill} stopOpacity="0.01" />
            </linearGradient>
            <filter id={`glow-${gradId}`} x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="2" result="blur" />
              <feComposite in="SourceGraphic" in2="blur" operator="over" />
            </filter>
          </defs>

          {/* Grid lines and Y-axis scale */}
          {[1.0, 0.75, 0.5, 0.25, 0.0].map((ratio, i) => {
            const y = PAD_TOP + plotH - ratio * plotH;
            const val = ratio * scaleMax;
            return (
              <g key={i}>
                <line
                  x1={PAD_LEFT}
                  y1={y}
                  x2={PAD_LEFT + plotW}
                  y2={y}
                  stroke="#334155"
                  strokeOpacity={i === 4 ? 0.5 : 0.25}
                  strokeDasharray={i === 4 ? "none" : "4 4"}
                  strokeWidth="1"
                />
                <text
                  x={PAD_LEFT - 6}
                  y={y + 3}
                  textAnchor="end"
                  fill="#64748b"
                  fontSize="9"
                  fontFamily="monospace"
                >
                  {val.toFixed(0)}
                  {unit}
                </text>
              </g>
            );
          })}

          {/* Threshold line (e.g. Quota Limit) */}
          {thresholdY !== null && (
            <g>
              <line
                x1={PAD_LEFT}
                y1={thresholdY}
                x2={PAD_LEFT + plotW}
                y2={thresholdY}
                stroke="#f43f5e"
                strokeWidth="1.5"
                strokeDasharray="6 3"
              />
              <text
                x={PAD_LEFT + plotW - 4}
                y={thresholdY - 3}
                textAnchor="end"
                fill="#f43f5e"
                fontSize="9"
                fontFamily="monospace"
                fontWeight="600"
              >
                {thresholdLabel || `Limit: ${threshold}${unit}`}
              </text>
            </g>
          )}

          {/* Area fill */}
          {areaPath && <path d={areaPath} fill={`url(#${gradId})`} />}

          {/* Stroke path */}
          {linePath && (
            <path
              d={linePath}
              fill="none"
              stroke={theme.stroke}
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              filter={`url(#glow-${gradId})`}
            />
          )}

          {/* Latest live pulsing dot */}
          {latestPoint && (
            <g>
              <circle cx={latestPoint.x} cy={latestPoint.y} r="3" fill={theme.stroke} />
              <circle
                cx={latestPoint.x}
                cy={latestPoint.y}
                r="6"
                fill="none"
                stroke={theme.stroke}
                strokeWidth="1.5"
                opacity="0.6"
              />
            </g>
          )}

          {/* Hover Crosshair & Tooltip Indicator */}
          {hoverIndex !== null && activePoint && (
            <g>
              <line
                x1={activePoint.x}
                y1={PAD_TOP}
                x2={activePoint.x}
                y2={PAD_TOP + plotH}
                stroke="#94a3b8"
                strokeWidth="1"
                strokeDasharray="3 3"
              />
              <circle cx={activePoint.x} cy={activePoint.y} r="4.5" fill="#ffffff" stroke={theme.stroke} strokeWidth="2.5" />
            </g>
          )}

          {/* Bottom X-axis time marks */}
          <text x={PAD_LEFT} y={SVG_H - 6} fill="#64748b" fontSize="9" fontFamily="monospace">
            -15 min
          </text>
          <text x={PAD_LEFT + plotW * 0.5} y={SVG_H - 6} textAnchor="middle" fill="#64748b" fontSize="9" fontFamily="monospace">
            -7.5 min
          </text>
          <text x={PAD_LEFT + plotW} y={SVG_H - 6} textAnchor="end" fill={theme.stroke} fontSize="9" fontFamily="monospace" fontWeight="600">
            ● Live
          </text>
        </svg>

        {/* Hover info tooltip floating badge */}
        {hoverIndex !== null && activePoint && (
          <div
            className="absolute top-2 pointer-events-none rounded bg-slate-900/95 border border-slate-700 px-2 py-0.5 text-[10px] font-mono text-slate-200 shadow-md transform -translate-x-1/2"
            style={{
              left: `${(activePoint.x / SVG_W) * 100}%`,
            }}
          >
            Sample: <span className={cn("font-semibold", theme.text)}>{activePoint.v.toFixed(1)}{unit}</span>
          </div>
        )}
      </div>
    </div>
  );
}
