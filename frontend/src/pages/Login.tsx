import React, { useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import {
  Sparkles,
  Lock,
  User,
  ArrowRight,
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
  Briefcase,
  ChevronLeft,
} from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/lib/authContext";
import { Button } from "@/components/ui/Button";

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login } = useAuth();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    const result = await login(username, password);
    setLoading(false);

    if (result.success) {
      toast.success("Welcome back! Your career workspace is ready.");
      const from = (location.state as any)?.from?.pathname || "/dashboard";
      navigate(from, { replace: true });
    } else {
      setError(result.error || "Authentication failed. Please verify your credentials.");
    }
  };

  return (
    <div className="min-h-screen w-full flex bg-slate-950 text-slate-100">
      {/* ─── Left Column: Product Story (Desktop >= lg) ─── */}
      <div className="hidden lg:flex lg:w-1/2 flex-col justify-between p-12 border-r border-slate-800/80 bg-gradient-to-br from-slate-900 via-slate-950 to-slate-900 relative overflow-hidden">
        <div className="absolute top-1/4 left-1/4 -translate-x-1/2 -translate-y-1/2 h-[350px] w-[450px] bg-emerald-500/10 blur-3xl pointer-events-none rounded-full" />

        {/* Top Brand */}
        <Link to="/landing" className="flex items-center gap-2.5 z-10">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-tr from-emerald-600 to-teal-400 text-slate-950 font-bold shadow-md shadow-emerald-500/20">
            <Sparkles className="h-5 w-5" />
          </div>
          <span className="text-base font-bold tracking-tight text-slate-100 flex items-center gap-2">
            ApplyPilot
            <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              AI
            </span>
          </span>
        </Link>

        {/* Value Proposition */}
        <div className="max-w-md z-10 space-y-6">
          <h2 className="text-3xl font-extrabold tracking-tight text-slate-100 leading-snug">
            Automate the repetitive job search. Spend your time on the right interviews.
          </h2>

          <div className="space-y-4">
            <div className="flex items-start gap-3.5">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 shrink-0 mt-0.5">
                <CheckCircle2 className="h-4 w-4" />
              </div>
              <div>
                <p className="text-xs font-semibold text-slate-200">AI-Powered Screening</p>
                <p className="text-xs text-slate-400 mt-0.5">Answers screening questionnaires using verified facts from your uploaded resume.</p>
              </div>
            </div>

            <div className="flex items-start gap-3.5">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 shrink-0 mt-0.5">
                <CheckCircle2 className="h-4 w-4" />
              </div>
              <div>
                <p className="text-xs font-semibold text-slate-200">Dual-Channel Automation</p>
                <p className="text-xs text-slate-400 mt-0.5">Simultaneously monitors and applies across Naukri.com and LinkedIn Easy Apply.</p>
              </div>
            </div>

            <div className="flex items-start gap-3.5">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 shrink-0 mt-0.5">
                <CheckCircle2 className="h-4 w-4" />
              </div>
              <div>
                <p className="text-xs font-semibold text-slate-200">Human-Speed Protection</p>
                <p className="text-xs text-slate-400 mt-0.5">Natural jitter delays and daily application caps keep your accounts 100% safe.</p>
              </div>
            </div>
          </div>
        </div>

        {/* Reassurance Footer */}
        <div className="z-10 flex items-center gap-2 text-xs text-slate-400 border-t border-slate-800/80 pt-4">
          <ShieldCheck className="h-4 w-4 text-emerald-400 shrink-0" />
          <span>Encrypted credential storage · Zero tracking · Private deployment</span>
        </div>
      </div>

      {/* ─── Right Column: Authentication Card ─── */}
      <div className="flex-1 flex flex-col justify-center items-center p-6 sm:p-12 relative">
        <Link
          to="/landing"
          className="absolute top-6 left-6 flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
          Back to overview
        </Link>

        <div className="w-full max-w-sm space-y-6">
          {/* Card Header */}
          <div className="space-y-1 text-center sm:text-left">
            <h1 className="text-2xl font-bold tracking-tight text-slate-100">
              Sign in to your workspace
            </h1>
            <p className="text-xs text-slate-400">
              Enter your credentials to access your automation controls.
            </p>
          </div>

          {/* Error Banner */}
          {error && (
            <div className="flex items-start gap-2.5 rounded-xl border border-rose-500/30 bg-rose-500/10 p-3.5 text-xs text-rose-300">
              <AlertCircle className="h-4 w-4 shrink-0 text-rose-400 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {/* Login Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-slate-300">Username or ID</label>
              <div className="relative">
                <User className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500 pointer-events-none" />
                <input
                  type="text"
                  required
                  autoComplete="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="Enter your username"
                  className="h-10 w-full rounded-xl border border-slate-800 bg-slate-900/80 pl-10 pr-3.5 text-xs text-slate-100 placeholder:text-slate-500 focus:border-emerald-500/60 focus:outline-none focus:ring-1 focus:ring-emerald-500/30 transition-all"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <label className="text-xs font-medium text-slate-300">Password</label>
              </div>
              <div className="relative">
                <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500 pointer-events-none" />
                <input
                  type="password"
                  required
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="h-10 w-full rounded-xl border border-slate-800 bg-slate-900/80 pl-10 pr-3.5 text-xs text-slate-100 placeholder:text-slate-500 focus:border-emerald-500/60 focus:outline-none focus:ring-1 focus:ring-emerald-500/30 transition-all"
                />
              </div>
            </div>

            <Button
              type="submit"
              variant="primary"
              size="md"
              isLoading={loading}
              className="w-full mt-2"
              rightIcon={<ArrowRight className="h-3.5 w-3.5" />}
            >
              Sign In to Workspace
            </Button>
          </form>
        </div>
      </div>
    </div>
  );
}
