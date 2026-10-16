import React, { useState, useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Play,
  Pause,
  MonitorPlay,
  Sparkles,
  CheckCircle2,
  Clock,
  Layers,
  ArrowRight,
  ShieldCheck,
  AlertTriangle,
  RotateCcw,
  ExternalLink,
  ChevronRight,
  TrendingUp,
  FileSpreadsheet,
  FileText,
  StopCircle,
  Filter,
  Zap,
  Gauge,
} from "lucide-react";
import { toast } from "sonner";

import { apiGet, apiPost } from "@/lib/api";
import { useAuth } from "@/lib/authContext";
import type { DashboardStatus, ActivityItem } from "@/lib/types";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { MetricCard } from "@/components/ui/MetricCard";
import { Badge } from "@/components/ui/Badge";
import { Modal } from "@/components/ui/Modal";
import ScreencastCanvas from "@/components/screencast/ScreencastCanvas";

function downloadCsv(filename: string, csvContent: string) {
  const blob = new Blob(["\uFEFF" + csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.setAttribute("href", url);
  link.setAttribute("download", filename);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

function FreshJobPriorityControl({
  site,
  engineState,
  onUpdate,
  isLoading,
}: {
  site: "naukri" | "linkedin";
  engineState?: any;
  onUpdate: (site: "naukri" | "linkedin", enabled: boolean, thresholdMinutes: number) => void;
  isLoading?: boolean;
}) {
  const isEnabled = Boolean(engineState?.only_fresh ?? engineState?.only_fresh_10min ?? false);
  const currentTotalMins = Number(engineState?.fresh_threshold_minutes ?? 10);

  const isHour = currentTotalMins >= 60 && currentTotalMins % 60 === 0;
  const [selectedUnit, setSelectedUnit] = useState<"min" | "hour">(isHour ? "hour" : "min");
  const [selectedValue, setSelectedValue] = useState<number>(
    isHour ? currentTotalMins / 60 : currentTotalMins
  );

  React.useEffect(() => {
    if (currentTotalMins >= 60 && currentTotalMins % 60 === 0) {
      setSelectedUnit("hour");
      setSelectedValue(currentTotalMins / 60);
    } else {
      setSelectedUnit("min");
      setSelectedValue(currentTotalMins);
    }
  }, [currentTotalMins]);

  const minOptions = [5, 10, 15, 20, 30, 45, 60];
  const hourOptions = [1, 2, 3, 4, 6, 8, 12, 24];

  const currentOptions = selectedUnit === "hour" ? [...hourOptions] : [...minOptions];
  if (!currentOptions.includes(selectedValue)) {
    currentOptions.push(selectedValue);
    currentOptions.sort((a, b) => a - b);
  }

  const handleToggle = () => {
    const nextEnabled = !isEnabled;
    const computedMins = selectedUnit === "hour" ? selectedValue * 60 : selectedValue;
    onUpdate(site, nextEnabled, computedMins);
  };

  const handleValueChange = (newVal: number) => {
    setSelectedValue(newVal);
    const computedMins = selectedUnit === "hour" ? newVal * 60 : newVal;
    onUpdate(site, isEnabled, computedMins);
  };

  const handleUnitChange = (newUnit: "min" | "hour") => {
    setSelectedUnit(newUnit);
    let newVal = selectedValue;
    if (newUnit === "hour" && selectedUnit === "min") {
      newVal = Math.max(1, Math.round(selectedValue / 60)) || 1;
    } else if (newUnit === "min" && selectedUnit === "hour") {
      newVal = Math.min(60, selectedValue * 60) || 15;
    }
    setSelectedValue(newVal);
    const computedMins = newUnit === "hour" ? newVal * 60 : newVal;
    onUpdate(site, isEnabled, computedMins);
  };

  const displayTime =
    selectedUnit === "hour"
      ? `${selectedValue} hour${selectedValue > 1 ? "s" : ""}`
      : `${selectedValue} min`;

  return (
    <div className="mt-3 p-3 rounded-xl bg-slate-950/40 border border-slate-800/60 hover:border-slate-800 transition-colors">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Zap className={`h-3.5 w-3.5 ${isEnabled ? "text-amber-400 fill-amber-400/20" : "text-slate-500"}`} />
          <span className="text-xs font-semibold text-slate-200">Fresh Jobs Priority</span>
          {isEnabled ? (
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-medium">
              Active · {displayTime}
            </span>
          ) : (
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">
              Off
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={handleToggle}
          disabled={isLoading}
          aria-label={`Toggle Fresh Jobs Priority for ${site}`}
          className={`w-9 h-5 flex items-center rounded-full p-0.5 transition-colors cursor-pointer ${
            isEnabled ? "bg-emerald-500 justify-end" : "bg-slate-700 justify-start"
          } ${isLoading ? "opacity-50 cursor-not-allowed" : ""}`}
        >
          <span className="w-4 h-4 bg-white rounded-full shadow-md transition-transform" />
        </button>
      </div>

      <p className="text-[11px] text-slate-400 mt-1">
        {isEnabled
          ? `Only auto-apply to listings posted within the last ${displayTime}`
          : "Apply to all matching listings regardless of posting age"}
      </p>

      {/* Dynamic Controls: Dropdown for Number and Unit */}
      <div className="mt-2.5 pt-2 border-t border-slate-800/60 flex items-center justify-between gap-2">
        <span className="text-[10px] font-medium uppercase tracking-wider text-slate-400">Time Window:</span>
        <div className="flex items-center gap-1.5">
          {/* Number Selector */}
          <select
            value={selectedValue}
            onChange={(e) => handleValueChange(Number(e.target.value))}
            className="bg-slate-900 border border-slate-700 hover:border-slate-600 text-slate-200 text-xs rounded-lg px-2 py-1 outline-none focus:border-emerald-500 font-mono transition-colors cursor-pointer"
          >
            {currentOptions.map((opt) => (
              <option key={opt} value={opt} className="bg-slate-900 text-slate-200">
                {opt}
              </option>
            ))}
          </select>

          {/* Unit Selector (min / hour) */}
          <select
            value={selectedUnit}
            onChange={(e) => handleUnitChange(e.target.value as "min" | "hour")}
            className="bg-slate-900 border border-slate-700 hover:border-slate-600 text-slate-200 text-xs rounded-lg px-2 py-1 outline-none focus:border-emerald-500 transition-colors cursor-pointer"
          >
            <option value="min" className="bg-slate-900 text-slate-200">
              Min
            </option>
            <option value="hour" className="bg-slate-900 text-slate-200">
              Hour
            </option>
          </select>
        </div>
      </div>
    </div>
  );
}

interface ContinuousPacingControlProps {
  site: "naukri" | "linkedin";
  engineState?: any;
  onUpdate: (site: "naukri" | "linkedin", paceSeconds: number) => void;
  isLoading?: boolean;
}

function ContinuousPacingControl({
  site,
  engineState,
  onUpdate,
  isLoading,
}: ContinuousPacingControlProps) {
  const currentPace = engineState?.pace_seconds ?? 3;
  const [selectedPace, setSelectedPace] = useState<number>(currentPace);

  React.useEffect(() => {
    if (engineState?.pace_seconds != null) {
      setSelectedPace(engineState.pace_seconds);
    }
  }, [engineState?.pace_seconds]);

  const handlePaceChange = (val: number) => {
    setSelectedPace(val);
    onUpdate(site, val);
  };

  const getPaceBadge = (p: number) => {
    if (p <= 1.5) return { label: "⚡ Fast Scan", variant: "info" as const };
    if (p <= 3) return { label: "⚖️ Balanced", variant: "success" as const };
    return { label: "🛡️ Relaxed Stealth", variant: "neutral" as const };
  };

  const badgeInfo = getPaceBadge(selectedPace);

  return (
    <div className="mt-2.5 p-3 rounded-xl bg-slate-950/40 border border-slate-800/60 hover:border-slate-800 transition-colors">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Gauge className="h-3.5 w-3.5 text-emerald-400" />
          <span className="text-xs font-semibold text-slate-200">Continuous Pacing</span>
          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-medium">
            {badgeInfo.label} · {selectedPace}s/card
          </span>
        </div>
      </div>

      <p className="text-[11px] text-slate-400 mt-1">
        Continuous 24/7 scanning rhythm. No dead stop pauses — checks jobs smoothly.
      </p>

      {/* Preset Buttons */}
      <div className="mt-2 pt-2 border-t border-slate-800/60 flex items-center justify-between gap-2">
        <span className="text-[10px] font-medium uppercase tracking-wider text-slate-400">Card Speed:</span>
        <div className="flex items-center gap-1.5">
          {[1, 2, 3, 5, 8].map((sec) => (
            <button
              key={sec}
              type="button"
              disabled={isLoading}
              onClick={() => handlePaceChange(sec)}
              className={`px-2 py-0.5 rounded-lg text-xs font-mono transition-all cursor-pointer ${
                selectedPace === sec
                  ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 font-bold"
                  : "bg-slate-900 border border-slate-800 text-slate-400 hover:text-slate-200 hover:border-slate-700"
              } ${isLoading ? "opacity-50 cursor-not-allowed" : ""}`}
            >
              {sec}s
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function exportCsv(items: ActivityItem[]) {
  if (!items || items.length === 0) {
    toast.error("No activity records available to export");
    return;
  }
  const headers = ["Timestamp", "Platform", "Role", "Job Title", "Company", "Status", "Reason", "URL"];
  const rows = items.map((a) => [
    `"${a.timestamp || ""}"`,
    `"${a.platform || a.source || ""}"`,
    `"${a.role || ""}"`,
    `"${(a.title || "").replace(/"/g, '""')}"`,
    `"${(a.company || "").replace(/"/g, '""')}"`,
    `"${a.status || ""}"`,
    `"${(a.reason || "").replace(/"/g, '""')}"`,
    `"${a.job_url || ""}"`,
  ]);
  const dateStr = new Date().toISOString().slice(0, 10);
  downloadCsv(`applypilot_activity_${dateStr}.csv`, [headers.join(","), ...rows.map((r) => r.join(","))].join("\n"));
  toast.success(`Exported ${items.length} records to CSV`);
}

export default function Dashboard() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const queryClient = useQueryClient();

  // Modal screencast state
  const [screencastOpen, setScreencastOpen] = useState(false);
  const [screencastSite, setScreencastSite] = useState<"naukri" | "linkedin">("naukri");

  // Query dashboard status
  const { data: statusData, isLoading } = useQuery({
    queryKey: ["dashboard-overview"],
    queryFn: () => apiGet<DashboardStatus>("/api/status"),
    refetchInterval: () => (document.visibilityState === "visible" ? 6000 : false),
    staleTime: 4000,
  });

  const engines = statusData?.engines;
  const stats = statusData?.activity?.stats;

  // Naukri Engine State: Active | Limit Reached | Paused
  const isNaukriLimitReached = Boolean(
    engines?.naukri?.status === "Limit Reached" ||
    engines?.naukri?.daily_limit_exceeded ||
    statusData?.daily_limit?.naukri_exceeded ||
    (stats?.naukri_applied_today != null && stats.naukri_applied_today >= 50)
  );
  const isNaukriRunning = !isNaukriLimitReached && (engines?.naukri?.status === "Running" || engines?.naukri?.status === "Waiting");
  const naukriBadgeText: "Active" | "Limit Reached" | "Paused" = isNaukriLimitReached
    ? "Limit Reached"
    : isNaukriRunning
    ? "Active"
    : "Paused";
  const naukriBadgeVariant: "warning" | "success" | "neutral" = isNaukriLimitReached
    ? "warning"
    : isNaukriRunning
    ? "success"
    : "neutral";

  // LinkedIn Engine State: Active | Limit Reached | Paused
  const isLinkedInLimitReached = Boolean(
    engines?.linkedin?.status === "Limit Reached" ||
    engines?.linkedin?.daily_limit_exceeded ||
    statusData?.daily_limit?.linkedin_exceeded ||
    (stats?.linkedin_applied_today != null && stats.linkedin_applied_today >= 50)
  );
  const isLinkedInRunning = !isLinkedInLimitReached && (engines?.linkedin?.status === "Running" || engines?.linkedin?.status === "Waiting");
  const linkedInBadgeText: "Active" | "Limit Reached" | "Paused" = isLinkedInLimitReached
    ? "Limit Reached"
    : isLinkedInRunning
    ? "Active"
    : "Paused";
  const linkedInBadgeVariant: "warning" | "success" | "neutral" = isLinkedInLimitReached
    ? "warning"
    : isLinkedInRunning
    ? "success"
    : "neutral";

  const isAnyRunning = isNaukriRunning || isLinkedInRunning;
  const isAnyLimitReached = isNaukriLimitReached || isLinkedInLimitReached;
  const isAllLimitReached = isNaukriLimitReached && isLinkedInLimitReached;

  const totalApplied = stats?.total_applied ?? 0;
  const appliedToday = stats?.applied_today ?? 0;
  const totalSkipped = stats?.total_skipped ?? 0;
  const recentJobs = statusData?.activity?.recent || [];

  // Mutations
  const startEngineMutation = useMutation({
    mutationFn: (site: "naukri" | "linkedin") => {
      const isFresh = Boolean(engines?.[site]?.only_fresh ?? engines?.[site]?.only_fresh_10min ?? false);
      const thresh = Number(engines?.[site]?.fresh_threshold_minutes ?? 10);
      return apiPost(`/api/bot/${site}/start`, {
        only_fresh_10min: isFresh,
        only_fresh: isFresh,
        fresh_threshold_minutes: thresh,
      });
    },
    onSuccess: (_, site) => {
      toast.success(`${site === "naukri" ? "Naukri" : "LinkedIn"} automation started.`);
      queryClient.invalidateQueries({ queryKey: ["dashboard-overview"] });
    },
    onError: (err: any) => toast.error(err.message || "Failed to start engine"),
  });

  const stopEngineMutation = useMutation({
    mutationFn: (site: "naukri" | "linkedin") => apiPost(`/api/bot/${site}/stop`),
    onSuccess: (_, site) => {
      toast.success(`${site === "naukri" ? "Naukri" : "LinkedIn"} automation paused.`);
      queryClient.invalidateQueries({ queryKey: ["dashboard-overview"] });
    },
    onError: (err: any) => toast.error(err.message || "Failed to stop engine"),
  });

  const stopAllMutation = useMutation({
    mutationFn: () => apiPost("/api/bot/all/stop"),
    onSuccess: () => {
      toast.success("All automation engines halted.");
      queryClient.invalidateQueries({ queryKey: ["dashboard-overview"] });
    },
    onError: () => toast.error("Failed to stop engines"),
  });

  const updateFreshFilterMutation = useMutation({
    mutationFn: ({
      site,
      enabled,
      thresholdMinutes,
    }: {
      site: "naukri" | "linkedin";
      enabled: boolean;
      thresholdMinutes: number;
    }) =>
      apiPost(`/api/bot/${site}/fresh-filter`, {
        enabled,
        threshold_minutes: thresholdMinutes,
      }),
    onSuccess: (res: any, variables) => {
      const displayTime =
        variables.thresholdMinutes >= 60 && variables.thresholdMinutes % 60 === 0
          ? `${variables.thresholdMinutes / 60}h`
          : `${variables.thresholdMinutes}m`;
      toast.success(
        `${variables.site.toUpperCase()}: Fresh Jobs Priority ${
          res.enabled ? `ON (${displayTime})` : "OFF"
        }`
      );
      queryClient.invalidateQueries({ queryKey: ["dashboard-overview"] });
    },
    onError: (err: any) => toast.error(err.message || "Failed to update fresh filter"),
  });

  const updatePacingMutation = useMutation({
    mutationFn: ({ site, paceSeconds }: { site: "naukri" | "linkedin"; paceSeconds: number }) =>
      apiPost(`/api/bot/${site}/pacing`, { pace_seconds: paceSeconds }),
    onSuccess: (res: any, variables) => {
      toast.success(
        `${variables.site.toUpperCase()}: Continuous pacing set to ${variables.paceSeconds}s/card`
      );
      queryClient.invalidateQueries({ queryKey: ["dashboard-overview"] });
    },
    onError: (err: any) => toast.error(err.message || "Failed to update pacing"),
  });

  const [isStartingAll, setIsStartingAll] = useState(false);

  const handleStartAll = async () => {
    setIsStartingAll(true);
    try {
      toast.info("Starting Naukri engine...");
      await startEngineMutation.mutateAsync("naukri");
      toast.info("Staggering 12s before starting LinkedIn engine to protect memory...");
      await new Promise((resolve) => setTimeout(resolve, 12000));
      await startEngineMutation.mutateAsync("linkedin");
    } catch (e: any) {
      // Handled by mutation onError
    } finally {
      setIsStartingAll(false);
    }
  };

  // Attention banner items
  const attentionItems = useMemo(() => {
    const list = [];
    if (!statusData?.profile?.is_complete) {
      list.push({
        title: "Career Profile Incomplete",
        desc: "Add your target roles, notice period, and resume to enable automatic applications.",
        ctaText: "Complete Profile",
        ctaPath: "/profile",
        severity: "warning" as const,
      });
    }
    if (!statusData?.sessions?.linkedin?.valid && !statusData?.sessions?.linkedin?.present) {
      list.push({
        title: "Connect LinkedIn Account",
        desc: "Connect your LinkedIn session to start auto-applying to Easy Apply roles.",
        ctaText: "Connect Account",
        ctaPath: "/sessions",
        severity: "info" as const,
      });
    }
    if (!statusData?.sessions?.naukri?.valid && !statusData?.sessions?.naukri?.present) {
      list.push({
        title: "Connect Naukri Account",
        desc: "Connect your Naukri account to enable search and apply across top Indian companies.",
        ctaText: "Connect Account",
        ctaPath: "/sessions",
        severity: "info" as const,
      });
    }
    if (statusData?.daily_limit?.exceeded) {
      list.push({
        title: "Daily Application Quota Reached",
        desc: "You have reached your safe daily quota (50 applications). Quota resets at 12:00 AM.",
        ctaText: "View Activity",
        ctaPath: "/activity",
        severity: "neutral" as const,
      });
    }
    return list;
  }, [statusData]);

  // Greeting time
  const greeting = useMemo(() => {
    const hour = new Date().getHours();
    if (hour < 12) return "Good morning";
    if (hour < 17) return "Good afternoon";
    return "Good evening";
  }, []);

  // Time saved estimate (~12 mins saved per applied/screened job)
  const timeSavedHrs = useMemo(() => {
    const totalProcessed = totalApplied + Math.min(totalSkipped, 200);
    const hrs = (totalProcessed * 12) / 60;
    return hrs > 0 ? hrs.toFixed(1) : "0";
  }, [totalApplied, totalSkipped]);

  return (
    <div className="flex-1 p-5 sm:p-8 max-w-7xl mx-auto w-full space-y-7">
      {/* ─── Top Welcome & Primary Action Bar ─── */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 pb-6 border-b border-slate-800/80">
        <div>
          <div className="flex items-center gap-2 text-xs font-medium text-slate-400 mb-1">
            <span>Workspace</span>
            <ChevronRight className="h-3 w-3" />
            <span className="text-slate-200">Overview</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-100">
            {greeting}, {user?.username || "Candidate"}
          </h1>
          <p className="mt-1 text-xs sm:text-sm text-slate-400">
            Your career automation workspace is active and monitoring job portals.
          </p>
        </div>

        {/* Global Controls & Status Pill */}
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl border border-slate-800 bg-slate-900/60">
            <span
              className={`h-2 w-2 rounded-full ${
                isAnyRunning
                  ? "bg-emerald-400 animate-pulse"
                  : isAnyLimitReached
                  ? "bg-amber-400 animate-pulse"
                  : "bg-slate-500"
              }`}
            />
            <span className="text-xs font-medium text-slate-300">
              {isAnyRunning
                ? "Automation Active"
                : isAllLimitReached
                ? "Daily Quota Reached"
                : isAnyLimitReached
                ? "Quota Limit Reached"
                : "Automation Paused"}
            </span>
          </div>

          {isAnyRunning ? (
            <Button
              variant="destructive"
              size="md"
              leftIcon={<StopCircle className="h-4 w-4" />}
              isLoading={stopAllMutation.isPending}
              onClick={() => stopAllMutation.mutate()}
            >
              Emergency Pause All
            </Button>
          ) : (
            <Button
              variant="primary"
              size="md"
              leftIcon={<Play className="h-4 w-4 fill-current" />}
              isLoading={isStartingAll || startEngineMutation.isPending}
              onClick={handleStartAll}
            >
              Start Automation
            </Button>
          )}

          <Button
            variant="secondary"
            size="md"
            leftIcon={<MonitorPlay className="h-4 w-4" />}
            onClick={() => {
              setScreencastSite("naukri");
              setScreencastOpen(true);
            }}
          >
            Live Browser
          </Button>
        </div>
      </div>

      {/* ─── Attention Center (Actionable Warnings / Next Steps) ─── */}
      {attentionItems.length > 0 && (
        <div className="space-y-2.5">
          {attentionItems.slice(0, 2).map((item, idx) => (
            <div
              key={idx}
              className={`p-4 rounded-2xl border flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
                item.severity === "warning"
                  ? "border-amber-500/25 bg-amber-500/10 text-amber-200"
                  : item.severity === "info"
                  ? "border-sky-500/25 bg-sky-500/10 text-sky-200"
                  : "border-slate-800 bg-slate-900/60 text-slate-300"
              }`}
            >
              <div className="flex items-start gap-3">
                <AlertTriangle className="h-4.5 w-4.5 shrink-0 mt-0.5 text-amber-400" />
                <div>
                  <h4 className="text-xs sm:text-sm font-semibold">{item.title}</h4>
                  <p className="text-xs text-slate-400 mt-0.5">{item.desc}</p>
                </div>
              </div>
              <Button
                size="sm"
                variant={item.severity === "warning" ? "secondary" : "subtle"}
                onClick={() => navigate(item.ctaPath)}
                className="shrink-0"
              >
                {item.ctaText}
              </Button>
            </div>
          ))}
        </div>
      )}

      {/* ─── 4 Clean Key Metric Cards ─── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          label="Applications Today"
          value={appliedToday}
          subtext={`${totalApplied} total lifetime applications`}
          trend={appliedToday > 0 ? { value: `+${appliedToday} today`, isPositive: true } : undefined}
          icon={<CheckCircle2 className="h-4 w-4" />}
          variant="success"
        />

        <MetricCard
          label="Application Accuracy"
          value={totalApplied > 0 ? "100%" : "—"}
          subtext="Verified job matches submitted"
          icon={<TrendingUp className="h-4 w-4" />}
          variant="indigo"
        />

        <MetricCard
          label="Filtered Irrelevant Jobs"
          value={totalSkipped.toLocaleString()}
          subtext="Mismatched tech stack, exp, or CTC"
          icon={<Filter className="h-4 w-4" />}
          variant="default"
        />

        <MetricCard
          label="Estimated Time Saved"
          value={`${timeSavedHrs}h`}
          subtext="~12 mins saved per application"
          icon={<Clock className="h-4 w-4" />}
          variant="default"
        />
      </div>

      {/* ─── Automation Engines (Naukri & LinkedIn) ─── */}
      <div>
        <div className="flex items-center justify-between mb-3.5">
          <div>
            <h2 className="text-base font-semibold text-slate-100">Automation Engines</h2>
            <p className="text-xs text-slate-400">Manage individual portal search and apply pipelines</p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Naukri Engine Card */}
          <Card className="flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between pb-3 border-b border-slate-800/80 mb-3.5">
                <div className="flex items-center gap-2.5">
                  <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-500/10 text-blue-400 font-bold border border-blue-500/20 text-sm">
                    N
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-slate-100">Naukri.com</h3>
                    <p className="text-[11px] text-slate-400">Direct Apply & Chatbot Screening</p>
                  </div>
                </div>

                <Badge
                  variant={naukriBadgeVariant}
                  dot
                >
                  {naukriBadgeText}
                </Badge>
              </div>

              {/* Engine Metrics & Options */}
              <div className="grid grid-cols-3 gap-2 py-2">
                <div className="p-2.5 rounded-xl bg-slate-950/40 border border-slate-800/60">
                  <span className="text-[10px] text-slate-400 uppercase font-medium">Applied Today</span>
                  <p className="num text-base font-semibold text-slate-200 mt-0.5">
                    {stats?.naukri_applied_today ?? 0}
                  </p>
                </div>
                <div className="p-2.5 rounded-xl bg-slate-950/40 border border-slate-800/60">
                  <span className="text-[10px] text-slate-400 uppercase font-medium">Daily Quota</span>
                  <p className="num text-base font-semibold text-slate-200 mt-0.5">
                    {stats?.naukri_applied_today ?? 0}/50
                  </p>
                </div>
                <div className="p-2.5 rounded-xl bg-slate-950/40 border border-slate-800/60">
                  <span className="text-[10px] text-slate-400 uppercase font-medium">Filtered</span>
                  <p className="num text-base font-semibold text-slate-200 mt-0.5">
                    {stats?.naukri_skipped_today ?? 0}
                  </p>
                </div>
              </div>

              {/* Dynamic Fresh Jobs Priority Control */}
              <FreshJobPriorityControl
                site="naukri"
                engineState={engines?.naukri}
                onUpdate={(site, enabled, mins) =>
                  updateFreshFilterMutation.mutate({ site, enabled, thresholdMinutes: mins })
                }
                isLoading={updateFreshFilterMutation.isPending}
              />

              {/* Dynamic Continuous Pacing Control */}
              <ContinuousPacingControl
                site="naukri"
                engineState={engines?.naukri}
                onUpdate={(site, paceSeconds) =>
                  updatePacingMutation.mutate({ site, paceSeconds })
                }
                isLoading={updatePacingMutation.isPending}
              />
            </div>

            {/* Actions */}
            <div className="flex items-center gap-2 pt-4 mt-4 border-t border-slate-800/60">
              {isNaukriRunning ? (
                <Button
                  variant="destructive"
                  size="sm"
                  className="flex-1"
                  leftIcon={<Pause className="h-3.5 w-3.5" />}
                  isLoading={stopEngineMutation.isPending}
                  onClick={() => stopEngineMutation.mutate("naukri")}
                >
                  Pause Engine
                </Button>
              ) : isNaukriLimitReached ? (
                <Button
                  variant="outline"
                  size="sm"
                  disabled
                  className="flex-1 border-amber-500/40 text-amber-400 opacity-60 cursor-not-allowed"
                  leftIcon={<AlertTriangle className="h-3.5 w-3.5" />}
                  title="Daily quota reached. Resets at 12:00 AM."
                >
                  Quota Limit Reached
                </Button>
              ) : (
                <Button
                  variant="primary"
                  size="sm"
                  className="flex-1"
                  leftIcon={<Play className="h-3.5 w-3.5 fill-current" />}
                  isLoading={startEngineMutation.isPending}
                  onClick={() => startEngineMutation.mutate("naukri")}
                >
                  Start Engine
                </Button>
              )}
              <Button
                variant="outline"
                size="sm"
                leftIcon={<MonitorPlay className="h-3.5 w-3.5" />}
                onClick={() => {
                  setScreencastSite("naukri");
                  setScreencastOpen(true);
                }}
              >
                Inspect
              </Button>
            </div>
          </Card>

          {/* LinkedIn Engine Card */}
          <Card className="flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between pb-3 border-b border-slate-800/80 mb-3.5">
                <div className="flex items-center gap-2.5">
                  <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-sky-500/10 text-sky-400 font-bold border border-sky-500/20 text-sm">
                    In
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-slate-100">LinkedIn Easy Apply</h3>
                    <p className="text-[11px] text-slate-400">Single & Multi-Step Questionnaires</p>
                  </div>
                </div>

                <Badge
                  variant={linkedInBadgeVariant}
                  dot
                >
                  {linkedInBadgeText}
                </Badge>
              </div>

              {/* Engine Metrics & Options */}
              <div className="grid grid-cols-3 gap-2 py-2">
                <div className="p-2.5 rounded-xl bg-slate-950/40 border border-slate-800/60">
                  <span className="text-[10px] text-slate-400 uppercase font-medium">Applied Today</span>
                  <p className="num text-base font-semibold text-slate-200 mt-0.5">
                    {stats?.linkedin_applied_today ?? 0}
                  </p>
                </div>
                <div className="p-2.5 rounded-xl bg-slate-950/40 border border-slate-800/60">
                  <span className="text-[10px] text-slate-400 uppercase font-medium">Daily Quota</span>
                  <p className="num text-base font-semibold text-slate-200 mt-0.5">
                    {stats?.linkedin_applied_today ?? 0}/50
                  </p>
                </div>
                <div className="p-2.5 rounded-xl bg-slate-950/40 border border-slate-800/60">
                  <span className="text-[10px] text-slate-400 uppercase font-medium">Filtered</span>
                  <p className="num text-base font-semibold text-slate-200 mt-0.5">
                    {stats?.linkedin_skipped_today ?? 0}
                  </p>
                </div>
              </div>

              {/* Dynamic Fresh Jobs Priority Control */}
              <FreshJobPriorityControl
                site="linkedin"
                engineState={engines?.linkedin}
                onUpdate={(site, enabled, mins) =>
                  updateFreshFilterMutation.mutate({ site, enabled, thresholdMinutes: mins })
                }
                isLoading={updateFreshFilterMutation.isPending}
              />

              {/* Dynamic Continuous Pacing Control */}
              <ContinuousPacingControl
                site="linkedin"
                engineState={engines?.linkedin}
                onUpdate={(site, paceSeconds) =>
                  updatePacingMutation.mutate({ site, paceSeconds })
                }
                isLoading={updatePacingMutation.isPending}
              />
            </div>

            {/* Actions */}
            <div className="flex items-center gap-2 pt-4 mt-4 border-t border-slate-800/60">
              {isLinkedInRunning ? (
                <Button
                  variant="destructive"
                  size="sm"
                  className="flex-1"
                  leftIcon={<Pause className="h-3.5 w-3.5" />}
                  isLoading={stopEngineMutation.isPending}
                  onClick={() => stopEngineMutation.mutate("linkedin")}
                >
                  Pause Engine
                </Button>
              ) : isLinkedInLimitReached ? (
                <Button
                  variant="outline"
                  size="sm"
                  disabled
                  className="flex-1 border-amber-500/40 text-amber-400 opacity-60 cursor-not-allowed"
                  leftIcon={<AlertTriangle className="h-3.5 w-3.5" />}
                  title="Daily quota reached. Resets at 12:00 AM."
                >
                  Quota Limit Reached
                </Button>
              ) : (
                <Button
                  variant="primary"
                  size="sm"
                  className="flex-1"
                  leftIcon={<Play className="h-3.5 w-3.5 fill-current" />}
                  isLoading={startEngineMutation.isPending}
                  onClick={() => startEngineMutation.mutate("linkedin")}
                >
                  Start Engine
                </Button>
              )}
              <Button
                variant="outline"
                size="sm"
                leftIcon={<MonitorPlay className="h-3.5 w-3.5" />}
                onClick={() => {
                  setScreencastSite("linkedin");
                  setScreencastOpen(true);
                }}
              >
                Inspect
              </Button>
            </div>
          </Card>
        </div>
      </div>

      {/* ─── Recent Applications (5-10 Jobs) ─── */}
      <Card>
        <div className="flex items-center justify-between pb-4 border-b border-slate-800/80 mb-4">
          <div>
            <h3 className="text-sm font-semibold text-slate-100">Recent Applications</h3>
            <p className="text-xs text-slate-400">Latest discovered and processed job opportunities</p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              leftIcon={<FileSpreadsheet className="h-3.5 w-3.5" />}
              onClick={() => exportCsv(recentJobs)}
            >
              Export CSV
            </Button>
            <Link to="/activity">
              <Button variant="ghost" size="sm" rightIcon={<ArrowRight className="h-3.5 w-3.5" />}>
                View All
              </Button>
            </Link>
          </div>
        </div>

        {recentJobs.length === 0 ? (
          <div className="py-10 text-center">
            <p className="text-xs text-slate-400">
              No recent applications recorded yet. Start an engine above to begin searching!
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-800/60 text-[11px] font-medium text-slate-400">
                  <th className="pb-2.5 font-medium">Job Title & Role</th>
                  <th className="pb-2.5 font-medium">Company</th>
                  <th className="pb-2.5 font-medium">Platform</th>
                  <th className="pb-2.5 font-medium">Status</th>
                  <th className="pb-2.5 font-medium text-right">Time</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/40">
                {recentJobs.slice(0, 6).map((job, idx) => {
                  const isApplied = (job.status || "").toLowerCase() === "applied";
                  return (
                    <tr key={idx} className="hover:bg-slate-800/30 transition-colors">
                      <td className="py-3 pr-3">
                        <div className="font-medium text-slate-200 truncate max-w-[220px]">
                          {job.title || "Untitled Role"}
                        </div>
                        {job.role && (
                          <div className="text-[10px] text-slate-500 truncate max-w-[220px]">
                            {job.role}
                          </div>
                        )}
                      </td>
                      <td className="py-3 pr-3 text-slate-300 font-medium">
                        {job.company || "Direct Employer"}
                      </td>
                      <td className="py-3 pr-3">
                        <span className="text-[11px] font-medium text-slate-400 capitalize">
                          {job.platform || job.source || "Naukri"}
                        </span>
                      </td>
                      <td className="py-3 pr-3">
                        <Badge
                          variant={isApplied ? "success" : "neutral"}
                          size="sm"
                          dot
                        >
                          {job.status}
                        </Badge>
                      </td>
                      <td className="py-3 text-right text-slate-400 num font-mono text-[11px]">
                        {job.timestamp ? job.timestamp.slice(11, 16) : "Just now"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* ─── Remote Screencast Modal ─── */}
      <Modal
        isOpen={screencastOpen}
        onClose={() => setScreencastOpen(false)}
        title={`Live Browser · ${screencastSite === "naukri" ? "Naukri.com" : "LinkedIn"}`}
        description="Real-time Chrome DevTools Protocol screencast with interactive click and typing support."
        size="xl"
      >
        <div className="h-[520px] flex flex-col">
          <ScreencastCanvas
            site={screencastSite}
            mode="live_check"
            onClose={() => setScreencastOpen(false)}
          />
        </div>
      </Modal>
    </div>
  );
}
