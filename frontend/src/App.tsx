// Szkielet aplikacji: menu zakładek. Każda zakładka = ekran z folderu właściciela (TEAM.md).
// Ten plik zmieniamy tylko przy dodawaniu nowej zakładki.
import { useEffect, useState } from 'react';
import { Bell, BookOpen, Inbox, Plug, SlidersHorizontal, Users } from 'lucide-react';
import AlertsPage from './alerts/AlertsPage';
import RulesPage from './rules/RulesPage';
import PeoplePage from './people/PeoplePage';
import SourcesPage from './sources/SourcesPage';
import OutboxPage from './outbox/OutboxPage';
import RunbooksPage from './runbooks/RunbooksPage';

const TABS = [
  { id: 'alerts', label: 'Alerts', icon: Bell, page: AlertsPage },
  { id: 'rules', label: 'Rules', icon: SlidersHorizontal, page: RulesPage },
  { id: 'people', label: 'People', icon: Users, page: PeoplePage },
  { id: 'sources', label: 'Sources', icon: Plug, page: SourcesPage },
  { id: 'runbooks', label: 'Runbooks', icon: BookOpen, page: RunbooksPage },
  { id: 'outbox', label: 'Outbox', icon: Inbox, page: OutboxPage },
] as const;

function currentTab() {
  const id = window.location.hash.replace('#', '');
  return TABS.find((t) => t.id === id) ?? TABS[0];
}

export default function App() {
  const [tab, setTab] = useState(currentTab);

  useEffect(() => {
    const onChange = () => setTab(currentTab());
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);

  const Page = tab.page;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans">
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-4 h-14 flex items-center gap-6 overflow-x-auto">
          <a href="#alerts" className="flex items-center gap-2 shrink-0">
            <span className="w-7 h-7 rounded-lg bg-amber-500 flex items-center justify-center font-black text-slate-950 text-xs">GS</span>
            <span className="font-bold text-white">Alerting</span>
          </a>
          <nav className="flex gap-1">
            {TABS.map((t) => {
              const Icon = t.icon;
              const active = t.id === tab.id;
              return (
                <a key={t.id} href={`#${t.id}`}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm shrink-0 transition ${
                    active ? 'bg-slate-800 text-white' : 'text-slate-400 hover:text-white'}`}>
                  <Icon className="w-4 h-4" />{t.label}
                </a>
              );
            })}
          </nav>
          <a href="/docs" target="_blank" rel="noreferrer" className="ml-auto text-xs text-slate-500 hover:text-white shrink-0">API docs</a>
        </div>
      </header>
      <main className="max-w-6xl mx-auto px-4 py-8">
        <Page />
      </main>
    </div>
  );
}
