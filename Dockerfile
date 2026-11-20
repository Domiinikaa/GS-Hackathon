# --- Stage 1: Build Frontend (React + TSX + Vite) ---
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/ ./
RUN npm install
RUN npm run build

# --- Stage 2: Python Backend (FastAPI) ---
FROM python:3.11-slim
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY . .

# Copy compiled React frontend from Stage 1
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

EXPOSE 8000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
