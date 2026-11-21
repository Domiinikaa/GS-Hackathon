export interface TeamItem {
  id: number;
  name: string;
  description?: string | null;
  created_at: string;
  user_count?: number;
  people_count?: number;
  rules_count?: number;
  sources_count?: number;
}

export type DepartmentItem = TeamItem;

export interface User {
  id: number;
  uname: string;
  email: string;
  nrtel?: string | null;
  team?: string | null;
  dzial?: string | null;
  is_admin: boolean;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface InviteCode {
  id: number;
  code: string;
  is_used: boolean;
  is_admin_invite?: boolean;
  created_at: string;
  used_at?: string | null;
  created_by_uname?: string | null;
  used_by_uname?: string | null;
}

export interface Item {
  id: number;
  user_id?: number | null;
  title: string;
  category: string;
  value: number;
  description?: string;
  created_at: string;
}

export interface StatsResponse {
  stats: {
    count: number;
    total_value: number;
    average_value: number;
    status: string;
  };
  external: {
    market_status: string;
    benchmark_sp500: number;
    sentiment_score: number;
  };
  user?: {
    uname: string;
    email: string;
    dzial?: string | null;
  } | null;
}
