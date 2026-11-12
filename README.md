# Ponto MaisOuMenos

A background punch scheduler built with Dramatiq and SQLite.
The scheduler generates a monthly calendar; workers submit punches through the PontoMais API.
Each deployment serves one account. Use a separate database file for another account.

> [!WARNING]
> I have never used this application myself. I use this repository as an experimentation ground
> for Python tools and concepts, including Dramatiq, type checking, AsyncIO, and other approaches
> to building background workers.

## Running the application

The pinned Nix/devenv environment supplies Python and uv for installation, application processes,
checks, and packaging. No database server or Redis service is needed by default.

```shell
cp .env.example .env
# Fill in credentials in .env and adjust config/default.toml.
make install
make dev
```

`make dev` applies migrations and supervises the application through devenv. The `serve` command
runs the scheduler and Dramatiq worker threads in one process. Jobs persist in
`pontomaisoumenos.db` in the working directory. See [the build contract](docs/build.md) for the
shared local/CI task graph and environment update procedure.

For a fresh Docker Compose environment:

```shell
cp .env.example .env
# Fill in PM_USER__EMAIL and PM_USER__PASSWORD in .env.
# Adjust hours, address, and coordinates in config/default.toml.
make docker
docker compose up -d
docker compose logs -f application
```

Compose applies migrations before starting the application and stores SQLite in the
`application_data` volume at `/data/pontomaisoumenos.db`. The image installs the verified wheel
and hashed runtime dependencies produced by `make ci`. Build those artifacts before using
`docker compose build` directly.

To upgrade an existing installation, follow the
[upgrade runbook](docs/runbooks/pontomaisoumenos-upgrade.md) before starting the new processes.

To run without Nix or containers, use Python 3.14 or 3.15 and uv.
uv can load `.env` explicitly; the application does not search the checkout for configuration.

```shell
uv sync --locked
uv run --locked --env-file .env pontomaisoumenos migrate
uv run --locked --env-file .env pontomaisoumenos --config config/default.toml serve
```

For separate scheduling and worker processes on one host, run these commands in separate terminals
with the same working directory, database URL, configuration, and credentials:

```shell
uv run --locked --env-file .env pontomaisoumenos --config config/default.toml schedule
uv run --locked --env-file .env pontomaisoumenos --config config/default.toml worker
```

In memory mode, `schedule` generates calendars and `worker` polls SQL and dispatches to its own
worker threads. `schedule --once` generates one calendar without leaving jobs in an unconsumed
memory queue. `serve` combines both roles. `python -m pontomaisoumenos` supports the same commands.

Redis remains available for independent producers and worker processes, and PostgreSQL remains
available for deployments that already use it. Install the optional dependencies with
`uv sync --locked --extra distributed` and include `--extra distributed` in subsequent `uv run`
commands. Set `PM_BROKER=redis`, `PM_REDIS_URL`, and optionally `PM_DATABASE_URL` to a
`postgresql+psycopg://...` URL, then start `schedule` and `worker`. Redis mode also makes
`schedule --once` dispatch near-term IDs. Existing PostgreSQL data is not automatically copied
to SQLite; keep its explicit URL when upgrading an existing installation.

## Scheduling behavior

The scheduler creates the current month's calendar when needed and keeps running across month
boundaries. Schedules persist in SQL and survive process restarts. Only near-term punches
are sent to workers; interrupted dispatches and lost messages are recovered after the persisted
delivery lease expires (300 seconds by default), provided they remain within the lateness limit.
The memory transport is based on Dramatiq's [StubBroker](https://dramatiq.io/reference.html#dramatiq.brokers.stub.StubBroker),
which upstream documents for testing, with an adapter that preserves delayed retry counters.
It carries disposable IDs; SQLite owns schedules and delivery state. Keep the SQLite file on
local persistent storage shared by the processes on that host. Memory queues do not cross processes.

Schedules match the configured monthly hours while respecting the start/end ranges and daily
maximum. An impossible combination of settings produces an error instead of an approximate calendar.
The minute range has an exclusive upper bound; `accepted_start_hour_variation = 1` fixes both the
hour and minutes. Brazilian holidays follow the configured state, with `SP` as the default.
Carnival Monday and Tuesday are also days off by default. See [optional holidays](#optional-holidays)
to select which additional dates should block punches.

## Delivery, retries, and reconciliation

| State | Meaning |
| --- | --- |
| `pending` | Eligible for dispatch and submission |
| `submitting` | Submission in progress; duplicate delivery will not submit another punch |
| `done` | Submission confirmed and recorded |
| `uncertain` | The server may have accepted the punch; manual verification required |
| `failed` | Expired punch, inactive user, or definitive rejection |

Connection failures before submission, expired authentication, and rate limits can retry with
backoff (up to five retries per message). Read/write timeouts, a 5xx response to the POST, or a
response without a verifiable time card leave the punch `uncertain`. An interrupted submission
also becomes `uncertain` after the delivery lease expires. Check the remote result before retrying:
repeating a submission with an unknown outcome could create a second punch.

Punches more than 900 seconds late expire. Restarting the scheduler does not submit the entire
historical calendar. Inspect retained work using `sqlite3 pontomaisoumenos.db` (or your PostgreSQL client):

```sql
SELECT id, should_punch_at, status, updated_at
FROM "WORKING_PUNCHES"
WHERE status IN ('uncertain', 'failed', 'submitting')
ORDER BY should_punch_at;
```

After checking the remote result in PontoMais, record the known outcome. Set `pending` only after
confirming that the punch was not accepted; the lateness limit still applies. Do not change the
scheduled date to bypass that limit.

```shell
uv run --locked --env-file .env pontomaisoumenos reconcile PUNCH_ID done
# Use 'pending' instead only after confirming there was no remote registration.
```

Confirm API compatibility with an appropriate account before enabling scheduled submissions.

## Configuration

The optional TOML file is always supplied explicitly through `--config`. `PM_` environment variables
take precedence, including nested values such as `PM_USER__EMAIL` and `PM_LOCATION__LATITUDE`.
Keep credentials out of versioned TOML. `.env` is excluded from Git and the Docker build context.

| Variable | Default / purpose |
| --- | --- |
| `PM_DATABASE_URL` | `sqlite+aiosqlite:///pontomaisoumenos.db` (relative to the process working directory) |
| `PM_BROKER` | `memory`; optional `redis` for separate broker-connected processes |
| `PM_REDIS_URL` | `redis://localhost:36379/0` |
| `PM_REDIS_NAMESPACE` | `pontomaisoumenos-v2`; Redis mode only, unique per account |
| `PM_USER__EMAIL`, `PM_USER__PASSWORD` | Required for scheduler and worker |
| `PM_TIMEZONE` | `America/Sao_Paulo`; generate local dates and persist UTC |
| `PM_HOLIDAY_SUBDIVISION` | `SP` |
| `PM_ENABLED_OPTIONAL_HOLIDAYS` | `["carnival"]`; JSON list of optional holidays treated as full days off |
| `PM_WORKER_PROCESSES`, `PM_WORKER_THREADS` | `1`, `16`; memory mode requires one process |
| `PM_HTTP_MAX_CONNECTIONS`, `PM_DATABASE_POOL_SIZE` | `16`, `5` per process |
| `PM_HTTP_TIMEOUT_SECONDS` | `20` per HTTP phase; job deadline is three times this value |
| `PM_POLL_INTERVAL_SECONDS`, `PM_DISPATCH_HORIZON_SECONDS` | `10`, `60` |
| `PM_DELIVERY_LEASE_SECONDS`, `PM_MAX_LATENESS_SECONDS` | `300`, `900` |
| `PM_DISPATCH_BATCH_SIZE` | `100` messages per cycle |
| `PM_LOG_LEVEL` | `INFO` |
| `PM_API_URL` | `https://api.pontomais.com.br` |

Changing hours, holidays, or timezone does not regenerate months with existing punches. Stop the
processes and review the persisted calendar before changing those rules in an active installation.

### Optional holidays

`enabled_optional_holidays` selects optional Brazilian holidays that this deployment treats as full
days off. An enabled date is excluded from punch generation and the monthly hours target. Public
holidays for the configured state remain excluded regardless of this list.

| Identifier | Dates excluded when enabled |
| --- | --- |
| `carnival` | Carnival Monday and Tuesday (48 and 47 days before Western Easter) |
| `ash_wednesday` | Ash Wednesday (46 days before Western Easter), the entire day |
| `corpus_christi` | Corpus Christi (60 days after Western Easter) |
| `public_servants_day` | Public Servant's Day, October 28 |
| `christmas_eve` | Christmas Eve, December 24, the entire day |
| `new_years_eve` | New Year's Eve, December 31, the entire day |

Add identifiers to the top-level list in the explicitly supplied TOML file (before `[working_hours]`):

```toml
enabled_optional_holidays = ["carnival", "corpus_christi"]
```

Remove an identifier to stop treating that optional holiday as a day off. Use `[]` to disable all
optional entries. For example, with `holiday_subdivision = "RJ"`, Carnival Tuesday remains excluded
as a state public holiday even when `carnival` is absent; Monday follows the optional setting.
Unknown identifiers fail configuration validation.

The environment override replaces the complete list and must contain a JSON array:

```shell
export PM_ENABLED_OPTIONAL_HOLIDAYS='["carnival", "corpus_christi"]'
# Or disable every optional entry:
export PM_ENABLED_OPTIONAL_HOLIDAYS='[]'
```

The existing [python-holidays](https://holidays.readthedocs.io/en/latest/auto_gen_docs/brazil/)
dependency calculates movable dates locally for each requested year. Carnival follows Western
Easter's calendar calculation; no public API, live moon-phase lookup, or annual date entry is needed.
Only the selected optional dates are added to the public calendar.

These settings describe this deployment's working calendar. The 2026 federal public-administration
[calendar](https://agenciagov.ebc.com.br/noticias/202512/confira-o-calendario-oficial-de-feriados-nacionais-e-pontos-facultativos-em-2026)
lists Ash Wednesday as optional until 14:00 and holiday eves as partial days. This scheduler supports
whole days only: enabling one of those identifiers excludes the entire date; leaving it disabled
uses normal configured hours. Partial-day hours, employer agreements, municipal holidays, and
additional days declared by annual decrees are not inferred from the state setting. Check the
calendar that applies to the deployment before enabling these entries. Existing persisted months
are not regenerated when the list changes.

### Operating the deployment

Worker threads limit the number of concurrent punches per process. Increase concurrency only when
request latency and API rate limits justify it; more processes also multiply connection pools.

Before replacing an SQLite installation, stop application processes and back up the file using
`sqlite3 pontomaisoumenos.db ".backup 'pontomaisoumenos-backup.db'"`. Preserve that backup and the
previous package/configuration for rollback. SQLite uses WAL mode; copying only the main file from
a running application can omit committed work. A database restore does not undo remote submissions.

## Credits

Based on [pontomenos](https://github.com/gustavohenrique/pontomenos).
Thanks to [g-sponda](https://github.com/g-sponda) for contributions and the project name.
License: [Unlicense](UNLICENSE).
