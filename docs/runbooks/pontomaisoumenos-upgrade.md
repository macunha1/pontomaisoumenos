# PontoMaisOuMenos: upgrading the legacy worker

This procedure upgrades an installation using `app.main`, Python 3.7, PostgreSQL 11, and Dramatiq 1
to the installed `pontomaisoumenos` package. It preserves records and converts local timestamps
to `timestamptz`. For an empty installation, follow the [README](../../README.md).

This procedure deliberately retains PostgreSQL and Redis. Fresh installs default to SQLite and
memory queues, but switching a database URL does not transfer existing data. The default Compose
file provisions SQLite only; operate the destination PostgreSQL and Redis services separately.

# Configuration and behavior changes

Use `pontomaisoumenos schedule` and `pontomaisoumenos worker` instead of `python -m app.main`
and `dramatiq app.tasks`. Run migrations explicitly with `pontomaisoumenos migrate`.

The old `default.toml` used INI syntax. Convert it to valid TOML and supply credentials through
`PM_USER__EMAIL` and `PM_USER__PASSWORD`. The old `DATABASE_USER`, `DATABASE_PASSWORD`, `POSTGRES_*`,
`TARGET_MONTH`, `TARGET_YEAR`, and `RUN_MIGRATIONS` application variables are no longer supported.
The scheduler generates the current month automatically and continues across month boundaries.

Remove `algorithm.max_num_of_gens` and `algorithm.enable_best_effort` from configuration. Impossible
working-hour settings now produce an error that requires correcting the ranges. Movable holidays
are calculated for each year and the selected state; December 31 is no longer automatically a day off.
Carnival Monday and Tuesday are excluded by default through `enabled_optional_holidays = ["carnival"]`.
Review the [optional holiday policy](../../README.md#optional-holidays) when migrating; use `[]` for
public holidays only, or add the documented identifiers for additional full days off. Partial-day
hours and annual local decrees require separate review. Changing the list does not replace an
existing persisted month's calendar.
Coordinate variation now produces different positions within its configured interval.

# Requirements

- Access to the old processes, source and destination databases, old Redis instance, and backup storage.
- PostgreSQL 18 client tools (`pg_dump`, `pg_restore`, `psql`), Python 3.14 or 3.15, and uv.
- An empty destination database with permission to create tables and indexes.
- The timezone actually used by the old Python process (the old image normally used `America/Sao_Paulo`).
- A verified backup and a maintenance window with no punch submissions during the switch.
- Replace every `MIND_THE_GAP` value. Keep credential-bearing URLs out of shared shell histories.

# Details

## 0. Stop the old scheduler and workers

Stop both `app.main` and `dramatiq app.tasks` through their existing supervisor. The original Compose
services are named `application` and `dramatiq`. Run this from the old checkout before replacing its
Compose file:

```shell
docker compose stop application dramatiq
docker compose ps
```

### Validating

Confirm that no old worker remains active on another host or supervisor. Old workers must not consume
their queues while new workers are active: old payloads lack a punch ID for deduplication.
Do not drain the queue by executing future punches ahead of schedule.

## 1. Identify the databases and timezone

Use ordinary PostgreSQL URLs for PostgreSQL tools. The application URL uses the `postgresql+psycopg`
driver prefix. Verify which database the old installation actually used: its connection string could
ignore the database name in the configuration file.

```shell
export OLD_DATABASE_URL='MIND_THE_GAP'
export TARGET_DATABASE_URL='MIND_THE_GAP'
export PM_DATABASE_URL='MIND_THE_GAP'
export LEGACY_TIMEZONE='MIND_THE_GAP'
export BACKUP_FILE='/MIND_THE_GAP/pontomaisoumenos-before-upgrade.dump'
psql "$OLD_DATABASE_URL" -c "SELECT current_database(), current_setting('TimeZone');"
```

### Validating

The PostgreSQL session timezone does not establish the timezone used by the old `datetime.now()`.
Compare a known record with its expected local time and inspect the old container or host.
Use `America/Sao_Paulo` rather than a fixed offset when records span historical daylight saving periods.

## 2. Back up and inspect the legacy data

With the application stopped, capture a dump and restrict access to the backup. Preserve the old
application version, configuration, and Redis volume. Old Redis messages can contain passwords.

```shell
umask 077
pg_dump --format=custom --no-owner --no-acl --file="$BACKUP_FILE" "$OLD_DATABASE_URL"
pg_restore --list "$BACKUP_FILE"
psql "$OLD_DATABASE_URL" -c 'SELECT count(*) FROM "USERS";'
psql "$OLD_DATABASE_URL" -c 'SELECT count(*) FROM "WORKING_PUNCHES";'
```

### Validating

Verify that `USERS` contains `id`, `email`, `active`, `updated_at`, and `created_at`, and that
`WORKING_PUNCHES` contains `id`, `user_id`, `should_punch_at`, `done`, `updated_at`, and `created_at`.
Do not stamp a different schema as the baseline. The upgrade does not automatically resolve duplicate
punches; the new unique constraint requires an explicit decision about any duplicates first.

```shell
psql "$OLD_DATABASE_URL" -c '\d "USERS"'
psql "$OLD_DATABASE_URL" -c '\d "WORKING_PUNCHES"'
psql "$OLD_DATABASE_URL" -c 'SELECT user_id, should_punch_at, count(*) FROM "WORKING_PUNCHES" GROUP BY user_id, should_punch_at HAVING count(*) > 1;'
```

## 3. Restore into a compatible PostgreSQL installation

**Confirm that the destination is a new, empty database. Do not attach a PostgreSQL 11 data volume
to PostgreSQL 18.** Restore the dump into a separately provisioned destination. Preserve the
original database volume and backup until migration validation is complete.

```shell
pg_restore --exit-on-error --no-owner --no-acl --dbname="$TARGET_DATABASE_URL" "$BACKUP_FILE"
psql "$TARGET_DATABASE_URL" -c 'SELECT count(*) FROM "USERS";'
psql "$TARGET_DATABASE_URL" -c 'SELECT count(*) FROM "WORKING_PUNCHES";'
```

### Validating

Counts must match the source. Check a known punch before converting its timestamp and resolve
duplicates before proceeding. The new Redis namespace is `pontomaisoumenos-v2`; preserve the old
Redis instance or namespace with all of its workers stopped.

## 4. Install the package and apply migrations

In the new checkout, install the locked dependencies. Baseline `0001` corresponds to the old tables;
stamping records that correspondence without recreating them. Migration `0002` adds delivery states
and converts timestamps using the supplied timezone.

```shell
uv sync --locked --extra distributed
uv run --locked --extra distributed pontomaisoumenos migrate --stamp-legacy
uv run --locked --extra distributed pontomaisoumenos migrate --legacy-timezone "$LEGACY_TIMEZONE"
psql "$TARGET_DATABASE_URL" -c 'SELECT version_num FROM alembic_version;'
psql "$TARGET_DATABASE_URL" -c 'SELECT status, count(*) FROM "WORKING_PUNCHES" GROUP BY status;'
```

### Validating

The revision must be `0002`. Records with `done = true` must have state `done`; other records start
as `pending`. The old worker did not update `done` after submitting a punch, so check remote records
that might have been submitted before shutdown. The new scheduler expires old punches, but records
still within the lateness window need verification before starting the new processes.
Confirm that a known punch's UTC timestamp corresponds to the expected local time.

```shell
psql "$TARGET_DATABASE_URL" -c 'SELECT id, should_punch_at AT TIME ZONE '\''UTC'\'' AS utc, status FROM "WORKING_PUNCHES" ORDER BY should_punch_at LIMIT 10;'
```

## 5. Convert configuration and start both processes

Convert the old INI configuration to the current TOML format, saved as `config/local.toml`.
Supply credentials through `PM_USER__EMAIL` and `PM_USER__PASSWORD`, Redis through `PM_REDIS_URL`,
and the calendar timezone through `PM_TIMEZONE`. Both processes need the same namespace, settings,
and credentials. Review the calendar first: changing timezone or hours does not regenerate existing work.

Start the scheduler in one terminal using the converted configuration:

```shell
export PM_TIMEZONE="$LEGACY_TIMEZONE"
export PM_BROKER=redis
export PM_REDIS_URL='MIND_THE_GAP'
export PM_USER__EMAIL='MIND_THE_GAP'
export PM_USER__PASSWORD='MIND_THE_GAP'
uv run --locked --extra distributed pontomaisoumenos --config config/local.toml schedule
```

In another terminal with the same environment, start the worker. Under a supervisor or container,
run these as separate processes and allow at least 90 seconds for shutdown.

```shell
uv run --locked --extra distributed pontomaisoumenos --config config/local.toml worker
```

# Validating

1. Both processes start, and the scheduler reports no failed cycles.
2. The current month's calendar exists without duplicate user/timestamp pairs.
3. A due punch moves through `pending`, `submitting`, and `done`, with one corresponding remote record.
4. Expired punches become `failed`, without remote submissions outside the lateness window.
5. Verify `uncertain` outcomes remotely before using `reconcile`; see the [README](../../README.md).
6. On shutdown, workers finish or retain submissions for reconciliation, then close their connection pools.

# Rollback

**Stop the new scheduler and workers before rolling back. Check remote records created since the backup.**
Migration `0002` intentionally has no automatic downgrade because reinterpreting timestamps could
shift scheduled times. Restore the backup into another database and reinstall the old application
pointing at that database. Keep old workers stopped until reconciling both submissions made by the new
version and messages retained in old Redis. Restoring a database does not undo punches accepted by
the API. Preserve the migrated database for inspection and keep the original volumes until validation ends.
