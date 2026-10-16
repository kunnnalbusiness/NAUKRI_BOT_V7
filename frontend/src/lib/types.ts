export interface UserClaims {
  username: string;
  role: "admin" | "user";
  is_admin: boolean;
  delay_seconds?: number;
  total_applied?: number;
  csrf_token?: string;
}

export interface EngineState {
  status: "Running" | "Waiting" | "Stopped" | "Error" | "Limit Reached" | "Completed";
  reason?: string;
  last_heartbeat?: string | null;
  enabled?: boolean;
  current_action?: string;
  session_applied_count?: number;
  daily_limit_exceeded?: boolean;
  only_fresh_10min?: boolean;
  only_fresh?: boolean;
  fresh_threshold_minutes?: number;
  pace_seconds?: number;
}

export interface SessionInfo {
  present: boolean;
  valid: boolean;
  status: "Valid" | "Expired" | "Missing" | "Checking...";
  last_verified: string | null;
  message?: string;
}

export interface ActivityItem {
  id?: string;
  timestamp: string;
  source: string;
  platform?: "naukri" | "linkedin";
  title: string;
  company: string;
  role?: string;
  posted_time?: string;
  status: string;
  reason?: string;
  job_url?: string;
  sheet_name?: string;
}

export interface PlatformStats {
  applied_today: number;
  total_applied: number;
  skipped_today: number;
  total_skipped: number;
  failed_today?: number;
  total_failed?: number;
}

export interface ActivityStats {
  total_applied: number;
  applied_today: number;
  applied_radar: number;
  applied_sweep: number;
  applied_linkedin: number;
  total_skipped: number;
  naukri?: PlatformStats;
  linkedin?: PlatformStats;
  naukri_applied_today?: number;
  naukri_total_applied?: number;
  naukri_skipped_today?: number;
  naukri_total_skipped?: number;
  linkedin_applied_today?: number;
  linkedin_total_applied?: number;
  linkedin_skipped_today?: number;
  linkedin_total_skipped?: number;
}

export interface KeyItem {
  id: string;
  provider: "gemini" | "groq";
  masked_key: string;
  status: string;
  enabled: boolean;
  cooldown_remaining: number;
  created_at?: string;
}

export interface DashboardStatus {
  user: UserClaims;
  profile: {
    is_complete: boolean;
    reason: string;
    missing: string[];
  };
  engines: {
    naukri: EngineState;
    linkedin: EngineState;
  };
  daily_limit: {
    exceeded: boolean;
    naukri_exceeded: boolean;
    linkedin_exceeded: boolean;
    reason: string;
    reset_time: string;
  };
  sessions: {
    naukri: SessionInfo;
    linkedin: SessionInfo;
  };
  sheet: {
    sheet_url: string;
    webhook_url: string;
    webhook_configured: boolean;
    is_optional: boolean;
  };
  llm: {
    keys: KeyItem[];
    current_key: string | null;
    quota_status: string;
    active_provider: string | null;
  };
  activity: {
    stats: ActivityStats;
    recent: ActivityItem[];
  };
  csrf_token: string;
}

export interface ProfileData {
  username?: string;
  full_name?: string;
  email?: string;
  phone?: string;
  current_city?: string;
  relocate_cities?: string[];
  work_mode?: string;
  night_shift_ok?: boolean;
  weekend_ok?: boolean;
  date_of_birth?: string;
  gender?: string;
  marital_status?: string;

  target_roles?: string[];
  role_required_keywords?: Record<string, string[]>;
  total_experience_years?: number | null;
  current_employer?: string;
  current_title_official?: string;
  current_title_functional?: string;
  highest_qualification?: string;
  certifications?: string[];
  skills_primary?: string[];
  skills_adjacent?: string[];
  work_history_narrative?: string;

  notice_period_days?: number;
  immediately_available?: boolean;
  current_ctc_lpa?: number | null;
  expected_ctc_lpa?: number | null;
  ctc_disclosure_policy?: string;

  company_exclude?: string[];
  company_include_only?: string[];
  seniority_floor_years?: number;
  seniority_ceiling_years?: number;
  job_freshness_days?: number;
  salary_floor_lpa?: number | null;
  stop_after_n_applications?: number;
  pace_seconds_between_actions?: number;
  max_pages_per_role?: number;

  resume_file_name?: string;
  resume_path?: string;
  resume_size_bytes?: number;
  resume_uploaded_at?: string;

  is_complete?: boolean;
  completeness_reason?: string;
  missing_fields?: string[];
  is_admin?: boolean;
}

export interface UserAccount {
  username: string;
  role: "admin" | "user";
  delay_seconds: number;
  stream_fps?: number;
  status: string;
  email?: string;
  created_at?: string;
  total_applied?: number;
}

export interface UserSettings {
  username?: string;
  delay_seconds: number;
  stream_fps?: number;
  sheet_config: {
    sheet_url?: string;
    webhook_url?: string;
  };
  role?: string;
  total_applied?: number;
  created_at?: string;
}
