import React, { useState, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  KeyRound,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  MonitorPlay,
  RotateCw,
  Trash2,
  Upload,
  Download,
  ShieldCheck,
  ExternalLink,
  Lock,
  ArrowRight,
} from "lucide-react";
import { toast } from "sonner";

import { apiGet, apiPost, apiDelete } from "@/lib/api";
import type { SessionInfo } from "@/lib/types";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { Modal } from "@/components/ui/Modal";
import ScreencastCanvas from "@/components/screencast/ScreencastCanvas";

export default function Sessions() {
  const queryClient = useQueryClient();

  const [modalOpen, setModalOpen] = useState(false);
  const [modalSite, setModalSite] = useState<"naukri" | "linkedin">("naukri");
  const [modalMode, setModalMode] = useState<"login" | "live_check">("login");

  // Import JSON session modal
  const [importModalOpen, setImportModalOpen] = useState(false);
  const [importSite, setImportSite] = useState<"naukri" | "linkedin">("linkedin");
  const [importJsonText, setImportJsonText] = useState("");

  const { data: sessions, refetch } = useQuery({
    queryKey: ["sessions-status"],
    queryFn: () => apiGet<{ naukri: SessionInfo; linkedin: SessionInfo }>("/api/sessions"),
    refetchInterval: () => (!modalOpen && document.visibilityState === "visible" ? 15000 : false),
    staleTime: 10000,
  });

  const checkMutation = useMutation({
    mutationFn: (site: string) => apiPost<SessionInfo>(`/api/sessions/${site}/check`),
    onSuccess: (res, site) => {
      toast.success(`${site.toUpperCase()} session verified: ${res.status}`);
      refetch();
    },
    onError: () => toast.error("Verification failed"),
  });

  const removeMutation = useMutation({
    mutationFn: (site: string) => apiDelete(`/api/sessions/${site}`),
    onSuccess: (_, site) => {
      toast.success(`${site.toUpperCase()} session disconnected.`);
      refetch();
    },
    onError: () => toast.error("Failed to disconnect session"),
  });

  const importMutation = useMutation({
    mutationFn: async () => {
      let parsed;
      try {
        parsed = JSON.parse(importJsonText);
      } catch {
        throw new Error("Invalid JSON. Please paste a valid Playwright storage_state JSON.");
      }
      return apiPost(`/api/sessions/${importSite}/import`, parsed);
    },
    onSuccess: (res: any) => {
      toast.success(res.message || "Session state imported successfully!");
      setImportModalOpen(false);
      setImportJsonText("");
      refetch();
    },
    onError: (err: any) => {
      toast.error(err.message || "Session import failed");
    },
  });

  const handleExport = async (site: "naukri" | "linkedin") => {
    try {
      const data = await apiGet<any>(`/api/sessions/${site}/export`);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${site}_session_backup.json`;
      link.click();
      URL.revokeObjectURL(url);
      toast.success(`Exported ${site.toUpperCase()} encrypted session backup.`);
    } catch (err: any) {
      toast.error(err.message || "Failed to export session");
    }
  };

  const platforms = [
    {
      id: "naukri" as const,
      name: "Naukri.com",
      subtitle: "India's #1 Job Portal",
      data: sessions?.naukri,
      tag: "Direct Apply & Screening",
      accent: "text-blue-400 bg-blue-500/10 border-blue-500/20",
    },
    {
      id: "linkedin" as const,
      name: "LinkedIn",
      subtitle: "Easy Apply Automation",
      data: sessions?.linkedin,
      tag: "Professional Network",
      accent: "text-sky-400 bg-sky-500/10 border-sky-500/20",
    },
  ];

  return (
    <div className="flex-1 p-5 sm:p-8 max-w-7xl mx-auto w-full space-y-7">
      <PageHeader
        title="Connected Accounts"
        description="Securely manage authentication state and cookies for autonomous job portal applications."
      />

      {/* ─── Reassurance Security Banner ─── */}
      <div className="p-4.5 rounded-2xl border border-slate-800 bg-slate-900/60 flex items-start gap-3.5">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 shrink-0 mt-0.5">
          <ShieldCheck className="h-5 w-5" />
        </div>
        <div className="space-y-0.5">
          <h4 className="text-xs sm:text-sm font-semibold text-slate-200">
            Encrypted Session Vault
          </h4>
          <p className="text-xs text-slate-400 leading-relaxed max-w-3xl">
            Your login cookies are symmetrically encrypted with Fernet (AES-256) before storage. Plaintext passwords are never saved. On cloud restarts, your sessions are restored automatically without re-login.
          </p>
        </div>
      </div>

      {/* ─── Platform Connection Cards ─── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {platforms.map((p) => {
          const isConnected = p.data?.valid;
          const isPresent = p.data?.present;

          return (
            <Card key={p.id} className="flex flex-col justify-between space-y-5">
              <div>
                {/* Header */}
                <div className="flex items-start justify-between pb-4 border-b border-slate-800/80">
                  <div className="flex items-center gap-3">
                    <div className={`flex h-11 w-11 items-center justify-center rounded-2xl font-bold text-base border ${p.accent}`}>
                      {p.id === "naukri" ? "N" : "In"}
                    </div>
                    <div>
                      <h3 className="text-base font-semibold text-slate-100">{p.name}</h3>
                      <p className="text-xs text-slate-400">{p.subtitle}</p>
                    </div>
                  </div>

                  <Badge
                    variant={isConnected ? "success" : isPresent ? "warning" : "neutral"}
                    size="md"
                    dot
                  >
                    {isConnected ? "Connected" : isPresent ? "Needs Verification" : "Not Connected"}
                  </Badge>
                </div>

                {/* Session Telemetry */}
                <div className="mt-4 space-y-2 text-xs">
                  <div className="flex items-center justify-between p-2.5 rounded-xl bg-slate-950/40 border border-slate-800/60">
                    <span className="text-slate-400">Connection Status</span>
                    <span className="font-semibold text-slate-200">{p.data?.status || "Checking..."}</span>
                  </div>
                  <div className="flex items-center justify-between p-2.5 rounded-xl bg-slate-950/40 border border-slate-800/60">
                    <span className="text-slate-400">Last Verified</span>
                    <span className="text-slate-300 font-mono text-[11px]">
                      {p.data?.last_verified ? p.data.last_verified.slice(0, 19).replace("T", " ") : "Never"}
                    </span>
                  </div>
                  {p.data?.message && (
                    <p className="text-[11px] text-slate-500 pt-1 px-1">{p.data.message}</p>
                  )}
                </div>
              </div>

              {/* Action Buttons */}
              <div className="space-y-2 pt-2 border-t border-slate-800/60">
                <div className="flex items-center gap-2">
                  <Button
                    variant="primary"
                    size="sm"
                    className="flex-1"
                    leftIcon={<MonitorPlay className="h-3.5 w-3.5" />}
                    onClick={() => {
                      setModalSite(p.id);
                      setModalMode("login");
                      setModalOpen(true);
                    }}
                  >
                    {isConnected ? "Reconnect Session" : "Connect via Browser"}
                  </Button>

                  <Button
                    variant="outline"
                    size="sm"
                    leftIcon={<RotateCw className="h-3.5 w-3.5" />}
                    isLoading={checkMutation.isPending}
                    onClick={() => checkMutation.mutate(p.id)}
                  >
                    Verify
                  </Button>
                </div>

                <div className="flex items-center gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    className="flex-1"
                    leftIcon={<Upload className="h-3.5 w-3.5" />}
                    onClick={() => {
                      setImportSite(p.id);
                      setImportModalOpen(true);
                    }}
                  >
                    Import Cookie JSON
                  </Button>

                  {isPresent && (
                    <Button
                      variant="ghost"
                      size="sm"
                      title="Export Encrypted Session Backup"
                      onClick={() => handleExport(p.id)}
                    >
                      <Download className="h-3.5 w-3.5" />
                    </Button>
                  )}

                  {isPresent && (
                    <Button
                      variant="destructive"
                      size="sm"
                      title="Disconnect Account"
                      isLoading={removeMutation.isPending}
                      onClick={() => {
                        if (window.confirm(`Disconnect ${p.name}? Your stored cookies will be cleared.`)) {
                          removeMutation.mutate(p.id);
                        }
                      }}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  )}
                </div>
              </div>
            </Card>
          );
        })}
      </div>

      {/* ─── Browser Login Screencast Modal ─── */}
      <Modal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        title={`Authenticate ${modalSite === "naukri" ? "Naukri" : "LinkedIn"}`}
        description="Log into your account in the live browser. Once logged in, your session cookies will be saved automatically."
        size="xl"
      >
        <div className="h-[520px] flex flex-col">
          <ScreencastCanvas
            site={modalSite}
            mode={modalMode}
            onClose={() => {
              setModalOpen(false);
              refetch();
            }}
            onSaved={() => {
              toast.success("Login session verified and encrypted!");
              setModalOpen(false);
              refetch();
            }}
          />
        </div>
      </Modal>

      {/* ─── Import Session Modal ─── */}
      <Modal
        isOpen={importModalOpen}
        onClose={() => setImportModalOpen(false)}
        title={`Import Residential Cookies · ${importSite === "naukri" ? "Naukri" : "LinkedIn"}`}
        description="If cloud datacenter IPs are blocked by security checkpoints, paste your desktop session JSON here."
        size="md"
      >
        <div className="space-y-4">
          <p className="text-xs text-slate-400">
            Paste your Playwright <code className="text-emerald-400">storage_state.json</code> content below:
          </p>
          <textarea
            rows={8}
            value={importJsonText}
            onChange={(e) => setImportJsonText(e.target.value)}
            placeholder='{"cookies": [...], "origins": [...]}'
            className="w-full rounded-xl border border-slate-800 bg-slate-950 p-3 text-xs font-mono text-slate-200 placeholder:text-slate-600 focus:border-emerald-500/50 focus:outline-none"
          />
          <div className="flex justify-end gap-2 pt-2 border-t border-slate-800">
            <Button variant="ghost" size="sm" onClick={() => setImportModalOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              isLoading={importMutation.isPending}
              onClick={() => importMutation.mutate()}
            >
              Save & Verify Session
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
