import React from "react";
import { motion } from "framer-motion";
import {
  Sparkles,
  Bot,
  Zap,
  ShieldCheck,
  Clock,
  Compass,
  Cpu,
  TrendingUp,
  Layers,
  ArrowRight,
  Terminal,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface AssistantCopilotHUDProps {
  botRunning: boolean;
  activeAction?: string;
  naukriStatus?: string;
  linkedinStatus?: string;
  appliedToday?: number;
  totalApplied?: number;
  onStartAll?: () => void;
  onStopAll?: () => void;
  isStarting?: boolean;
}

export default function AssistantCopilotHUD({
  botRunning,
  activeAction,
  naukriStatus = "Idle",
  linkedinStatus = "Idle",
  appliedToday = 0,
  totalApplied = 0,
  onStartAll,
  onStopAll,
  isStarting = false,
}: AssistantCopilotHUDProps) {
  // Estimated manual time saved: 12 minutes per job application
  const totalMinutesSaved = totalApplied * 12;
  const hoursSaved = (totalMinutesSaved / 60).toFixed(1);

  return (
    <div className="relative overflow-hidden rounded-2xl border border-emerald-500/30 bg-gradient-to-b from-card/95 via-card/80 to-background/95 p-5 shadow-[0_8px_32px_0_rgba(0,0,0,0.5)] backdrop-blur-2xl">
      {/* Background Cyber Grid Accent */}
      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(to_right,#00ff4108_1px,transparent_1px),linear-gradient(to_bottom,#00ff4108_1px,transparent_1px)] bg-[size:24px_24px] opacity-40" />

      {/* Ambient Gradient Glows */}
      <div className="pointer-events-none absolute -top-24 left-1/4 h-56 w-56 rounded-full bg-emerald-500/15 blur-[90px]" />
      <div className="pointer-events-none absolute -bottom-24 right-1/4 h-56 w-56 rounded-full bg-emerald-600/10 blur-[90px]" />

      <div className="relative z-10 flex flex-col lg:flex-row items-start lg:items-center justify-between gap-6">
        {/* Left: 3D Holographic Assistant Identity & Status */}
        <div className="flex items-start sm:items-center gap-4.5">
          {/* 3D Orb Graphic */}
          <div className="relative flex h-16 w-16 shrink-0 items-center justify-center">
            {/* Outer Rotating Ring */}
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ duration: 12, repeat: Infinity, ease: "linear" }}
              className="absolute inset-0 rounded-full border border-dashed border-emerald-500/40"
            />
            {/* Counter-Rotating Middle Ring */}
            <motion.div
              animate={{ rotate: -360 }}
              transition={{ duration: 8, repeat: Infinity, ease: "linear" }}
              className="absolute inset-1.5 rounded-full border border-emerald-400/30"
              style={{ borderTopColor: "transparent", borderBottomColor: "transparent" }}
            />
            {/* Core Pulsing Orb */}
            <motion.div
              animate={{
                scale: botRunning ? [1, 1.15, 1] : [1, 1.05, 1],
                boxShadow: botRunning
                  ? [
                      "0 0 15px rgba(16, 185, 129, 0.4)",
                      "0 0 30px rgba(16, 185, 129, 0.8)",
                      "0 0 15px rgba(16, 185, 129, 0.4)",
                    ]
                  : [
                      "0 0 8px rgba(16, 185, 129, 0.2)",
                      "0 0 16px rgba(16, 185, 129, 0.3)",
                      "0 0 8px rgba(16, 185, 129, 0.2)",
                    ],
              }}
              transition={{ duration: 2.2, repeat: Infinity, ease: "easeInOut" }}
              className={cn(
                "flex h-10 w-10 items-center justify-center rounded-full bg-emerald-500/20 text-emerald-400 backdrop-blur-md",
                botRunning ? "border border-emerald-400 text-emerald-300" : "border border-emerald-500/40"
              )}
            >
              <Sparkles className="h-5 w-5" />
            </motion.div>
          </div>

          <div>
            <div className="flex items-center gap-2.5 flex-wrap">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-0.5 text-[10.5px] font-mono font-medium text-emerald-400">
                <span className={cn(
                  "h-1.5 w-1.5 rounded-full",
                  botRunning ? "bg-emerald-400 animate-ping" : "bg-emerald-500/50"
                )} />
                {botRunning ? "AI COPILOT ACTIVE" : "AI COPILOT STANDBY"}
              </span>

              <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-0.5 text-[10px] font-mono text-muted-foreground uppercase tracking-wider">
                SaaS Pro Autonomous
              </span>
            </div>

            <h2 className="mt-1 font-heading text-lg sm:text-xl font-bold tracking-tight text-foreground flex items-center gap-2">
              <span>Personal Career AI Assistant</span>
              <span className="text-xs font-mono font-normal text-emerald-400/90 hidden sm:inline">
                · Gemini 3.1 & Playwright Engine
              </span>
            </h2>

            {/* Live Assistant Reasoning Feed */}
            <div className="mt-1.5 flex items-center gap-2 text-xs text-muted-foreground font-mono">
              <Terminal className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
              <p className="truncate max-w-[280px] sm:max-w-md md:max-w-lg text-emerald-300/90">
                {activeAction ||
                  (botRunning
                    ? "Scanning live radar feeds and autonomously screening Easy Apply opportunities..."
                    : "Ready for deployment. Target roles, fresh filter (10m), and credentials loaded.")}
              </p>
            </div>
          </div>
        </div>

        {/* Right: Telemetry Badges & Quick Action Controls */}
        <div className="flex flex-wrap items-center gap-3 w-full lg:w-auto justify-start lg:justify-end">
          {/* Metrics Pill 1: Time Saved */}
          <div className="flex items-center gap-2.5 rounded-xl border border-white/10 bg-card/80 px-3.5 py-2 shadow-xs backdrop-blur-md">
            <Clock className="h-4 w-4 text-emerald-400 shrink-0" />
            <div>
              <div className="text-[10px] uppercase font-mono tracking-wider text-muted-foreground">Time Saved</div>
              <div className="num font-bold text-sm text-foreground">
                {hoursSaved} <span className="text-xs font-normal text-muted-foreground">hrs</span>
              </div>
            </div>
          </div>

          {/* Metrics Pill 2: AI Success Rate */}
          <div className="flex items-center gap-2.5 rounded-xl border border-white/10 bg-card/80 px-3.5 py-2 shadow-xs backdrop-blur-md">
            <TrendingUp className="h-4 w-4 text-emerald-400 shrink-0" />
            <div>
              <div className="text-[10px] uppercase font-mono tracking-wider text-muted-foreground">AI Match Rate</div>
              <div className="num font-bold text-sm text-emerald-400">100%</div>
            </div>
          </div>

          {/* Master Autonomous Start / Stop Button */}
          {onStartAll && (
            <motion.button
              whileHover={{ scale: 1.03 }}
              whileTap={{ scale: 0.97 }}
              onClick={botRunning ? onStopAll : onStartAll}
              disabled={isStarting}
              className={cn(
                "relative overflow-hidden rounded-xl px-5 py-2.5 text-xs font-mono font-bold uppercase tracking-wider transition-all duration-200 shadow-md flex items-center gap-2 shrink-0 cursor-pointer",
                botRunning
                  ? "bg-rose-500/20 text-rose-300 border border-rose-500/40 hover:bg-rose-500/30 hover:border-rose-500/60 shadow-[0_0_20px_rgba(244,63,94,0.2)]"
                  : "bg-emerald-500 text-black border border-emerald-400 hover:bg-emerald-400 shadow-[0_0_25px_rgba(16,185,129,0.35)]"
              )}
            >
              <Zap className={cn("h-4 w-4", botRunning ? "fill-rose-400" : "fill-black")} />
              <span>{botRunning ? "Halt AI Assistant" : "Deploy All Engines"}</span>
            </motion.button>
          )}
        </div>
      </div>

      {/* Bottom Features Ticker Strip */}
      <div className="mt-4 pt-3 border-t border-white/5 flex items-center justify-between text-[11px] font-mono text-muted-foreground flex-wrap gap-2">
        <div className="flex items-center gap-4 flex-wrap">
          <span className="flex items-center gap-1.5 text-emerald-400/80">
            <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
            10-Minute Fresh Shield
          </span>
          <span className="hidden sm:inline text-white/20">•</span>
          <span className="flex items-center gap-1.5 text-foreground/80">
            <Cpu className="h-3.5 w-3.5 text-emerald-400" />
            Gemini Flash Screening Autopilot
          </span>
          <span className="hidden sm:inline text-white/20">•</span>
          <span className="flex items-center gap-1.5 text-foreground/80">
            <Layers className="h-3.5 w-3.5 text-emerald-400" />
            Dual-Channel (Naukri + LinkedIn)
          </span>
        </div>

        <div className="text-[10px] text-muted-foreground/70">
          Quota: Active 50/day Cap · Resets Midnight IST
        </div>
      </div>
    </div>
  );
}
