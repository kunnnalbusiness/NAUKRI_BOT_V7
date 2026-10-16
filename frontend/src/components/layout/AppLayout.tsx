import React, { useState } from "react";
import { Link, useLocation, Outlet, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  LayoutDashboard,
  FileText,
  MonitorPlay,
  KeyRound,
  User,
  Settings as SettingsIcon,
  Users,
  LogOut,
  Sparkles,
  Menu,
  X,
  ChevronRight,
  ExternalLink,
  Shield,
  Activity,
  Gauge,
} from "lucide-react";
import { useAuth } from "@/lib/authContext";
import { apiGet } from "@/lib/api";
import type { DashboardStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

export default function AppLayout() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { user, isAdmin, logout } = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // Poll engine status
  const statusQuery = useQuery({
    queryKey: ["app-layout-status"],
    queryFn: () => apiGet<DashboardStatus>("/api/status"),
    refetchInterval: () => (document.visibilityState === "visible" ? 8000 : false),
    retry: false,
    refetchOnWindowFocus: false,
    staleTime: 5000,
  });

  const engines = statusQuery.data?.engines;
  const isRunning =
    engines?.naukri?.status === "Running" ||
    engines?.naukri?.status === "Waiting" ||
    engines?.linkedin?.status === "Running" ||
    engines?.linkedin?.status === "Waiting";

  const appliedToday = statusQuery.data?.activity?.stats?.applied_today ?? 0;

  const navGroups = [
    {
      group: "Workspace",
      items: [
        { label: "Overview", path: "/dashboard", icon: LayoutDashboard },
        { label: "Applications", path: "/activity", icon: FileText },
        { label: "Live Browser", path: "/browser", icon: MonitorPlay },
      ],
    },
    {
      group: "Career",
      items: [
        { label: "Profile & Resume", path: "/profile", icon: User },
      ],
    },
    {
      group: "Automation",
      items: [
        { label: "Connected Accounts", path: "/sessions", icon: KeyRound },
        { label: "Preferences", path: "/settings", icon: SettingsIcon },
      ],
    },
    ...(isAdmin
      ? [
          {
            group: "Administration",
            items: [
              { label: "Workspace Members", path: "/admin/users", icon: Users },
              { label: "System Monitor", path: "/admin/system", icon: Gauge },
            ],
          },
        ]
      : []),
  ];

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground antialiased">
      {/* ─── Desktop Left Sidebar (>= md) ─── */}
      <aside className="hidden md:flex w-64 flex-col border-r border-slate-800/80 bg-slate-900/40 shrink-0 select-none">
        {/* Brand Header */}
        <div className="flex h-16 items-center justify-between border-b border-slate-800/80 px-5">
          <Link to="/dashboard" className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-tr from-emerald-600 to-teal-400 text-slate-950 font-bold shadow-md shadow-emerald-500/20">
              <Sparkles className="h-4.5 w-4.5" />
            </div>
            <div>
              <span className="text-sm font-semibold tracking-tight text-slate-100 flex items-center gap-1.5">
                ApplyPilot
                <span className="text-[10px] font-medium px-1.5 py-0.2 rounded-md bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  AI
                </span>
              </span>
              <p className="text-[11px] text-slate-400 leading-none mt-0.5">Career Automation</p>
            </div>
          </Link>
        </div>

        {/* Status Indicator Banner */}
        <div className="p-3 mx-3 my-3 rounded-xl border border-slate-800 bg-slate-900/60 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span
              className={cn(
                "h-2 w-2 rounded-full shrink-0",
                isRunning ? "bg-emerald-400 animate-pulse" : "bg-slate-500"
              )}
            />
            <span className="text-xs font-medium text-slate-300">
              {isRunning ? "Engine Running" : "Automation Idle"}
            </span>
          </div>
          <span className="num text-[11px] font-medium text-slate-400 bg-slate-800/80 px-2 py-0.5 rounded-md">
            {appliedToday} today
          </span>
        </div>

        {/* Navigation Groups */}
        <div className="flex-1 overflow-y-auto px-3 py-2 space-y-6 scrollbar-none">
          {navGroups.map((group) => (
            <div key={group.group}>
              <h4 className="px-3 mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                {group.group}
              </h4>
              <div className="space-y-1">
                {group.items.map((item) => {
                  const isActive =
                    pathname === item.path ||
                    (item.path === "/dashboard" && pathname === "/") ||
                    (item.path === "/admin/users" && pathname.startsWith("/admin/users")) ||
                    (item.path === "/admin/system" && pathname.startsWith("/admin/system"));
                  const Icon = item.icon;
                  return (
                    <Link
                      key={item.path}
                      to={item.path}
                      className={cn(
                        "flex items-center gap-3 rounded-xl px-3 py-2 text-xs font-medium transition-all duration-150 app-press",
                        isActive
                          ? "bg-emerald-500/10 text-emerald-400 font-semibold border border-emerald-500/20 shadow-xs"
                          : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
                      )}
                    >
                      <Icon className={cn("h-4 w-4 shrink-0", isActive ? "text-emerald-400" : "text-slate-400")} />
                      <span>{item.label}</span>
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </div>

        {/* Sidebar Footer: User Card & Logout */}
        <div className="border-t border-slate-800/80 p-3 bg-slate-900/50">
          <div className="flex items-center justify-between gap-2 p-2 rounded-xl hover:bg-slate-800/50 transition-colors">
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="flex h-7.5 w-7.5 items-center justify-center rounded-lg bg-slate-800 text-slate-200 font-semibold text-xs border border-slate-700/60 shrink-0">
                {user?.username ? user.username.charAt(0).toUpperCase() : "U"}
              </div>
              <div className="min-w-0">
                <p className="text-xs font-medium text-slate-200 truncate">{user?.username || "User"}</p>
                <p className="text-[10px] text-slate-400 capitalize">{user?.role || "Member"}</p>
              </div>
            </div>
            <button
              onClick={() => logout()}
              title="Sign Out"
              className="rounded-lg p-1.5 text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 transition-colors app-press"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </aside>

      {/* ─── Main Content Shell ─── */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Mobile Top Header (< md) */}
        <header className="md:hidden flex h-14 items-center justify-between border-b border-slate-800/80 bg-slate-900/80 px-4 backdrop-blur-md shrink-0">
          <Link to="/dashboard" className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500 text-slate-950 font-bold">
              <Sparkles className="h-4 w-4" />
            </div>
            <span className="text-sm font-semibold tracking-tight text-slate-100">ApplyPilot</span>
          </Link>

          <div className="flex items-center gap-2">
            <span
              className={cn(
                "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-medium border",
                isRunning
                  ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                  : "bg-slate-800 text-slate-400 border-slate-700/60"
              )}
            >
              <span className={cn("h-1.5 w-1.5 rounded-full", isRunning ? "bg-emerald-400 animate-pulse" : "bg-slate-500")} />
              {isRunning ? "Running" : "Idle"}
            </span>
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="p-1.5 rounded-lg text-slate-300 hover:bg-slate-800 transition-colors"
            >
              {mobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
          </div>
        </header>

        {/* Mobile Slide-Over Drawer */}
        {mobileMenuOpen && (
          <div className="md:hidden fixed inset-0 z-50 top-14 bg-slate-950/90 backdrop-blur-md flex flex-col p-4 animate-in fade-in">
            <div className="space-y-4 flex-1 overflow-y-auto">
              {navGroups.map((group) => (
                <div key={group.group}>
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1">
                    {group.group}
                  </p>
                  <div className="space-y-1">
                    {group.items.map((item) => (
                      <Link
                        key={item.path}
                        to={item.path}
                        onClick={() => setMobileMenuOpen(false)}
                        className={cn(
                          "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium",
                          pathname === item.path
                            ? "bg-emerald-500/10 text-emerald-400 font-semibold"
                            : "text-slate-300 hover:bg-slate-800/60"
                        )}
                      >
                        <item.icon className="h-4 w-4" />
                        <span>{item.label}</span>
                      </Link>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            <div className="pt-4 border-t border-slate-800 flex items-center justify-between">
              <div>
                <p className="text-xs font-semibold text-slate-200">{user?.username}</p>
                <p className="text-[10px] text-slate-400 capitalize">{user?.role}</p>
              </div>
              <button
                onClick={() => {
                  setMobileMenuOpen(false);
                  logout();
                }}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-rose-400 bg-rose-500/10 hover:bg-rose-500/20"
              >
                <LogOut className="h-3.5 w-3.5" />
                Sign Out
              </button>
            </div>
          </div>
        )}

        {/* Content Outlet */}
        <main className="flex-1 min-h-0 overflow-y-auto bg-background">
          <Outlet />
        </main>

        {/* Mobile Bottom Navigation (< md) */}
        <nav className="md:hidden flex h-14 items-center justify-around border-t border-slate-800/80 bg-slate-900/95 backdrop-blur-lg px-2 shrink-0 z-30">
          <Link
            to="/dashboard"
            className={cn(
              "flex flex-col items-center gap-0.5 text-[10px] font-medium transition-colors",
              pathname === "/dashboard" || pathname === "/" ? "text-emerald-400" : "text-slate-400"
            )}
          >
            <LayoutDashboard className="h-4.5 w-4.5" />
            <span>Overview</span>
          </Link>
          <Link
            to="/activity"
            className={cn(
              "flex flex-col items-center gap-0.5 text-[10px] font-medium transition-colors",
              pathname === "/activity" ? "text-emerald-400" : "text-slate-400"
            )}
          >
            <FileText className="h-4.5 w-4.5" />
            <span>Applications</span>
          </Link>
          <Link
            to="/browser"
            className={cn(
              "flex flex-col items-center gap-0.5 text-[10px] font-medium transition-colors",
              pathname === "/browser" ? "text-emerald-400" : "text-slate-400"
            )}
          >
            <MonitorPlay className="h-4.5 w-4.5" />
            <span>Live View</span>
          </Link>
          <Link
            to="/profile"
            className={cn(
              "flex flex-col items-center gap-0.5 text-[10px] font-medium transition-colors",
              pathname === "/profile" ? "text-emerald-400" : "text-slate-400"
            )}
          >
            <User className="h-4.5 w-4.5" />
            <span>Profile</span>
          </Link>
        </nav>
      </div>
    </div>
  );
}
