import React, { useEffect, useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  User,
  Briefcase,
  DollarSign,
  FileText,
  Upload,
  Download,
  CheckCircle2,
  AlertTriangle,
  Save,
  Check,
  FileCheck,
  MapPin,
  Clock,
  Sparkles,
} from "lucide-react";
import { toast } from "sonner";

import { apiGet, apiPost } from "@/lib/api";
import type { ProfileData } from "@/lib/types";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";

export default function MyProfile() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<"personal" | "roles" | "comp" | "resume">("personal");
  const [formData, setFormData] = useState<ProfileData>({});
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const { data: profile, isLoading } = useQuery({
    queryKey: ["user-profile-data"],
    queryFn: () => apiGet<ProfileData>("/api/profile"),
    staleTime: 10000,
  });

  useEffect(() => {
    if (profile) {
      setFormData(profile);
    }
  }, [profile]);

  const saveMutation = useMutation({
    mutationFn: (data: ProfileData) => apiPost("/api/profile", data),
    onSuccess: () => {
      toast.success("Career profile saved successfully!");
      queryClient.invalidateQueries({ queryKey: ["user-profile-data"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-overview"] });
    },
    onError: (err: any) => {
      toast.error(err.message || "Failed to save profile");
    },
  });

  const uploadResumeMutation = useMutation({
    mutationFn: async (file: File) => {
      const f = new FormData();
      f.append("file", file);
      return apiPost("/api/profile/resume", f);
    },
    onSuccess: (res: any) => {
      toast.success(res.message || "Resume uploaded and verified!");
      setSelectedFile(null);
      queryClient.invalidateQueries({ queryKey: ["user-profile-data"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-overview"] });
    },
    onError: (err: any) => {
      toast.error(err.message || "Resume upload failed");
    },
  });

  const handleChange = (field: keyof ProfileData, value: any) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  const handleArrayChange = (field: keyof ProfileData, value: string) => {
    const list = value.split(",").map((s) => s.trim()).filter(Boolean);
    setFormData((prev) => ({ ...prev, [field]: list }));
  };

  // Calculate profile completeness score
  const completeness = useMemo(() => {
    let score = 0;
    const checks = [
      Boolean(formData.full_name),
      Boolean(formData.email),
      Boolean(formData.phone),
      Boolean(formData.current_city),
      Boolean(formData.target_roles && formData.target_roles.length > 0),
      formData.total_experience_years !== null && formData.total_experience_years !== undefined,
      formData.notice_period_days !== undefined,
      Boolean(formData.resume_path || formData.resume_uploaded_at),
    ];
    checks.forEach((c) => { if (c) score += 12.5; });
    return Math.round(score);
  }, [formData]);

  const tabs = [
    { id: "personal" as const, label: "Personal & Contact", icon: User },
    { id: "roles" as const, label: "Target Roles & Skills", icon: Briefcase },
    { id: "comp" as const, label: "Compensation & Notice", icon: DollarSign },
    { id: "resume" as const, label: "Resume Document", icon: FileText },
  ];

  return (
    <div className="flex-1 p-5 sm:p-8 max-w-4xl mx-auto w-full space-y-7">
      <PageHeader
        title="Career Profile & Resume"
        description="Used by AI to match job postings and answer custom recruiter screening questionnaires."
        actions={
          <Button
            variant="primary"
            size="sm"
            leftIcon={<Save className="h-3.5 w-3.5" />}
            isLoading={saveMutation.isPending}
            onClick={() => saveMutation.mutate(formData)}
          >
            Save Profile
          </Button>
        }
      />

      {/* ─── Profile Strength Card ─── */}
      <Card className="p-4 sm:p-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-slate-100">Profile Readiness</span>
              <Badge variant={completeness >= 80 ? "success" : "warning"} size="sm">
                {completeness >= 80 ? "Ready for Automation" : "Needs Information"}
              </Badge>
            </div>
            <p className="text-xs text-slate-400">
              Complete your profile facts so the AI can automatically answer screening questions without hallucinating.
            </p>
          </div>

          <div className="flex items-center gap-3 shrink-0">
            <div className="text-right">
              <span className="num text-2xl font-bold text-slate-100">{completeness}%</span>
              <p className="text-[10px] text-slate-500 uppercase font-medium">Completed</p>
            </div>
            <div className="w-24 h-2.5 rounded-full bg-slate-800 overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-emerald-500 to-teal-400 rounded-full transition-all duration-300"
                style={{ width: `${completeness}%` }}
              />
            </div>
          </div>
        </div>
      </Card>

      {/* ─── Tab Segmented Control ─── */}
      <div className="flex items-center gap-1.5 border-b border-slate-800/80 pb-2 overflow-x-auto scrollbar-none">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
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

      {/* ─── Tab Content ─── */}
      <Card className="p-6">
        {/* TAB 1: Personal & Contact */}
        {activeTab === "personal" && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-slate-300">Full Name</label>
                <input
                  type="text"
                  value={formData.full_name || ""}
                  onChange={(e) => handleChange("full_name", e.target.value)}
                  placeholder="e.g. Rahul Sharma"
                  className="h-10 w-full rounded-xl border border-slate-800 bg-slate-950 px-3 text-xs text-slate-100 focus:border-emerald-500/50 focus:outline-none"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-slate-300">Email Address</label>
                <input
                  type="email"
                  value={formData.email || ""}
                  onChange={(e) => handleChange("email", e.target.value)}
                  placeholder="e.g. rahul@example.com"
                  className="h-10 w-full rounded-xl border border-slate-800 bg-slate-950 px-3 text-xs text-slate-100 focus:border-emerald-500/50 focus:outline-none"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-slate-300">Phone Number (with +91)</label>
                <input
                  type="text"
                  value={formData.phone || ""}
                  onChange={(e) => handleChange("phone", e.target.value)}
                  placeholder="+91 9876543210"
                  className="h-10 w-full rounded-xl border border-slate-800 bg-slate-950 px-3 text-xs text-slate-100 focus:border-emerald-500/50 focus:outline-none"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-slate-300">Current City</label>
                <input
                  type="text"
                  value={formData.current_city || ""}
                  onChange={(e) => handleChange("current_city", e.target.value)}
                  placeholder="e.g. Bengaluru, Karnataka"
                  className="h-10 w-full rounded-xl border border-slate-800 bg-slate-950 px-3 text-xs text-slate-100 focus:border-emerald-500/50 focus:outline-none"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-slate-300">Preferred Relocation Cities (comma separated)</label>
              <input
                type="text"
                value={(formData.relocate_cities || []).join(", ")}
                onChange={(e) => handleArrayChange("relocate_cities", e.target.value)}
                placeholder="e.g. Bengaluru, Hyderabad, Pune, Mumbai, Remote"
                className="h-10 w-full rounded-xl border border-slate-800 bg-slate-950 px-3 text-xs text-slate-100 focus:border-emerald-500/50 focus:outline-none"
              />
            </div>
          </div>
        )}

        {/* TAB 2: Target Roles & Skills */}
        {activeTab === "roles" && (
          <div className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-slate-300">Target Job Titles (comma separated)</label>
              <input
                type="text"
                value={(formData.target_roles || []).join(", ")}
                onChange={(e) => handleArrayChange("target_roles", e.target.value)}
                placeholder="e.g. Python Developer, Full Stack Engineer, Backend Engineer"
                className="h-10 w-full rounded-xl border border-slate-800 bg-slate-950 px-3 text-xs text-slate-100 focus:border-emerald-500/50 focus:outline-none"
              />
              <p className="text-[11px] text-slate-500">The automation engine will search for and filter jobs matching these roles.</p>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-slate-300">Primary Technical Skills (comma separated)</label>
              <input
                type="text"
                value={(formData.skills_primary || []).join(", ")}
                onChange={(e) => handleArrayChange("skills_primary", e.target.value)}
                placeholder="e.g. Python, FastAPI, Django, React, PostgreSQL, Docker, AWS"
                className="h-10 w-full rounded-xl border border-slate-800 bg-slate-950 px-3 text-xs text-slate-100 focus:border-emerald-500/50 focus:outline-none"
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-slate-300">Total Years of Experience</label>
                <input
                  type="number"
                  step="0.5"
                  value={formData.total_experience_years ?? ""}
                  onChange={(e) => handleChange("total_experience_years", e.target.value ? parseFloat(e.target.value) : null)}
                  placeholder="e.g. 3.5"
                  className="h-10 w-full rounded-xl border border-slate-800 bg-slate-950 px-3 text-xs text-slate-100 focus:border-emerald-500/50 focus:outline-none"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-slate-300">Current Employer (will also be blacklisted)</label>
                <input
                  type="text"
                  value={formData.current_employer || ""}
                  onChange={(e) => handleChange("current_employer", e.target.value)}
                  placeholder="e.g. Current Tech Company"
                  className="h-10 w-full rounded-xl border border-slate-800 bg-slate-950 px-3 text-xs text-slate-100 focus:border-emerald-500/50 focus:outline-none"
                />
              </div>
            </div>
          </div>
        )}

        {/* TAB 3: Compensation & Notice */}
        {activeTab === "comp" && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-slate-300">Current CTC (in ₹ Lakhs/year)</label>
                <input
                  type="number"
                  step="0.5"
                  value={formData.current_ctc_lpa ?? ""}
                  onChange={(e) => handleChange("current_ctc_lpa", e.target.value ? parseFloat(e.target.value) : null)}
                  placeholder="e.g. 12"
                  className="h-10 w-full rounded-xl border border-slate-800 bg-slate-950 px-3 text-xs text-slate-100 focus:border-emerald-500/50 focus:outline-none"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-slate-300">Expected CTC (in ₹ Lakhs/year)</label>
                <input
                  type="number"
                  step="0.5"
                  value={formData.expected_ctc_lpa ?? ""}
                  onChange={(e) => handleChange("expected_ctc_lpa", e.target.value ? parseFloat(e.target.value) : null)}
                  placeholder="e.g. 18"
                  className="h-10 w-full rounded-xl border border-slate-800 bg-slate-950 px-3 text-xs text-slate-100 focus:border-emerald-500/50 focus:outline-none"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-slate-300">Notice Period (in Days)</label>
                <input
                  type="number"
                  value={formData.notice_period_days ?? 30}
                  onChange={(e) => handleChange("notice_period_days", parseInt(e.target.value) || 0)}
                  placeholder="e.g. 30"
                  className="h-10 w-full rounded-xl border border-slate-800 bg-slate-950 px-3 text-xs text-slate-100 focus:border-emerald-500/50 focus:outline-none"
                />
              </div>

              <div className="flex items-center justify-between p-3 rounded-xl border border-slate-800 bg-slate-950/60 mt-auto">
                <div>
                  <span className="text-xs font-medium text-slate-200">Immediately Available?</span>
                  <p className="text-[10px] text-slate-400">Can join within 15 days or serving notice</p>
                </div>
                <button
                  type="button"
                  onClick={() => handleChange("immediately_available", !formData.immediately_available)}
                  className={`w-9 h-5 flex items-center rounded-full p-0.5 transition-colors cursor-pointer ${
                    formData.immediately_available ? "bg-emerald-500 justify-end" : "bg-slate-700 justify-start"
                  }`}
                >
                  <span className="w-4 h-4 bg-white rounded-full shadow-md" />
                </button>
              </div>
            </div>
          </div>
        )}

        {/* TAB 4: Resume Document */}
        {activeTab === "resume" && (
          <div className="space-y-5">
            {/* Active Resume Card */}
            <div className="p-4 rounded-xl border border-slate-800 bg-slate-950/60 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  <FileText className="h-5 w-5" />
                </div>
                <div>
                  <h4 className="text-xs sm:text-sm font-semibold text-slate-200">
                    {formData.resume_path ? "Active Resume Document (PDF)" : "No Resume Uploaded Yet"}
                  </h4>
                  <p className="text-[11px] text-slate-400">
                    {formData.resume_path ? "Verified · Max 5MB PDF format" : "Upload a PDF resume to enable auto-applying"}
                  </p>
                </div>
              </div>

              {formData.resume_path && (
                <div className="flex items-center gap-2">
                  <Badge variant="success" size="sm" dot>
                    Verified
                  </Badge>
                  <a
                    href="/api/profile/resume/download"
                    target="_blank"
                    rel="noreferrer"
                    className="p-2 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
                    title="Download active resume"
                  >
                    <Download className="h-4 w-4" />
                  </a>
                </div>
              )}
            </div>

            {/* Upload Drag/Drop Box */}
            <div className="border border-dashed border-slate-800 rounded-2xl p-6 text-center space-y-3 bg-slate-950/30">
              <div className="flex justify-center">
                <div className="h-10 w-10 rounded-xl bg-slate-800/80 text-slate-400 flex items-center justify-center">
                  <Upload className="h-5 w-5" />
                </div>
              </div>
              <div className="space-y-1">
                <p className="text-xs font-semibold text-slate-200">
                  Select a new resume PDF to replace
                </p>
                <p className="text-[11px] text-slate-400">
                  PDF format only, maximum file size 5 MB
                </p>
              </div>

              <input
                type="file"
                accept=".pdf,application/pdf"
                onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                className="text-xs text-slate-400 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-slate-800 file:text-slate-200 hover:file:bg-slate-700 cursor-pointer"
              />

              {selectedFile && (
                <div className="pt-2">
                  <Button
                    size="sm"
                    variant="primary"
                    isLoading={uploadResumeMutation.isPending}
                    onClick={() => uploadResumeMutation.mutate(selectedFile)}
                  >
                    Upload {selectedFile.name}
                  </Button>
                </div>
              )}
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
