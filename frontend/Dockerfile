# internal-ai-search frontend — Vite dev server (Docker Compose dev only)
# Build context: repository root (see docker-compose.dev.yml)
# TODO: production multi-stage build (nginx) — follow-up

FROM node:20-bookworm-slim

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
