.PHONY: help up down logs logs-api logs-runners rebuild rebuild-api rebuild-python rebuild-lstm rebuild-r rebuild-julia rebuild-frontend migrate health tidy build clean data data-mpox data-synthetic data-clean benchmark ui-dev ui-build ui-install

COMPOSE := docker compose

help:
	@echo "Targets:"
	@echo "  up              - start full stack (yugabyte, redis, migrate, api, 4 runners)"
	@echo "  down            - stop and remove containers"
	@echo "  logs            - tail all logs"
	@echo "  logs-api        - tail api logs"
	@echo "  logs-runners    - tail logs of all 4 runners"
	@echo "  rebuild         - rebuild + restart api and all runners"
	@echo "  rebuild-api     - rebuild api image only"
	@echo "  rebuild-python  - rebuild python runner only"
	@echo "  rebuild-lstm    - rebuild LSTM runner only"
	@echo "  rebuild-r       - rebuild R runner only"
	@echo "  rebuild-julia   - rebuild Julia runner only"
	@echo "  migrate         - re-run migrations only"
	@echo "  health          - curl /api/health"
	@echo "  tidy            - go mod tidy in ./api"
	@echo "  build           - go build in ./api"
	@echo "  clean           - down + remove yugabyte volume"
	@echo "  data            - generate COVID-19 country CSVs from OWID (scripts/preprocess_owid.py)"
	@echo "  data-mpox       - generate mpox country CSVs from OWID (scripts/preprocess_mpox.py)"
	@echo "  data-synthetic  - generate large synthetic stress datasets (scripts/generate_synthetic.py)"
	@echo "  data-clean      - delete data/processed/ output CSVs"
	@echo "  benchmark       - run a benchmark campaign (scripts/run_benchmark.py); pass ARGS=\"...\""
	@echo "  rebuild-frontend- rebuild frontend image only"
	@echo "  ui-install      - npm install in ./frontend"
	@echo "  ui-dev          - npm run dev (vite dev server on :5173)"
	@echo "  ui-build        - npm run build in ./frontend"

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

logs-api:
	$(COMPOSE) logs -f api

logs-runners:
	$(COMPOSE) logs -f runner-python runner-lstm runner-r runner-julia

rebuild:
	$(COMPOSE) up -d --build api runner-python runner-lstm runner-r runner-julia

rebuild-api:
	$(COMPOSE) up -d --build api

rebuild-python:
	$(COMPOSE) up -d --build runner-python

rebuild-lstm:
	$(COMPOSE) up -d --build runner-lstm

rebuild-r:
	$(COMPOSE) up -d --build runner-r

rebuild-julia:
	$(COMPOSE) up -d --build runner-julia

migrate:
	$(COMPOSE) run --rm migrate

health:
	@curl -fsS http://localhost:8080/api/health | jq . || curl -v http://localhost:8080/api/health

tidy:
	cd api && go mod tidy

build:
	cd api && go build ./...

clean: down
	docker volume rm emedicine_yugabyte-data 2>/dev/null || true

data:
	cd scripts && python3 preprocess_owid.py

data-mpox:
	cd scripts && python3 preprocess_mpox.py

data-synthetic:
	cd scripts && python3 generate_synthetic.py --profile multiwave && \
		python3 generate_synthetic.py --profile sharp && \
		python3 generate_synthetic.py --profile slow

data-clean:
	rm -f data/processed/*.csv

benchmark:
	cd scripts && python3 run_benchmark.py $(ARGS)

rebuild-frontend:
	$(COMPOSE) up -d --build frontend

ui-install:
	cd frontend && npm install

ui-dev:
	cd frontend && npm run dev

ui-build:
	cd frontend && npm run build
