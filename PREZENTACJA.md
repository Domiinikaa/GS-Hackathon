# Notatki na prezentację – Osoba 1 (Alerty)

Rzeczy, którymi warto się pochwalić. Każdy punkt: **co** + **dowód** (test / liczba) + **zdanie do powiedzenia**.
Dopisujemy na bieżąco.

---

## 1. Deduplikacja odporna na wiele kopii serwera ⭐ (Scalability, 2.5 "Don't flood people")

- **Co:** 500 takich samych błędów = 1 alert z licznikiem „×500”, także gdy zdarzenia trafiają naraz do kilku kopii serwera.
- **Jak:** częściowy unikalny indeks w bazie („jeden `dedup_key` = najwyżej jeden nierozwiązany alert”)
  + jedno atomowe polecenie `INSERT … ON CONFLICT DO UPDATE SET count = alerts.count + 1`.
  Ten sam kod działa na SQLite (lokalnie) i Postgresie (produkcja).
- **Dowód – test „przed i po” (3 instancje, wspólny Postgres, równoległe zdarzenia z tym samym kluczem):**

  | | zdarzeń | alertów | suma liczników |
  |---|---|---|---|
  | przed poprawką | 50 | **7** (duplikaty) | **13** (zgubione zliczenia) |
  | po poprawce | 50 | **1** | **50** |
  | po poprawce | 300 | **1** | **300** |

- **Do powiedzenia:** „Pierwsza wersja miała klasyczny race condition – przy 50 równoległych zdarzeniach na 3 instancje
  powstawało 7 alertów i ginęło 37 zliczeń. Przenieśliśmy deduplikację do bazy: partial unique index plus atomowy upsert.
  Teraz 300 równoległych zdarzeń daje dokładnie 1 alert z licznikiem 300.”
- Bonus: błąd znalazł kolega z zespołu w code review – dobry przykład pracy zespołowej.

## 2. Live feed działający na wielu instancjach ⭐ (Scalability, 2.4 "push, not page refresh")

- **Co:** alerty pojawiają się i zmieniają na ekranie same, bez odświeżania (zielona kropka „Live”).
- **Jak – dwa piętra:**
  - serwer → przeglądarka: **SSE (Server-Sent Events)** – zwykłe HTTP, wbudowane w przeglądarki, samo się ponownie łączy;
  - serwer ↔ serwer: **Postgres LISTEN/NOTIFY** – każda instancja dostaje ogłoszenie z bazy i przekazuje je swoim przeglądarkom.
  - Lokalnie (SQLite) ten sam kod sam przełącza się na tryb in-memory – zespół nic nie instaluje.
- **Dowód – test na 3 instancjach (8001/8002/8003):** alert wysłany tylko do :8003, Acknowledge kliknięty tylko na :8002
  → słuchacze na **wszystkich trzech** dostali wszystkie zmiany. Ten sam test w trybie in-memory: słuchacze na :8011 i :8012 dostali **0**.
- **Do powiedzenia:** „Live feed jest bezstanowy względem instancji – używamy Postgresa, który i tak mamy, więc skalowanie
  poziome nie wymaga dodatkowej infrastruktury typu Redis.”
- Szczegóły warte wspomnienia:
  - NOTIFY wychodzi **dopiero po commit** – UI nigdy nie pokaże alertu, którego zapis się nie udał;
  - ogłaszamy tylko id alertu (limit 8 KB), każda instancja czyta świeżą wersję z bazy;
  - 1 dodatkowe połączenie z bazą na instancję, niezależnie od liczby przeglądarek;
  - po zerwaniu połączenia (np. Wi-Fi) przeglądarka łączy się sama i pobiera listę od nowa – nic nie ginie.

## 3. Obsługa alertu z pełną historią (2.4, 2.6 "record who did what")

- **Co:** Acknowledge („zajmuję się tym”) i Resolve („naprawione”), każda akcja zapisuje **kto i kiedy**
  – użytkownik z systemu logowania (np. „acknowledged by admin”).
- Dozwolone przejścia statusu pilnowane w backendzie (błąd 409 przy próbie np. ack na rozwiązanym alercie).
- Po Resolve to samo zdarzenie tworzy **nowy** alert – stary problem został zamknięty, nowy jest nowym incydentem.

## 4. Czytelne alerty (UX, 2.2 "per-rule presentation")

- Kolor i ważność biorą się z reguły (czerwony pasek + CRITICAL, bursztynowy + WARNING).
- Licznik „×N”, „last seen 2 min ago”, filtr zespołu i statusu, czytelne stany puste i błędu.
- Działa na żywo w dwóch oknach naraz – **dobre ujęcie do filmiku**: klik w jednym oknie, zmiana w drugim.

## 5. Praca bez blokowania zespołu

- Testowy endpoint `POST /api/alerts/test` udaje silnik reguł – front i back alertów były gotowe i przetestowane,
  zanim powstał silnik reguł Osoby 4. Wspólny kontrakt (`Match`) = zero zmian po podłączeniu prawdziwego silnika.

---

## Uczciwie: ograniczenia i co dalej (jurorzy lubią, gdy zespół je zna)

- Live feed na bardzo dużą skalę (tysiące instancji / bardzo duży ruch) → podmiana LISTEN/NOTIFY na Redis pub/sub lub Kafkę.
- Filtr zespołu nie jest jeszcze powiązany z zalogowanym użytkownikiem (konta mają „działy”, reguły „zespoły” – do ujednolicenia).

## Pomysły na filmik

1. Dwa okna obok siebie: klik Acknowledge w jednym → karta zmienia się w drugim.
2. Terminal: 300 równoległych zdarzeń → na ekranie jeden alert z licznikiem ×300.
3. Slajd z tabelą „przed i po” z punktu 1.
