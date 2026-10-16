import React, { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Search,
  Filter,
  FileSpreadsheet,
  FileText,
  Trash2,
  ExternalLink,
  ChevronLeft,
  ChevronRight,
  TrendingUp,
  X,
  CheckCircle2,
  Clock,
  Layers,
  ChevronDown,
} from "lucide-react";
import { toast } from "sonner";

import { apiGet, apiPost } from "@/lib/api";
import type { ActivityItem } from "@/lib/types";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { TableRowSkeleton } from "@/components/ui/Skeleton";

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

function exportCsv(items: ActivityItem[]) {
  if (!items || items.length === 0) {
    toast.error("No job application records to export");
    return;
  }
  const headers = ["Timestamp", "Platform", "Role", "Job Title", "Company", "Posted", "Status", "Reason", "URL"];
  const rows = items.map((a) => [
    `"${a.timestamp || ""}"`,
    `"${a.platform || a.source || ""}"`,
    `"${a.role || ""}"`,
    `"${(a.title || "").replace(/"/g, '""')}"`,
    `"${(a.company || "").replace(/"/g, '""')}"`,
    `"${a.posted_time || ""}"`,
    `"${a.status || ""}"`,
    `"${(a.reason || "").replace(/"/g, '""')}"`,
    `"${a.job_url || ""}"`,
  ]);
  const dateStr = new Date().toISOString().slice(0, 10);
  downloadCsv(`applypilot_applications_${dateStr}.csv`, [headers.join(","), ...rows.map((r) => r.join(","))].join("\n"));
  toast.success(`Exported ${items.length} records to CSV!`);
}

export default function LiveActivity() {
  const queryClient = useQueryClient();

  const [searchQuery, setSearchQuery] = useState("");
  const [platformFilter, setPlatformFilter] = useState<"all" | "naukri" | "linkedin">("all");
  const [statusFilter, setStatusFilter] = useState<"all" | "applied" | "skipped" | "limit_reached">("all");
  const [currentPage, setCurrentPage] = useState(1);
  const [selectedJob, setSelectedJob] = useState<ActivityItem | null>(null);
  const pageSize = 12;

  const { data, isLoading } = useQuery({
    queryKey: ["live-activity-feed"],
    queryFn: () => apiGet<{ stats: any; recent: ActivityItem[] }>("/api/activity"),
    refetchInterval: () => (document.visibilityState === "visible" ? 6000 : false),
    staleTime: 5000,
  });

  const recent = data?.recent || [];
  const stats = data?.stats;

  // Clear activity
  const clearMutation = useMutation({
    mutationFn: () => apiPost("/api/activity/clear"),
    onSuccess: () => {
      toast.success("Activity log cleared.");
      queryClient.invalidateQueries({ queryKey: ["live-activity-feed"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-overview"] });
    },
    onError: () => toast.error("Failed to clear activity log"),
  });

  // Filtered Items
  const filteredItems = useMemo(() => {
    let list = recent;

    if (platformFilter === "naukri") {
      list = list.filter((i) => (i.platform !== "linkedin" && !(i.source || "").toLowerCase().includes("linkedin")));
    } else if (platformFilter === "linkedin") {
      list = list.filter((i) => (i.platform === "linkedin" || (i.source || "").toLowerCase().includes("linkedin")));
    }

    if (statusFilter === "applied") {
      list = list.filter((i) => (i.status || "").toLowerCase() === "applied");
    } else if (statusFilter === "limit_reached") {
      list = list.filter((i) => (i.status || "").toLowerCase().includes("limit"));
    } else if (statusFilter === "skipped") {
      list = list.filter((i) => (i.status || "").toLowerCase() === "skipped");
    }

    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      list = list.filter(
        (i) =>
          (i.title || "").toLowerCase().includes(q) ||
          (i.company || "").toLowerCase().includes(q) ||
          (i.role || "").toLowerCase().includes(q) ||
          (i.reason || "").toLowerCase().includes(q)
      );
    }

    return list;
  }, [recent, platformFilter, statusFilter, searchQuery]);

  // Pagination
  const totalPages = Math.max(1, Math.ceil(filteredItems.length / pageSize));
  const safeCurrentPage = Math.min(currentPage, totalPages);
  const pagedItems = useMemo(() => {
    const start = (safeCurrentPage - 1) * pageSize;
    return filteredItems.slice(start, start + pageSize);
  }, [filteredItems, safeCurrentPage, pageSize]);

  return (
    <div className="flex-1 p-5 sm:p-8 max-w-7xl mx-auto w-full space-y-6">
      <PageHeader
        title="Application Activity"
        description="Comprehensive audit journal of all searched, filtered, and submitted applications."
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              leftIcon={<FileSpreadsheet className="h-3.5 w-3.5" />}
              onClick={() => exportCsv(filteredItems)}
            >
              Export CSV
            </Button>
            {recent.length > 0 && (
              <Button
                variant="destructive"
                size="sm"
                leftIcon={<Trash2 className="h-3.5 w-3.5" />}
                isLoading={clearMutation.isPending}
                onClick={() => {
                  if (window.confirm("Are you sure you want to clear your activity journal?")) {
                    clearMutation.mutate();
                  }
                }}
              >
                Clear Log
              </Button>
            )}
          </div>
        }
      />

      {/* ─── Filter Bar ─── */}
      <Card className="p-3 sm:p-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
          {/* Search Box */}
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-500" />
            <input
              type="text"
              placeholder="Search by job title, company, or skill..."
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setCurrentPage(1);
              }}
              className="h-9 w-full rounded-xl border border-slate-800 bg-slate-950/60 pl-9 pr-3 text-xs text-slate-200 placeholder:text-slate-500 focus:border-emerald-500/50 focus:outline-none"
            />
          </div>

          {/* Filter Pills */}
          <div className="flex items-center gap-2 flex-wrap">
            {/* Platform Segment */}
            <div className="flex items-center rounded-xl border border-slate-800 bg-slate-950/60 p-1">
              <button
                onClick={() => { setPlatformFilter("all"); setCurrentPage(1); }}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                  platformFilter === "all" ? "bg-slate-800 text-slate-100" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                All Portals
              </button>
              <button
                onClick={() => { setPlatformFilter("naukri"); setCurrentPage(1); }}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                  platformFilter === "naukri" ? "bg-slate-800 text-slate-100" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Naukri
              </button>
              <button
                onClick={() => { setPlatformFilter("linkedin"); setCurrentPage(1); }}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                  platformFilter === "linkedin" ? "bg-slate-800 text-slate-100" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                LinkedIn
              </button>
            </div>

            {/* Status Segment */}
            <div className="flex items-center rounded-xl border border-slate-800 bg-slate-950/60 p-1">
              <button
                onClick={() => { setStatusFilter("all"); setCurrentPage(1); }}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                  statusFilter === "all" ? "bg-slate-800 text-slate-100" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                All
              </button>
              <button
                onClick={() => { setStatusFilter("applied"); setCurrentPage(1); }}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                  statusFilter === "applied" ? "bg-emerald-500/15 text-emerald-400" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Applied
              </button>
              <button
                onClick={() => { setStatusFilter("skipped"); setCurrentPage(1); }}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                  statusFilter === "skipped" ? "bg-slate-800 text-slate-100" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Filtered
              </button>
              <button
                onClick={() => { setStatusFilter("limit_reached"); setCurrentPage(1); }}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                  statusFilter === "limit_reached" ? "bg-amber-500/15 text-amber-400" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Limit Hit
              </button>
            </div>
          </div>
        </div>
      </Card>

      {/* ─── Applications Data Table ─── */}
      <Card className="p-0 overflow-hidden">
        {isLoading ? (
          <div className="divide-y divide-slate-800/60 p-4">
            <TableRowSkeleton cols={6} />
            <TableRowSkeleton cols={6} />
            <TableRowSkeleton cols={6} />
            <TableRowSkeleton cols={6} />
          </div>
        ) : filteredItems.length === 0 ? (
          <div className="p-10">
            <EmptyState
              title="No applications match your filter"
              description="Try adjusting your search query, or start an automation engine from the overview dashboard."
            />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-950/40 border-b border-slate-800 text-slate-400">
                <tr>
                  <th className="py-3 px-4 font-medium">Job Title & Target Role</th>
                  <th className="py-3 px-4 font-medium">Company</th>
                  <th className="py-3 px-4 font-medium">Portal</th>
                  <th className="py-3 px-4 font-medium">Status</th>
                  <th className="py-3 px-4 font-medium">Evaluation Note / Skip Reason</th>
                  <th className="py-3 px-4 font-medium text-right">Time</th>
                  <th className="py-3 px-4 font-medium text-center">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/40">
                {pagedItems.map((job, idx) => {
                  const isApplied = (job.status || "").toLowerCase() === "applied";
                  return (
                    <tr
                      key={idx}
                      className="hover:bg-slate-800/30 transition-colors cursor-pointer"
                      onClick={() => setSelectedJob(job)}
                    >
                      <td className="py-3.5 px-4">
                        <div className="font-semibold text-slate-100 truncate max-w-[200px]">
                          {job.title || "Untitled Position"}
                        </div>
                        {job.role && (
                          <div className="text-[10px] text-slate-400 truncate max-w-[200px] mt-0.5">
                            {job.role}
                          </div>
                        )}
                      </td>
                      <td className="py-3.5 px-4 text-slate-200 font-medium whitespace-nowrap">
                        {job.company || "Direct Listing"}
                      </td>
                      <td className="py-3.5 px-4 whitespace-nowrap">
                        <span className="text-slate-400 capitalize">
                          {job.platform || job.source || "Naukri"}
                        </span>
                      </td>
                      <td className="py-3.5 px-4 whitespace-nowrap">
                        <Badge
                          variant={
                            isApplied
                              ? "success"
                              : (job.status || "").toLowerCase().includes("limit")
                              ? "warning"
                              : "neutral"
                          }
                          size="sm"
                          dot
                        >
                          {(job.status || "").toLowerCase() === "limit_reached" ? "Limit Reached" : job.status}
                        </Badge>
                      </td>
                      <td className="py-3.5 px-4 text-slate-400 max-w-[280px] truncate">
                        {job.reason || (isApplied ? "Application submitted successfully" : "Processed")}
                      </td>
                      <td className="py-3.5 px-4 text-right text-slate-400 num whitespace-nowrap">
                        {job.timestamp ? job.timestamp.slice(0, 16) : "—"}
                      </td>
                      <td className="py-3.5 px-4 text-center whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                        {job.job_url ? (
                          <a
                            href={job.job_url}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex p-1.5 rounded-lg text-slate-400 hover:text-emerald-400 hover:bg-slate-800 transition-colors"
                            title="Open Job Posting"
                          >
                            <ExternalLink className="h-3.5 w-3.5" />
                          </a>
                        ) : (
                          <span className="text-slate-600">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination Bar */}
        {filteredItems.length > pageSize && (
          <div className="flex items-center justify-between border-t border-slate-800/80 px-4 py-3 bg-slate-950/30">
            <span className="text-xs text-slate-400">
              Showing <span className="font-medium text-slate-200">{(safeCurrentPage - 1) * pageSize + 1}</span> to{" "}
              <span className="font-medium text-slate-200">
                {Math.min(safeCurrentPage * pageSize, filteredItems.length)}
              </span>{" "}
              of <span className="font-medium text-slate-200">{filteredItems.length}</span> jobs
            </span>

            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={safeCurrentPage <= 1}
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              >
                Previous
              </Button>
              <span className="text-xs font-medium text-slate-300 px-2">
                {safeCurrentPage} / {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={safeCurrentPage >= totalPages}
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </Card>

      {/* ─── Slide-Out Job Detail Drawer ─── */}
      {selectedJob && (
        <div className="fixed inset-0 z-50 flex justify-end bg-slate-950/70 backdrop-blur-xs">
          <div className="w-full max-w-md h-full bg-slate-900 border-l border-slate-800 p-6 flex flex-col space-y-5 animate-in slide-in-from-right duration-200 overflow-y-auto">
            <div className="flex items-start justify-between border-b border-slate-800 pb-4">
              <div>
                <Badge
                  variant={(selectedJob.status || "").toLowerCase() === "applied" ? "success" : "neutral"}
                  dot
                >
                  {selectedJob.status}
                </Badge>
                <h3 className="text-base font-bold text-slate-100 mt-2">{selectedJob.title}</h3>
                <p className="text-xs text-slate-400 mt-0.5">{selectedJob.company}</p>
              </div>
              <button
                onClick={() => setSelectedJob(null)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="space-y-4 text-xs">
              <div>
                <span className="text-slate-400 font-medium">Portal / Channel</span>
                <p className="text-slate-200 font-semibold capitalize mt-0.5">{selectedJob.platform || selectedJob.source || "Naukri"}</p>
              </div>

              {selectedJob.role && (
                <div>
                  <span className="text-slate-400 font-medium">Target Role Category</span>
                  <p className="text-slate-200 font-semibold mt-0.5">{selectedJob.role}</p>
                </div>
              )}

              <div>
                <span className="text-slate-400 font-medium">Timestamp</span>
                <p className="text-slate-200 font-mono mt-0.5">{selectedJob.timestamp || "—"}</p>
              </div>

              <div>
                <span className="text-slate-400 font-medium">Evaluation Feedback / Reason</span>
                <div className="mt-1 p-3 rounded-xl border border-slate-800 bg-slate-950/60 text-slate-300 leading-relaxed">
                  {selectedJob.reason || "Processed according to your career preferences."}
                </div>
              </div>

              {selectedJob.job_url && (
                <div className="pt-2">
                  <a
                    href={selectedJob.job_url}
                    target="_blank"
                    rel="noreferrer"
                    className="w-full flex items-center justify-center gap-2 p-2.5 rounded-xl border border-emerald-500/30 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 font-semibold transition-colors"
                  >
                    <ExternalLink className="h-4 w-4" />
                    Open Job on Portal
                  </a>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
