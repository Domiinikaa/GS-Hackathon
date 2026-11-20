// OSOBA 4 – runbooki: wklej YAML / Markdown / tekst, zobacz kroki, podepnij do reguły.
import Placeholder from '../shared/Placeholder';

export default function RunbooksPage() {
  return (
    <Placeholder title="Runbooks" owner="Osoba 4" todo={[
      'List: GET /api/runbooks',
      'Paste YAML / Markdown / free text → live preview: POST /api/runbooks/parse',
      'Steps with action + "needs approval" badge',
      'Attach runbook to a rule (rule.runbook_id)',
    ]} />
  );
}
