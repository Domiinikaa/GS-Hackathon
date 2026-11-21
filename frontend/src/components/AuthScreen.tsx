import React, { useState, useEffect } from 'react';
import { authService, teamService } from '../services/auth';
import { User, TeamItem } from '../types';
import { Lock, Mail, User as UserIcon, Phone, Briefcase, ArrowRight, ShieldCheck, Key } from 'lucide-react';

interface AuthScreenProps {
  onSuccess: (user: User) => void;
}

export const AuthScreen: React.FC<AuthScreenProps> = ({ onSuccess }) => {
  const [isRegister, setIsRegister] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Dynamic teams fetched from database
  const [teams, setTeams] = useState<TeamItem[]>([]);

  // Form fields
  const [uname, setUname] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [inviteCode, setInviteCode] = useState('');
  const [nrtel, setNrtel] = useState('');
  const [team, setTeam] = useState('');

  useEffect(() => {
    teamService.getTeams().then((list) => {
      setTeams(list);
    });
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      if (isRegister) {
        if (!uname.trim() || !email.trim() || !password || !confirmPassword || !inviteCode.trim()) {
          setError('Username, Email, Password, Password Confirmation, and Invite Code are required.');
          setLoading(false);
          return;
        }
        if (password !== confirmPassword) {
          setError('Passwords do not match. Please verify your password.');
          setLoading(false);
          return;
        }
        const res = await authService.register({
          uname: uname.trim(),
          email: email.trim(),
          password,
          confirm_password: confirmPassword,
          invite_code: inviteCode.trim(),
          nrtel: nrtel.trim() || undefined,
          team: team || undefined,
        });
        onSuccess(res.user);
      } else {
        if (!uname.trim() || !password) {
          setError('Please enter your username/email and password.');
          setLoading(false);
          return;
        }
        const res = await authService.login(uname.trim(), password);
        onSuccess(res.user);
      }
    } catch (err: any) {
      setError(err.message || 'Authentication error.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-[80vh] flex items-center justify-center p-4">
      <div className="glass-card glass-card--static w-full max-w-md p-8 relative overflow-hidden">
        {/* Glow accent */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-48 h-1 bg-amber-500/80 rounded-full blur-[2px]" />

        {/* Header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400 mb-3">
            <ShieldCheck className="w-6 h-6" />
          </div>
          <h2 className="text-3xl font-semibold tracking-tight text-white tracking-tight">
            {isRegister ? 'Register with Invite Code' : 'Sign In to Portal'}
          </h2>
          <p className="text-xs text-ink-muted mt-1">
            {isRegister
              ? 'Single-use invite code required from your Administrator'
              : 'Enter your credentials to access your private dashboard'}
          </p>
        </div>

        {/* Mode Toggle Buttons */}
        <div className="surface-well flex p-1 mb-6">
          <button
            type="button"
            onClick={() => { setIsRegister(false); setError(null); setConfirmPassword(''); }}
            className={`flex-1 py-2 text-xs font-semibold rounded-md transition ${
              !isRegister ? 'btn-primary' : 'text-ink-muted hover:text-white'
            }`}
          >
            Sign In
          </button>
          <button
            type="button"
            onClick={() => { setIsRegister(true); setError(null); setConfirmPassword(''); }}
            className={`flex-1 py-2 text-xs font-semibold rounded-md transition ${
              isRegister ? 'btn-primary' : 'text-ink-muted hover:text-white'
            }`}
          >
            Register with Code
          </button>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="mb-4 p-3 bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs rounded-lg">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Uname */}
          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1">
              Username <span className="text-amber-400">*</span>
            </label>
            <div className="relative">
              <UserIcon className="w-4 h-4 text-slate-500 absolute left-3 top-3" />
              <input
                type="text"
                required
                value={uname}
                onChange={(e) => setUname(e.target.value)}
                placeholder={isRegister ? 'e.g. jsmith' : 'username or email'}
                className="field w-full pl-9 pr-3 py-2 text-sm placeholder-slate-600"
              />
            </div>
          </div>

          {/* Email */}
          {isRegister && (
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">
                Email Address <span className="text-amber-400">*</span>
              </label>
              <div className="relative">
                <Mail className="w-4 h-4 text-slate-500 absolute left-3 top-3" />
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="e.g. jsmith@goldmansachs.com"
                  className="field w-full pl-9 pr-3 py-2 text-sm placeholder-slate-600"
                />
              </div>
            </div>
          )}

          {/* Password */}
          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1">
              Password <span className="text-amber-400">*</span>
            </label>
            <div className="relative">
              <Lock className="w-4 h-4 text-slate-500 absolute left-3 top-3" />
              <input
                type="password"
                required
                minLength={6}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="field w-full pl-9 pr-3 py-2 text-sm placeholder-slate-600"
              />
            </div>
          </div>

          {/* Confirm Password (Registration only) */}
          {isRegister && (
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">
                Confirm Password <span className="text-amber-400">*</span>
              </label>
              <div className="relative">
                <Lock className="w-4 h-4 text-slate-500 absolute left-3 top-3" />
                <input
                  type="password"
                  required
                  minLength={6}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Repeat password"
                  className="field w-full pl-9 pr-3 py-2 text-sm placeholder-slate-600"
                />
              </div>
            </div>
          )}

          {/* Registration fields */}
          {isRegister && (
            <>
              {/* Single-Use Invite Code */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-xs font-medium text-amber-400">
                    Invite Code <span className="text-amber-400">*</span>
                  </label>
                  <span className="text-[10px] text-slate-500">from Admin</span>
                </div>
                <div className="relative">
                  <Key className="w-4 h-4 text-amber-500 absolute left-3 top-3" />
                  <input
                    type="text"
                    required
                    value={inviteCode}
                    onChange={(e) => setInviteCode(e.target.value.toUpperCase())}
                    placeholder="e.g. GS-XXXX-XXXX"
                    className="field w-full border-amber-500/40 pl-9 pr-3 py-2 text-sm placeholder-slate-600 font-mono tracking-wider uppercase"
                  />
                </div>
              </div>

              {/* Phone */}
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Phone Number <span className="text-slate-500 text-[10px]">(optional)</span>
                </label>
                <div className="relative">
                  <Phone className="w-4 h-4 text-slate-500 absolute left-3 top-3" />
                  <input
                    type="tel"
                    value={nrtel}
                    onChange={(e) => setNrtel(e.target.value)}
                    placeholder="+1 (212) 555-0199"
                    className="field w-full pl-9 pr-3 py-2 text-sm placeholder-slate-600"
                  />
                </div>
              </div>

              {/* Team */}
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Team <span className="text-slate-500 text-[10px]">(optional)</span>
                </label>
                <div className="relative">
                  <Briefcase className="w-4 h-4 text-slate-500 absolute left-3 top-3" />
                  <select
                    value={team}
                    onChange={(e) => setTeam(e.target.value)}
                    className="field w-full pl-9 pr-3 py-2 text-sm"
                  >
                    <option value="">Select team...</option>
                    {teams.map((t) => (
                      <option key={t.id} value={t.name}>
                        {t.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            </>
          )}

          {/* Submit */}
          <button
            type="submit"
            disabled={loading}
            className="btn-primary w-full py-2.5 text-sm flex items-center justify-center space-x-2 shadow-amber-500/10 active:scale-95"
          >
            <span>{loading ? 'Processing...' : (isRegister ? 'Complete Registration' : 'Sign In')}</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </form>
      </div>
    </div>
  );
};
