import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, AlertTriangle, XCircle, RefreshCw } from "lucide-react";
import { apiGet } from "@/lib/api";
import { cn } from "@/lib/utils";

interface ComponentStatus {
  key: string;
  label: string;
  status: string;
  latency_ms: number | null;
  uptime: { "24h"?: number | null; "7d"?: number | null; "30d"?: number | null; "90d"?: number | null };
  daily: { date: string; uptime_pct: number | null }[];
}

interface StatusSummary {
  overall: string;
  banner: string;
  generated_at: string;
  components: ComponentStatus[];
  incidents: {
    component: string;
    started_at: string | null;
    resolved_at: string | null;
    note: string;
    manual: boolean;
  }[];
}

const BANNER_STYLE: Record<string, { wrap: string; icon: React.ElementType }> = {
  operational: { wrap: "border-emerald-500/20 bg-emerald-500/5 text-emerald-400", icon: CheckCircle2 },
  partial_outage: { wrap: "border-amber-500/20 bg-amber-500/5 text-amber-400", icon: AlertTriangle },
  major_outage: { wrap: "border-rose-500/20 bg-rose-500/5 text-rose-400", icon: XCircle },
};

function statusColor(status: string): string {
  return status === "up" ? "text-emerald-400" : "text-rose-400";
}

function barColor(pct: number | null): string {
  if (pct === null) return "bg-slate-700/50";
  if (pct >= 99.9) return "bg-emerald-500";
  if (pct >= 95) return "bg-emerald-500/60";
  if (pct >= 80) return "bg-amber-500";
  return "bg-rose-500";
}

function fmtPct(p: number | null | undefined): string {
  return p === null || p === undefined ? "—" : `${p.toFixed(2)}%`;
}

export default function PublicStatus() {
  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ["public-status-page"],
    queryFn: () => apiGet<StatusSummary>("/api/status/summary"),
    refetchInterval: 30000,
    retry: 1,
  });

  const [hoveredDay, setHoveredDay] = useState<{ comp: string; date: string; pct: number | null } | null>(null);

  const banner = BANNER_STYLE[data?.overall ?? "operational"] ?? BANNER_STYLE.operational;
  const BannerIcon = banner.icon;

  return (
    <div className="min-h-screen bg-[#000000] text-slate-100">
      <div className="mx-auto max-w-3xl px-4 py-10 md:px-8 space-y-8">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Service Status</h1>
            <p className="text-xs text-slate-500 mt-0.5">
              Public uptime overview{data?.generated_at ? ` · updated ${new Date(data.generated_at).toLocaleString()}` : ""}
            </p>
          </div>
          <button
            onClick={() => refetch()}
            className="p-2 rounded-lg text-slate-400 hover:text-emerald-400 hover:bg-emerald-500/10 transition-colors app-press"
            aria-label="Refresh status"
          >
            <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} />
          </button>
        </div>

        {/* Loading skeletons */}
        {isLoading && (
          <div className="space-y-4">
            <div className="h-16 rounded-xl border border-slate-800 bg-slate-900/40 animate-pulse" />
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-24 rounded-xl border border-slate-800 bg-slate-900/40 animate-pulse" />
            ))}
          </div>
        )}

        {isError && (
          <div className="rounded-xl border border-rose-500/20 bg-rose-500/5 p-4 text-sm text-rose-400">
            Status page is temporarily unavailable.
            <button onClick={() => refetch()} className="ml-2 underline hover:text-rose-300">Retry</button>
          </div>
        )}

        {data && (
          <>
            {/* Overall banner */}
            <div className={cn("rounded-xl border p-4 flex items-center gap-3", banner.wrap)}>
              <BannerIcon className="h-5 w-5 shrink-0" />
              <span className="text-sm font-semibold">{data.banner}</span>
            </div>

            {/* Per-component status */}
            <div className="space-y-3">
              {data.components.map((comp) => (
                <div key={comp.key} className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="flex items-center gap-2 text-sm font-medium">
                      <span
                        className={cn(
                          "h-2 w-2 rounded-full",
                          comp.status === "up" ? "bg-emerald-400" : "bg-rose-400 animate-pulse"
                        )}
                      />
                      <span className={statusColor(comp.status)}>{comp.label}</span>
                      {comp.latency_ms !== null && (
                        <span className="num text-[10px] text-slate-500">{comp.latency_ms} ms</span>
                      )}
                    </span>
                    <span className="num text-[11px] text-slate-400">
                      24h {fmtPct(comp.uptime["24h"])} · 7d {fmtPct(comp.uptime["7d"])} · 30d{" "}
                      {fmtPct(comp.uptime["30d"])} · 90d {fmtPct(comp.uptime["90d"])}
                    </span>
                  </div>

                  {/* 90-day bar */}
                  <div
                    className="flex gap-[2px] h-6"
                    role="img"
                    aria-label={`${comp.label} 90-day uptime history`}
                  >
                    {comp.daily.length === 0 && (
                      <span className="text-[11px] text-slate-600">No history recorded yet.</span>
                    )}
                    {comp.daily.map((day) => (
                      <div
                        key={day.date}
                        className={cn("flex-1 rounded-sm min-w-[4px] transition-opacity hover:opacity-80", barColor(day.uptime_pct))}
                        onMouseEnter={() => setHoveredDay({ comp: comp.key, date: day.date, pct: day.uptime_pct })}
                        onMouseLeave={() => setHoveredDay(null)}
                      />
                    ))}
                  </div>
                  <p className="text-[10px] text-slate-500 h-3">
                    {hoveredDay?.comp === comp.key
                      ? `${hoveredDay.date}: ${hoveredDay.pct === null ? "no data" : `${hoveredDay.pct.toFixed(2)}% uptime`}`
                      : "Hover a day block for its uptime."}
                  </p>
                </div>
              ))}
            </div>

            {/* Incident history */}
            <div>
              <h2 className="text-sm font-semibold text-slate-200 mb-3">Incident history</h2>
              {data.incidents.length === 0 ? (
                <p className="text-xs text-slate-500">No incidents in the retained window.</p>
              ) : (
                <ul className="space-y-2">
                  {data.incidents.map((inc, i) => (
                    <li key={i} className="rounded-lg border border-slate-800 bg-slate-900/60 p-3 text-xs">
                      <div className="flex items-center gap-2">
                        <span className={cn("h-1.5 w-1.5 rounded-full", inc.resolved_at ? "bg-emerald-400" : "bg-rose-400 animate-pulse")} />
                        <span className="font-medium capitalize text-slate-200">{inc.component.replace("_", " ")}</span>
                        <span className="num text-[10px] text-slate-500">{inc.started_at}</span>
                        {inc.manual && (
                          <span className="text-[10px] text-purple-400 border border-purple-500/20 bg-purple-500/10 rounded px-1">manual</span>
                        )}
                      </div>
                      <p className="text-slate-400 mt-1">{inc.note}</p>
                      {inc.resolved_at && <p className="text-[10px] text-emerald-400/80 mt-1">Resolved {inc.resolved_at}</p>}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </>
        )}

        <p className="text-[10px] text-slate-600 text-center">
          This page shows aggregate service health only. No user data is exposed.
        </p>
      </div>
    </div>
  );
}
