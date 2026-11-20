// OSOBA 1 – live feed alertów + szczegóły alertu (kroki runbooka, ack/resolve, zatwierdzanie).
import Placeholder from '../shared/Placeholder';

export default function AlertsPage() {
  return (
    <Placeholder title="Alerts" owner="Osoba 1" todo={[
      'Live list for a team: GET /api/alerts?team=… + EventSource("/api/alerts/stream")',
      'Card: colour + severity from the rule, title, counter "×500", last seen',
      'Details: body, runbook steps, Approve button for risky steps, history',
      'Acknowledge / Resolve: POST /api/alerts/{id}/ack | /resolve',
    ]} />
  );
}
