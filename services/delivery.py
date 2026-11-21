"""
OSOBA 3 – wysyłka: zapis do Outboxa i (udawane) kanały z ponawianiem.

Kontrakt przekazywany z pipeline'u (`services/pipeline.py`):
- `enqueue_deliveries(db, alert, recipients)` jest wołane RAZ na nowy alert
  (nowy problem, ponowne wystąpienie po Resolve, lub nowe okno czasowe `group_window_s`).
  Powtórzenia zdeduplikowane (`count += 1`) NIE wołają ponownie `enqueue_deliveries`.
- `alert` ma już nadane `alert.id` (np. do krótkiego linku w SMS: `/#alerts/{alert.id}`),
  wyrenderowane `title` / `body`, `severity`, `color`, `team` oraz `steps` z podstawionymi
  zmiennymi zdarzenia (w tym `action`, `params`, `approval`).
- `recipients` są już rozwiązani z uwzględnieniem `channel_prefs`, `on_call`, `quiet_hours`
  i fallbacków (dla kanału `"ui"` pole `person_id` ma wartość `None`, a `to` ma wartość `None`).

Zadanie Osoby 3:
- `enqueue_deliveries`: zapisać po jednym wierszu `Delivery` na odbiorcę (status `"pending"`),
  w tej samej transakcji sesji `db` (bez osobnego commitu jeśli używasz `db.add` / `db.flush`).
- worker w tle (podpięty w `main.py` w `lifespan`, np. co 1 s): bierze `"pending"`/`"failed"`
  z `attempts < 5` za pomocą `SELECT ... FOR UPDATE SKIP LOCKED` (patrz `SKALOWANIE.md`),
  wywołuje kanał, ustawia `"sent"` + `sent_at` albo `"failed"` + `last_error`.
- kanały to małe klasy z metodą `send(to, alert)` – prawdziwy dostawca = podmiana jednej klasy.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from models import Alert, Delivery
from services.contracts import Recipient


def enqueue_deliveries(db: Session, alert: Alert, recipients: list[Recipient]) -> list[Delivery]:
    # TODO (Osoba 3): zapisać Delivery dla każdego odbiorcy
    return []
