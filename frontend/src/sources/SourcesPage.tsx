// OSOBA 3 – źródła zdarzeń: dodaj program, dostań adres webhooka, wklej przykładowe zdarzenie.
import Placeholder from '../shared/Placeholder';

export default function SourcesPage() {
  return (
    <Placeholder title="Sources" owner="Osoba 3" todo={[
      'List: GET /api/sources, with the ingest URL /api/ingest/{key} + copy button',
      'New source: name, team, type (webhook / Kafka / RabbitMQ)',
      'Paste a sample event → show detected fields (payload.desk, payload.notional…)',
      'Recent events: GET /api/events',
    ]} />
  );
}
