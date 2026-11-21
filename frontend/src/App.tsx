import { useEffect, useState } from 'react';
import {
  Bell,
  BookOpen,
  Inbox,
  Plug,
  SlidersHorizontal,
  Users,
  Key,
  LogOut,
  RefreshCw,
  ShieldCheck
} from 'lucide-react';
import { User } from './types';
import { authService, authStorage } from './services/auth';
import { AuthScreen } from './components/AuthScreen';
import { AdminPanel } from './components/AdminPanel';
import { AccessDenied } from './components/AccessDenied';

import AlertsPage from './alerts/AlertsPage';
import RulesPage from './rules/RulesPage';
import PeoplePage from './people/PeoplePage';
import SourcesPage from './sources/SourcesPage';
import OutboxPage from './outbox/OutboxPage';
import RunbooksPage from './runbooks/RunbooksPage';

interface TabItem {
  id: string;
  label: string;
  icon: any;
  page: React.ComponentType;
  adminOnly?: boolean;
}

const BASE_TABS: TabItem[] = [
  { id: 'alerts', label: 'Alerts', icon: Bell, page: AlertsPage },
  { id: 'rules', label: 'Rules', icon: SlidersHorizontal, page: RulesPage },
  { id: 'people', label: 'People', icon: Users, page: PeoplePage },
  { id: 'sources', label: 'Sources', icon: Plug, page: SourcesPage },
  { id: 'runbooks', label: 'Runbooks', icon: BookOpen, page: RunbooksPage },
  { id: 'outbox', label: 'Outbox', icon: Inbox, page: OutboxPage },
  { id: 'admin', label: 'Admin & Invites', icon: Key, page: AdminPanel, adminOnly: true },
];

function getInitialTab(): string {
  const hash = window.location.hash.replace('#', '').split('/')[0];
  if (hash) return hash;
  const path = window.location.pathname.replace(/^\/+|\/+$/g, '');
  if (path === 'admin') return 'admin';
  return 'alerts';
}

export default function App() {
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [authChecking, setAuthChecking] = useState(true);
  const [activeTabId, setActiveTabId] = useState<string>(getInitialTab);

  // Check JWT session on load
  useEffect(() => {
    const initAuth = async () => {
      const token = authStorage.getToken();
      if (token) {
        try {
          const user = await authService.getMe();
          setCurrentUser(user);
        } catch {
          authStorage.clearToken();
        }
      }
      setAuthChecking(false);
    };
    initAuth();
  }, []);

  // Listen to hash changes
  useEffect(() => {
    const onHashChange = () => {
      const hash = window.location.hash.replace('#', '').split('/')[0];
      if (hash) setActiveTabId(hash);
    };
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  const handleLogout = () => {
    authService.logout();
    setCurrentUser(null);
    window.location.hash = '#alerts';
    setActiveTabId('alerts');
  };

  if (authChecking) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center text-slate-400">
        <RefreshCw className="w-6 h-6 animate-spin text-amber-500 mr-2" />
        <span>Verifying JWT session...</span>
      </div>
    );
  }

  // Unauthenticated: Show Login & Single-Use Invite Code Registration
  if (!currentUser) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
        <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur px-6 py-4 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <span className="w-8 h-8 rounded-lg bg-amber-500 flex items-center justify-center font-black text-slate-950">
              GS
            </span>
            <span className="text-lg font-bold tracking-tight text-white">
              Alerting <span className="text-amber-400">Portal</span>
            </span>
          </div>
          <span className="text-xs text-slate-400">Goldman Sachs Hackathon • Invite-Only Access</span>
        </header>

        <AuthScreen onSuccess={(user) => setCurrentUser(user)} />
      </div>
    );
  }

  // Filter tabs: Admin sees all tabs; Regular users NEVER see the admin tab
  const visibleTabs = BASE_TABS.filter((tab) => !tab.adminOnly || currentUser.is_admin);

  // Detect if a non-admin user navigated directly to the admin route
  const isUnauthorizedAdminRoute = activeTabId === 'admin' && !currentUser.is_admin;

  const currentTab = visibleTabs.find((t) => t.id === activeTabId) ?? visibleTabs[0];
  const PageComponent = currentTab.page;

  const handleReturnToAlerts = () => {
    if (window.location.pathname !== '/') {
      window.history.replaceState(null, '', '/#alerts');
    } else {
      window.location.hash = '#alerts';
    }
    setActiveTabId('alerts');
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans">
      {/* Top Navbar */}
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 h-14 flex items-center justify-between gap-4">
          
          {/* Brand & Tabs */}
          <div className="flex items-center gap-6 overflow-x-auto">
            <a href="#alerts" className="flex items-center gap-2 shrink-0">
              <span className="w-7 h-7 rounded-lg bg-amber-500 flex items-center justify-center font-black text-slate-950 text-xs shadow">
                GS
              </span>
              <span className="font-bold text-white tracking-tight">Alerting</span>
            </a>

            <nav className="flex items-center gap-1">
              {visibleTabs.map((t) => {
                const Icon = t.icon;
                const active = !isUnauthorizedAdminRoute && t.id === currentTab.id;
                const isAdminTab = t.adminOnly;

                return (
                  <a
                    key={t.id}
                    href={`#${t.id}`}
                    onClick={() => setActiveTabId(t.id)}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm shrink-0 transition ${
                      active
                        ? isAdminTab
                          ? 'bg-amber-500 text-slate-950 font-bold shadow'
                          : 'bg-slate-800 text-white font-medium'
                        : isAdminTab
                        ? 'text-amber-400/80 hover:text-amber-300 hover:bg-amber-500/10'
                        : 'text-slate-400 hover:text-white'
                    }`}
                  >
                    <Icon className="w-4 h-4" />
                    <span>{t.label}</span>
                  </a>
                );
              })}
            </nav>
          </div>

          {/* Profile & Controls */}
          <div className="flex items-center gap-3 shrink-0">
            <div className="text-right hidden sm:block">
              <div className="flex items-center justify-end space-x-1.5">
                <span className="text-xs font-semibold text-white">@{currentUser.uname}</span>
                {currentUser.is_admin && (
                  <span className="text-[9px] px-1.5 py-0.2 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40 font-mono font-bold">
                    ADMIN
                  </span>
                )}
              </div>
              <div className="text-[10px] text-slate-400">
                {currentUser.dzial ? `${currentUser.dzial} • ` : ''}{currentUser.email}
              </div>
            </div>

            <button
              onClick={handleLogout}
              title="Sign Out"
              className="p-1.5 rounded-lg bg-slate-800 hover:bg-rose-500/20 text-slate-400 hover:text-rose-400 border border-slate-700 transition"
            >
              <LogOut className="w-4 h-4" />
            </button>

            <a
              href="/docs"
              target="_blank"
              rel="noreferrer"
              className="text-xs text-slate-500 hover:text-white shrink-0 ml-1"
            >
              API docs
            </a>
          </div>

        </div>
      </header>

      {/* Main Content Area */}
      <main className="max-w-7xl mx-auto px-4 py-8">
        {isUnauthorizedAdminRoute ? (
          <AccessDenied user={currentUser} onReturn={handleReturnToAlerts} />
        ) : activeTabId === 'admin' ? (
          <AdminPanel currentUser={currentUser} />
        ) : (
          <PageComponent />
        )}
      </main>
    </div>
  );
}
