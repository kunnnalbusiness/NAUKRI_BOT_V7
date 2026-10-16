import React, { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { LayoutDashboard, Sparkles, LogOut, ShieldAlert, User, Cpu } from "lucide-react";
import { useAuth } from "@/lib/authContext";
import { cn } from "@/lib/utils";

function useLiveISTClock() {
  const formatClock = () => {
    const d = new Date();
    const weekday = d.toLocaleDateString("en-US", { weekday: "short", timeZone: "Asia/Kolkata" });
    const day = d.toLocaleDateString("en-US", { day: "numeric", timeZone: "Asia/Kolkata" });
    const month = d.toLocaleDateString("en-US", { month: "short", timeZone: "Asia/Kolkata" });
    const time = d.toLocaleTimeString("en-US", {
      hour12: true,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      timeZone: "Asia/Kolkata",
    });
    return `${weekday}, ${day} ${month} · ${time} IST`;
  };

  const [clock, setClock] = useState(formatClock);

  useEffect(() => {
    const timer = setInterval(() => setClock(formatClock()), 1000);
    return () => clearInterval(timer);
  }, []);

  return clock;
}

interface DesktopHeaderProps {
  botRunning?: boolean;
  totalApplied?: number;
  appliedToday?: number;
  totalSkipped?: number;
}

export default function DesktopHeader({
  botRunning = false,
  totalApplied = 0,
  appliedToday = 0,
  totalSkipped = 0,
}: DesktopHeaderProps) {
  const { user, logout, isAdmin } = useAuth();
  const liveClock = useLiveISTClock();

  return (
    <header className="hidden md:flex h-[50px] shrink-0 items-center justify-between border-b border-border bg-background/95 px-4 backdrop-blur-2xl">
      {/* Left: Terminal Icon + Title */}
      <div className="flex items-center gap-2.5">
        <div className="flex h-7.5 w-7.5 items-center justify-center rounded-full border border-emerald-500/30 bg-emerald-500/10 text-emerald-400 shadow-[0_0_12px_rgba(16,185,129,0.2)]">
          <Sparkles className="h-4 w-4 animate-pulse text-emerald-400" />
        </div>
        <div>
          <h1 className="font-heading text-[14px] font-bold tracking-[-0.02em] text-foreground flex items-center gap-2">
            <span>Career AI Assistant</span>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 text-emerald-400">
              SaaS Co-Pilot v2.0
            </span>
          </h1>
        </div>
      </div>

      {/* Right Controls: Pill Stats + IST Clock + Bot Status + User Profile + Logout */}
      <div className="flex items-center gap-2.5">
        {/* SolanaTracker-style pill stats strip */}
        <div className="flex items-center gap-3 rounded-full border border-border bg-card px-3.5 py-1 text-xs shadow-xs">
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] uppercase font-mono tracking-wider text-muted-foreground">Total</span>
            <p className="num font-bold text-foreground leading-tight">{totalApplied}</p>
          </div>
          <div className="h-3.5 w-px bg-border" />
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] uppercase font-mono tracking-wider text-emerald-400">Today</span>
            <p className="num font-bold text-emerald-400 leading-tight">{appliedToday}</p>
          </div>
          <div className="h-3.5 w-px bg-border" />
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] uppercase font-mono tracking-wider text-muted-foreground">Skipped</span>
            <p className="num font-bold text-muted-foreground leading-tight">{totalSkipped}</p>
          </div>
        </div>

        {/* Live Clock Pill */}
        <div className="hidden xl:flex items-center rounded-full border border-border bg-card px-3 py-1 text-[11px] font-mono text-muted-foreground tracking-tight">
          <span>{liveClock}</span>
        </div>

        {/* Live Bot Status Beacon */}
        <span
          className={cn(
            "inline-flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-[10.5px] font-mono font-semibold transition-all shrink-0",
            botRunning
              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400 shadow-[0_0_12px_rgba(16,185,129,0.15)]"
              : "border-border bg-card text-muted-foreground"
          )}
        >
          <span
            className={cn(
              "h-1.5 w-1.5 rounded-full",
              botRunning
                ? "bg-emerald-400 animate-[beacon_1.6s_ease-in-out_infinite]"
                : "bg-muted-foreground/60"
            )}
          />
          {botRunning ? "Workers Active" : "Standby"}
        </span>

        {/* User Identity Pill */}
        <div className="flex items-center gap-1.5 rounded-full border border-border bg-card px-2.5 py-1 text-xs">
          <User className="h-3 w-3 text-muted-foreground" />
          <span className="font-semibold text-foreground text-[11px] font-mono">{user?.username}</span>
          <span
            className={cn(
              "text-[9px] font-bold px-1.5 py-0.2 rounded font-mono uppercase",
              isAdmin
                ? "bg-purple-500/20 text-purple-300 border border-purple-500/30"
                : "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
            )}
          >
            {user?.role}
          </span>
        </div>

        {/* Logout Button */}
        <button
          type="button"
          onClick={logout}
          title="Sign out"
          className="app-press grid h-7 w-7 place-items-center rounded-full border border-border bg-card text-muted-foreground hover:text-rose-400 hover:border-rose-500/30 transition-colors cursor-pointer"
        >
          <LogOut className="h-3.5 w-3.5" />
        </button>
      </div>
    </header>
  );
}
