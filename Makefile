# Inkstave — Docker orchestration shortcuts.
#
# `make up` runs the DEV stack: everything in Docker WITH hot reload (uvicorn
# --reload on the backend, arq --watch on the worker, Vite HMR on the frontend).
# Source is bind-mounted, so code edits reload in place — no production build.
# It runs ATTACHED so all logs stream to your terminal; Ctrl+C stops it.
#
#   Browser → http://localhost:5173  (SPA, talks to the API on :8000)
#
# `make up-prod` runs the optimized PRODUCTION stack (static bundle behind nginx,
# no reload) from docker-compose.prod.yml, served on http://localhost.
#
# Both need a .env (with MIGRATE_ON_START=true so the backend migrates on boot).

DEV  := docker compose -f docker-compose.dev.yml
PROD := docker compose -f docker-compose.prod.yml

.PHONY: up up-d down clean build logs ps restart \
        up-prod up-prod-d down-prod clean-prod logs-prod

# --- Development (hot reload) ------------------------------------------------- #

# Build images (first run) + bring the dev stack up, ATTACHED with live logs.
# Ctrl+C stops it. The backend image build is slow once (Tectonic); reruns are fast.
up:
	$(DEV) up --build

# Same, detached (background). Use `make logs` to follow.
up-d:
	$(DEV) up -d --build

# Stop and remove the dev containers (keeps db / uploads / node_modules volumes).
down:
	$(DEV) down

# Stop and remove dev containers AND volumes (wipes db, uploads, deps, cache).
clean:
	$(DEV) down -v

# Build the dev images without starting.
build:
	$(DEV) build

# Follow logs from the dev stack (after `make up-d`).
logs:
	$(DEV) logs -f

# Show dev service status / health.
ps:
	$(DEV) ps

# Restart the dev app services.
restart:
	$(DEV) restart backend worker frontend

# --- Production (optimized build, no reload) --------------------------------- #

# Build + run the production stack, attached. Served on http://localhost.
up-prod:
	$(PROD) up --build

# Production stack, detached.
up-prod-d:
	$(PROD) up -d --build

# Stop the production stack (keeps volumes).
down-prod:
	$(PROD) down

# Stop the production stack AND wipe its volumes.
clean-prod:
	$(PROD) down -v

# Follow production logs.
logs-prod:
	$(PROD) logs -f
