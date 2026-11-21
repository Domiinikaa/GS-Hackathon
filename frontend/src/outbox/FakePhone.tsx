// Fałszywy telefon: SMS-y i połączenia z udawanej bramki, z możliwością odpowiedzi (ACK / YES / klawisz 1).
// Na demo pokazuje, jak człowiek dostaje alert na telefon i zatwierdza krok, odpisując na SMS-a.
import { useEffect, useRef, useState } from 'react';
import { MessageSquare, Phone, Send } from 'lucide-react';
import { api } from '../shared/api';
import type { GatewayMessage } from '../shared/types';
import { parseUtc } from '../alerts/AlertCard';

interface PhoneEntry { number: string; name: string | null }

function hhmm(iso: string) {
  return parseUtc(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

// Kod do odpowiedzi z ostatniego SMS-a, np. "Reply ACK 4821" → "4821"
function lastCode(messages: GatewayMessage[]): string | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i].body.match(/Reply ACK (\d{4})/);
    if (messages[i].direction === 'out' && m) return m[1];
  }
  return null;
}

export default function FakePhone({ refreshKey }: { refreshKey: number }) {
  const [phones, setPhones] = useState<PhoneEntry[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [messages, setMessages] = useState<GatewayMessage[]>([]);
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);   // okno rozmowy (przewijamy tylko je, nie całą stronę)

  // Lista telefonów + rozmowa z wybranym; odświeżane razem z Outboxem
  useEffect(() => {
    api<PhoneEntry[]>('/channels/phones').then((list) => {
      setPhones(list);
      setSelected((cur) => cur ?? list[0]?.number ?? null);
    }).catch(() => {});
  }, [refreshKey]);

  useEffect(() => {
    if (!selected) return;
    api<GatewayMessage[]>(`/channels/messages?number=${encodeURIComponent(selected)}`)
      .then(setMessages).catch(() => {});
  }, [selected, refreshKey]);

  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTop = el.scrollHeight;          // najnowsza wiadomość na dole, jak w telefonie
  }, [messages.length, selected]);

  async function sendSms(body: string) {
    if (!selected || !body.trim()) return;
    setSending(true);
    try {
      await api('/channels/sms/inbound', { method: 'POST', body: JSON.stringify({ from: selected, text: body }) });
      setText('');
      setMessages(await api<GatewayMessage[]>(`/channels/messages?number=${encodeURIComponent(selected)}`));
    } finally {
      setSending(false);
    }
  }

  async function pressOne() {
    if (!selected) return;
    await api('/channels/phone/inbound', { method: 'POST', body: JSON.stringify({ from: selected, digit: '1' }) });
    setMessages(await api<GatewayMessage[]>(`/channels/messages?number=${encodeURIComponent(selected)}`));
  }

  const code = lastCode(messages);
  const current = phones.find((p) => p.number === selected);

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
      <div className="px-4 py-3 border-b border-slate-800">
        <h2 className="font-semibold text-white">Fake phone</h2>
        <p className="text-xs text-slate-400">What people receive by SMS / phone call – reply to act on the alert.</p>
      </div>

      {phones.length === 0 ? (
        <p className="text-sm text-slate-500 p-6 text-center">No SMS or calls sent yet.</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-[180px_1fr]">
          {/* lista telefonów */}
          <ul className="border-b sm:border-b-0 sm:border-r border-slate-800 max-h-80 overflow-y-auto">
            {phones.map((p) => (
              <li key={p.number}>
                <button onClick={() => setSelected(p.number)}
                  className={`w-full text-left px-4 py-2.5 text-sm ${p.number === selected ? 'bg-slate-800 text-white' : 'text-slate-300 hover:bg-slate-800/50'}`}>
                  <div className="font-medium">{p.name ?? 'Unknown'}</div>
                  <div className="text-xs text-slate-500 font-mono">{p.number}</div>
                </button>
              </li>
            ))}
          </ul>

          {/* rozmowa */}
          <div className="flex flex-col min-h-80">
            <div ref={scroller} className="flex-1 p-4 space-y-2 overflow-y-auto max-h-80">
              {messages.map((m) => {
                const mine = m.direction === 'in';   // odpowiedź człowieka = po prawej, jak w telefonie
                const isCall = m.channel === 'phone' && m.direction === 'out';
                return (
                  <div key={m.id} className={`flex ${mine ? 'justify-end' : 'justify-start'}`}>
                    <div className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm ${
                      mine ? 'bg-sky-600 text-white rounded-br-sm' : 'bg-slate-800 text-slate-100 rounded-bl-sm'}`}>
                      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide opacity-70 mb-0.5">
                        {m.channel === 'phone' ? <Phone className="w-3 h-3" /> : <MessageSquare className="w-3 h-3" />}
                        {isCall ? 'voice call' : m.channel} · {hhmm(m.created_at)}
                      </div>
                      <div className="break-words">{m.body}</div>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* odpowiedź */}
            <div className="border-t border-slate-800 p-3 space-y-2">
              <div className="flex flex-wrap gap-2">
                {code && (
                  <>
                    <button onClick={() => sendSms(`ACK ${code}`)} disabled={sending}
                      className="text-xs px-2.5 py-1 rounded-full border border-slate-600 text-slate-200 hover:bg-slate-800">ACK {code}</button>
                    <button onClick={() => sendSms(`YES ${code}`)} disabled={sending}
                      className="text-xs px-2.5 py-1 rounded-full border border-amber-500/50 text-amber-300 hover:bg-amber-500/10">YES {code} (approve)</button>
                    <button onClick={() => sendSms(`RESOLVE ${code}`)} disabled={sending}
                      className="text-xs px-2.5 py-1 rounded-full border border-emerald-500/40 text-emerald-300 hover:bg-emerald-500/10">RESOLVE {code}</button>
                  </>
                )}
                {messages.some((m) => m.channel === 'phone') && (
                  <button onClick={pressOne}
                    className="text-xs px-2.5 py-1 rounded-full border border-sky-500/50 text-sky-300 hover:bg-sky-500/10">📞 Press 1 (acknowledge)</button>
                )}
              </div>
              <form onSubmit={(e) => { e.preventDefault(); sendSms(text); }} className="flex gap-2">
                <input value={text} onChange={(e) => setText(e.target.value)}
                  placeholder={`Reply as ${current?.name ?? selected ?? ''}…`}
                  className="flex-1 bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-sky-500" />
                <button type="submit" disabled={sending || !text.trim()}
                  className="px-3 rounded-lg bg-sky-600 hover:bg-sky-500 text-white disabled:opacity-40" aria-label="Send reply">
                  <Send className="w-4 h-4" />
                </button>
              </form>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
