// OSOBA 3 – Outbox: co poszło mailem / SMS / telefonem, statusy i ponawianie.
import Placeholder from '../shared/Placeholder';

export default function OutboxPage() {
  return (
    <Placeholder title="Outbox" owner="Osoba 3" todo={[
      'Table: GET /api/deliveries — alert, person, channel, to, status, attempts, last error',
      'Filter by status (pending / sent / failed)',
      'Show retries after a simulated channel outage',
    ]} />
  );
}
