import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { apiGet, apiPost, clearAuthToken, setAuthToken, getAuthToken } from "@/lib/api";
import type { UserClaims } from "@/lib/types";

interface AuthContextType {
  user: UserClaims | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  isAdmin: boolean;
  login: (username: string, password: string) => Promise<{ success: boolean; error?: string }>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<UserClaims | null>(() => {
    try {
      const saved = sessionStorage.getItem("bot_user_claims");
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  });
  const [isLoading, setIsLoading] = useState(true);

  const refreshUser = useCallback(async () => {
    try {
      const claims = await apiGet<UserClaims>("/api/auth/me");
      setUser(claims);
      sessionStorage.setItem("bot_user_claims", JSON.stringify(claims));
    } catch {
      setUser(null);
      sessionStorage.removeItem("bot_user_claims");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  const login = async (username: string, password: string) => {
    try {
      const res = await apiPost<{
        success: boolean;
        token: string;
        csrf_token: string;
        username: string;
        role: "admin" | "user";
      }>("/api/auth/login", { username, password });

      if (res.token) {
        setAuthToken(res.token);
      }
      const claims: UserClaims = {
        username: res.username,
        role: res.role,
        is_admin: res.role === "admin",
        csrf_token: res.csrf_token,
      };
      setUser(claims);
      sessionStorage.setItem("bot_user_claims", JSON.stringify(claims));
      return { success: true };
    } catch (err: any) {
      return { success: false, error: err.message || "Login failed" };
    }
  };

  const logout = async () => {
    try {
      await apiPost("/api/auth/logout");
    } catch {
      // ignore
    } finally {
      clearAuthToken();
      setUser(null);
      sessionStorage.removeItem("bot_user_claims");
      window.location.href = "/login";
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: Boolean(user),
        isAdmin: Boolean(user?.is_admin),
        login,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
};
