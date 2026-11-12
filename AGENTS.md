# PontoMaisOuMenos engineering boundaries

- Preserve the README's explicit experimentation disclaimer and the one-account deployment contract.
- `flake.lock` owns Nix tooling; `uv.lock` owns Python resolution. Use the selected Nix interpreter
  and locked uv commands. Keep install/check/build/verification decisions in native `devenv.nix`
  tasks, with CI YAML owning orchestration, caching, and artifact transfer.
- Run `nix develop --impure --no-update-lock-file --command devenv tasks run app:ci` for the complete
  validation graph. Do not bypass the validation barrier or rebuild source in artifact consumers.
- SQLite and process-local Dramatiq queues are the defaults. SQL owns schedules, claims, and
  restart recovery; memory messages carry only stable job IDs. Separate memory workers poll SQL
  themselves. Redis and PostgreSQL are optional, with dependencies in the `distributed` extra.
- SQLite does not implement `SELECT FOR UPDATE`. Claims must remain atomic SQL updates. Keep
  external HTTP calls outside transactions and preserve duplicate-delivery and concurrency tests.
- A POST with an unknown remote outcome must never be retried automatically. Preserve the
  `submitting`/`uncertain` reconciliation boundary, lateness limits, and durable leases.
- Process startup owns resources; close worker loops, HTTP pools, engines, and brokers on shutdown.
  Test the actual signal entry point when lifecycle behavior changes.
- Preserve wheel resources, migrations, CLI contracts, and regular-install checks outside the checkout.
- Keep setup, operational contracts, and update procedures in repository docs. Store session logs,
  test counts, timing evidence, and implementation history in local memory or CI logs.
