import React, { useState, useEffect } from 'react';
import { Item, StatsResponse } from './types';
import { PlusCircle, Trash2, TrendingUp, RefreshCw, Layers, DollarSign } from 'lucide-react';

export default function App() {
  const [items, setItems] = useState<Item[]>([]);
  const [statsData, setStatsData] = useState<StatsResponse | null>(null);
  const [loading, setLoading] = useState(true);

  // Form state
  const [title, setTitle] = useState('');
  const [category, setCategory] = useState('Equity');
  const [value, setValue] = useState('100.0');
  const [description, setDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [itemsRes, statsRes] = await Promise.all([
        fetch('/api/items'),
        fetch('/api/stats'),
      ]);
      if (itemsRes.ok) setItems(await itemsRes.json());
      if (statsRes.ok) setStatsData(await statsRes.json());
    } catch (err) {
      console.error('Failed to fetch data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleAddItem = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;

    try {
      setSubmitting(true);
      const res = await fetch('/api/items', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title,
          category,
          value: parseFloat(value) || 0,
          description,
        }),
      });

      if (res.ok) {
        setTitle('');
        setDescription('');
        await fetchData();
      }
    } catch (err) {
      console.error('Error adding item:', err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      {/* Navbar */}
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-4 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <span className="w-8 h-8 rounded-lg bg-amber-500 flex items-center justify-center font-black text-slate-950">
              GS
            </span>
            <span className="text-lg font-bold tracking-tight text-white">
              QuantFlow <span className="text-amber-400">React + TSX</span>
            </span>
            <span className="text-xs bg-amber-500/10 text-amber-400 border border-amber-500/30 px-2 py-0.5 rounded font-mono">
              FastAPI Backend
            </span>
          </div>

          <div className="flex items-center space-x-4">
            <button
              onClick={fetchData}
              className="flex items-center space-x-1.5 text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 px-3 py-1.5 rounded-lg border border-slate-700 transition"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              <span>Refresh</span>
            </button>
            <a
              href="/docs"
              target="_blank"
              rel="noreferrer"
              className="text-xs text-slate-400 hover:text-white transition"
            >
              API Docs (/docs)
            </a>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 max-w-6xl w-full mx-auto px-4 py-8 space-y-8">
        {/* Metric Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="bg-slate-900 border border-slate-800 p-5 rounded-xl">
            <div className="flex items-center justify-between text-slate-400 text-xs font-semibold uppercase">
              <span>Total Items</span>
              <Layers className="w-4 h-4 text-slate-500" />
            </div>
            <p className="text-2xl font-bold font-mono text-white mt-2">
              {statsData?.stats.count ?? items.length}
            </p>
          </div>

          <div className="bg-slate-900 border border-slate-800 p-5 rounded-xl">
            <div className="flex items-center justify-between text-slate-400 text-xs font-semibold uppercase">
              <span>Total Value</span>
              <DollarSign className="w-4 h-4 text-amber-500" />
            </div>
            <p className="text-2xl font-bold font-mono text-amber-400 mt-2">
              ${statsData?.stats.total_value?.toLocaleString('en-US', { minimumFractionDigits: 2 }) ?? '0.00'}
            </p>
          </div>

          <div className="bg-slate-900 border border-slate-800 p-5 rounded-xl">
            <div className="flex items-center justify-between text-slate-400 text-xs font-semibold uppercase">
              <span>Average Value</span>
              <TrendingUp className="w-4 h-4 text-emerald-500" />
            </div>
            <p className="text-2xl font-bold font-mono text-emerald-400 mt-2">
              ${statsData?.stats.average_value?.toLocaleString('en-US', { minimumFractionDigits: 2 }) ?? '0.00'}
            </p>
          </div>

          <div className="bg-slate-900 border border-slate-800 p-5 rounded-xl">
            <div className="flex items-center justify-between text-slate-400 text-xs font-semibold uppercase">
              <span>External S&P 500</span>
              <span className="text-[10px] text-blue-400 bg-blue-500/10 px-1.5 py-0.5 rounded">
                {statsData?.external.market_status ?? 'MOCK'}
              </span>
            </div>
            <p className="text-2xl font-bold font-mono text-blue-400 mt-2">
              {statsData?.external.benchmark_sp500 ?? '5,120.45'}
            </p>
          </div>
        </div>

        {/* Dashboard Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Add Item Form */}
          <div className="bg-slate-900 border border-slate-800 p-6 rounded-xl h-fit">
            <h2 className="text-lg font-bold text-white mb-1">Add Record</h2>
            <p className="text-xs text-slate-400 mb-4">
              Sends JSON payload directly to <code className="text-amber-400">/api/items</code>
            </p>

            <form onSubmit={handleAddItem} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Title / Symbol</label>
                <input
                  type="text"
                  required
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="e.g. Goldman Sachs (GS)"
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-amber-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">Category</label>
                  <select
                    value={category}
                    onChange={(e) => setCategory(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-amber-500"
                  >
                    <option value="Equity">Equity</option>
                    <option value="Crypto">Crypto</option>
                    <option value="Fixed Income">Fixed Income</option>
                    <option value="General">General</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">Value ($)</label>
                  <input
                    type="number"
                    step="0.01"
                    required
                    value={value}
                    onChange={(e) => setValue(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm font-mono text-white focus:outline-none focus:border-amber-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Description</label>
                <textarea
                  rows={2}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Optional thesis or details"
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-amber-500"
                />
              </div>

              <button
                type="submit"
                disabled={submitting}
                className="w-full bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold py-2 rounded-lg text-sm transition flex items-center justify-center space-x-2"
              >
                <PlusCircle className="w-4 h-4" />
                <span>{submitting ? 'Saving...' : 'Add to Database'}</span>
              </button>
            </form>
          </div>

          {/* Database Table */}
          <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
            <div className="p-5 border-b border-slate-800 flex justify-between items-center">
              <div>
                <h2 className="text-lg font-bold text-white">Live Data Table</h2>
                <p className="text-xs text-slate-400">Fetched dynamically from FastAPI + SQLite</p>
              </div>
              <span className="text-xs font-mono bg-slate-800 px-2 py-1 rounded border border-slate-700 text-slate-300">
                {items.length} records
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-950 text-slate-400 text-xs font-semibold uppercase border-b border-slate-800">
                  <tr>
                    <th className="px-5 py-3">ID</th>
                    <th className="px-5 py-3">Title</th>
                    <th className="px-5 py-3">Category</th>
                    <th className="px-5 py-3 text-right">Value</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800 font-mono text-xs">
                  {items.map((item) => (
                    <tr key={item.id} className="hover:bg-slate-800/40">
                      <td className="px-5 py-3 text-slate-500">#{item.id}</td>
                      <td className="px-5 py-3 font-sans font-bold text-white">{item.title}</td>
                      <td className="px-5 py-3 font-sans text-slate-400">{item.category}</td>
                      <td className="px-5 py-3 text-right font-bold text-amber-400">
                        ${item.value.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                      </td>
                    </tr>
                  ))}
                  {items.length === 0 && !loading && (
                    <tr>
                      <td colSpan={4} className="px-5 py-8 text-center text-slate-500 font-sans">
                        No records in database. Add one using the form!
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </main>

      <footer className="border-t border-slate-800 py-4 text-center text-xs text-slate-500">
        GS Hackathon Fullstack • React + Vite + TypeScript + FastAPI
      </footer>
    </div>
  );
}
