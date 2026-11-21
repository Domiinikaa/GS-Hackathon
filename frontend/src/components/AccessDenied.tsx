import React from 'react';
import { ShieldOff, ArrowLeft, Lock } from 'lucide-react';
import { User } from '../types';

interface AccessDeniedProps {
  user: User;
  onReturn: () => void;
}

export const AccessDenied: React.FC<AccessDeniedProps> = ({ user, onReturn }) => {
  return (
    <div className="min-h-[65vh] flex items-center justify-center p-4">
      <div className="w-full max-w-lg bg-slate-900 border border-rose-500/30 rounded-2xl p-8 md:p-10 shadow-2xl relative overflow-hidden text-center">
        {/* Top ambient accent */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-64 h-1 bg-gradient-to-r from-transparent via-rose-500/80 to-transparent blur-[1px]" />

        {/* Icon badge */}
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-rose-500/10 border border-rose-500/30 text-rose-400 mb-6 shadow-inner">
          <ShieldOff className="w-8 h-8" />
        </div>

        {/* Status pill */}
        <div className="mb-3">
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-mono font-bold tracking-wider uppercase bg-rose-500/10 text-rose-400 border border-rose-500/20">
            <Lock className="w-3 h-3" />
            <span>403 • Restricted Area</span>
          </span>
        </div>

        {/* Heading */}
        <h2 className="text-2xl font-bold text-white tracking-tight mb-2">
          Lead Access Required
        </h2>

        {/* Description */}
        <p className="text-sm text-slate-400 leading-relaxed mb-6">
          You are currently signed in as{' '}
          <span className="text-white font-semibold font-mono">@{user.uname}</span>{' '}
          with standard user permissions. The Lead &amp; Teams Command Center is
          restricted to authorized workspace leads.
        </p>

        {/* Info box */}
        <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-4 mb-7 text-left">
          <div className="text-xs text-slate-400 space-y-1">
            <div className="flex items-center justify-between">
              <span className="text-slate-500">Account</span>
              <span className="font-mono text-slate-300">{user.email}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-500">Current Role</span>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-slate-800 text-slate-300 border border-slate-700">
                STANDARD USER
              </span>
            </div>
            {user.dzial && (
              <div className="flex items-center justify-between">
                <span className="text-slate-500">Department</span>
                <span className="font-mono text-slate-300">{user.dzial}</span>
              </div>
            )}
          </div>
          <p className="text-[11px] text-slate-500 mt-3 pt-3 border-t border-slate-800/80">
            If you believe you should have access to this page, please contact your
            workspace lead to request elevated privileges.
          </p>
        </div>

        {/* Action button */}
        <button
          onClick={onReturn}
          className="inline-flex items-center justify-center gap-2 px-6 py-2.5 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-sm rounded-lg transition shadow-lg shadow-amber-500/10 active:scale-95"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Return to Alerts</span>
        </button>
      </div>
    </div>
  );
};
