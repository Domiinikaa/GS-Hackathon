// Pusta strona "w budowie" – właściciel podmienia ją na swój ekran.
export default function Placeholder({ title, owner, todo }: { title: string; owner: string; todo: string[] }) {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-white">{title}</h1>
        <p className="text-sm text-slate-400">Owner: {owner}</p>
      </div>
      <div className="bg-slate-900 border border-dashed border-slate-700 rounded-xl p-6">
        <p className="text-xs font-semibold uppercase text-slate-400 mb-2">To build</p>
        <ul className="list-disc list-inside space-y-1 text-sm text-slate-300">
          {todo.map((t) => <li key={t}>{t}</li>)}
        </ul>
      </div>
    </div>
  );
}
