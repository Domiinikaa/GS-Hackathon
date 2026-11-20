// OSOBA 2 – ludzie i preferencje kanałów (critical → phone + SMS, warning → email, info → UI, godziny pracy).
import Placeholder from '../shared/Placeholder';

export default function PeoplePage() {
  return (
    <Placeholder title="People & channels" owner="Osoba 2" todo={[
      'List of people per team: GET /api/people',
      'Form: name, team, email, phone, on-call',
      'Per severity: which channels (critical / warning / info)',
      'Quiet hours: e.g. SMS only 08:00–20:00, otherwise email',
    ]} />
  );
}
