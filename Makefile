.PHONY: setup backend frontend dev test clean

# One-time setup: backend venv + deps, frontend deps.
setup:
	cd backend && python3 -m venv .venv && ./.venv/bin/pip install -U pip && ./.venv/bin/pip install -r requirements.txt
	cd frontend && npm install

# Run the backend API (http://127.0.0.1:8000).
backend:
	cd backend && ./.venv/bin/uvicorn app.main:app --reload --port 8000

# Run the frontend (http://localhost:3000), proxying /api to the backend.
frontend:
	cd frontend && npm run dev

# Convenience: start both (needs two terminals normally; this backgrounds the API).
dev:
	cd backend && ./.venv/bin/uvicorn app.main:app --port 8000 & \
	cd frontend && npm run dev

test:
	cd backend && ./.venv/bin/python -m pytest -q

clean:
	rm -rf backend/.cache backend/atlas.db frontend/.next
