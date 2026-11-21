# Skalowanie poziome – jak to działa i czego pilnować

Dokument dla całego zespołu (i dla Waszego AI – można go wkleić jako kontekst).
Cel: aplikacja ma działać tak samo przy **1 i przy N kopiach serwera** (kryterium „Scalability” z kartki:
*„Can the service scale horizontally? How is state handled (rules, dedup windows, delivery status)? Is there an obvious bottleneck or single point of failure?”*).

---

## 1. Architektura w jednym obrazku

```
   programy klientów (webhook, broker, log)          przeglądarki ludzi
                │                                          ▲  SSE (/api/alerts/stream)
                ▼                                          │
        ┌───────────────── load balancer (Railway) ─────────────────┐
        ▼                         ▼                                 ▼
   ┌─────────┐               ┌─────────┐                       ┌─────────┐
   │ kopia A │               │ kopia B │        …              │ kopia N │   ← identyczne, BEZSTANOWE
   └────┬────┘               └────┬────┘                       └────┬────┘
        └───────────────┬─────────┴─────────────────────────────────┘
                        ▼
              ┌───────────────────┐
              │  PostgreSQL       │  ← JEDYNE miejsce ze stanem: reguły, ludzie, zdarzenia,
              │  (wspólny)        │    alerty, liczniki, wysyłki, historia
              │  + LISTEN/NOTIFY  │  ← „dzwonek” między kopiami
              └───────────────────┘
```

**Zasada nr 1: kopia serwera nic nie pamięta „u siebie”.** Wszystko, co musi być wspólne, jest w Postgresie.
Dzięki temu load balancer może wysłać dowolne zapytanie do dowolnej kopii, a padnięcie jednej kopii nic nie psuje.

Lokalnie (SQLite, jedna kopia) ten sam kod też działa – tam część rzeczy przełącza się na tryb „w pamięci”.

---

## 2. Gdzie jest stan i jak jest chroniony – komponent po komponencie

| Komponent (właściciel) | Stan | Jak działa przy N kopiach | Status |
|---|---|---|---|
| **Logowanie** (Kacper) | brak – token JWT | każda kopia sprawdza token tym samym `SECRET_KEY` | ✅ działa – **na produkcji ustawcie `SECRET_KEY` w zmiennych Railway** (teraz jest wartość domyślna z kodu) |
| **Ingest** `/api/ingest` (Osoba 3) | zdarzenia w tabeli `events` | dowolna kopia przyjmuje, zapisuje do bazy | ✅ bezstanowe |
| **Ingest z brokera** (Kafka/RabbitMQ) (Osoba 3) | pozycja odczytu | Kafka: *consumer group* – partycje dzielą się między kopie. RabbitMQ: *competing consumers* – jedna wiadomość trafia do jednej kopii | ⏳ przy implementacji pamiętać |
| **Reguły** (Osoba 2/4) | tabela `rules` | czytane z bazy; jeśli ktoś trzyma je w pamięci (cache) – po zmianie reguły trzeba powiadomić wszystkie kopie (NOTIFY na kanale np. `rules`), inaczej kopia B użyje starej wersji | ⚠️ patrz punkt 3 |
| **Deduplikacja** (Osoba 1) | `alerts.count`, `dedup_key` | częściowy unikalny indeks + `INSERT … ON CONFLICT DO UPDATE SET count = alerts.count + 1` – atomowo w bazie | ✅ przetestowane: 300 równoległych zdarzeń na 3 kopie → 1 alert, count=300 |
| **Grupowanie / okna czasowe** (`group_by`, `group_window_s`) (Osoba 4) | okno czasowe | okno musi wynikać z **danych**, nie z pamięci kopii: np. `dedup_key = rule_id \| wartość group_by \| floor(czas / okno)` | ⚠️ patrz punkt 3 |
| **Live feed** (Osoba 1) | lista podłączonych przeglądarek – **lokalna dla kopii** (to OK) | każda zmiana alertu → `NOTIFY alerts '<id>'`; każda kopia słucha (`LISTEN`) i przekazuje swoim przeglądarkom | ✅ przetestowane na 3 kopiach |
| **Wysyłki / Outbox** (Osoba 3) | tabela `deliveries` (status, attempts) | worker na KAŻDEJ kopii, ale wiersz bierze tylko jedna: `SELECT … FOR UPDATE SKIP LOCKED` | ⚠️ patrz punkt 3 – inaczej SMS pójdzie N razy |
| **Kroki runbooka / akcje** (kolega od akcji) | `alerts.steps` | zapis zgody i wyniku w bazie; akcję uruchamia kopia, która dostała kliknięcie | ✅ o ile akcja nie jest „w tle” na każdej kopii |

---

## 3. Pułapki – czego każdy musi pilnować ⚠️

To są błędy, które **nie wychodzą na jednej kopii**, a wychodzą przy kilku. Wszystkie mają tę samą przyczynę:
dwie kopie robią to samo w tej samej chwili.

### 3.1. „Sprawdź, potem zapisz” = wyścig

```python
# ❌ ŹLE – dwie kopie naraz: obie "nie ma", obie tworzą
if not db.query(X).filter(...).first():
    db.add(X(...))

# ❌ ŹLE – dwie kopie naraz czytają 1, obie zapisują 2 (zgubione zliczenie)
obj.counter += 1

# ✅ DOBRZE – unikalny indeks + jedno polecenie
INSERT ... ON CONFLICT (...) DO UPDATE SET counter = tabela.counter + 1
# ✅ DOBRZE – licznik liczony w bazie
obj.counter = Model.counter + 1
```
Dowód, że to realne: u nas pierwsza wersja deduplikacji dała **7 alertów zamiast 1 i zgubiła 37 z 50 zliczeń**.

### 3.2. Worker w tle na każdej kopii = robota N razy

Pętla „co sekundę weź oczekujące wysyłki i wyślij” uruchomi się na **każdej** kopii. Bez blokady ten sam SMS wyślą wszystkie.

```sql
-- ✅ każda kopia bierze INNE wiersze, nikt nie czeka na nikogo
SELECT * FROM deliveries
WHERE status IN ('pending','failed') AND attempts < 5
ORDER BY id
LIMIT 20
FOR UPDATE SKIP LOCKED;
-- ...wyślij, ustaw status='sent' albo attempts+1, COMMIT
```
Zadanie, które ma iść **dokładnie raz** w całym systemie (np. sprzątanie co godzinę) → Postgres advisory lock:
`SELECT pg_try_advisory_lock(12345)` – tylko kopia, która dostała `true`, robi zadanie.

### 3.3. Pamięć podręczna (cache) się rozjeżdża

Jeśli kopia trzyma coś w zmiennej (np. listę reguł, żeby nie czytać bazy przy każdym zdarzeniu), to po zmianie
reguły w UI tylko kopia, która obsłużyła zapis, ma nową wersję. Rozwiązania (od najprostszego):
1. nie cache'ować – czytać z bazy przy każdym zdarzeniu (na hackathon wystarczy);
2. cache + `NOTIFY rules` po każdej zmianie – każda kopia na ten sygnał czyści cache (wzór: `services/live.py`).

### 3.4. Okna czasowe w pamięci

„Jeden alert na 5 minut per instrument” liczony licznikiem w pamięci kopii → każda kopia ma swoje okno → N alertów.
Okno musi być w danych (np. w `dedup_key`) albo w bazie.

### 3.5. SQLite nie jest do wielu kopii

SQLite to plik na dysku jednej maszyny. Na produkcji z wieloma kopiami → **tylko Postgres** (`DATABASE_URL` na Railway).
Kod musi działać na obu: unikać składni tylko z jednej bazy (wyjątek: `ON CONFLICT` działa w obu).

---

## 4. Checklista dla każdej nowej funkcji

Zanim zrobisz merge, odpowiedz sobie:

- [ ] Czy coś trzymam w zmiennej globalnej / w pamięci, co powinno być wspólne? → do bazy.
- [ ] Czy mam „sprawdź, potem zapisz” albo `x += 1` na danych w bazie? → unikalny indeks + `ON CONFLICT` / licznik w SQL.
- [ ] Czy mam pętlę w tle? → `FOR UPDATE SKIP LOCKED` albo advisory lock.
- [ ] Czy po zmianie danych inne kopie muszą się dowiedzieć? → `NOTIFY` (wzór w `services/live.py`).
- [ ] Czy to działa i na SQLite (laptop), i na Postgresie (produkcja)?

---

## 5. Jak przetestować na kilku kopiach lokalnie

Potrzebny Postgres (`brew install postgresql@16`). Potem:

```bash
# baza testowa (raz)
createdb -h localhost -U postgres alerts_test

# 3 kopie serwera na wspólnej bazie
export DATABASE_URL="postgresql://postgres@localhost:5432/alerts_test"
.venv/bin/uvicorn main:app --port 8001 &
.venv/bin/uvicorn main:app --port 8002 &
.venv/bin/uvicorn main:app --port 8003 &

# zasypać różne kopie tym samym naraz i sprawdzić wynik w bazie
for i in $(seq 1 300); do
  curl -s -o /dev/null -X POST "localhost:800$((i % 3 + 1))/api/alerts/test" \
       -H 'Content-Type: application/json' -d '{"dedup_key":"race"}' &
done; wait
psql -h localhost -U postgres -d alerts_test -c "select dedup_key, count, status from alerts;"
```
Oczekiwane: **1 wiersz, count=300**. Ten sam schemat do testu wysyłek: N wysyłek w tabeli → każda wysłana **dokładnie raz**.

---

## 6. Gdyby ruch był naprawdę ogromny (na pytania jurorów)

| Ograniczenie | Kiedy zaboli | Następny krok |
|---|---|---|
| Postgres jako jedyne źródło stanu | bardzo wiele zapisów/s | repliki do odczytu, partycjonowanie tabel `events`/`deliveries`, PgBouncer na połączenia |
| LISTEN/NOTIFY | tysiące instancji / bardzo dużo zmian | Redis pub/sub albo Kafka jako szyna zdarzeń |
| Ingest HTTP przyjmuje i przetwarza w jednym zapytaniu | skoki ruchu | przyjąć → wrzucić do kolejki (Kafka/RabbitMQ) → przetwarzać osobnymi workerami |

Zmierzone liczby (przepustowość, opóźnienie p50/p99) – wpisujemy do `PREZENTACJA.md`.
