import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Settings as SettingsIcon,
  Sliders,
  FileSpreadsheet,
  Key,
  CheckCircle2,
  AlertTriangle,
  Play,
  Plus,
  Trash2,
  Save,
  RotateCw,
  Sparkles,
  ExternalLink,
  ShieldAlert,
  ChevronDown,
} from "lucide-react";
import { toast } from "sonner";

import { apiGet, apiPost, apiDelete } from "@/lib/api";
import { useAuth } from "@/lib/authContext";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { Modal } from "@/components/ui/Modal";

interface UserSettings {
  username: string;
  delay_seconds: number;
  stream_fps?: number;
  sheet_config: {
    sheet_url?: string;
    webhook_url?: string;
  };
}

interface MaskedKey {
  id: string;
  provider: "gemini" | "groq";
  key_masked: string;
  enabled: boolean;
  total_calls: number;
  failed_calls: number;
}

export default function Settings() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const isAdmin = user?.role === "admin";

  const [activeTab, setActiveTab] = useState<"automation" | "integrations" | "ai" | "danger">("automation");

  // Form states
  const [delayInput, setDelayInput] = useState<number>(3);
  const [streamFpsInput, setStreamFpsInput] = useState<number>(15);
  const [sheetUrl, setSheetUrl] = useState<string>("");
  const [webhookUrl, setWebhookUrl] = useState<string>("");
  const [showAdvancedSheets, setShowAdvancedSheets] = useState(false);

  // Key modal state
  const [keyModalOpen, setKeyModalOpen] = useState(false);
  const [newKeyProvider, setNewKeyProvider] = useState<"gemini" | "groq">("gemini");
  const [newKeyValue, setNewKeyValue] = useState<string>("");

  // Fetch settings
  const { data: settings, isLoading: settingsLoading } = useQuery({
    queryKey: ["user-settings"],
    queryFn: async () => {
      const res = await apiGet<UserSettings>("/api/user/settings");
      if (res) {
        setDelayInput(res.delay_seconds || 3);
        setStreamFpsInput(res.stream_fps || 15);
        setSheetUrl(res.sheet_config?.sheet_url || "");
        setWebhookUrl(res.sheet_config?.webhook_url || "");
      }
      return res;
    },
    staleTime: 30000,
  });

  // Fetch AI keys
  const { data: keysData } = useQuery({
    queryKey: ["ai-keys"],
    queryFn: () => apiGet<{ keys: MaskedKey[]; total_active: number }>("/api/keys"),
    enabled: isAdmin,
    staleTime: 30000,
  });

  // Save delay and synchronize with active engines
  const saveDelayMutation = useMutation({
    mutationFn: async (delay: number) => {
      await apiPost("/api/user/settings", { delay_seconds: Math.max(2, delay) });
      try {
        await apiPost("/api/bot/naukri/pacing", { pace_seconds: delay });
        await apiPost("/api/bot/linkedin/pacing", { pace_seconds: delay });
      } catch (e) {
        // Ignored if engine not started
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["user-settings"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-overview"] });
      toast.success("Automation continuous pacing delay saved & synchronized successfully!");
    },
    onError: (err: any) => toast.error(err.message || "Failed to update delay"),
  });

  // Save stream FPS
  const saveFpsMutation = useMutation({
    mutationFn: (fps: number) =>
      apiPost("/api/user/settings", { stream_fps: fps }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["user-settings"] });
      sessionStorage.setItem("preferred_stream_fps", String(streamFpsInput));
      toast.success(`Remote stream framerate set to ${streamFpsInput} FPS!`);
    },
    onError: (err: any) => toast.error(err.message || "Failed to update stream framerate"),
  });

  // Save sheets
  const saveSheetMutation = useMutation({
    mutationFn: () =>
      apiPost("/api/sheet", { sheet_url: sheetUrl, webhook_url: webhookUrl }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["user-settings"] });
      toast.success("Google Sheets configuration saved!");
    },
    onError: (err: any) => toast.error(err.message || "Failed to save sheet settings"),
  });

  // Test sheet row
  const testSheetMutation = useMutation({
    mutationFn: () => apiPost("/api/sheet/test"),
    onSuccess: () => toast.success("Test row sent! Check your Google Sheet."),
    onError: (err: any) => toast.error(err.message || "Test failed. Check webhook URL."),
  });

  // Add AI key
  const addKeyMutation = useMutation({
    mutationFn: () =>
      apiPost("/api/keys", { provider: newKeyProvider, api_key: newKeyValue }),
    onSuccess: () => {
      toast.success("AI API key added successfully!");
      setKeyModalOpen(false);
      setNewKeyValue("");
      queryClient.invalidateQueries({ queryKey: ["ai-keys"] });
    },
    onError: (err: any) => toast.error(err.message || "Failed to add API key"),
  });

  const deleteKeyMutation = useMutation({
    mutationFn: (keyId: string) => apiDelete(`/api/keys/${keyId}`),
    onSuccess: () => {
      toast.success("API key deleted.");
      queryClient.invalidateQueries({ queryKey: ["ai-keys"] });
    },
    onError: (err: any) => toast.error(err.message || "Failed to delete key"),
  });

  const isSheetsConnected = Boolean(sheetUrl || webhookUrl);

  const tabs = [
    { id: "automation" as const, label: "Automation & Safety", icon: Sliders },
    { id: "integrations" as const, label: "Integrations", icon: FileSpreadsheet },
    ...(isAdmin ? [{ id: "ai" as const, label: "AI Screening Keys", icon: Key }] : []),
    { id: "danger" as const, label: "Danger Zone", icon: ShieldAlert },
  ];

  return (
    <div className="flex-1 p-5 sm:p-8 max-w-4xl mx-auto w-full space-y-7">
      <PageHeader
        title="Workspace Preferences"
        description="Fine-tune automation pacing, external spreadsheet integrations, and AI providers."
      />

      {/* ─── Navigation Tabs ─── */}
      <div className="flex items-center gap-1.5 border-b border-slate-800/80 pb-2 overflow-x-auto scrollbar-none">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-medium transition-all shrink-0 cursor-pointer ${
                isActive
                  ? "bg-slate-800 text-slate-100 shadow-xs border border-slate-700/80"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
              }`}
            >
              <Icon className={`h-3.5 w-3.5 ${isActive ? "text-emerald-400" : "text-slate-400"}`} />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* ─── TAB 1: Automation Safety & Pacing ─── */}
      {activeTab === "automation" && (
        <Card className="p-6 space-y-6">
          <div className="space-y-1">
            <h3 className="text-sm font-semibold text-slate-100">Anti-Detection Pacing</h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              Controls the minimum delay between automated form interactions. Natural pauses prevent account flags.
            </p>
          </div>

          <div className="p-4 rounded-xl border border-slate-800 bg-slate-950/60 space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-xs font-medium text-slate-200">Application Pacing Delay</span>
                <p className="text-[11px] text-slate-400">Enforces randomized human-like jitter between clicks</p>
              </div>
              <div className="flex items-center gap-2">
                <Badge variant={delayInput === 3 ? "success" : "neutral"} size="sm">
                  {delayInput === 3 ? "Recommended (Balanced)" : `${delayInput}s Delay`}
                </Badge>
                <span className="num font-bold text-slate-100 text-sm">{delayInput}s</span>
              </div>
            </div>

            <input
              type="range"
              min="2"
              max="15"
              step="1"
              value={delayInput}
              onChange={(e) => setDelayInput(parseInt(e.target.value))}
              className="w-full accent-emerald-500 cursor-pointer"
            />
            <div className="flex justify-between text-[10px] text-slate-500 font-mono">
              <span>2s (Fastest · Min Safety)</span>
              <span>3s (Balanced)</span>
              <span>15s (Ultra-Safe)</span>
            </div>
          </div>

          <div className="flex justify-end pt-3 border-t border-slate-800">
            <Button
              variant="primary"
              size="sm"
              leftIcon={<Save className="h-3.5 w-3.5" />}
              isLoading={saveDelayMutation.isPending}
              onClick={() => saveDelayMutation.mutate(delayInput)}
            >
              Save Pacing Delay
            </Button>
          </div>

          {/* ─── Remote Browser Screencast Framerate (Stream FPS) ─── */}
          <div className="pt-6 border-t border-slate-800/80 space-y-4">
            <div className="space-y-1">
              <h3 className="text-sm font-semibold text-slate-100">Live Screencast Stream Framerate</h3>
              <p className="text-xs text-slate-400 leading-relaxed">
                Configure target frames per second (FPS) for live remote browser monitoring and screencast inspection. Lower FPS conserves bandwidth; higher FPS delivers fluid real-time video.
              </p>
            </div>

            <div className="p-4 rounded-xl border border-slate-800 bg-slate-950/60 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-slate-200">Stream Delivery Target</span>
                    <Badge variant={streamFpsInput === 15 ? "neutral" : "success"} size="sm">
                      {streamFpsInput === 15 ? "Default · 15 FPS" : `${streamFpsInput} FPS`}
                    </Badge>
                  </div>
                  <p className="text-[11px] text-slate-400 mt-0.5">
                    Throttles WebSocket video frames sent from headless Chromium
                  </p>
                </div>
                <span className="num font-bold text-emerald-400 text-sm">{streamFpsInput} FPS</span>
              </div>

              <div className="space-y-3">
                <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
                  <div className="relative flex-1">
                    <select
                      value={streamFpsInput}
                      onChange={(e) => setStreamFpsInput(parseInt(e.target.value))}
                      className="w-full appearance-none rounded-xl border border-slate-800 bg-slate-900/90 px-3.5 py-2.5 text-xs font-medium text-slate-100 hover:border-slate-700 focus:border-emerald-500/50 focus:outline-none transition-colors cursor-pointer"
                    >
                      <option value={5}>5 FPS — Ultra Low Bandwidth (Eco · ~120 KB/s)</option>
                      <option value={10}>10 FPS — Efficient Performance (~250 KB/s)</option>
                      <option value={15}>15 FPS — Balanced Standard (Default · ~400 KB/s)</option>
                      <option value={20}>20 FPS — Fluid Performance (~550 KB/s)</option>
                      <option value={24}>24 FPS — Cinematic Motion (24p · ~650 KB/s)</option>
                      <option value={30}>30 FPS — High Refresh Smooth (~900 KB/s)</option>
                      <option value={60}>60 FPS — Maximum Realtime (~1.8 MB/s)</option>
                    </select>
                    <ChevronDown className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400" />
                  </div>

                  <Button
                    variant="primary"
                    size="sm"
                    leftIcon={<Save className="h-3.5 w-3.5" />}
                    isLoading={saveFpsMutation.isPending}
                    onClick={() => saveFpsMutation.mutate(streamFpsInput)}
                  >
                    Save Framerate
                  </Button>
                </div>

                {/* Quick Presets */}
                <div className="flex items-center gap-2 flex-wrap pt-1">
                  <span className="text-slate-500 text-[10px] uppercase font-mono">Quick Presets:</span>
                  {[5, 10, 15, 24, 30, 60].map((val) => (
                    <button
                      key={val}
                      type="button"
                      onClick={() => {
                        setStreamFpsInput(val);
                        saveFpsMutation.mutate(val);
                      }}
                      className={`px-2.5 py-1 rounded-lg font-mono text-[11px] border transition-colors cursor-pointer ${
                        streamFpsInput === val
                          ? "bg-emerald-500/15 border-emerald-500/40 text-emerald-400 font-bold"
                          : "bg-slate-900/60 border-slate-800 text-slate-400 hover:text-slate-200 hover:border-slate-700"
                      }`}
                    >
                      {val} FPS{val === 15 ? " (Def)" : ""}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* ─── TAB 2: Integrations (Google Sheets Marketplace Card) ─── */}
      {activeTab === "integrations" && (
        <div className="space-y-4">
          <Card className="p-6 space-y-5">
            <div className="flex items-start justify-between pb-4 border-b border-slate-800/80">
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  <FileSpreadsheet className="h-6 w-6" />
                </div>
                <div>
                  <h3 className="text-base font-semibold text-slate-100">Google Sheets Live Journal</h3>
                  <p className="text-xs text-slate-400">Automatically appends every applied job to your personal Google Sheet</p>
                </div>
              </div>

              <Badge variant={isSheetsConnected ? "success" : "neutral"} dot>
                {isSheetsConnected ? "Connected" : "Not Configured"}
              </Badge>
            </div>

            <div className="space-y-3">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-slate-300">Google Sheet URL</label>
                <input
                  type="url"
                  value={sheetUrl}
                  onChange={(e) => setSheetUrl(e.target.value)}
                  placeholder="https://docs.google.com/spreadsheets/d/your-sheet-id/edit"
                  className="h-10 w-full rounded-xl border border-slate-800 bg-slate-950 px-3 text-xs text-slate-100 placeholder:text-slate-600 focus:border-emerald-500/50 focus:outline-none"
                />
              </div>

              {/* Advanced Webhook Toggle */}
              <div>
                <button
                  type="button"
                  onClick={() => setShowAdvancedSheets(!showAdvancedSheets)}
                  className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors"
                >
                  <ChevronDown className={`h-3.5 w-3.5 transition-transform ${showAdvancedSheets ? "rotate-180" : ""}`} />
                  <span>Advanced Apps Script Webhook URL</span>
                </button>

                {showAdvancedSheets && (
                  <div className="mt-2 space-y-1.5">
                    <input
                      type="url"
                      value={webhookUrl}
                      onChange={(e) => setWebhookUrl(e.target.value)}
                      placeholder="https://script.google.com/macros/s/AKfycb.../exec"
                      className="h-10 w-full rounded-xl border border-slate-800 bg-slate-950 px-3 text-xs text-slate-100 placeholder:text-slate-600 focus:border-emerald-500/50 focus:outline-none"
                    />
                    <p className="text-[11px] text-slate-500">
                      The web app webhook deployed in Google Apps Script (described in documentation).
                    </p>
                  </div>
                )}
              </div>
            </div>

            <div className="flex items-center justify-between pt-4 border-t border-slate-800">
              {isSheetsConnected ? (
                <Button
                  variant="outline"
                  size="sm"
                  leftIcon={<Play className="h-3 w-3 fill-current" />}
                  isLoading={testSheetMutation.isPending}
                  onClick={() => testSheetMutation.mutate()}
                >
                  Send Test Row
                </Button>
              ) : <div />}

              <Button
                variant="primary"
                size="sm"
                leftIcon={<Save className="h-3.5 w-3.5" />}
                isLoading={saveSheetMutation.isPending}
                onClick={() => saveSheetMutation.mutate()}
              >
                Save Integration
              </Button>
            </div>
          </Card>
        </div>
      )}

      {/* ─── TAB 3: AI Screening Keys (Admin) ─── */}
      {activeTab === "ai" && isAdmin && (
        <Card className="p-6 space-y-5">
          <div className="flex items-center justify-between pb-4 border-b border-slate-800/80">
            <div>
              <h3 className="text-sm font-semibold text-slate-100">AI Screening Provider Keys</h3>
              <p className="text-xs text-slate-400">Manages API keys for Gemini & Groq question answering</p>
            </div>
            <Button
              variant="primary"
              size="sm"
              leftIcon={<Plus className="h-3.5 w-3.5" />}
              onClick={() => setKeyModalOpen(true)}
            >
              Add API Key
            </Button>
          </div>

          <div className="space-y-2.5">
            {(!keysData?.keys || keysData.keys.length === 0) ? (
              <p className="py-6 text-center text-xs text-slate-500">
                No custom AI keys saved. The platform uses default environment keys.
              </p>
            ) : (
              keysData.keys.map((k) => (
                <div
                  key={k.id}
                  className="p-3 rounded-xl border border-slate-800 bg-slate-950/60 flex items-center justify-between"
                >
                  <div className="flex items-center gap-2.5">
                    <Badge variant="purple" size="sm">
                      {k.provider.toUpperCase()}
                    </Badge>
                    <span className="font-mono text-xs text-slate-200">{k.key_masked}</span>
                  </div>

                  <div className="flex items-center gap-3">
                    <span className="text-[11px] text-slate-400 num">
                      {k.total_calls} calls
                    </span>
                    <button
                      onClick={() => deleteKeyMutation.mutate(k.id)}
                      className="p-1 rounded text-slate-500 hover:text-rose-400 transition-colors"
                      title="Delete Key"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </Card>
      )}

      {/* ─── TAB 4: Danger Zone ─── */}
      {activeTab === "danger" && (
        <Card className="p-6 border-rose-500/20 bg-rose-500/5 space-y-4">
          <div className="space-y-1">
            <h3 className="text-sm font-semibold text-rose-300">Danger Zone</h3>
            <p className="text-xs text-slate-400">Destructive actions that cannot be undone.</p>
          </div>

          <div className="p-4 rounded-xl border border-rose-500/20 bg-slate-950/40 flex items-center justify-between">
            <div>
              <span className="text-xs font-semibold text-slate-200">Reset Application Logs</span>
              <p className="text-[11px] text-slate-400">Clears all historical job entries from your local audit feed</p>
            </div>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => {
                if (window.confirm("Are you sure? This will clear all records.")) {
                  apiPost("/api/activity/clear").then(() => toast.success("Activity cleared"));
                }
              }}
            >
              Clear Logs
            </Button>
          </div>
        </Card>
      )}

      {/* ─── Add Key Modal ─── */}
      <Modal
        isOpen={keyModalOpen}
        onClose={() => setKeyModalOpen(false)}
        title="Add AI Provider API Key"
        description="Provide a free API key from Google AI Studio (Gemini) or Groq Console."
        size="md"
      >
        <div className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-slate-300">Provider</label>
            <select
              value={newKeyProvider}
              onChange={(e) => setNewKeyProvider(e.target.value as any)}
              className="h-10 w-full rounded-xl border border-slate-800 bg-slate-950 px-3 text-xs text-slate-200 focus:outline-none"
            >
              <option value="gemini">Google Gemini (Recommended · Free)</option>
              <option value="groq">Groq Llama 3 (Fastest)</option>
            </select>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-slate-300">API Key String</label>
            <input
              type="password"
              value={newKeyValue}
              onChange={(e) => setNewKeyValue(e.target.value)}
              placeholder="AIzaSy... or gsk_..."
              className="h-10 w-full rounded-xl border border-slate-800 bg-slate-950 px-3 text-xs text-slate-100 placeholder:text-slate-600 focus:outline-none"
            />
          </div>

          <div className="flex justify-end gap-2 pt-2 border-t border-slate-800">
            <Button variant="ghost" size="sm" onClick={() => setKeyModalOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              isLoading={addKeyMutation.isPending}
              disabled={!newKeyValue.trim()}
              onClick={() => addKeyMutation.mutate()}
            >
              Save Key
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
