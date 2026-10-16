import React from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Layers,
  Sparkles,
  ExternalLink,
  CheckCircle2,
  Clock,
  Lock,
  ArrowUpRight,
  Shield,
  Zap,
  Globe,
} from "lucide-react";
import Card3D from "@/components/ui/Card3D";
import { cn } from "@/lib/utils";

interface SaaSChannelsOverviewProps {
  naukriStatus: string;
  linkedinStatus: string;
  naukriApplied: number;
  linkedinApplied: number;
}

export default function SaaSChannelsOverview({
  naukriStatus,
  linkedinStatus,
  naukriApplied,
  linkedinApplied,
}: SaaSChannelsOverviewProps) {
  const channels = [
    {
      id: "naukri",
      name: "Naukri.com",
      status: "Active",
      engineStatus: naukriStatus,
      applied: naukriApplied,
      badge: "Production Ready",
      description: "Dual-Engine: Live 10m HR Radar + Instant 1-Click Native Chat Apply",
      quota: "50 / Day",
      features: ["Custom Screening Q&A", "Live CDP Radar", "Anti-Bot Residential Mode"],
      actionLink: "/sessions",
      active: true,
      accentColor: "emerald",
    },
    {
      id: "linkedin",
      name: "LinkedIn",
      status: "Active",
      engineStatus: linkedinStatus,
      applied: linkedinApplied,
      badge: "Production Ready",
      description: "Easy Apply Multi-Step Form Pilot with targeted 10m age enforcement",
      quota: "50 / Day",
      features: ["Easy Apply Modal Pilot", "Gemini 3.1 Screening", "Salary Collision Guard"],
      actionLink: "/sessions",
      active: true,
      accentColor: "emerald",
    },
    {
      id: "indeed",
      name: "Indeed Jobs",
      status: "Roadmap v2.2",
      engineStatus: "Coming Soon",
      applied: 0,
      badge: "SaaS Pro Expansion",
      description: "Direct Employer & Indeed Apply automation with automated assessment answering",
      quota: "100 / Day",
      features: ["Indeed Resume Sync", "Salary Filter", "Global Remote Scan"],
      actionLink: "#",
      active: false,
      accentColor: "blue",
    },
    {
      id: "wellfound",
      name: "Wellfound (AngelList)",
      status: "Roadmap v2.3",
      engineStatus: "Coming Soon",
      applied: 0,
      badge: "Startup AI Matching",
      description: "High-growth YC/Seed stage startup applications with custom tailored pitches",
      quota: "30 / Day",
      features: ["Equity Filter", "Personalized AI Pitch", "Direct Founder Outreach"],
      actionLink: "#",
      active: false,
      accentColor: "purple",
    },
  ];

  return (
    <div className="space-y-4">
      {/* Header with SaaS Tag */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2.5">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg border border-emerald-500/30 bg-emerald-500/10 text-emerald-400">
            <Globe className="h-4 w-4" />
          </div>
          <div>
            <h3 className="font-heading text-sm font-bold tracking-tight text-foreground flex items-center gap-2">
              <span>SaaS Multi-Platform Channel Grid</span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 text-emerald-400">
                Extensible Architecture
              </span>
            </h3>
            <p className="text-xs text-muted-foreground">
              Autonomous application pipelines across tier-1 job networks and upcoming SaaS integrations
            </p>
          </div>
        </div>

        <Link
          to="/sessions"
          className="text-xs font-mono text-emerald-400 hover:text-emerald-300 flex items-center gap-1 transition-colors"
        >
          <span>Manage Session Keys</span>
          <ArrowUpRight className="h-3.5 w-3.5" />
        </Link>
      </div>

      {/* Grid of 3D Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
        {channels.map((ch, i) => (
          <Card3D
            key={ch.id}
            depth={ch.active ? 10 : 4}
            enableGlow={ch.active}
            className={cn(
              "p-4 flex flex-col justify-between h-full transition-all duration-300",
              ch.active
                ? "border-border/80 bg-card/90"
                : "border-border/40 bg-card/40 opacity-75 hover:opacity-100"
            )}
          >
            <div>
              {/* Top row: Name + Badge */}
              <div className="flex items-center justify-between gap-2">
                <span className="font-heading font-bold text-sm text-foreground flex items-center gap-1.5">
                  {ch.name}
                </span>

                <span
                  className={cn(
                    "text-[9.5px] font-mono px-2 py-0.5 rounded-full border tracking-wide uppercase",
                    ch.active
                      ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400"
                      : "border-purple-500/30 bg-purple-500/10 text-purple-400"
                  )}
                >
                  {ch.status}
                </span>
              </div>

              {/* Description */}
              <p className="mt-2 text-xs text-muted-foreground line-clamp-2 leading-relaxed">
                {ch.description}
              </p>

              {/* Feature Chips */}
              <div className="mt-3 flex flex-wrap gap-1.5">
                {ch.features.map((feat, fIdx) => (
                  <span
                    key={fIdx}
                    className="text-[9.5px] font-mono px-2 py-0.5 rounded bg-white/[0.04] border border-white/[0.06] text-muted-foreground"
                  >
                    {feat}
                  </span>
                ))}
              </div>
            </div>

            {/* Bottom: Quota & Status */}
            <div className="mt-4 pt-3 border-t border-white/5 flex items-center justify-between text-xs font-mono">
              <div className="text-[10px] text-muted-foreground">
                Cap: <span className="text-foreground font-semibold">{ch.quota}</span>
              </div>

              <div className="flex items-center gap-1.5">
                {ch.active ? (
                  <>
                    <span
                      className={cn(
                        "h-1.5 w-1.5 rounded-full",
                        ch.engineStatus === "Active"
                          ? "bg-emerald-400 animate-ping"
                          : "bg-emerald-500/40"
                      )}
                    />
                    <span className="text-[10.5px] text-emerald-400 font-semibold">
                      {ch.engineStatus}
                    </span>
                  </>
                ) : (
                  <>
                    <Lock className="h-3 w-3 text-muted-foreground" />
                    <span className="text-[10.5px] text-muted-foreground">Expansion</span>
                  </>
                )}
              </div>
            </div>
          </Card3D>
        ))}
      </div>
    </div>
  );
}
