import { User, AuthResponse, InviteCode, TeamItem } from '../types';

const TOKEN_KEY = 'gs_jwt_token';

export const authStorage = {
  getToken(): string | null {
    return localStorage.getItem(TOKEN_KEY);
  },
  setToken(token: string): void {
    localStorage.setItem(TOKEN_KEY, token);
  },
  clearToken(): void {
    localStorage.removeItem(TOKEN_KEY);
  },
};

/**
 * Fetch wrapper automatically attaching the Authorization: Bearer token header.
 */
export async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const token = authStorage.getToken();
  const headers = new Headers(options.headers || {});

  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  return fetch(url, { ...options, headers });
}

export const teamService = {
  async getTeams(): Promise<TeamItem[]> {
    try {
      const res = await fetch('/api/teams');
      if (!res.ok) return [];
      return await res.json();
    } catch {
      return [];
    }
  },
};

export const departmentService = {
  getDepartments: () => teamService.getTeams(),
};

export const authService = {
  async register(data: {
    uname: string;
    email: string;
    password: string;
    confirm_password?: string;
    invite_code: string;
    nrtel?: string;
    team?: string;
    dzial?: string;
  }): Promise<AuthResponse> {
    const resolvedTeam = data.team || data.dzial || null;
    const payload = {
      ...data,
      invite_code: data.invite_code.trim().toUpperCase(),
      team: resolvedTeam,
      dzial: resolvedTeam,
      nrtel: data.nrtel || null,
    };
    const res = await fetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Registration failed.');
    }
    const result: AuthResponse = await res.json();
    authStorage.setToken(result.access_token);
    return result;
  },

  async login(uname_or_email: string, password: string): Promise<AuthResponse> {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ uname_or_email, password }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Invalid login or password.');
    }
    const result: AuthResponse = await res.json();
    authStorage.setToken(result.access_token);
    return result;
  },

  async getMe(): Promise<User> {
    const res = await authFetch('/api/auth/me');
    if (!res.ok) {
      authStorage.clearToken();
      throw new Error('Session expired.');
    }
    return res.json();
  },

  logout(): void {
    authStorage.clearToken();
  },
};

export const adminService = {
  async createInvite(
    roleOrIsAdmin: 'member' | 'lead' | boolean = 'member',
    team?: string | null
  ): Promise<{ code: string; is_admin_invite?: boolean; role?: 'member' | 'lead'; team?: string | null; message: string }> {
    const role: 'member' | 'lead' =
      typeof roleOrIsAdmin === 'boolean' ? (roleOrIsAdmin ? 'lead' : 'member') : roleOrIsAdmin;
    const cleanTeam = team?.trim() || null;
    const res = await authFetch('/api/admin/invites', {
      method: 'POST',
      body: JSON.stringify({ role, is_admin: role === 'lead', team: cleanTeam }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to generate invite code.');
    }
    return res.json();
  },

  async updateUserRole(userId: number, isAdmin: boolean): Promise<User> {
    const res = await authFetch(`/api/admin/users/${userId}/role`, {
      method: 'PATCH',
      body: JSON.stringify({ is_admin: isAdmin }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to update user role.');
    }
    return res.json();
  },

  async listInvites(): Promise<InviteCode[]> {
    const res = await authFetch('/api/admin/invites');
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to fetch invite codes.');
    }
    return res.json();
  },

  async listUsers(): Promise<User[]> {
    const res = await authFetch('/api/admin/users');
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to fetch employee roster.');
    }
    return res.json();
  },

  async createTeam(name: string, description?: string): Promise<TeamItem> {
    const res = await authFetch('/api/admin/teams', {
      method: 'POST',
      body: JSON.stringify({ name, description }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to create team.');
    }
    return res.json();
  },

  async updateTeam(id: number, name: string, description?: string): Promise<TeamItem> {
    const res = await authFetch(`/api/admin/teams/${id}`, {
      method: 'PUT',
      body: JSON.stringify({ name, description }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to update team.');
    }
    return res.json();
  },

  async deleteTeam(id: number): Promise<void> {
    const res = await authFetch(`/api/admin/teams/${id}`, {
      method: 'DELETE',
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to delete team.');
    }
  },

  createDepartment(name: string, description?: string): Promise<TeamItem> {
    return this.createTeam(name, description);
  },

  deleteDepartment(id: number): Promise<void> {
    return this.deleteTeam(id);
  },
};
