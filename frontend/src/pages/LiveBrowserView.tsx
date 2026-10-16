import React, { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  MonitorPlay,
  RotateCw,
  Globe,
  ShieldCheck,
  Clock,
  Layers,
  ArrowRight,
  Sparkles,
  ExternalLink,
  ChevronRight,
  Maximize2,
} from "lucide-react";
import { toast } from "sonner";

import { apiGet, apiPost } from "@/lib/api";
import type { DashboardStatus } from "@/lib/types";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { PageHeader } from "@/components/ui/PageHeader";
import ScreencastCanvas from "@/components/screencast/ScreencastCanvas";

export default function LiveBrowserView() {
  const [site, setSite] = useState<"naukri" | "linkedin">("naukri");
  const [mode, setMode] = useState<"live_check" | "login">("live_check");
  const [activeSessionKey, setActiveSessionKey] = useState(0);

  // Dynamic stream FPS preference (defaults to saved user settings or sessionStorage)
  const [streamFps, setStreamFps] = useState<number>(() => {
    try {
      const saved = sessionStorage.getItem("preferred_stream_fps");
      return saved ? parseInt(saved, 10) : 15;
    } catch {
      return 15;
    }
  });

  const restartStream = () => {
    setActiveSessionKey((prev) => prev + 1);
  };

  // Fetch user settings to read saved stream_fps preference
  const { data: userSettings } = useQuery({
    queryKey: ["user-settings"],
    queryFn: () => apiGet<{ stream_fps?: number }>("/api/user/settings"),
    staleTime: 30000,
  });

  useEffect(() => {
    if (userSettings?.stream_fps) {
      setStreamFps(userSettings.stream_fps);
      try {
        sessionStorage.setItem("preferred_stream_fps", String(userSettings.stream_fps));
      } catch {}
    }
  }, [userSettings?.stream_fps]);

  const handleFpsChange = (newFps: number) => {
    setStreamFps(newFps);
    try {
      sessionStorage.setItem("preferred_stream_fps", String(newFps));
    } catch {}
    apiPost("/api/user/settings", { stream_fps: newFps }).catch(() => {});
    toast.success(`Stream framerate updated to ${newFps} FPS`);
    restartStream();
  };

  // Fetch recent activity for right-hand timeline
  const { data: statusData } = useQuery({
    queryKey: ["live-browser-status"],
    queryFn: () => apiGet<DashboardStatus>("/api/status"),
    refetchInterval: 5000,
  });

  const recentEvents = statusData?.activity?.recent || [];

  const portalUrls = {
    naukri: "https://www.naukri.com/it-jobs",
    linkedin: "https://www.linkedin.com/jobs/search/?f_AL=true",
  };

  return (
    <div className="flex-1 p-5 sm:p-8 max-w-7xl mx-auto w-full space-y-6 flex flex-col h-[calc(100vh-1rem)]">
      <PageHeader
        title="Live Remote Browser"
        description="Monitor real-time headless browser automation or intervene manually during captchas and multi-step forms."
        actions={
          <div className="flex items-center gap-2">
            {/* Site Switcher */}
            <div className="flex items-center rounded-xl border border-slate-800 bg-slate-900/80 p-1">
              <button
                onClick={() => { setSite("naukri"); restartStream(); }}
                className={`px-3 py-1 rounded-lg text-xs font-semibold transition-colors ${
                  site === "naukri" ? "bg-emerald-500/15 text-emerald-400" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Naukri.com
              </button>
              <button
                onClick={() => { setSite("linkedin"); restartStream(); }}
                className={`px-3 py-1 rounded-lg text-xs font-semibold transition-colors ${
                  site === "linkedin" ? "bg-sky-500/15 text-sky-400" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                LinkedIn
              </button>
            </div>

            {/* Mode Switcher */}
            <div className="hidden sm:flex items-center rounded-xl border border-slate-800 bg-slate-900/80 p-1">
              <button
                onClick={() => { setMode("live_check"); restartStream(); }}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                  mode === "live_check" ? "bg-slate-800 text-slate-100" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Live Bot View
              </button>
              <button
                onClick={() => { setMode("login"); restartStream(); }}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                  mode === "login" ? "bg-slate-800 text-slate-100" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Interactive Login
              </button>
            </div>

            <Button
              variant="outline"
              size="sm"
              leftIcon={<RotateCw className="h-3.5 w-3.5" />}
              onClick={restartStream}
            >
              Reconnect
            </Button>
          </div>
        }
      />

      {/* ─── Browser Frame & Split Timeline ─── */}
      <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-4 gap-5">
        {/* Main Remote Viewport (Left 3 columns) */}
        <div className="lg:col-span-3 flex flex-col rounded-2xl border border-slate-800 bg-slate-950 overflow-hidden shadow-2xl">
          {/* Simulated Browser Chrome Bar */}
          <div className="flex items-center justify-between border-b border-slate-800/80 bg-slate-900/90 px-4 py-2.5 shrink-0">
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full bg-rose-500/80" />
              <span className="h-2.5 w-2.5 rounded-full bg-amber-500/80" />
              <span className="h-2.5 w-2.5 rounded-full bg-emerald-500/80" />

              {/* Simulated Address Bar */}
              <div className="ml-3 flex items-center gap-2 rounded-lg bg-slate-950/80 border border-slate-800/80 px-3 py-1 text-[11px] text-slate-400 max-w-sm truncate">
                <Globe className="h-3 w-3 text-emerald-400 shrink-0" />
                <span className="truncate">{portalUrls[site]}</span>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <span className="flex items-center gap-1.5 text-[10px] font-medium text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-full">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                {streamFps} FPS Stream
              </span>
              <select
                value={streamFps}
                onChange={(e) => handleFpsChange(Number(e.target.value))}
                className="h-6 rounded-md border border-slate-800 bg-slate-900/90 px-1.5 text-[10px] font-medium text-slate-300 focus:outline-none focus:border-emerald-500/60 cursor-pointer"
                title="Select Stream Framerate"
              >
                <option value={5}>5 FPS</option>
                <option value={10}>10 FPS</option>
                <option value={15}>15 FPS</option>
                <option value={30}>30 FPS</option>
              </select>
            </div>
          </div>

          {/* Canvas Container */}
          <div className="flex-1 min-h-0 bg-slate-950 p-2 sm:p-3 overflow-hidden flex flex-col justify-center">
            <ScreencastCanvas
              key={`${site}-${mode}-${activeSessionKey}-${streamFps}`}
              site={site}
              mode={mode}
              fps={streamFps}
            />
          </div>

          {/* Browser Status Footer */}
          <div className="border-t border-slate-800/80 bg-slate-900/70 px-4 py-2 flex items-center justify-between text-[11px] text-slate-400 shrink-0">
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
              <span>Full interactive mode enabled (mouse clicks and keyboard typing supported)</span>
            </div>
            <span className="font-mono text-slate-500">WebSocket CDP Protocol</span>
          </div>
        </div>

        {/* Right Side: Automation Timeline */}
        <div className="hidden lg:flex flex-col rounded-2xl border border-slate-800 bg-slate-900/50 p-4 overflow-hidden">
          <div className="pb-3 border-b border-slate-800 mb-3 flex items-center justify-between">
            <div>
              <h3 className="text-xs font-semibold text-slate-200">Live Timeline</h3>
              <p className="text-[10px] text-slate-400">Events from active automation</p>
            </div>
            <Badge variant="neutral" size="sm">Real-time</Badge>
          </div>

          <div className="flex-1 overflow-y-auto space-y-3 pr-1 scrollbar-none">
            {recentEvents.length === 0 ? (
              <div className="py-12 text-center text-xs text-slate-500">
                Waiting for engine actions...
              </div>
            ) : (
              recentEvents.slice(0, 10).map((evt, idx) => {
                const isApplied = (evt.status || "").toLowerCase() === "applied";
                return (
                  <div key={idx} className="p-3 rounded-xl border border-slate-800/80 bg-slate-950/40 space-y-1">
                    <div className="flex items-center justify-between text-[10px]">
                      <span className="font-mono text-slate-400">
                        {evt.timestamp ? evt.timestamp.slice(11, 19) : "Now"}
                      </span>
                      <Badge variant={isApplied ? "success" : "neutral"} size="sm">
                        {evt.status}
                      </Badge>
                    </div>
                    <p className="text-xs font-semibold text-slate-200 truncate">{evt.title}</p>
                    <p className="text-[11px] text-slate-400 truncate">{evt.company}</p>
                    {evt.reason && (
                      <p className="text-[10px] text-slate-500 truncate pt-0.5 border-t border-slate-800/40">
                        {evt.reason}
                      </p>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
