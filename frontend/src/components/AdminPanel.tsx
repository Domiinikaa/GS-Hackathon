import React, { useState, useEffect } from 'react';
import { adminService, teamService, authService } from '../services/auth';
import { InviteCode, User, TeamItem } from '../types';
import {
  Key,
  PlusCircle,
  Check,
  Copy,
  Users,
  ShieldAlert,
  ShieldCheck,
  CheckCircle2,
  Briefcase,
  Trash2,
  FolderPlus,
  Pencil,
  Shield,
  UserX,
  X
} from 'lucide-react';

interface NewlyCreatedInvite {
  code: string;
  role: 'member' | 'lead';
  team?: string | null;
}

export const AdminPanel: React.FC<{ currentUser?: User | null }> = ({ currentUser: initialUser }) => {
  const [currentUser, setCurrentUser] = useState<User | null>(initialUser || null);
  const [invites, setInvites] = useState<InviteCode[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [teams, setTeams] = useState<TeamItem[]>([]);

  // Invite code generation (default: member, optional pre-selected team)
  const [inviteRole, setInviteRole] = useState<'member' | 'lead'>('member');
  const [inviteTeam, setInviteTeam] = useState<string>('');
  const [generating, setGenerating] = useState(false);
  const [newlyCreatedInvite, setNewlyCreatedInvite] = useState<NewlyCreatedInvite | null>(null);
  const [copiedCode, setCopiedCode] = useState<string | null>(null);

  // New team state
  const [newTeamName, setNewTeamName] = useState('');
  const [newTeamDesc, setNewTeamDesc] = useState('');
  const [addingTeam, setAddingTeam] = useState(false);

  // Edit / rename team state
  const [editingTeamId, setEditingTeamId] = useState<number | null>(null);
  const [editTeamName, setEditTeamName] = useState('');
  const [editTeamDesc, setEditTeamDesc] = useState('');
  const [savingTeamId, setSavingTeamId] = useState<number | null>(null);

  // Modifying user role
  const [roleChangingUserId, setRoleChangingUserId] = useState<number | null>(null);

  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const loadData = async () => {
    try {
      setError(null);
      const [invitesRes, usersRes, teamsRes, meRes] = await Promise.all([
        adminService.listInvites(),
        adminService.listUsers(),
        teamService.getTeams(),
        currentUser ? Promise.resolve(currentUser) : authService.getMe().catch(() => null),
      ]);
      setInvites(invitesRes);
      setUsers(usersRes);
      setTeams(teamsRes);
      if (meRes) setCurrentUser(meRes);
    } catch (err: any) {
      setError(err.message || 'Error loading administrator data.');
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleGenerateInvite = async () => {
    try {
      setGenerating(true);
      setError(null);
      const res = await adminService.createInvite(inviteRole, inviteTeam || null);
      setNewlyCreatedInvite({ code: res.code, role: inviteRole, team: res.team ?? (inviteTeam || null) });
      await loadData();
    } catch (err: any) {
      setError(err.message || 'Failed to generate invite code.');
    } finally {
      setGenerating(false);
    }
  };

  const handleToggleUserRole = async (targetUser: User) => {
    const newAdminStatus = !targetUser.is_admin;
    const actionLabel = newAdminStatus ? 'promote' : 'demote';
    const roleTitle = newAdminStatus ? 'Lead' : 'Standard User';

    if (!window.confirm(`Are you sure you want to ${actionLabel} @${targetUser.uname} to ${roleTitle}?`)) {
      return;
    }

    try {
      setRoleChangingUserId(targetUser.id);
      setError(null);
      await adminService.updateUserRole(targetUser.id, newAdminStatus);
      setSuccessMsg(`User @${targetUser.uname} is now an ${roleTitle}.`);
      setTimeout(() => setSuccessMsg(null), 3500);
      await loadData();
    } catch (err: any) {
      setError(err.message || 'Failed to update user role.');
    } finally {
      setRoleChangingUserId(null);
    }
  };


  const handleAddTeam = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTeamName.trim()) return;

    try {
      setAddingTeam(true);
      setError(null);
      const createdName = newTeamName.trim();
      await adminService.createTeam(createdName, newTeamDesc.trim() || undefined);
      setNewTeamName('');
      setNewTeamDesc('');
      setSuccessMsg(`Team "${createdName}" created successfully.`);
      setTimeout(() => setSuccessMsg(null), 3500);
      await loadData();
    } catch (err: any) {
      setError(err.message || 'Failed to add team.');
    } finally {
      setAddingTeam(false);
    }
  };

  const startEditingTeam = (team: TeamItem) => {
    setEditingTeamId(team.id);
    setEditTeamName(team.name);
    setEditTeamDesc(team.description ?? '');
  };

  const handleSaveTeam = async (teamId: number) => {
    if (!editTeamName.trim()) return;
    try {
      setSavingTeamId(teamId);
      setError(null);
      const saved = await adminService.updateTeam(teamId, editTeamName.trim(), editTeamDesc.trim() || undefined);
      setEditingTeamId(null);
      setSuccessMsg(`Team updated to "${saved.name}" across all rosters, rules, sources, and alerts.`);
      setTimeout(() => setSuccessMsg(null), 3500);
      await loadData();
    } catch (err: any) {
      setError(err.message || 'Failed to update team.');
    } finally {
      setSavingTeamId(null);
    }
  };

  const handleDeleteTeam = async (id: number, name: string) => {
    if (!window.confirm(`Are you sure you want to delete team "${name}"?`)) return;

    try {
      setError(null);
      await adminService.deleteTeam(id);
      setSuccessMsg(`Team "${name}" deleted successfully.`);
      setTimeout(() => setSuccessMsg(null), 3500);
      await loadData();
    } catch (err: any) {
      setError(err.message || 'Failed to delete team.');
    }
  };

  const copyToClipboard = (code: string) => {
    navigator.clipboard.writeText(code);
    setCopiedCode(code);
    setTimeout(() => setCopiedCode(null), 2500);
  };

  return (
    <div className="space-y-8">
      {/* Header Banner */}
      <div className="glass-card glass-card--static border border-ios-green/30 p-6 relative overflow-hidden">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center space-x-2 mb-1">
              <span className="p-1 rounded bg-ios-green/15 text-ios-green border border-ios-green/30">
                <ShieldAlert className="w-4 h-4" />
              </span>
              <h2 className="text-xl font-semibold text-white">Lead Command Center</h2>
            </div>
            <p className="text-xs text-ink-muted">
              Manage teams, issue single-use invite codes, and grant Lead privileges.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            {/* Team selector for invite code */}
            <select
              value={inviteTeam}
              onChange={(e) => setInviteTeam(e.target.value)}
              title="Assign team/department for the invited employee"
              className="field px-2.5 py-1.5 text-xs"
            >
              <option value="">Team: User chooses</option>
              {teams.map((t) => (
                <option key={t.id} value={t.name}>
                  Team: {t.name}
                </option>
              ))}
            </select>

            {/* Role selector for invite code */}
            <div className="surface-well flex items-center p-0.5">
              <span className="px-2 text-[11px] font-medium text-slate-500">Role:</span>
              <button
                type="button"
                onClick={() => setInviteRole('member')}
                className={`px-2.5 py-1 text-xs font-semibold rounded transition ${
                  inviteRole === 'member'
                    ? 'btn-primary'
                    : 'text-ink-muted hover:text-slate-200'
                }`}
              >
                Member
              </button>
              <button
                type="button"
                onClick={() => setInviteRole('lead')}
                className={`px-2.5 py-1 text-xs font-semibold rounded transition ${
                  inviteRole === 'lead'
                    ? 'btn-primary'
                    : 'text-ink-muted hover:text-slate-200'
                }`}
              >
                Lead
              </button>
            </div>

            <button
              onClick={handleGenerateInvite}
              disabled={generating}
              className="btn-primary px-4 py-2 text-xs flex items-center space-x-1.5 active:scale-95"
            >
              <PlusCircle className="w-4 h-4" />
              <span>{generating ? 'Generating...' : `Generate ${inviteRole === 'lead' ? 'Lead' : 'Member'} Invite`}</span>
            </button>
          </div>
        </div>

        {/* Newly created code callout */}
        {newlyCreatedInvite && (
          <div className="mt-4 p-4 bg-emerald-500/10 border border-emerald-500/30 rounded-xl flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
              <div>
                <span className="text-xs text-emerald-300 font-semibold block">
                  New Single-Use {newlyCreatedInvite.role === 'lead' ? 'LEAD' : 'MEMBER'} Invite Code Ready
                  {newlyCreatedInvite.team ? ` (${newlyCreatedInvite.team})` : ''}:
                </span>
                <span className="text-lg font-mono font-semibold text-white tracking-wider">
                  {newlyCreatedInvite.code}
                </span>
              </div>
            </div>
            <button
              onClick={() => copyToClipboard(newlyCreatedInvite.code)}
              className="px-3 py-1.5 text-xs bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold rounded-lg flex items-center space-x-1 transition"
            >
              {copiedCode === newlyCreatedInvite.code ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
              <span>{copiedCode === newlyCreatedInvite.code ? 'Copied!' : 'Copy Code'}</span>
            </button>
          </div>
        )}

        {/* Alerts */}
        {successMsg && (
          <div className="mt-4 p-3 bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs rounded-xl">
            {successMsg}
          </div>
        )}
        {error && (
          <div className="mt-4 p-3 bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs rounded-xl">
            {error}
          </div>
        )}
      </div>

      {/* --- SECTION: TEAM MANAGEMENT --- */}
      <div className="glass-card glass-card--static p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-base font-semibold text-white flex items-center space-x-2">
              <Briefcase className="w-4 h-4 text-ios-green" />
              <span>Teams ({teams.length})</span>
            </h3>
            <p className="text-xs text-ink-muted">
              Single source of truth for teams across user accounts, People, Rules, Sources, and Alerts.
            </p>
          </div>
        </div>

        {/* Create Team Form */}
        <form onSubmit={handleAddTeam} className="surface-well mb-6 p-4 flex flex-col md:flex-row gap-3 items-end">
          <div className="flex-1 w-full">
            <label className="block text-xs font-semibold text-slate-300 mb-1">Team Name *</label>
            <input
              type="text"
              required
              value={newTeamName}
              onChange={(e) => setNewTeamName(e.target.value)}
              placeholder="e.g. Risk Management, Quantitative Research, Trading"
              className="field w-full px-3 py-2 text-sm placeholder-slate-600"
            />
          </div>
          <div className="flex-1 w-full">
            <label className="block text-xs font-semibold text-slate-300 mb-1">Description (optional)</label>
            <input
              type="text"
              value={newTeamDesc}
              onChange={(e) => setNewTeamDesc(e.target.value)}
              placeholder="Responsibilities and mandate"
              className="field w-full px-3 py-2 text-sm placeholder-slate-600"
            />
          </div>
          <button
            type="submit"
            disabled={addingTeam}
            className="btn-primary w-full md:w-auto px-4 py-2 text-sm flex items-center justify-center space-x-1.5 active:scale-95 shrink-0"
          >
            <FolderPlus className="w-4 h-4" />
            <span>{addingTeam ? 'Adding...' : 'Add Team'}</span>
          </button>
        </form>

        {/* Teams Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {teams.map((team) => {
            const isEditing = editingTeamId === team.id;
            const isSaving = savingTeamId === team.id;
            return (
              <div key={team.id} className="surface-well p-4 flex flex-col justify-between gap-3 group hover:border-slate-700 transition">
                {isEditing ? (
                  <div className="space-y-2">
                    <input
                      type="text"
                      value={editTeamName}
                      onChange={(e) => setEditTeamName(e.target.value)}
                      placeholder="Team name"
                      className="field w-full px-2.5 py-1.5 text-sm"
                    />
                    <input
                      type="text"
                      value={editTeamDesc}
                      onChange={(e) => setEditTeamDesc(e.target.value)}
                      placeholder="Description (optional)"
                      className="field w-full px-2.5 py-1.5 text-xs"
                    />
                    <div className="flex items-center justify-end gap-1.5">
                      <button
                        type="button"
                        onClick={() => setEditingTeamId(null)}
                        className="px-2 py-1 text-xs rounded-lg border border-white/10 text-slate-300 hover:text-white flex items-center gap-1"
                      >
                        <X className="w-3 h-3" />
                        Cancel
                      </button>
                      <button
                        type="button"
                        disabled={isSaving || !editTeamName.trim()}
                        onClick={() => handleSaveTeam(team.id)}
                        className="btn-primary px-2.5 py-1 text-xs disabled:opacity-50 flex items-center gap-1"
                      >
                        <Check className="w-3 h-3" />
                        {isSaving ? 'Saving...' : 'Save'}
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="font-semibold text-sm text-white truncate">{team.name}</div>
                      {team.description && (
                        <p className="text-xs text-ink-muted mt-1 line-clamp-2">{team.description}</p>
                      )}
                      <p className="text-[11px] font-mono text-ink-muted mt-2">
                        {team.people_count ?? 0} people · {team.rules_count ?? 0} rules · {team.user_count ?? 0} accounts
                      </p>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      <button
                        type="button"
                        onClick={() => startEditingTeam(team)}
                        title="Rename / edit team"
                        className="opacity-70 group-hover:opacity-100 p-1.5 text-ink-muted hover:text-ios-green hover:bg-ios-green/25 rounded-lg transition"
                      >
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDeleteTeam(team.id, team.name)}
                        title="Delete this team"
                        className="opacity-70 group-hover:opacity-100 p-1.5 text-ink-muted hover:text-rose-400 hover:bg-rose-500/10 rounded-lg transition"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
          {teams.length === 0 && (
            <div className="col-span-full py-6 text-center text-xs text-slate-500">
              No teams configured. Use the form above to add your first team.
            </div>
          )}
        </div>
      </div>

      {/* Grid: Invite Codes Table + Employees Roster */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Single-Use Invite Codes Table */}
        <div className="glass-card glass-card--static lg:col-span-2 overflow-hidden">
          <div className="p-5 border-b border-white/[0.08] flex items-center justify-between">
            <div>
              <h3 className="text-base font-semibold text-white flex items-center space-x-2">
                <Key className="w-4 h-4 text-ios-green" />
                <span>Single-Use Invite Codes</span>
              </h3>
              <p className="text-xs text-ink-muted">Each code expires immediately after a single registration.</p>
            </div>
            <span className="text-xs font-mono bg-white/[0.06] px-2.5 py-1 rounded border border-white/10 text-slate-300">
              {invites.filter((i) => !i.is_used).length} active / {invites.length} total
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm font-mono">
              <thead className="surface-well text-ink-muted text-xs font-semibold uppercase border-b font-sans">
                <tr>
                  <th className="px-5 py-3">Invite Code</th>
                  <th className="px-5 py-3">Role Granted</th>
                  <th className="px-5 py-3">Team</th>
                  <th className="px-5 py-3">Status</th>
                  <th className="px-5 py-3">Claimed By</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.06] text-xs">
                {invites.map((inv) => (
                  <tr key={inv.id} className="hover:bg-slate-800/40 transition">
                    <td className="px-5 py-3 font-semibold text-white tracking-wider">
                      {inv.code}
                    </td>
                    <td className="px-5 py-3 font-sans">
                      {inv.role === 'lead' || inv.is_admin_invite ? (
                        <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-ios-green/15 text-ios-green border border-ios-green/30">
                          <ShieldCheck className="w-3 h-3" />
                          <span>LEAD</span>
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-white/[0.06] text-ink-muted border border-white/10">
                          MEMBER
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-3 font-sans text-slate-300">
                      {inv.team ? (
                        <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-white/[0.06] text-slate-200 border border-white/10">
                          {inv.team}
                        </span>
                      ) : (
                        <span className="text-slate-500">—</span>
                      )}
                    </td>
                    <td className="px-5 py-3 font-sans">
                      {inv.is_used ? (
                        <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-white/[0.06] text-ink-muted border border-white/10">
                          USED
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                          ACTIVE
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-3 font-sans text-slate-300">
                      {inv.used_by_uname ? `@${inv.used_by_uname}` : '—'}
                    </td>
                  </tr>
                ))}
                {invites.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-5 py-8 text-center text-slate-500 font-sans">
                      No invite codes generated yet. Click "Generate Invite" above to create one.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Employees & Leads Roster */}
        <div className="glass-card glass-card--static overflow-hidden h-fit">
          <div className="p-5 border-b border-white/[0.08] flex items-center justify-between">
            <h3 className="text-base font-semibold text-white flex items-center space-x-2">
              <Users className="w-4 h-4 text-ios-green" />
              <span>Employees & Leads ({users.length})</span>
            </h3>
          </div>

          <div className="divide-y divide-white/[0.06] max-h-[550px] overflow-y-auto">
            {users.map((u) => {
              const isSelf = currentUser?.id === u.id;
              const isChanging = roleChangingUserId === u.id;

              return (
                <div key={u.id} className="p-4 hover:bg-slate-800/40 transition">
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center space-x-2">
                      <span className="text-sm font-semibold text-white font-sans">
                        @{u.uname}
                        {isSelf && <span className="ml-1 text-[10px] text-ink-muted font-normal">(You)</span>}
                      </span>
                      {u.is_admin ? (
                        <span className="text-[9px] px-1.5 py-0.2 rounded bg-ios-green/15 text-ios-green border border-ios-green/30 font-mono font-semibold">
                          LEAD
                        </span>
                      ) : (
                        <span className="text-[9px] px-1.5 py-0.2 rounded bg-white/[0.06] text-ink-muted border border-white/10 font-mono">
                          USER
                        </span>
                      )}
                    </div>
                    {(u.team ?? u.dzial) && (
                      <span className="text-[10px] px-2 py-0.5 rounded font-mono bg-white/[0.06] text-slate-300 border border-white/10">
                        {u.team ?? u.dzial}
                      </span>
                    )}
                  </div>

                  <div className="text-xs text-ink-muted font-mono">{u.email}</div>
                  {u.nrtel && <div className="text-[11px] text-slate-500 font-mono mt-0.5">{u.nrtel}</div>}

                  {/* Role promote / demote action */}
                  {!isSelf && (
                    <div className="mt-2.5 pt-2 border-t border-slate-800/80 flex justify-end">
                      {u.is_admin ? (
                        <button
                          onClick={() => handleToggleUserRole(u)}
                          disabled={isChanging}
                          className="px-2 py-1 text-[10px] font-sans bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30 rounded flex items-center space-x-1 transition"
                          title="Revoke Lead privileges from this user"
                        >
                          <UserX className="w-3 h-3" />
                          <span>{isChanging ? 'Updating...' : 'Revoke Lead'}</span>
                        </button>
                      ) : (
                        <button
                          onClick={() => handleToggleUserRole(u)}
                          disabled={isChanging}
                          className="px-2 py-1 text-[10px] font-sans bg-ios-green/15 hover:bg-ios-green/25 text-ios-green border border-ios-green/30 rounded flex items-center space-x-1 transition"
                          title="Grant Lead privileges to this user"
                        >
                          <Shield className="w-3 h-3" />
                          <span>{isChanging ? 'Updating...' : 'Make Lead'}</span>
                        </button>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

      </div>
    </div>
  );
};
