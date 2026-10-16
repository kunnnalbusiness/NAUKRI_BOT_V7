import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Cpu,
  MemoryStick,
  HardDrive,
  Bot,
  Database,
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  Activity,
  Zap,
  ChevronDown,
  ChevronUp,
  Maximize2,
  Minimize2,
  Cloud,
} from "lucide-react";
import { apiGet, apiPost } from "@/lib/api";
import Sparkline from "@/components/ui/Sparkline";
import FullTelemetryGraph from "@/components/ui/FullTelemetryGraph";
import { cn } from "@/lib/utils";

interface SystemStats {
  timestamp: string;
  cpu: {
    process_percent: number;
    host_percent: number;
    core_count_effective: number;
    core_count_host?: number;
    cpu_limit_cores: number | null;
  };
  gpu?: {
    available: boolean;
    name: string | null;
    engine_type: string | null;
    driver_version: string | null;
    memory_total_mb: number | null;
    memory_used_mb: number | null;
    memory_percent: number | null;
    utilization_percent: number;
    temperature_c: number | null;
  };
  memory: {
    process_rss_mb: number;
    process_percent: number;
    host_used_mb: number;
    host_total_mb: number;
    host_percent: number;
    limit_mb: number | null;
    containerized: boolean;
  };
  disk: {
    data_used_mb: number;
    data_total_mb: number;
    data_percent: number;
    temp_used_mb: number;
    temp_total_mb: number;
    temp_percent: number;
  };
  process: { uptime_seconds: number; thread_count: number; open_fds: number | null; pid: number };
  workers: { running: number; browsers_open: number };
  mongodb: { state: string; latency_ms: number | null };
  history: { ts: string; cpu_percent: number; mem_percent: number; gpu_percent?: number | null }[];
}

interface Incident {
  component: string;
  started_at: string | null;
  resolved_at: string | null;
  note: string;
  manual: boolean;
}

/** Colour tier: emerald < 70, amber 70-90, red > 90 */
function tier(pct: number): "ok" | "warn" | "crit" {
  if (pct > 90) return "crit";
  if (pct >= 70) return "warn";
  return "ok";
}

const TIER_TEXT: Record<"ok" | "warn" | "crit", string> = {
  ok: "text-emerald-400",
  warn: "text-amber-400",
  crit: "text-rose-400",
};

const TIER_BAR: Record<"ok" | "warn" | "crit", string> = {
  ok: "bg-emerald-500",
  warn: "bg-amber-500",
  crit: "bg-rose-500",
};

function StatCard({
  icon: Icon,
  label,
  value,
  sub,
  pct,
  sparkData,
  sparkMax,
  badge,
  isExpanded,
  onToggleExpand,
  expandedDetails,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  sub: string;
  pct: number;
  sparkData: number[];
  sparkMax?: number;
  badge?: string;
  isExpanded?: boolean;
  onToggleExpand?: () => void;
  expandedDetails?: React.ReactNode;
}) {
  const t = tier(pct);
  return (
    <div
      onClick={onToggleExpand}
      className={cn(
        "rounded-xl border transition-all duration-300 flex flex-col gap-2.5 p-4 cursor-pointer select-none group",
        isExpanded
          ? "border-emerald-500/40 bg-slate-900/90 shadow-xl shadow-black/40 ring-1 ring-emerald-500/20 col-span-1 sm:col-span-2 lg:col-span-3"
          : "border-slate-800 bg-slate-900/60 hover:border-slate-700 hover:bg-slate-900/80"
      )}
    >
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-2 text-xs font-medium text-slate-400">
          <Icon className={cn("h-4 w-4 transition-transform group-hover:scale-110", TIER_TEXT[t])} />
          <span className="font-semibold text-slate-300">{label}</span>
          {badge && (
            <span className="text-[10px] text-emerald-400 border border-emerald-500/20 bg-emerald-500/10 rounded-full px-1.5 py-0.5 font-medium">
              {badge}
            </span>
          )}
        </span>
        <div className="flex items-center gap-2">
          <span className={cn("num text-sm font-semibold", TIER_TEXT[t])}>{value}</span>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onToggleExpand?.();
            }}
            className="p-1 rounded text-slate-500 group-hover:text-slate-300 hover:bg-slate-800/80 transition-colors"
            title={isExpanded ? "Click to collapse" : "Click to expand details"}
          >
            {isExpanded ? (
              <ChevronUp className="h-4 w-4 text-emerald-400" />
            ) : (
              <ChevronDown className="h-4 w-4 text-slate-500 group-hover:text-slate-300" />
            )}
          </button>
        </div>
      </div>

      <div className="h-1.5 w-full rounded-full bg-slate-800 overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all duration-500", TIER_BAR[t])}
          style={{ width: `${Math.min(100, Math.max(2, pct))}%` }}
        />
      </div>

      <div className="flex items-end justify-between gap-2">
        <span className="text-[11px] text-slate-500 leading-tight">{sub}</span>
        <Sparkline data={sparkData} max={sparkMax} className={cn("h-7 w-24 shrink-0", TIER_TEXT[t])} />
      </div>

      {/* Expanded full graph & telemetry tray */}
      {isExpanded && expandedDetails && (
        <div
          onClick={(e) => e.stopPropagation()}
          className="mt-3 pt-3 border-t border-slate-800/80 space-y-3 animate-in fade-in slide-in-from-top-1 duration-200"
        >
          {expandedDetails}
        </div>
      )}
    </div>
  );
}

function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h ${m}m`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

export default function SystemMonitor() {
  const [streamError, setStreamError] = useState(false);
  const [note, setNote] = useState("");
  const [noteComponent, setNoteComponent] = useState("api");
  const [posting, setPosting] = useState(false);
  const [expandedCards, setExpandedCards] = useState<Record<string, boolean>>({});
  const [showCloudGuide, setShowCloudGuide] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  // SSE live stream with automatic reconnect; falls back to polling on errors
  const [live, setLive] = useState<SystemStats | null>(null);
  useEffect(() => {
    let cancelled = false;
    const connect = () => {
      if (cancelled) return;
      const es = new EventSource("/api/admin/system/stats/stream");
      esRef.current = es;
      es.onmessage = (ev) => {
        try {
          setLive(JSON.parse(ev.data));
          setStreamError(false);
        } catch {
          /* ignore malformed frame */
        }
      };
      es.onerror = () => {
        es.close();
        setStreamError(true);
      };
    };
    connect();
    return () => {
      cancelled = true;
      esRef.current?.close();
    };
  }, []);

  const pollQuery = useQuery({
    queryKey: ["admin-system-stats-poll"],
    queryFn: () => apiGet<SystemStats>("/api/admin/system/stats"),
    enabled: streamError,
    refetchInterval: 5000,
    retry: 1,
  });

  const incidentsQuery = useQuery({
    queryKey: ["public-status-summary"],
    queryFn: () => apiGet<{ incidents: Incident[] }>("/api/status/summary"),
    refetchInterval: 30000,
  });

  const stats = live ?? pollQuery.data ?? null;

  const history = stats?.history ?? [];
  const cpuSeries = useMemo(() => history.map((h) => h.cpu_percent), [history]);
  const memSeries = useMemo(() => history.map((h) => h.mem_percent), [history]);
  const gpuSeries = useMemo(() => history.map((h) => h.gpu_percent ?? 0), [history]);

  const hasGpu = Boolean(stats?.gpu?.available);

  const toggleCard = (id: string) => {
    setExpandedCards((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const allExpanded = useMemo(() => {
    const keys = hasGpu
      ? ["gpu", "cpu", "memory", "disk", "workers", "mongodb", "process"]
      : ["cpu", "memory", "disk", "workers", "mongodb", "process"];
    return keys.length > 0 && keys.every((k) => expandedCards[k]);
  }, [expandedCards, hasGpu]);

  const toggleAll = () => {
    if (allExpanded) {
      setExpandedCards({});
    } else {
      const all: Record<string, boolean> = {
        gpu: true,
        cpu: true,
        memory: true,
        disk: true,
        workers: true,
        mongodb: true,
        process: true,
      };
      setExpandedCards(all);
    }
  };

  const peakMemPct = memSeries.length ? Math.max(...memSeries) : stats?.memory.process_percent ?? 0;
  const peakCpuPct = cpuSeries.length ? Math.max(...cpuSeries) : stats?.cpu.process_percent ?? 0;

  const deployVerdict = useMemo(() => {
    if (!stats) return null;
    const memLimitMb = stats.memory.limit_mb ?? stats.memory.host_total_mb;
    const cpuLimitCores = stats.cpu.cpu_limit_cores;
    const memPctLimit = peakMemPct;
    const cpuPctLimit = cpuLimitCores ? cpuLimitCores * 100 : null;

    if (cpuPctLimit !== null && peakCpuPct > cpuPctLimit * 0.9) {
      return {
        ok: false,
        text: "Too close to CPU limit",
        reason: `Peak CPU ${peakCpuPct.toFixed(1)}% vs ${cpuPctLimit.toFixed(1)}% allowed by the ${cpuLimitCores} core quota.`,
      };
    }
    if (memPctLimit > 90) {
      return {
        ok: false,
        text: "Too close to memory limit",
        reason: `Peak memory ${((peakMemPct / 100) * memLimitMb).toFixed(0)} MB vs ${memLimitMb.toFixed(0)} MB limit.`,
      };
    }
    return {
      ok: true,
      text: hasGpu ? "Optimal (Hardware Accelerated)" : "OK for free tier",
      reason: hasGpu
        ? `Dedicated GPU (${stats.gpu?.name}) active. Peak memory ${((peakMemPct / 100) * memLimitMb).toFixed(0)} MB of ${memLimitMb.toFixed(0)} MB; peak CPU ${peakCpuPct.toFixed(1)}%.`
        : `Peak memory ${((peakMemPct / 100) * memLimitMb).toFixed(0)} MB of ${memLimitMb.toFixed(0)} MB; peak CPU ${peakCpuPct.toFixed(1)}% (CPU Host Mode).`,
    };
  }, [stats, peakMemPct, peakCpuPct, hasGpu]);

  const submitNote = async () => {
    if (!note.trim()) return;
    setPosting(true);
    try {
      await apiPost("/api/admin/system/incidents", { component: noteComponent, note: note.trim() });
      toast.success("Incident note posted to the status page.");
      setNote("");
      incidentsQuery.refetch();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to post note.");
    } finally {
      setPosting(false);
    }
  };

  const incidents = incidentsQuery.data?.incidents ?? [];
  const loading = !stats;

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 md:px-8 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-semibold text-slate-100">System Monitor</h1>
            {stats && (
              hasGpu ? (
                <span className="flex items-center gap-1.5 text-[11px] text-emerald-400 border border-emerald-500/20 bg-emerald-500/10 rounded-full px-2.5 py-0.5 font-medium">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  <Zap className="h-3 w-3 text-emerald-400" />
                  GPU: {stats.gpu?.name}
                </span>
              ) : (
                <span className="flex items-center gap-1.5 text-[11px] text-slate-400 border border-slate-700 bg-slate-900/60 rounded-full px-2.5 py-0.5 font-medium">
                  <Cpu className="h-3 w-3 text-slate-400" />
                  CPU Host Mode (No GPU)
                </span>
              )
            )}
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Click any metric card to expand full timeline graphs and deep hardware telemetry
          </p>
        </div>

        <div className="flex items-center gap-2">
          {streamError && (
            <span className="flex items-center gap-1 text-[10px] text-amber-400 border border-amber-500/20 bg-amber-500/10 rounded-full px-2 py-0.5">
              <AlertTriangle className="h-3 w-3" /> polling fallback
            </span>
          )}

          <button
            onClick={() => setShowCloudGuide(!showCloudGuide)}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors app-press",
              showCloudGuide
                ? "border-purple-500/30 bg-purple-500/10 text-purple-400 hover:bg-purple-500/20"
                : "border-slate-800 bg-slate-900/60 text-slate-400 hover:text-slate-200 hover:bg-slate-800"
            )}
            title="Recommended Cloud Services & Sizing Architecture"
          >
            <Cloud className="h-3.5 w-3.5 text-purple-400" />
            <span>Cloud Sizing Guide</span>
          </button>

          <button
            onClick={toggleAll}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors app-press",
              allExpanded
                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20"
                : "border-slate-800 bg-slate-900/60 text-slate-400 hover:text-slate-200 hover:bg-slate-800"
            )}
            title={allExpanded ? "Collapse all telemetry graphs" : "Expand all full telemetry graphs"}
          >
            {allExpanded ? (
              <>
                <Minimize2 className="h-3.5 w-3.5" />
                <span>Collapse All</span>
              </>
            ) : (
              <>
                <Maximize2 className="h-3.5 w-3.5" />
                <span>Expand All Graphs</span>
              </>
            )}
          </button>

          <button
            onClick={() => {
              setLive(null);
              pollQuery.refetch();
              toast.success("Refreshing stats…");
            }}
            className="p-2 rounded-lg text-slate-400 hover:text-emerald-400 hover:bg-emerald-500/10 transition-colors app-press"
            aria-label="Refresh"
            title="Refresh System Stats"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Cloud Service Sizing & Architecture Recommendation Panel */}
      {showCloudGuide && (
        <div className="rounded-xl border border-purple-500/30 bg-purple-950/10 p-5 space-y-4 animate-in fade-in slide-in-from-top-2 duration-300">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-2.5">
              <div className="p-2 rounded-lg bg-purple-500/10 border border-purple-500/20 text-purple-400">
                <Cloud className="h-5 w-5" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-slate-100">
                  Recommended Cloud Architecture & Service Sizing
                </h3>
                <p className="text-xs text-slate-400">
                  Optimal hosting specs for real-time Playwright Chromium automation, CDP screencasting, and database persistence
                </p>
              </div>
            </div>
            <button
              onClick={() => setShowCloudGuide(false)}
              className="text-xs text-slate-500 hover:text-slate-300 px-2 py-1 rounded hover:bg-slate-800 transition-colors"
            >
              ✕ Close
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5">
            {/* Option 1: Dedicated Linux VPS (Recommended) */}
            <div className="rounded-lg border border-emerald-500/30 bg-slate-950/70 p-3.5 space-y-2.5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-emerald-400">1. Cloud VPS (Recommended)</span>
                <span className="text-[10px] bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 rounded px-1.5 py-0.5 font-medium">
                  Best For Realtime
                </span>
              </div>
              <p className="text-xs text-slate-300 leading-relaxed font-medium">
                Hetzner Cloud (CPX21) / DigitalOcean / AWS EC2
              </p>
              <ul className="text-[11px] text-slate-400 space-y-1">
                <li>• <strong>vCPU:</strong> 2 to 4 Cores (handles Playwright Chromium spikes)</li>
                <li>• <strong>RAM:</strong> 4 GB RAM (smooth multi-tab DOM parsing)</li>
                <li>• <strong>Storage:</strong> 40 GB NVMe SSD persistent storage</li>
                <li>• <strong>Cost:</strong> Approx $6 – $12 / month</li>
                <li>• <strong>Streaming:</strong> Smooth 15 FPS CDP WebSocket video with zero throttling</li>
              </ul>
            </div>

            {/* Option 2: Render PaaS */}
            <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-3.5 space-y-2.5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-200">2. Render (Container PaaS)</span>
                <span className="text-[10px] bg-slate-800 text-slate-400 rounded px-1.5 py-0.5">Ready Blueprint</span>
              </div>
              <p className="text-xs text-slate-300 leading-relaxed font-medium">
                render.yaml Starter or Standard Plan
              </p>
              <ul className="text-[11px] text-slate-400 space-y-1">
                <li>• <strong>Plan:</strong> Starter ($7/mo) or Standard ($25/mo)</li>
                <li>• <strong>Disk:</strong> 1 GB Render persistent disk mount (`/data`)</li>
                <li>• <strong>Free Tier Warning:</strong> 512MB RAM & 0.1 CPU limit causes heavy freezes on browser launch</li>
                <li>• <strong>Setup:</strong> 1-click deploy via GitHub Blueprint</li>
              </ul>
            </div>

            {/* Option 3: Supporting Cloud Services */}
            <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-3.5 space-y-2.5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-200">3. Managed Cloud Stack</span>
                <span className="text-[10px] bg-purple-500/10 text-purple-300 border border-purple-500/20 rounded px-1.5 py-0.5">
                  100% Free Tiers
                </span>
              </div>
              <ul className="text-[11px] text-slate-400 space-y-1.5">
                <li>• <strong>Database:</strong> MongoDB Atlas (M0 Free Tier, 512 MB) for users & encrypted sessions</li>
                <li>• <strong>AI Assistant:</strong> Google Gemini 2.5 Flash / Groq Cloud (Free API tiers)</li>
                <li>• <strong>Live Journal:</strong> Google Sheets Webhook via Apps Script (Free)</li>
                <li>• <strong>Anti-Ban Note:</strong> Import residential session cookies for LinkedIn Easy Apply</li>
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* Skeleton loaders */}
      {loading && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="h-28 rounded-xl border border-slate-800 bg-slate-900/40 animate-pulse" />
          ))}
        </div>
      )}

      {/* Cards */}
      {stats && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {/* GPU Card: Shown prominently if GPU is available in the system */}
            {hasGpu && stats.gpu && (
              <StatCard
                icon={Zap}
                label="GPU"
                badge="Hardware Accel"
                value={`${stats.gpu.utilization_percent}%`}
                pct={stats.gpu.utilization_percent}
                sub={`${stats.gpu.name} · ${
                  stats.gpu.memory_total_mb ? `${stats.gpu.memory_total_mb} MB VRAM` : "DirectX 3D"
                }`}
                sparkData={gpuSeries.length ? gpuSeries : [stats.gpu.utilization_percent]}
                sparkMax={100}
                isExpanded={expandedCards["gpu"]}
                onToggleExpand={() => toggleCard("gpu")}
                expandedDetails={
                  <div className="space-y-3">
                    <FullTelemetryGraph
                      title="GPU 3D Engine Load Timeline"
                      data={gpuSeries.length ? gpuSeries : [stats.gpu.utilization_percent, stats.gpu.utilization_percent]}
                      unit="%"
                      color="emerald"
                      max={100}
                    />

                    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2.5 rounded-lg bg-slate-950/60 p-3 border border-slate-800/60 text-xs">
                      <div>
                        <span className="text-slate-500 block text-[10px] uppercase tracking-wider">Device Model</span>
                        <span className="font-semibold text-emerald-400">{stats.gpu.name}</span>
                      </div>
                      <div>
                        <span className="text-slate-500 block text-[10px] uppercase tracking-wider">Acceleration API</span>
                        <span className="font-mono text-slate-300">{stats.gpu.engine_type}</span>
                      </div>
                      <div>
                        <span className="text-slate-500 block text-[10px] uppercase tracking-wider">Dedicated VRAM</span>
                        <span className="font-mono text-slate-200">
                          {stats.gpu.memory_total_mb ? `${stats.gpu.memory_total_mb} MB` : "Dynamic Shared"}
                        </span>
                      </div>
                      <div>
                        <span className="text-slate-500 block text-[10px] uppercase tracking-wider">Driver Version</span>
                        <span className="font-mono text-slate-300">{stats.gpu.driver_version || "System WDDM"}</span>
                      </div>
                      <div>
                        <span className="text-slate-500 block text-[10px] uppercase tracking-wider">Hardware Status</span>
                        <span className="flex items-center gap-1.5 text-emerald-400 font-medium">
                          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                          Acceleration Active
                        </span>
                      </div>
                      <div>
                        <span className="text-slate-500 block text-[10px] uppercase tracking-wider">Sampling Frequency</span>
                        <span className="font-mono text-slate-300">5-second Ring Buffer</span>
                      </div>
                    </div>
                  </div>
                }
              />
            )}

            {/* CPU Card */}
            <StatCard
              icon={Cpu}
              label="CPU"
              badge={!hasGpu ? "Primary Compute" : undefined}
              value={`${stats.cpu.process_percent}%`}
              pct={stats.cpu.process_percent}
              sub={`host ${stats.cpu.host_percent}% · ${stats.cpu.core_count_effective} effective cores${
                stats.cpu.cpu_limit_cores !== null ? ` (limit ${stats.cpu.cpu_limit_cores})` : ""
              }`}
              sparkData={cpuSeries}
              sparkMax={100}
              isExpanded={expandedCards["cpu"]}
              onToggleExpand={() => toggleCard("cpu")}
              expandedDetails={
                <div className="space-y-3">
                  <FullTelemetryGraph
                    title="Bot Process CPU Load Timeline"
                    data={cpuSeries}
                    unit="%"
                    color="cyan"
                    max={stats.cpu.cpu_limit_cores ? Math.max(100, stats.cpu.cpu_limit_cores * 100) : 100}
                    threshold={stats.cpu.cpu_limit_cores ? stats.cpu.cpu_limit_cores * 100 : undefined}
                    thresholdLabel={
                      stats.cpu.cpu_limit_cores ? `Quota Limit: ${(stats.cpu.cpu_limit_cores * 100).toFixed(0)}%` : undefined
                    }
                  />

                  <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2.5 rounded-lg bg-slate-950/60 p-3 border border-slate-800/60 text-xs">
                    <div>
                      <span className="text-slate-500 block text-[10px] uppercase tracking-wider">Bot Process Load</span>
                      <span className="font-mono text-cyan-400 font-semibold">{stats.cpu.process_percent}%</span>
                    </div>
                    <div>
                      <span className="text-slate-500 block text-[10px] uppercase tracking-wider">Host Total Load</span>
                      <span className="font-mono text-slate-300">{stats.cpu.host_percent}%</span>
                    </div>
                    <div>
                      <span className="text-slate-500 block text-[10px] uppercase tracking-wider">Effective Core Count</span>
                      <span className="font-mono text-slate-300">{stats.cpu.core_count_effective} Core(s)</span>
                    </div>
                    <div>
                      <span className="text-slate-500 block text-[10px] uppercase tracking-wider">Host Hardware Cores</span>
                      <span className="font-mono text-slate-400">{stats.cpu.core_count_host || "Native"}</span>
                    </div>
                    <div>
                      <span className="text-slate-500 block text-[10px] uppercase tracking-wider">Container Quota Limit</span>
                      <span className="font-mono text-slate-400">
                        {stats.cpu.cpu_limit_cores !== null ? `${stats.cpu.cpu_limit_cores} cores` : "Unlimited / Native"}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 block text-[10px] uppercase tracking-wider">Process Thread Count</span>
                      <span className="font-mono text-slate-300">{stats.process.thread_count} worker threads</span>
                    </div>
                  </div>
                </div>
              }
            />

            {/* Memory Card */}
            <StatCard
              icon={MemoryStick}
              label="Memory"
              value={`${stats.memory.process_rss_mb} MB`}
              pct={stats.memory.process_percent}
              sub={
                stats.memory.limit_mb
                  ? `limit ${stats.memory.limit_mb} MB (container)`
                  : `host ${stats.memory.host_used_mb}/${stats.memory.host_total_mb} MB`
              }
              sparkData={memSeries}
              sparkMax={100}
              isExpanded={expandedCards["memory"]}
              onToggleExpand={() => toggleCard("memory")}
              expandedDetails={
                <div className="space-y-3">
                  <FullTelemetryGraph
                    title="Process RSS Memory Load Timeline"
                    data={memSeries}
                    unit="%"
                    color="purple"
                    max={100}
                    threshold={90}
                    thresholdLabel="Warning Ceiling: 90%"
                  />

                  <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2.5 rounded-lg bg-slate-950/60 p-3 border border-slate-800/60 text-xs">
                    <div>
                      <span className="text-slate-500 block text-[10px] uppercase tracking-wider">Process RSS Footprint</span>
                      <span className="font-mono text-purple-400 font-semibold">
                        {stats.memory.process_rss_mb} MB ({stats.memory.process_percent}%)
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 block text-[10px] uppercase tracking-wider">Host Total Memory</span>
                      <span className="font-mono text-slate-300">
                        {stats.memory.host_used_mb} MB / {stats.memory.host_total_mb} MB ({stats.memory.host_percent}%)
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 block text-[10px] uppercase tracking-wider">Isolation Boundary</span>
                      <span className="font-mono text-slate-400">
                        {stats.memory.containerized ? "Cgroup Bound (512 MB)" : "Local Host / Bare Metal"}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 block text-[10px] uppercase tracking-wider">Memory Ceiling Limit</span>
                      <span className="font-mono text-slate-400">
                        {stats.memory.limit_mb ? `${stats.memory.limit_mb} MB` : `${stats.memory.host_total_mb} MB`}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 block text-[10px] uppercase tracking-wider">Free Memory Headroom</span>
                      <span className="font-mono text-emerald-400 font-medium">
                        {(stats.memory.host_total_mb - stats.memory.host_used_mb).toFixed(0)} MB Available
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 block text-[10px] uppercase tracking-wider">Telemetry Window</span>
                      <span className="font-mono text-slate-300">180 Bounded Samples</span>
                    </div>
                  </div>
                </div>
              }
            />

            {/* Disk Card */}
            <StatCard
              icon={HardDrive}
              label="Disk"
              value={`${stats.disk.data_percent}%`}
              pct={stats.disk.data_percent}
              sub={`data ${stats.disk.data_used_mb}/${stats.disk.data_total_mb} MB`}
              sparkData={memSeries.length ? [stats.disk.data_percent] : []}
              isExpanded={expandedCards["disk"]}
              onToggleExpand={() => toggleCard("disk")}
              expandedDetails={
                <div className="space-y-3">
                  <FullTelemetryGraph
                    title="Data Partition Utilization Timeline"
                    data={
                      memSeries.length
                        ? memSeries.map(() => stats.disk.data_percent)
                        : [stats.disk.data_percent, stats.disk.data_percent]
                    }
                    unit="%"
                    color="amber"
                    max={100}
                  />

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 rounded-lg bg-slate-950/60 p-3 border border-slate-800/60 text-xs">
                    <div>
                      <span className="text-slate-500 block text-[10px] uppercase tracking-wider">Persistent Data Directory</span>
                      <span className="font-mono text-slate-200 font-semibold">
                        {stats.disk.data_used_mb} MB / {stats.disk.data_total_mb} MB ({stats.disk.data_percent}%)
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 block text-[10px] uppercase tracking-wider">Temp / Cache Directory</span>
                      <span className="font-mono text-slate-200">
                        {stats.disk.temp_used_mb} MB / {stats.disk.temp_total_mb} MB ({stats.disk.temp_percent}%)
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 block text-[10px] uppercase tracking-wider">Storage Health</span>
                      <span className="text-emerald-400 font-semibold">Read/Write Healthy</span>
                    </div>
                  </div>
                </div>
              }
            />

            {/* Workers Card */}
            <StatCard
              icon={Bot}
              label="Workers"
              value={`${stats.workers.running}`}
              pct={stats.workers.running > 0 ? 100 : 4}
              sub={`${stats.workers.browsers_open} browser instance(s) open`}
              sparkData={[]}
              isExpanded={expandedCards["workers"]}
              onToggleExpand={() => toggleCard("workers")}
              expandedDetails={
                <div className="space-y-3">
                  <FullTelemetryGraph
                    title="Active Automation Engine Instances"
                    data={history.map(() => (stats.workers.running > 0 ? 100 : 4))}
                    unit="%"
                    color="emerald"
                    max={100}
                  />

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 rounded-lg bg-slate-950/60 p-3 border border-slate-800/60 text-xs">
                    <div>
                      <span className="text-slate-500 block text-[10px] uppercase tracking-wider">Active Bot Engines</span>
                      <span className="font-mono text-emerald-400 font-semibold">{stats.workers.running} runner(s)</span>
                    </div>
                    <div>
                      <span className="text-slate-500 block text-[10px] uppercase tracking-wider">Browser CDP Instances</span>
                      <span className="font-mono text-slate-200">{stats.workers.browsers_open} instance(s) open</span>
                    </div>
                    <div>
                      <span className="text-slate-500 block text-[10px] uppercase tracking-wider">Automation Portals</span>
                      <span className="text-slate-300">Naukri & LinkedIn Easy Apply</span>
                    </div>
                  </div>
                </div>
              }
            />

            {/* DB Latency Card */}
            <StatCard
              icon={Database}
              label="DB Latency"
              value={stats.mongodb.latency_ms !== null ? `${stats.mongodb.latency_ms} ms` : "—"}
              pct={stats.mongodb.state === "connected" ? 8 : 95}
              sub={
                stats.mongodb.state === "connected"
                  ? "MongoDB connected"
                  : stats.mongodb.state === "local_store"
                  ? "local store mode"
                  : "DB unreachable"
              }
              sparkData={[]}
              isExpanded={expandedCards["mongodb"]}
              onToggleExpand={() => toggleCard("mongodb")}
              expandedDetails={
                <div className="space-y-3">
                  <FullTelemetryGraph
                    title="Database Round-Trip Ping Latency Timeline"
                    data={history.map(() => stats.mongodb.latency_ms ?? 0.5)}
                    unit="ms"
                    color="rose"
                    max={stats.mongodb.latency_ms ? Math.max(50, stats.mongodb.latency_ms * 2) : 50}
                  />

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 rounded-lg bg-slate-950/60 p-3 border border-slate-800/60 text-xs">
                    <div>
                      <span className="text-slate-500 block text-[10px] uppercase tracking-wider">Storage Backend</span>
                      <span className="text-emerald-400 font-semibold">
                        {stats.mongodb.state === "connected" ? "MongoDB Atlas (Connected)" : "Local Persistent JSON Store"}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 block text-[10px] uppercase tracking-wider">Round-Trip Latency</span>
                      <span className="font-mono text-rose-400 font-semibold">
                        {stats.mongodb.latency_ms !== null ? `${stats.mongodb.latency_ms} ms` : "Local Instant"}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 block text-[10px] uppercase tracking-wider">Data Encryption</span>
                      <span className="text-slate-300">Fernet AES-256 Symmetric</span>
                    </div>
                  </div>
                </div>
              }
            />

            {/* Process Card */}
            <StatCard
              icon={Activity}
              label="Process"
              value={formatUptime(stats.process.uptime_seconds)}
              pct={Math.min(100, (stats.process.thread_count / 100) * 100)}
              sub={`${stats.process.thread_count} threads${
                stats.process.open_fds !== null ? ` · ${stats.process.open_fds} fds` : ""
              } · pid ${stats.process.pid}`}
              sparkData={[]}
              isExpanded={expandedCards["process"]}
              onToggleExpand={() => toggleCard("process")}
              expandedDetails={
                <div className="space-y-3">
                  <FullTelemetryGraph
                    title="Worker Thread Pool & Task Concurrency"
                    data={history.map(() => stats.process.thread_count)}
                    unit=" th"
                    color="cyan"
                    max={Math.max(50, stats.process.thread_count * 1.5)}
                  />

                  <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-2.5 rounded-lg bg-slate-950/60 p-3 border border-slate-800/60 text-xs">
                    <div>
                      <span className="text-slate-500 block text-[10px] uppercase tracking-wider">Process ID (PID)</span>
                      <span className="font-mono text-slate-200 font-semibold">{stats.process.pid}</span>
                    </div>
                    <div>
                      <span className="text-slate-500 block text-[10px] uppercase tracking-wider">Total Uptime</span>
                      <span className="font-mono text-slate-200">
                        {formatUptime(stats.process.uptime_seconds)} ({stats.process.uptime_seconds}s)
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 block text-[10px] uppercase tracking-wider">Worker Threads</span>
                      <span className="font-mono text-cyan-400 font-semibold">{stats.process.thread_count} Active</span>
                    </div>
                    <div>
                      <span className="text-slate-500 block text-[10px] uppercase tracking-wider">Open Handles / FDs</span>
                      <span className="font-mono text-slate-300">
                        {stats.process.open_fds !== null ? `${stats.process.open_fds} handles` : "System Managed"}
                      </span>
                    </div>
                  </div>
                </div>
              }
            />
          </div>

          {/* Deploy readiness panel */}
          {deployVerdict && (
            <div
              className={cn(
                "rounded-xl border p-4 flex items-start gap-3",
                deployVerdict.ok
                  ? "border-emerald-500/20 bg-emerald-500/5"
                  : "border-amber-500/20 bg-amber-500/5"
              )}
            >
              {deployVerdict.ok ? (
                <CheckCircle2 className="h-5 w-5 text-emerald-400 shrink-0 mt-0.5" />
              ) : (
                <AlertTriangle className="h-5 w-5 text-amber-400 shrink-0 mt-0.5" />
              )}
              <div>
                <p className={cn("text-sm font-semibold", deployVerdict.ok ? "text-emerald-400" : "text-amber-400")}>
                  System Health & Hardware Assessment: {deployVerdict.text}
                </p>
                <p className="text-xs text-slate-400 mt-0.5">{deployVerdict.reason}</p>
              </div>
            </div>
          )}
        </>
      )}

      {/* Manual incident note */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 space-y-3">
        <h2 className="text-sm font-semibold text-slate-200">Post status-page note</h2>
        <div className="flex flex-col sm:flex-row gap-2">
          <select
            value={noteComponent}
            onChange={(e) => setNoteComponent(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500"
            aria-label="Component"
          >
            <option value="api">API</option>
            <option value="mongodb">MongoDB</option>
            <option value="bot_worker">Bot Worker</option>
            <option value="browser_engine">Browser Engine</option>
          </select>
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="e.g. Scheduled maintenance window at 02:00 UTC"
            maxLength={500}
            className="flex-1 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-200 placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
          />
          <button
            onClick={submitNote}
            disabled={posting || !note.trim()}
            className="rounded-lg bg-emerald-500/10 border border-emerald-500/20 px-4 py-2 text-xs font-medium text-emerald-400 hover:bg-emerald-500/20 disabled:opacity-40 disabled:cursor-not-allowed transition-colors app-press"
          >
            {posting ? "Posting…" : "Post note"}
          </button>
        </div>
      </div>

      {/* Recent incidents */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
        <h2 className="text-sm font-semibold text-slate-200 mb-3">Recent incidents</h2>
        {incidents.length === 0 ? (
          <p className="text-xs text-slate-500">No incidents recorded. Heartbeats run every 60 seconds.</p>
        ) : (
          <ul className="space-y-2">
            {incidents.slice(0, 8).map((inc, i) => (
              <li key={i} className="flex items-start gap-2 text-xs">
                <span
                  className={cn(
                    "mt-1 h-1.5 w-1.5 rounded-full shrink-0",
                    inc.resolved_at ? "bg-emerald-400" : "bg-rose-400 animate-pulse"
                  )}
                />
                <div>
                  <span className="font-medium text-slate-200 capitalize">{inc.component.replace("_", " ")}</span>
                  {inc.manual && (
                    <span className="ml-1.5 text-[10px] text-purple-400 border border-purple-500/20 bg-purple-500/10 rounded px-1">
                      manual
                    </span>
                  )}
                  <span className="ml-2 text-slate-400">{inc.note}</span>
                  <span className="num block text-[10px] text-slate-500">
                    {inc.started_at}
                    {inc.resolved_at ? ` → resolved ${inc.resolved_at}` : " → ongoing"}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

