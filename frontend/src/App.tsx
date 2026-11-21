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
} from 'lucide-react';
import { User } from './types';
import LivingBackdrop from './shared/LivingBackdrop';
import { useLiquidGlass } from './shared/useLiquidGlass';
import { describeMood, useSystemMood, type SystemMood } from './shared/useSystemMood';
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
  { id: 'admin', label: 'Admin & Teams', icon: Key, page: AdminPanel, adminOnly: true },
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
  const mood = useSystemMood(currentUser !== null);
  const navGlass = useLiquidGlass<HTMLElement>();
  const signOutGlass = useLiquidGlass<HTMLButtonElement>();

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
      <div className="min-h-screen flex items-center justify-center text-ink-muted">
        <LivingBackdrop />
        <RefreshCw className="w-5 h-5 animate-spin text-gs-gold mr-2" />
        <span>Checking your session</span>
      </div>
    );
  }

  // Unauthenticated: Show Login & Single-Use Invite Code Registration
  if (!currentUser) {
    return (
      <div className="min-h-screen flex flex-col">
        <LivingBackdrop />
        <header className="px-6 py-5 flex items-center justify-between">
          <Brand />
          <span className="text-xs text-ink-muted">Invite-only access</span>
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

  const team = currentUser.team ?? currentUser.dzial;

  return (
    <div className="min-h-screen">
      <LivingBackdrop />

      {/* Floating glass navigation bar */}
      <div className="sticky top-0 z-50 px-3 pt-3 sm:px-4">
        <header ref={navGlass} className="glass glass--bar max-w-7xl mx-auto h-14 !rounded-full pl-5 pr-2 flex items-center justify-between gap-4">
          <div className="flex items-center gap-6 min-w-0">
            <a href="#alerts" onClick={() => setActiveTabId('alerts')} className="shrink-0 rounded-full">
              <Brand />
            </a>

            <nav aria-label="Main" className="flex items-center gap-1 overflow-x-auto min-w-0 [scrollbar-width:none]">
              {visibleTabs.map((t) => {
                const Icon = t.icon;
                const active = !isUnauthorizedAdminRoute && t.id === currentTab.id;
                return (
                  <a
                    key={t.id}
                    href={`#${t.id}`}
                    onClick={() => setActiveTabId(t.id)}
                    aria-current={active ? 'page' : undefined}
                    className={`relative flex items-center gap-1.5 px-3 py-2 rounded-full text-sm shrink-0 transition-colors ${
                      active ? 'text-ink font-semibold' : 'text-ink-muted hover:text-ink'
                    }`}
                  >
                    <Icon className={`w-4 h-4 ${active ? 'text-gs-gold' : ''}`} />
                    <span>{t.label}</span>
                    {active && (
                      <span className="absolute left-3 right-3 -bottom-0.5 h-0.5 rounded-full bg-gs-gold" />
                    )}
                  </a>
                );
              })}
            </nav>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <MoodIndicator mood={mood} onOpen={() => setActiveTabId('alerts')} />

            <div className="text-right hidden md:block px-2 leading-tight">
              <div className="text-sm font-semibold text-ink">
                @{currentUser.uname}
                {currentUser.is_admin && <span className="ml-1.5 text-xs font-medium text-gs-gold">Admin</span>}
              </div>
              {team && <div className="text-xs text-ink-muted">{team}</div>}
            </div>

            <a
              href="/docs"
              target="_blank"
              rel="noreferrer"
              className="hidden lg:block text-xs text-ink-muted hover:text-ink px-2"
            >
              API docs
            </a>

            <button
              ref={signOutGlass}
              onClick={handleLogout}
              title="Sign out"
              aria-label="Sign out"
              className="glass !rounded-full !shadow-none w-10 h-10 flex items-center justify-center text-ink-muted hover:text-signal-critical"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </header>
      </div>

      {/* Main Content Area */}
      <main className="max-w-7xl mx-auto px-4 py-8">
        {isUnauthorizedAdminRoute ? (
          <AccessDenied user={currentUser} onReturn={handleReturnToAlerts} />
        ) : currentTab.id === 'admin' ? (
          <AdminPanel currentUser={currentUser} />
        ) : currentTab.id === 'alerts' ? (
          <AlertsPage currentUser={currentUser} />
        ) : (
          <PageComponent />
        )}
      </main>
    </div>
  );
}

function Brand() {
  return (
    <span className="flex items-baseline gap-1.5 text-[17px] tracking-tight">
      <span className="font-bold text-gs-gold">GS</span>
      <span className="font-semibold text-ink">Alerting</span>
    </span>
  );
}

const MOOD_DOT: Record<SystemMood['mood'], string> = {
  idle: 'bg-ink-muted',
  clear: 'bg-signal-clear',
  warning: 'bg-signal-warning',
  critical: 'bg-signal-critical',
};

// Names what the backdrop glow means, so color is never the only signal.
function MoodIndicator({ mood, onOpen }: { mood: SystemMood; onOpen: () => void }) {
  return (
    <a
      href="#alerts"
      onClick={onOpen}
      aria-live="polite"
      className="glass-chip h-10 px-3.5 hidden sm:flex items-center gap-2 text-sm text-ink"
    >
      <span className="relative flex w-2 h-2">
        {mood.mood === 'critical' && (
          <span className="absolute inset-0 rounded-full bg-signal-critical opacity-60 motion-safe:animate-ping" />
        )}
        <span className={`relative w-2 h-2 rounded-full ${MOOD_DOT[mood.mood]}`} />
      </span>
      {describeMood(mood)}
    </a>
  );
}
