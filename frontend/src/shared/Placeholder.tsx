// Pusta strona "w budowie" – właściciel podmienia ją na swój ekran.
export default function Placeholder({ title, owner, todo }: { title: string; owner: string; todo: string[] }) {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight text-white">{title}</h1>
        <p className="text-sm text-ink-muted">Owner: {owner}</p>
      </div>
      <div className="glass-card glass-card--static border-dashed p-6">
        <p className="text-xs font-semibold uppercase text-ink-muted mb-2">To build</p>
        <ul className="list-disc list-inside space-y-1 text-sm text-slate-300">
          {todo.map((t) => <li key={t}>{t}</li>)}
        </ul>
      </div>
    </div>
  );
}
