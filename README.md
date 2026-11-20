# 🚀 GS Hackathon Starter (FastAPI + React/TSX + SQLite)

Elastyczny szkielet fullstack przygotowany na hackathon dla **4-osobowego zespołu**, gotowy do pracy zarówno w **czystym Pythonie**, jak i z nowoczesnym frontendem w **React + TypeScript (TSX)**.

---

## 💻 Jak pracujecie lokalnie?

### 1. Backendowiec (lub praca bez Node.js):
```bash
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```
- API działa pod `http://localhost:8000/api`
- Swagger pod `http://localhost:8000/docs`

### 2. Frontendowiec (React + TSX + Tailwind):
```bash
cd frontend
npm install
npm run dev
```
- Otwórz: `http://localhost:5173`
- **Zero problemów z CORS:** `vite.config.ts` ma skonfigurowany proxy – każde zapytanie do `/api/...` wędruje bezpośrednio do Twojego backendu FastAPI na porcie 8000!

---

## ☁️ Deployment na Railway / Render (Zero konfiguracji!)

W projekcie znajduje się **multi-stage Dockerfile**:
1. Sam pobiera Node, buduje Reacta (`npm run build`).
2. Kopiuje zbuildowany frontend do kontenera z FastAPI.
3. FastAPI automatycznie serwuje aplikację React pod adresem głównym `/`.

Wystarczy w terminalu:
```bash
railway up
```
I cała aplikacja (React + FastAPI + SQLite) działa online pod jednym URL!

---

## 👥 Podział ról w zespole

Podział pionowy, pliki każdej osoby i styki między nimi: **[TEAM.md](TEAM.md)**.
