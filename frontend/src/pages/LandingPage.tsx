import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Sparkles,
  ArrowRight,
  ShieldCheck,
  CheckCircle2,
  Clock,
  Layers,
  FileSpreadsheet,
  MonitorPlay,
  Briefcase,
  ChevronDown,
  HelpCircle,
  ExternalLink,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";

export default function LandingPage() {
  const navigate = useNavigate();
  const [openFaq, setOpenFaq] = useState<number | null>(0);

  const faqs = [
    {
      q: "Will my current employer find out that I am applying?",
      a: "Never. ApplyPilot includes an active Employer Blacklist filter. You can enter your current company name (and subsidiary names) in settings, and the engine will immediately skip any openings from those employers.",
    },
    {
      q: "Is automated job applying safe from platform account bans?",
      a: "Yes. ApplyPilot enforces anti-bot human pacing (minimum 2.0 to 5.0 second natural random jitter between actions) and respects strict daily quotas (50/day ceiling). It behaves indistinguishably from a human candidate clicking Easy Apply.",
    },
    {
      q: "How does AI answer screening questions in job forms?",
      a: "The assistant reads your uploaded resume facts, notice period, and CTC expectations. When a recruiter form asks 'Why are you suitable for this role?' or 'Years of Python experience?', it drafts factual answers strictly from your profile without hallucinating.",
    },
    {
      q: "Do I need any coding or technical knowledge to use this?",
      a: "Not at all. You simply upload your resume PDF, set your target job titles and city preferences, connect your Naukri or LinkedIn account in one click, and press 'Start Automation'.",
    },
  ];

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col selection:bg-emerald-500/30 selection:text-emerald-200">
      {/* ─── Navigation Header ─── */}
      <header className="sticky top-0 z-50 border-b border-slate-800/80 bg-slate-950/80 backdrop-blur-xl px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-tr from-emerald-600 to-teal-400 text-slate-950 font-bold shadow-md shadow-emerald-500/20">
            <Sparkles className="h-4.5 w-4.5" />
          </div>
          <span className="text-base font-bold tracking-tight text-slate-100 flex items-center gap-2">
            ApplyPilot
            <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/25">
              AI
            </span>
          </span>
        </div>

        <nav className="hidden md:flex items-center gap-6 text-xs font-medium text-slate-400">
          <a href="#how-it-works" className="hover:text-slate-200 transition-colors">How It Works</a>
          <a href="#features" className="hover:text-slate-200 transition-colors">Features</a>
          <a href="#pricing" className="hover:text-slate-200 transition-colors">Pricing</a>
          <a href="#faq" className="hover:text-slate-200 transition-colors">FAQ</a>
        </nav>

        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => navigate("/login")}>
            Sign In
          </Button>
          <Button variant="primary" size="sm" onClick={() => navigate("/login")} rightIcon={<ArrowRight className="h-3.5 w-3.5" />}>
            Get Started
          </Button>
        </div>
      </header>

      {/* ─── Hero Section ─── */}
      <section className="relative overflow-hidden px-6 pt-16 pb-20 md:pt-24 md:pb-32 flex flex-col items-center text-center max-w-5xl mx-auto">
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 h-[350px] w-[600px] bg-gradient-to-tr from-emerald-500/10 via-teal-500/5 to-transparent blur-3xl pointer-events-none rounded-full" />

        <Badge variant="success" size="md" dot className="mb-6">
          Tailored for Indian Tech Job Seekers · Freshers & 1–6 Yrs Experience
        </Badge>

        <h1 className="text-4xl sm:text-5xl md:text-6xl font-extrabold tracking-tight text-slate-100 max-w-3xl leading-[1.15]">
          Automate your job search. Land interviews on <span className="bg-gradient-to-r from-emerald-400 to-teal-300 bg-clip-text text-transparent">autopilot</span>.
        </h1>

        <p className="mt-5 max-w-2xl text-sm sm:text-base text-slate-400 leading-relaxed">
          ApplyPilot searches, filters, and applies to relevant job openings across Naukri and LinkedIn Easy Apply. Powered by AI screening answering, anti-ban pacing, and real-time live browser monitoring.
        </p>

        <div className="mt-8 flex flex-col sm:flex-row items-center gap-3">
          <Button size="lg" variant="primary" onClick={() => navigate("/login")} rightIcon={<ArrowRight className="h-4 w-4" />}>
            Start Free Automation
          </Button>
          <Button size="lg" variant="secondary" onClick={() => navigate("/login")}>
            View Live Demo
          </Button>
        </div>

        {/* Hero Interactive Preview Card */}
        <div className="mt-14 w-full max-w-4xl rounded-2xl border border-slate-800 bg-slate-900/70 p-4 sm:p-6 shadow-2xl backdrop-blur-md text-left">
          <div className="flex items-center justify-between border-b border-slate-800/80 pb-3 mb-4">
            <div className="flex items-center gap-2">
              <span className="h-3 w-3 rounded-full bg-rose-500/80" />
              <span className="h-3 w-3 rounded-full bg-amber-500/80" />
              <span className="h-3 w-3 rounded-full bg-emerald-500/80" />
              <span className="ml-2 text-xs font-mono text-slate-400">applypilot.workspace/live-session</span>
            </div>
            <span className="text-[11px] font-medium text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-full flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
              Active Engine
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="p-4 rounded-xl border border-slate-800 bg-slate-950/60">
              <span className="text-xs text-slate-400">Applied Today</span>
              <p className="num text-2xl font-bold text-slate-100 mt-1">38</p>
              <span className="text-[10px] text-emerald-400">Naukri + LinkedIn</span>
            </div>
            <div className="p-4 rounded-xl border border-slate-800 bg-slate-950/60">
              <span className="text-xs text-slate-400">Filtered Irrelevant Jobs</span>
              <p className="num text-2xl font-bold text-slate-100 mt-1">412</p>
              <span className="text-[10px] text-slate-400">Experience & salary guard</span>
            </div>
            <div className="p-4 rounded-xl border border-slate-800 bg-slate-950/60">
              <span className="text-xs text-slate-400">AI Screening Accuracy</span>
              <p className="num text-2xl font-bold text-emerald-400 mt-1">100%</p>
              <span className="text-[10px] text-slate-400">From verified resume</span>
            </div>
          </div>
        </div>
      </section>

      {/* ─── How It Works (3 Steps) ─── */}
      <section id="how-it-works" className="border-t border-slate-800/80 bg-slate-900/30 px-6 py-20">
        <div className="max-w-5xl mx-auto">
          <div className="text-center max-w-xl mx-auto mb-14">
            <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-100">
              How ApplyPilot works in 3 simple steps
            </h2>
            <p className="mt-2 text-xs sm:text-sm text-slate-400">
              Zero coding. Setup once and let your personal career assistant do the heavy lifting.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="p-6 rounded-2xl border border-slate-800 bg-slate-900/60 space-y-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-400 font-bold border border-emerald-500/20">
                1
              </div>
              <h3 className="text-base font-semibold text-slate-100">Upload Resume & Preferences</h3>
              <p className="text-xs text-slate-400 leading-relaxed">
                Add your resume PDF, preferred job titles (e.g. Frontend Engineer, Full Stack), expected CTC, and notice period.
              </p>
            </div>

            <div className="p-6 rounded-2xl border border-slate-800 bg-slate-900/60 space-y-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-400 font-bold border border-emerald-500/20">
                2
              </div>
              <h3 className="text-base font-semibold text-slate-100">Connect Naukri & LinkedIn</h3>
              <p className="text-xs text-slate-400 leading-relaxed">
                Connect your accounts securely. Cookies are encrypted with AES-256 Fernet to ensure your credentials never leak.
              </p>
            </div>

            <div className="p-6 rounded-2xl border border-slate-800 bg-slate-900/60 space-y-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-400 font-bold border border-emerald-500/20">
                3
              </div>
              <h3 className="text-base font-semibold text-slate-100">Launch Autonomous Apply</h3>
              <p className="text-xs text-slate-400 leading-relaxed">
                ApplyPilot matches relevant jobs, completes Easy Apply forms with AI answers, and logs everything to your Google Sheet.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ─── Features Grid ─── */}
      <section id="features" className="px-6 py-20 max-w-5xl mx-auto">
        <div className="text-center max-w-xl mx-auto mb-14">
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-100">
            Engineered for reliability & discretion
          </h2>
          <p className="mt-2 text-xs sm:text-sm text-slate-400">
            Built with modern security and thoughtful safeguards to protect your career.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          <div className="p-5 rounded-2xl border border-slate-800 bg-slate-900/50 space-y-2">
            <Zap className="h-5 w-5 text-emerald-400" />
            <h4 className="text-sm font-semibold text-slate-100">Smart AI Screening Answering</h4>
            <p className="text-xs text-slate-400 leading-relaxed">
              Gemini & Groq automatically answer custom recruiter screening questions strictly using your resume facts.
            </p>
          </div>

          <div className="p-5 rounded-2xl border border-slate-800 bg-slate-900/50 space-y-2">
            <Clock className="h-5 w-5 text-emerald-400" />
            <h4 className="text-sm font-semibold text-slate-100">Anti-Ban Human Pacing</h4>
            <p className="text-xs text-slate-400 leading-relaxed">
              Enforces natural 2.0s–5.0s delays between clicks with random jitter to stay completely undetected.
            </p>
          </div>

          <div className="p-5 rounded-2xl border border-slate-800 bg-slate-900/50 space-y-2">
            <MonitorPlay className="h-5 w-5 text-emerald-400" />
            <h4 className="text-sm font-semibold text-slate-100">Live Remote Browser Canvas</h4>
            <p className="text-xs text-slate-400 leading-relaxed">
              Watch forms get filled live at 15 FPS via WebSockets. Click and type directly if any OTP or captcha pops up.
            </p>
          </div>

          <div className="p-5 rounded-2xl border border-slate-800 bg-slate-900/50 space-y-2">
            <FileSpreadsheet className="h-5 w-5 text-emerald-400" />
            <h4 className="text-sm font-semibold text-slate-100">Real-Time Google Sheets Sync</h4>
            <p className="text-xs text-slate-400 leading-relaxed">
              Every applied job, salary, and company is automatically appended to your personal Google Sheet.
            </p>
          </div>

          <div className="p-5 rounded-2xl border border-slate-800 bg-slate-900/50 space-y-2">
            <ShieldCheck className="h-5 w-5 text-emerald-400" />
            <h4 className="text-sm font-semibold text-slate-100">Current Employer Blacklist</h4>
            <p className="text-xs text-slate-400 leading-relaxed">
              Protect yourself by blacklisting your current employer and staffing agencies from applications.
            </p>
          </div>

          <div className="p-5 rounded-2xl border border-slate-800 bg-slate-900/50 space-y-2">
            <Briefcase className="h-5 w-5 text-emerald-400" />
            <h4 className="text-sm font-semibold text-slate-100">Fresh Jobs Priority (10 Min)</h4>
            <p className="text-xs text-slate-400 leading-relaxed">
              Apply first before other candidates by filtering for positions posted within the last 10 minutes.
            </p>
          </div>
        </div>
      </section>

      {/* ─── Pricing Section ─── */}
      <section id="pricing" className="border-t border-slate-800/80 bg-slate-900/30 px-6 py-20">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-100">
            Simple, transparent plans
          </h2>
          <p className="mt-2 text-xs sm:text-sm text-slate-400">
            Start free on your local machine or deploy seamlessly to the cloud.
          </p>

          <div className="mt-12 grid grid-cols-1 md:grid-cols-2 gap-6 text-left">
            {/* Free Tier */}
            <div className="p-6 rounded-2xl border border-slate-800 bg-slate-900/60 space-y-4">
              <div>
                <h3 className="text-lg font-bold text-slate-100">Community Edition</h3>
                <p className="text-xs text-slate-400 mt-1">Full-featured open source self-hosted platform</p>
              </div>
              <div className="flex items-baseline gap-1">
                <span className="text-3xl font-extrabold text-slate-100">₹0</span>
                <span className="text-xs text-slate-400">/ forever</span>
              </div>
              <ul className="space-y-2 text-xs text-slate-300 pt-2 border-t border-slate-800">
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                  Naukri & LinkedIn autonomous engines
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                  AI question answering with free Gemini API
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                  Live CDP Screencast & manual intervention
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                  Personal Google Sheets synchronization
                </li>
              </ul>
              <Button variant="outline" className="w-full mt-4" onClick={() => navigate("/login")}>
                Start Self-Hosting
              </Button>
            </div>

            {/* Pro Tier */}
            <div className="p-6 rounded-2xl border border-emerald-500/30 bg-slate-900/80 space-y-4 relative">
              <div className="absolute top-4 right-4">
                <Badge variant="success" size="sm">Recommended</Badge>
              </div>
              <div>
                <h3 className="text-lg font-bold text-slate-100">Career Pilot Pro</h3>
                <p className="text-xs text-slate-400 mt-1">Managed cloud runner with zero laptop keeping open</p>
              </div>
              <div className="flex items-baseline gap-1">
                <span className="text-3xl font-extrabold text-emerald-400">₹999</span>
                <span className="text-xs text-slate-400">/ month</span>
              </div>
              <ul className="space-y-2 text-xs text-slate-300 pt-2 border-t border-slate-800">
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                  Runs 24/7 on residential cloud servers
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                  Ultra-fast fresh 10min job priority apply
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                  Multi-portal expansion (Instahyre & Wellfound)
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                  Audit reports & resume tailoring per role
                </li>
              </ul>
              <Button variant="primary" className="w-full mt-4" onClick={() => navigate("/login")}>
                Get Started
              </Button>
            </div>
          </div>
        </div>
      </section>

      {/* ─── FAQ Section ─── */}
      <section id="faq" className="px-6 py-20 max-w-3xl mx-auto w-full">
        <div className="text-center mb-12">
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-100">
            Frequently Asked Questions
          </h2>
        </div>

        <div className="space-y-3">
          {faqs.map((faq, idx) => (
            <div
              key={idx}
              className="rounded-2xl border border-slate-800 bg-slate-900/50 p-4 transition-colors"
            >
              <button
                onClick={() => setOpenFaq(openFaq === idx ? null : idx)}
                className="w-full flex items-center justify-between text-left text-sm font-semibold text-slate-200"
              >
                <span>{faq.q}</span>
                <ChevronDown
                  className={`h-4 w-4 text-slate-400 transition-transform ${
                    openFaq === idx ? "rotate-180 text-emerald-400" : ""
                  }`}
                />
              </button>
              {openFaq === idx && (
                <p className="mt-3 text-xs text-slate-400 leading-relaxed border-t border-slate-800/80 pt-3">
                  {faq.a}
                </p>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* ─── Footer ─── */}
      <footer className="border-t border-slate-800/80 bg-slate-950 px-6 py-8 text-center text-xs text-slate-400 mt-auto">
        <div className="flex flex-col sm:flex-row items-center justify-between max-w-5xl mx-auto gap-4">
          <div className="flex items-center gap-2">
            <div className="h-6 w-6 rounded-lg bg-emerald-500 text-slate-950 flex items-center justify-center font-bold text-xs">
              AP
            </div>
            <span className="font-semibold text-slate-300">ApplyPilot AI</span>
            <span>— Autonomous Career Automation</span>
          </div>
          <div className="flex items-center gap-4 text-slate-400">
            <Link to="/login" className="hover:text-slate-200">Sign In</Link>
            <a href="https://github.com" target="_blank" rel="noreferrer" className="hover:text-slate-200">GitHub</a>
            <span>MIT License</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
