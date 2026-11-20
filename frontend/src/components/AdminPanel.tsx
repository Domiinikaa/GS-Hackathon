import React, { useState, useEffect } from 'react';
import { adminService, departmentService } from '../services/auth';
import { InviteCode, User, DepartmentItem } from '../types';
import {
  Key,
  PlusCircle,
  Check,
  Copy,
  Users,
  RefreshCw,
  ShieldAlert,
  CheckCircle2,
  Briefcase,
  Trash2,
  FolderPlus
} from 'lucide-react';

export const AdminPanel: React.FC = () => {
  const [invites, setInvites] = useState<InviteCode[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [departments, setDepartments] = useState<DepartmentItem[]>([]);
  const [loading, setLoading] = useState(false);

  // Invite code generation
  const [generating, setGenerating] = useState(false);
  const [newlyCreatedCode, setNewlyCreatedCode] = useState<string | null>(null);
  const [copiedCode, setCopiedCode] = useState<string | null>(null);

  // New department state
  const [newDeptName, setNewDeptName] = useState('');
  const [newDeptDesc, setNewDeptDesc] = useState('');
  const [addingDept, setAddingDept] = useState(false);

  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [invitesRes, usersRes, deptsRes] = await Promise.all([
        adminService.listInvites(),
        adminService.listUsers(),
        departmentService.getDepartments(),
      ]);
      setInvites(invitesRes);
      setUsers(usersRes);
      setDepartments(deptsRes);
    } catch (err: any) {
      setError(err.message || 'Error loading administrator data.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleGenerateInvite = async () => {
    try {
      setGenerating(true);
      setError(null);
      const res = await adminService.createInvite();
      setNewlyCreatedCode(res.code);
      await loadData();
    } catch (err: any) {
      setError(err.message || 'Failed to generate invite code.');
    } finally {
      setGenerating(false);
    }
  };

  const handleAddDepartment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newDeptName.trim()) return;

    try {
      setAddingDept(true);
      setError(null);
      await adminService.createDepartment(newDeptName.trim(), newDeptDesc.trim() || undefined);
      setNewDeptName('');
      setNewDeptDesc('');
      setSuccessMsg(`Department "${newDeptName.trim()}" created successfully.`);
      setTimeout(() => setSuccessMsg(null), 3500);
      await loadData();
    } catch (err: any) {
      setError(err.message || 'Failed to add department.');
    } finally {
      setAddingDept(false);
    }
  };

  const handleDeleteDepartment = async (id: number, name: string) => {
    if (!window.confirm(`Are you sure you want to delete department "${name}"?`)) return;

    try {
      setError(null);
      await adminService.deleteDepartment(id);
      setSuccessMsg(`Department "${name}" deleted successfully.`);
      setTimeout(() => setSuccessMsg(null), 3500);
      await loadData();
    } catch (err: any) {
      setError(err.message || 'Failed to delete department.');
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
      <div className="bg-slate-900 border border-amber-500/30 rounded-2xl p-6 relative overflow-hidden">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center space-x-2 mb-1">
              <span className="p-1 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30">
                <ShieldAlert className="w-4 h-4" />
              </span>
              <h2 className="text-xl font-bold text-white">Administrator Command Center</h2>
            </div>
            <p className="text-xs text-slate-400">
              Manage dynamic company departments and issue single-use registration invite codes.
            </p>
          </div>

          <div className="flex items-center space-x-3">
            <button
              onClick={loadData}
              disabled={loading}
              className="px-3 py-2 text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg border border-slate-700 flex items-center space-x-1.5 transition"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              <span>Refresh</span>
            </button>

            <button
              onClick={handleGenerateInvite}
              disabled={generating}
              className="px-4 py-2 text-xs bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded-lg flex items-center space-x-1.5 transition shadow active:scale-95"
            >
              <PlusCircle className="w-4 h-4" />
              <span>{generating ? 'Generating...' : 'Generate Invite Code'}</span>
            </button>
          </div>
        </div>

        {/* Newly created code callout */}
        {newlyCreatedCode && (
          <div className="mt-4 p-4 bg-emerald-500/10 border border-emerald-500/30 rounded-xl flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
              <div>
                <span className="text-xs text-emerald-300 font-semibold block">New Single-Use Invite Code Ready:</span>
                <span className="text-lg font-mono font-bold text-white tracking-wider">{newlyCreatedCode}</span>
              </div>
            </div>
            <button
              onClick={() => copyToClipboard(newlyCreatedCode)}
              className="px-3 py-1.5 text-xs bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold rounded-lg flex items-center space-x-1 transition"
            >
              {copiedCode === newlyCreatedCode ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
              <span>{copiedCode === newlyCreatedCode ? 'Copied!' : 'Copy Code'}</span>
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

      {/* --- SECTION: DEPARTMENT MANAGEMENT --- */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-base font-bold text-white flex items-center space-x-2">
              <Briefcase className="w-4 h-4 text-amber-400" />
              <span>Company Departments ({departments.length})</span>
            </h3>
            <p className="text-xs text-slate-400">
              Dynamic organization taxonomy. Any additions or removals immediately update the registration directory.
            </p>
          </div>
        </div>

        {/* Create Department Form */}
        <form onSubmit={handleAddDepartment} className="mb-6 bg-slate-950 p-4 rounded-xl border border-slate-800 flex flex-col md:flex-row gap-3 items-end">
          <div className="flex-1 w-full">
            <label className="block text-xs font-semibold text-slate-300 mb-1">Department Name *</label>
            <input
              type="text"
              required
              value={newDeptName}
              onChange={(e) => setNewDeptName(e.target.value)}
              placeholder="e.g. Risk Management, ESG, Quantitative Research, Trading"
              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-amber-500"
            />
          </div>
          <div className="flex-1 w-full">
            <label className="block text-xs font-semibold text-slate-300 mb-1">Description (optional)</label>
            <input
              type="text"
              value={newDeptDesc}
              onChange={(e) => setNewDeptDesc(e.target.value)}
              placeholder="Responsibilities and mandate"
              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-amber-500"
            />
          </div>
          <button
            type="submit"
            disabled={addingDept}
            className="w-full md:w-auto px-4 py-2 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-sm rounded-lg flex items-center justify-center space-x-1.5 transition active:scale-95 shrink-0"
          >
            <FolderPlus className="w-4 h-4" />
            <span>{addingDept ? 'Adding...' : 'Add Department'}</span>
          </button>
        </form>

        {/* Department Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {departments.map((dept) => (
            <div key={dept.id} className="bg-slate-950/70 border border-slate-800 p-4 rounded-xl flex items-start justify-between group hover:border-slate-700 transition">
              <div>
                <div className="flex items-center space-x-2">
                  <span className="font-bold text-sm text-white">{dept.name}</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 font-mono">
                    {dept.user_count ?? 0} users
                  </span>
                </div>
                {dept.description && (
                  <p className="text-xs text-slate-400 mt-1 line-clamp-2">{dept.description}</p>
                )}
              </div>
              <button
                onClick={() => handleDeleteDepartment(dept.id, dept.name)}
                title="Delete this department"
                className="opacity-60 group-hover:opacity-100 p-1.5 text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 rounded-lg transition"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
          {departments.length === 0 && (
            <div className="col-span-full py-6 text-center text-xs text-slate-500">
              No departments configured. Use the form above to add your first department.
            </div>
          )}
        </div>
      </div>

      {/* Grid: Invite Codes Table + Employees Roster */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Single-Use Invite Codes Table */}
        <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
          <div className="p-5 border-b border-slate-800 flex items-center justify-between">
            <div>
              <h3 className="text-base font-bold text-white flex items-center space-x-2">
                <Key className="w-4 h-4 text-amber-400" />
                <span>Single-Use Invite Codes</span>
              </h3>
              <p className="text-xs text-slate-400">Each code expires immediately after a single successful registration.</p>
            </div>
            <span className="text-xs font-mono bg-slate-800 px-2.5 py-1 rounded border border-slate-700 text-slate-300">
              {invites.filter((i) => !i.is_used).length} active / {invites.length} total
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm font-mono">
              <thead className="bg-slate-950 text-slate-400 text-xs font-semibold uppercase border-b border-slate-800 font-sans">
                <tr>
                  <th className="px-5 py-3">Invite Code</th>
                  <th className="px-5 py-3">Status</th>
                  <th className="px-5 py-3">Created</th>
                  <th className="px-5 py-3">Claimed By</th>
                  <th className="px-5 py-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800 text-xs">
                {invites.map((inv) => (
                  <tr key={inv.id} className="hover:bg-slate-800/40 transition">
                    <td className="px-5 py-3 font-bold text-white tracking-wider">
                      {inv.code}
                    </td>
                    <td className="px-5 py-3 font-sans">
                      {inv.is_used ? (
                        <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-800 text-slate-400 border border-slate-700">
                          USED
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                          ACTIVE
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-3 text-slate-400">
                      {new Date(inv.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-5 py-3 font-sans text-slate-300">
                      {inv.used_by_uname ? `@${inv.used_by_uname}` : '—'}
                    </td>
                    <td className="px-5 py-3 text-right">
                      {!inv.is_used && (
                        <button
                          onClick={() => copyToClipboard(inv.code)}
                          className="px-2 py-1 text-[11px] font-sans bg-slate-800 hover:bg-slate-700 text-slate-300 rounded border border-slate-700 transition"
                        >
                          {copiedCode === inv.code ? 'Copied' : 'Copy'}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
                {invites.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-5 py-8 text-center text-slate-500 font-sans">
                      No invite codes generated yet. Click "Generate Invite Code" above to create one.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Employees Roster */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden h-fit">
          <div className="p-5 border-b border-slate-800 flex items-center justify-between">
            <h3 className="text-base font-bold text-white flex items-center space-x-2">
              <Users className="w-4 h-4 text-amber-400" />
              <span>Employees ({users.length})</span>
            </h3>
          </div>

          <div className="divide-y divide-slate-800 max-h-[500px] overflow-y-auto">
            {users.map((u) => (
              <div key={u.id} className="p-4 hover:bg-slate-800/40 transition">
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center space-x-2">
                    <span className="text-sm font-bold text-white font-sans">@{u.uname}</span>
                    {u.is_admin && (
                      <span className="text-[9px] px-1.5 py-0.2 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40 font-mono font-bold">
                        ADMIN
                      </span>
                    )}
                  </div>
                  {u.dzial && (
                    <span className="text-[10px] px-2 py-0.5 rounded font-mono bg-slate-800 text-slate-300 border border-slate-700">
                      {u.dzial}
                    </span>
                  )}
                </div>
                <div className="text-xs text-slate-400 font-mono">{u.email}</div>
                {u.nrtel && <div className="text-[11px] text-slate-500 font-mono mt-0.5">{u.nrtel}</div>}
              </div>
            ))}
          </div>
        </div>

      </div>
    </div>
  );
};
