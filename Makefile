.PHONY: help install seed run test sim sim-audit sim-scenario docker-up docker-scale docker-down

VENV := .venv/bin

help:
	@echo "Available commands for Cloud-Native RFID Library System:"
	@echo "  make install       - Install Python dependencies into virtualenv"
	@echo "  make seed          - Seed database with RFID books, patrons, and readers"
	@echo "  make run           - Run FastAPI local server (serves API and Dashboard at http://localhost:8000)"
	@echo "  make test          - Run full pytest test suite (22 tests across FR1-FR11)"
	@echo "  make sim           - Run Interactive RFID Reader Simulator CLI"
	@echo "  make sim-audit     - Run Automated 5-Point Edge Security Audit"
	@echo "  make sim-scenario  - Run Realistic Library Day Traffic Scenario"
	@echo "  make docker-up     - Launch PostgreSQL, API, and Nginx via Docker Compose"
	@echo "  make docker-scale  - Scale API to 3 container replicas behind Nginx"
	@echo "  make docker-down   - Stop Docker Compose services"

seed:
	$(VENV)/python backend/seed_data.py

run:
	$(VENV)/uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000 --reload

test:
	$(VENV)/pytest backend/tests -v

sim:
	$(VENV)/python simulator/simulator.py --mode interactive

sim-audit:
	$(VENV)/python simulator/simulator.py --mode security-audit

sim-scenario:
	$(VENV)/python simulator/simulator.py --mode scenario

docker-up:
	docker compose up --build -d

docker-scale:
	docker compose up --scale api=3 -d

docker-down:
	docker compose down -v
