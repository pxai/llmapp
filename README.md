# Quote App

## Run

```sh
 docker compose up . -d
```

## Stop it

```sh
 docker compose down  -v --remove-orphans
```

## Rebuild

```sh
docker compose down -v --remove-orphans && docker compose up -d --build
```

Or

```sh
docker compose up -d --force-recreate vector_db && docker compose up -d
```

## Check logs

```sh
docker compose logs --tail 50
docker compose logs -f --tail 100 api
```

## Connect to CLI

```sh
docker compose exec redis redis-cli
docker compose exec postgres psql -U postgres -d dev
```


## CircleCI

CircleCI runs backend and frontend lint/tests on every branch using Node.js 24. The frontend checks include Playwright E2E tests against the Compose API and test database. On the `staging` branch, CircleCI also builds the frontend and stores `frontend/dist` as an artifact.

Set the `STAGING_API_URL` environment variable in CircleCI project settings to the API URL that the staging frontend should use. The staging job builds an artifact; it does not deploy it.

## Run Tests

Requires Docker Compose and Node.js 24. Run these commands from the repository root.

Install project dependencies and the Playwright browser:

```sh
npm ci --prefix backend
npm ci --prefix frontend
cd frontend && npx playwright install chromium && cd ..
```

Start PostgreSQL and ensure the test database and quote fixtures exist:

```sh
docker compose up -d postgres
docker compose exec -T postgres psql -U postgres -d postgres -f /docker-entrypoint-initdb.d/00-create-databases.sql
docker compose exec -T postgres psql -U postgres -d postgres -f /docker-entrypoint-initdb.d/seed-testing.sql
```

Run backend lint and unit tests, then frontend lint, unit, and browser E2E tests:

```sh
npm test --prefix backend
POSTGRES_DSN='postgres://postgres:postgres@postgres:5432/test?sslmode=disable' \
CORS_ORIGIN='http://127.0.0.1:5173' docker compose up -d --build api
npm test --prefix frontend
```

The frontend test script starts its own Vite server. After testing, restore the API to its default `dev` database:

```sh
docker compose up -d api
```


# ⚡ Redis CLI Cheat Sheet

### 1. List Keys (Read All)
```bash
KEYS *
```

### 2. Create / Update
```bash
SET my_key "my_value"
```

### 3. Read Single Key
```bash
GET my_key
```

### 4. Delete
```bash
DEL my_key
```

### 5. Expiration & TTL
* **Set expiration (seconds):** `EXPIRE my_key 60`
* **Create with expiration:** `SETEX my_key 60 "my_value"`
* **Check remaining time:** `TTL my_key` *(-1 = persistent, -2 = does not exist)*

### 6. Wipe Database (Reset)
```bash
FLUSHALL
```
