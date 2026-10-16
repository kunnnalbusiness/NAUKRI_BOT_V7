import React, { useState } from "react";
import { Navigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Users,
  UserPlus,
  ShieldAlert,
  ShieldCheck,
  User,
  Trash2,
  Lock,
  Mail,
  Clock,
  CheckCircle2,
  AlertCircle,
  X,
  Search,
} from "lucide-react";
import { toast } from "sonner";

import { apiGet, apiPost, apiDelete } from "@/lib/api";
import { useAuth } from "@/lib/authContext";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { Modal } from "@/components/ui/Modal";
import { MetricCard } from "@/components/ui/MetricCard";

interface AdminUser {
  id: string;
  username: string;
  role: "admin" | "user";
  email?: string;
  created_at: string;
  is_active: boolean;
  delay_seconds: number;
}

export default function AdminUsers() {
  const { user } = useAuth();
  const queryClient = useQueryClient();

  if (user?.role !== "admin") {
    return <Navigate to="/dashboard" replace />;
  }

  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [deleteConfirmUser, setDeleteConfirmUser] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  // Create Form State
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"user" | "admin">("user");
  const [delaySeconds, setDelaySeconds] = useState(3);

  // Fetch users
  const { data: users = [], isLoading } = useQuery({
    queryKey: ["admin-users"],
    queryFn: () => apiGet<AdminUser[]>("/api/admin/users"),
    staleTime: 10000,
  });

  // Create user
  const createUserMutation = useMutation({
    mutationFn: (data: any) => apiPost("/api/admin/users", data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
      setCreateModalOpen(false);
      setUsername("");
      setPassword("");
      setEmail("");
      setRole("user");
      setDelaySeconds(3);
      toast.success("New workspace member account created!");
    },
    onError: (err: any) => toast.error(err.message || "Failed to create user"),
  });

  // Delete user
  const deleteUserMutation = useMutation({
    mutationFn: (targetUsername: string) => apiDelete(`/api/admin/users/${targetUsername}`),
    onSuccess: (_, targetUsername) => {
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
      setDeleteConfirmUser(null);
      toast.success(`User '${targetUsername}' removed.`);
    },
    onError: (err: any) => toast.error(err.message || "Failed to delete user"),
  });

  const filteredUsers = users.filter((u) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      u.username.toLowerCase().includes(q) ||
      (u.email || "").toLowerCase().includes(q) ||
      u.role.toLowerCase().includes(q)
    );
  });

  const totalUsers = users.length;
  const adminCount = users.filter((u) => u.role === "admin").length;
  const activeCount = users.filter((u) => u.is_active !== false).length;

  const handleCreateSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) {
      toast.error("Username and password are required");
      return;
    }
    createUserMutation.mutate({
      username: username.trim(),
      password: password.trim(),
      email: email.trim() || undefined,
      role,
      delay_seconds: delaySeconds,
    });
  };

  return (
    <div className="flex-1 p-5 sm:p-8 max-w-7xl mx-auto w-full space-y-7">
      <PageHeader
        title="Workspace Members"
        description="Manage role-based permissions, invite new members, and enforce tenant isolation."
        actions={
          <Button
            variant="primary"
            size="sm"
            leftIcon={<UserPlus className="h-3.5 w-3.5" />}
            onClick={() => setCreateModalOpen(true)}
          >
            Invite Member
          </Button>
        }
      />

      {/* ─── Metric Cards ─── */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <MetricCard
          label="Total Workspace Accounts"
          value={totalUsers}
          subtext="Active tenant profiles"
          icon={<Users className="h-4 w-4" />}
          variant="default"
        />

        <MetricCard
          label="Active Users"
          value={activeCount}
          subtext="Authorized automation access"
          icon={<CheckCircle2 className="h-4 w-4" />}
          variant="success"
        />

        <MetricCard
          label="System Administrators"
          value={adminCount}
          subtext="Full privileges"
          icon={<ShieldCheck className="h-4 w-4" />}
          variant="indigo"
        />
      </div>

      {/* ─── Search & Members Table ─── */}
      <Card className="p-0 overflow-hidden">
        <div className="p-4 border-b border-slate-800/80 flex items-center justify-between gap-3">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-500" />
            <input
              type="text"
              placeholder="Filter by name, email, or role..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="h-9 w-full rounded-xl border border-slate-800 bg-slate-950/60 pl-9 pr-3 text-xs text-slate-200 placeholder:text-slate-500 focus:outline-none"
            />
          </div>
          <span className="text-xs text-slate-400">
            {filteredUsers.length} member{filteredUsers.length === 1 ? "" : "s"}
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-950/40 border-b border-slate-800 text-slate-400">
              <tr>
                <th className="py-3 px-4 font-medium">Member</th>
                <th className="py-3 px-4 font-medium">Role</th>
                <th className="py-3 px-4 font-medium">Status</th>
                <th className="py-3 px-4 font-medium">Pacing Delay</th>
                <th className="py-3 px-4 font-medium text-right">Created</th>
                <th className="py-3 px-4 font-medium text-center">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/40">
              {filteredUsers.map((u) => {
                const isSuperAdmin = u.username === "admin";
                return (
                  <tr key={u.id || u.username} className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3.5 px-4">
                      <div className="flex items-center gap-3">
                        <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-slate-800 text-slate-200 font-semibold text-xs border border-slate-700/60">
                          {u.username.charAt(0).toUpperCase()}
                        </div>
                        <div>
                          <p className="font-semibold text-slate-200">{u.username}</p>
                          <p className="text-[11px] text-slate-400">{u.email || "No email registered"}</p>
                        </div>
                      </div>
                    </td>

                    <td className="py-3.5 px-4">
                      <Badge variant={u.role === "admin" ? "purple" : "neutral"} size="sm">
                        {u.role === "admin" ? "Administrator" : "Member"}
                      </Badge>
                    </td>

                    <td className="py-3.5 px-4">
                      <Badge variant={u.is_active !== false ? "success" : "error"} size="sm" dot>
                        {u.is_active !== false ? "Active" : "Suspended"}
                      </Badge>
                    </td>

                    <td className="py-3.5 px-4 text-slate-400 font-mono text-[11px]">
                      {u.delay_seconds || 3}s minimum
                    </td>

                    <td className="py-3.5 px-4 text-right text-slate-400 font-mono text-[11px]">
                      {u.created_at ? u.created_at.slice(0, 10) : "—"}
                    </td>

                    <td className="py-3.5 px-4 text-center">
                      {!isSuperAdmin && u.username !== user?.username && (
                        <button
                          onClick={() => setDeleteConfirmUser(u.username)}
                          className="p-1.5 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 transition-colors"
                          title="Delete Member"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      {/* ─── Create User Modal ─── */}
      <Modal
        isOpen={createModalOpen}
        onClose={() => setCreateModalOpen(false)}
        title="Invite Workspace Member"
        description="Create an isolated tenant account with customized permissions."
        size="md"
      >
        <form onSubmit={handleCreateSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-slate-300">Username *</label>
            <input
              type="text"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="e.g. rahul_s"
              className="h-10 w-full rounded-xl border border-slate-800 bg-slate-950 px-3 text-xs text-slate-100 focus:outline-none"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-slate-300">Password *</label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className="h-10 w-full rounded-xl border border-slate-800 bg-slate-950 px-3 text-xs text-slate-100 focus:outline-none"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-slate-300">Email Address (Optional)</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="rahul@example.com"
              className="h-10 w-full rounded-xl border border-slate-800 bg-slate-950 px-3 text-xs text-slate-100 focus:outline-none"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-slate-300">Role</label>
              <select
                value={role}
                onChange={(e) => setRole(e.target.value as any)}
                className="h-10 w-full rounded-xl border border-slate-800 bg-slate-950 px-3 text-xs text-slate-200 focus:outline-none"
              >
                <option value="user">Member</option>
                <option value="admin">Administrator</option>
              </select>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-slate-300">Pacing Delay</label>
              <input
                type="number"
                min="2"
                max="15"
                value={delaySeconds}
                onChange={(e) => setDelaySeconds(parseInt(e.target.value) || 3)}
                className="h-10 w-full rounded-xl border border-slate-800 bg-slate-950 px-3 text-xs text-slate-200 focus:outline-none"
              />
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-3 border-t border-slate-800">
            <Button variant="ghost" size="sm" onClick={() => setCreateModalOpen(false)}>
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              size="sm"
              isLoading={createUserMutation.isPending}
            >
              Create Account
            </Button>
          </div>
        </form>
      </Modal>

      {/* ─── Delete Confirmation Modal ─── */}
      <Modal
        isOpen={Boolean(deleteConfirmUser)}
        onClose={() => setDeleteConfirmUser(null)}
        title="Delete Member Account"
        description={`Are you sure you want to delete '${deleteConfirmUser}'? All associated candidate profile data and logs will be permanently deleted.`}
        size="sm"
      >
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" size="sm" onClick={() => setDeleteConfirmUser(null)}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            size="sm"
            isLoading={deleteUserMutation.isPending}
            onClick={() => {
              if (deleteConfirmUser) {
                deleteUserMutation.mutate(deleteConfirmUser);
              }
            }}
          >
            Delete Permanently
          </Button>
        </div>
      </Modal>
    </div>
  );
}
