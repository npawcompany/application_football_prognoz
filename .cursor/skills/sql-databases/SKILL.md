---
name: sql-databases
description: >
  Design and write SQL and data-access code across PostgreSQL, MySQL/MariaDB, SQL Server,
  SQLite, Oracle, and common NoSQL (MongoDB, Redis). Use for schemas, queries, indexes,
  migrations, ORMs, and performance. Prefer parameterized SQL and migrations over ad-hoc DDL.
---

# SQL & databases

## Pick the store
| Need | Prefer |
|------|--------|
| Relational + constraints + joins | PostgreSQL (default), MySQL, SQL Server, SQLite (local/embedded) |
| Document / flexible JSON | MongoDB (or Postgres JSONB if mostly relational) |
| Cache / queues / ephemeral | Redis |
| Analytics / warehouse | Separate OLAP (BigQuery/Snowflake/Redshift) — do not overload OLTP |

## Universal SQL rules
1. **Parameterized queries only** — never string-concat user input
2. Explicit column lists (avoid `SELECT *` in app code)
3. Transactions for multi-step writes; keep them short
4. Index for actual query patterns; measure with `EXPLAIN` / plans
5. Migrations versioned (Alembic, golang-migrate, Flyway, Prisma migrate, etc.)
6. Connection pooling in servers; set timeouts

## Dialect cheat
### PostgreSQL
- JSONB, arrays, CTEs, `RETURNING`, `ON CONFLICT`, partial indexes
- Drivers: `psycopg` / `asyncpg` + SQLAlchemy; Go: `pgx`

### MySQL / MariaDB
- Careful with silent truncations / sql_mode
- `ON DUPLICATE KEY UPDATE`; InnoDB transactions

### SQL Server
- T-SQL, schemas, `MERGE` carefully; parameterized with sp_executesql patterns
- NVARCHAR for Unicode

### SQLite
- Great for local/dev/tests; one writer; typed affinity quirks
- Use for agent memory DBs, not heavy multi-writer prod

### Oracle
- Sequences/identity, `MERGE`, bind variables; heavier ops practices

## NoSQL notes
- **MongoDB**: model for query patterns; indexes; transactions only when needed
- **Redis**: keys TTL, avoid huge keys, pick data structure deliberately

## Python data layer
- SQLAlchemy 2.0 + Alembic (see `sqlalchemy-postgres`)
- Or raw SQL with clearly typed repos

## Go data layer
- `database/sql` + `sqlx`/`pgx` — prefer explicit SQL (see `golang-database`)
- Repository interfaces; context on every DB call

## Performance checklist
- N+1 queries → batch/join
- Missing index on filter/join columns
- Over-indexing write-heavy tables
- Large OFFSET pagination → keyset pagination
- See also `query-builder`, `query-optimizer`

## Deliverables when asked to "add a DB"
1. ER sketch / tables
2. Migration plan
3. Access layer pattern for the project language
4. Seed/test strategy
5. Backup/migrate risk notes