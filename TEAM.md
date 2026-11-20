# Podział pracy (pionowy)

Każdy ma swój kawałek w całości: ekran + endpointy + logikę. Edytujesz **tylko swoje pliki**, więc nie ma konfliktów przy merge'u.

| Osoba | Kawałek | Frontend | Backend |
|---|---|---|---|
| **1** | Alerty | `frontend/src/alerts/` | `routers/alerts.py`, `services/alert_service.py` (deduplikacja), `services/live.py` (SSE) |
| **2** | Reguły i ludzie | `frontend/src/rules/` ✅, `frontend/src/people/` | `routers/rules.py`, `routers/people.py`, `services/people_service.py` (kto i jakim kanałem) |
| **3** | Wejście i wysyłka | `frontend/src/sources/`, `frontend/src/outbox/` | `routers/sources.py` (ingest działa), `routers/deliveries.py`, `services/delivery.py` (mock kanałów + retry), deploy |
| **4** | Mózg | `frontend/src/runbooks/` | `services/rules_engine.py` (dopasowanie + szablony), `services/runbook_parser.py`, `routers/runbooks.py` |

## Pliki wspólne – zmiana tylko po ustaleniu z zespołem

- `models.py` – wszystkie tabele; każdy edytuje tylko swoją klasę
- `services/contracts.py` – `Match` i `Recipient`, czyli dane na styku osób
- `services/pipeline.py` – droga zdarzenia przez system
- `frontend/src/App.tsx` – menu zakładek
- `frontend/src/shared/types.ts` – typy TS = kształt JSON z `models.py`
- `seed.py` – dane startowe (każdy dopisuje w swojej funkcji)

## Jak przepływa jedno zdarzenie

```
POST /api/ingest/{key}                       Osoba 3   zapis do tabeli events
  -> evaluate(event, rules)   -> [Match]     Osoba 4   które reguły pasują, wypełnione szablony
  -> upsert_alert(db, match)  -> Alert       Osoba 1   nowy alert albo count += 1
  -> recipients_for(db, alert)-> [Recipient] Osoba 2   kto, jakim kanałem, godziny pracy
  -> enqueue_deliveries(...)  -> [Delivery]  Osoba 3   Outbox, wysyłka z ponawianiem
```

Każda funkcja ma już stub, który zwraca `[]` / `None`, więc całość działa od razu, tylko nic nie robi.
Napisz swoją funkcję, a reszta zacznie z niej korzystać bez innych zmian.

## Jak testować swój kawałek bez czekania na innych

```bash
source venv/bin/activate && uvicorn main:app --reload     # backend :8000, Swagger na /docs
cd frontend && npm run dev                                 # frontend :5173
```

Przykładowe zdarzenie (źródło `trade-gateway` jest w seedzie):

```bash
curl -X POST localhost:8000/api/ingest/trade-gateway -H 'Content-Type: application/json' \
  -d '{"meta":{"schema":"trade.rejected.v2","producer":"trade-gateway"},"payload":{"tradeId":"T-998877","desk":"rates","notional":25000000,"currency":"EUR","reason":"LIMIT_BREACH"}}'
```

- **Osoba 4**: w seedzie są 4 reguły z kartki. Pisz `evaluate` i testuj je w czystym Pythonie, bez UI.
- **Osoba 1**: zanim powstanie silnik reguł, wrzuć sobie alert ręcznie do bazy (albo dopisz go w `seed.py`).
- **Osoba 2**: w seedzie są reguły i 3 osoby. `GET /api/rules` i `GET /api/people` już zwracają dane.
- **Osoba 3**: ingest już zapisuje zdarzenia, a podgląd jest pod `GET /api/events`.

Po zmianie pól w `models.py` usuń `app.db` (SQLite nie robi migracji), a seed wypełni bazę od nowa.

## Lokalnie Python 3.9

W routerach FastAPI pisz `Optional[str]`, nie `str | None`, bo 3.9 tego nie obsługuje.
W `services/` jest `from __future__ import annotations`, więc tam `X | None` działa.
