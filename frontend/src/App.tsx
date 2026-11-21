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
  { id: 'admin', label: 'Lead & Teams', icon: Key, page: AdminPanel, adminOnly: true },
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
        <RefreshCw className="w-5 h-5 animate-spin text-gs-gold mr-2" />
        <span>Checking your session</span>
      </div>
    );
  }

  // Unauthenticated: Show Login & Single-Use Invite Code Registration
  if (!currentUser) {
    return (
      <div className="min-h-screen flex flex-col">
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
      {/* Translucent iOS-style navigation bar */}
      <header className="sticky top-0 z-50 bg-[rgba(22,22,24,0.78)] backdrop-blur-2xl backdrop-saturate-[1.8] shadow-[inset_0_-0.5px_0_rgba(84,84,88,0.65)]">
        <div className="max-w-5xl mx-auto h-14 px-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-5 min-w-0">
            <a href="#alerts" onClick={() => setActiveTabId('alerts')} className="shrink-0 rounded-md">
              <Brand />
            </a>

            <nav aria-label="Main" className="flex items-center gap-0.5 overflow-x-auto min-w-0 [scrollbar-width:none]">
              {visibleTabs.map((t) => {
                const Icon = t.icon;
                const active = !isUnauthorizedAdminRoute && t.id === currentTab.id;
                return (
                  <a
                    key={t.id}
                    href={`#${t.id}`}
                    onClick={() => setActiveTabId(t.id)}
                    aria-current={active ? 'page' : undefined}
                    className={`flex items-center gap-1.5 px-2.5 h-9 rounded-lg text-[14px] shrink-0 transition-colors ${
                      active ? 'text-ios-blue font-semibold' : 'text-ink-muted hover:text-white'
                    }`}
                  >
                    <Icon className="w-[18px] h-[18px]" strokeWidth={active ? 2.3 : 2} />
                    <span>{t.label}</span>
                  </a>
                );
              })}
            </nav>
          </div>

          <div className="flex items-center gap-3 shrink-0">
            <MoodIndicator mood={mood} onOpen={() => setActiveTabId('alerts')} />
            <span className="hidden md:block text-[14px] text-ink-muted">
              {currentUser.uname}{currentUser.is_admin && ', lead'}
            </span>
            <button onClick={handleLogout} title="Sign out" aria-label="Sign out"
              className="w-9 h-9 rounded-full flex items-center justify-center text-ios-blue hover:bg-white/[0.08] transition-colors">
              <LogOut className="w-[18px] h-[18px]" />
            </button>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="max-w-5xl mx-auto px-4 pt-6 pb-16">
        {isUnauthorizedAdminRoute ? (
          <AccessDenied user={currentUser} onReturn={handleReturnToAlerts} />
        ) : currentTab.id === 'admin' ? (
          <AdminPanel currentUser={currentUser} />
        ) : currentTab.id === 'alerts' ? (
          <AlertsPage currentUser={currentUser} />
        ) : currentTab.id === 'people' ? (
          <PeoplePage currentUser={currentUser} />
        ) : (
          <PageComponent />
        )}
      </main>
    </div>
  );
}

function Brand() {
  return (
    <span className="flex items-center gap-2 text-[16px] font-semibold text-white">
      <span className="w-7 h-7 rounded-[8px] bg-ios-blue flex items-center justify-center text-[12px] font-bold">GS</span>
      Alerting
    </span>
  );
}

const MOOD_DOT: Record<SystemMood['mood'], string> = {
  idle: 'bg-ink-faint',
  clear: 'bg-ios-green',
  warning: 'bg-ios-orange',
  critical: 'bg-ios-red',
};

// Shows at a glance whether anything urgent is open.
function MoodIndicator({ mood, onOpen }: { mood: SystemMood; onOpen: () => void }) {
  return (
    <a href="#alerts" onClick={onOpen} aria-live="polite"
      className="hidden sm:flex items-center gap-1.5 text-[14px] text-white hover:opacity-80 transition-opacity">
      <span className={`w-2 h-2 rounded-full ${MOOD_DOT[mood.mood]}`} />
      {describeMood(mood)}
    </a>
  );
}
