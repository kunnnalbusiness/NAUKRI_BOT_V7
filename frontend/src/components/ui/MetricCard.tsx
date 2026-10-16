import React from "react";
import { cn } from "@/lib/utils";

export interface MetricCardProps {
  label: string;
  value: string | number;
  subtext?: string;
  icon?: React.ReactNode;
  trend?: {
    value: string;
    isPositive?: boolean;
  };
  variant?: "default" | "success" | "warning" | "indigo";
  className?: string;
}

export function MetricCard({
  label,
  value,
  subtext,
  icon,
  trend,
  variant = "default",
  className,
}: MetricCardProps) {
  const iconBg = {
    default: "bg-slate-800 text-slate-300 border-slate-700/60",
    success: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
    warning: "bg-amber-500/10 text-amber-300 border-amber-500/20",
    indigo: "bg-indigo-500/10 text-indigo-400 border-indigo-500/20",
  };

  return (
    <div
      className={cn(
        "relative rounded-2xl border border-slate-800/80 bg-slate-900/60 p-4.5 sm:p-5 shadow-xs transition-all duration-150 hover:border-slate-700/80 hover:bg-slate-900/80",
        className
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-medium text-slate-400 tracking-wide">{label}</span>
        {icon && (
          <div
            className={cn(
              "flex h-8 w-8 items-center justify-center rounded-xl border",
              iconBg[variant]
            )}
          >
            {icon}
          </div>
        )}
      </div>

      <div className="mt-2.5 flex items-baseline gap-2">
        <span className="num text-2xl sm:text-3xl font-semibold text-slate-100 tracking-tight">
          {value}
        </span>
        {trend && (
          <span
            className={cn(
              "text-[11px] font-medium px-1.5 py-0.5 rounded-md",
              trend.isPositive
                ? "text-emerald-400 bg-emerald-500/10"
                : "text-slate-400 bg-slate-800"
            )}
          >
            {trend.value}
          </span>
        )}
      </div>

      {subtext && (
        <p className="mt-1 text-[11px] text-slate-400 leading-normal line-clamp-1">
          {subtext}
        </p>
      )}
    </div>
  );
}
