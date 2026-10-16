import React, { Suspense, lazy } from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "@/lib/authContext";
import AppLayout from "@/components/layout/AppLayout";

// Lazy-loaded pages for maximum performance and light bundle chunks
const Login = lazy(() => import("@/pages/Login"));
const LandingPage = lazy(() => import("@/pages/LandingPage"));
const Dashboard = lazy(() => import("@/pages/Dashboard"));
const LiveActivity = lazy(() => import("@/pages/LiveActivity"));
const LiveBrowserView = lazy(() => import("@/pages/LiveBrowserView"));
const Sessions = lazy(() => import("@/pages/Sessions"));
const MyProfile = lazy(() => import("@/pages/MyProfile"));
const Settings = lazy(() => import("@/pages/Settings"));
const AdminUsers = lazy(() => import("@/pages/AdminUsers"));
const SystemMonitor = lazy(() => import("@/pages/SystemMonitor"));
const PublicStatus = lazy(() => import("@/pages/PublicStatus"));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 15000,
    },
  },
});

function FullScreenSpinner() {
  return (
    <div className="flex h-screen w-screen items-center justify-center bg-[#000000] text-emerald-400">
      <div className="flex flex-col items-center gap-3">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-emerald-500/20 border-t-emerald-400" />
        <span className="font-mono text-xs text-muted-foreground animate-pulse">
          Loading Naukri Auto-Apply...
        </span>
      </div>
    </div>
  );
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return <FullScreenSpinner />;
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <>{children}</>;
}

function AdminRoute({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();

  if (isLoading) {
    return <FullScreenSpinner />;
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (user.role !== "admin") {
    return <Navigate to="/dashboard" replace />;
  }

  return <>{children}</>;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Suspense fallback={<FullScreenSpinner />}>
            <Routes>
              {/* Public Routes */}
              <Route path="/landing" element={<LandingPage />} />
              <Route path="/login" element={<Login />} />
              <Route path="/status" element={<PublicStatus />} />

              {/* Protected App Routes wrapped inside AppLayout */}
              <Route
                element={
                  <ProtectedRoute>
                    <AppLayout />
                  </ProtectedRoute>
                }
              >
                <Route path="/" element={<Navigate to="/dashboard" replace />} />
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/activity" element={<LiveActivity />} />
                <Route path="/browser" element={<LiveBrowserView />} />
                <Route path="/sessions" element={<Sessions />} />
                <Route path="/profile" element={<MyProfile />} />
                <Route path="/settings" element={<Settings />} />

                {/* Strict Admin-Only Routes */}
                <Route
                  path="/admin/users"
                  element={
                    <AdminRoute>
                      <AdminUsers />
                    </AdminRoute>
                  }
                />
                <Route
                  path="/admin/system"
                  element={
                    <AdminRoute>
                      <SystemMonitor />
                    </AdminRoute>
                  }
                />
              </Route>

              {/* 404 Fallback */}
              <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Routes>
          </Suspense>
          <Toaster
            position="bottom-right"
            theme="dark"
            toastOptions={{
              className: "border border-border bg-card text-foreground font-sans text-xs shadow-2xl",
              duration: 3500,
            }}
          />
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}
