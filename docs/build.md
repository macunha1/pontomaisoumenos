# PontoMaisOuMenos development and CI

`flake.lock` pins Nixpkgs, devenv, Python, uv, and system tooling. `uv.lock` owns application
dependencies, optional dependencies, and development tools. The build backend is pinned in
`pyproject.toml` and included in the locked development environment. Shell entry installs no
application dependencies and starts no application processes.

Use the same complete graph locally and in GitHub Actions:

```shell
nix develop --impure --no-update-lock-file --command devenv tasks run app:ci
```

The default shell uses Python 3.14. `.#python314` and `.#python315` explicitly select the supported
interpreters; `UV_PYTHON` points at the selected Nix interpreter so `.python-version` cannot change
the CI interpreter. uv cannot download a different interpreter. The declared platforms are
`x86_64-linux`, `aarch64-linux`, and `aarch64-darwin`; GitHub Actions exercises `x86_64-linux`.
The other platforms need their own validation before being relied upon.

## Task ownership

| Task | Contract |
| --- | --- |
| `app:install` | Validate the uv lock and install the selected environment |
| `app:lint` | Ruff lint/format checks and pinned Nix formatting |
| `app:typecheck` | ty with warnings treated as errors |
| `app:test` | Offline behavior tests, including SQLite concurrency, restart recovery, and process shutdown |
| `app:check` | Barrier requiring every validation task to succeed |
| `app:build` | Build an sdist and its wheel only after successful validation |
| `app:verify` | Install the wheel normally in a fresh venv, run CLI/migrations/tests outside the checkout, export hashed runtime requirements, checksum artifacts |
| `app:ci` | Complete validation, packaging, and verification graph |
| `app:image` | Verify downloaded artifact checksums, build the runtime image, smoke-test CLI and SQLite migrations |
| `app:migrate` | Load `.env` explicitly and apply packaged migrations |
| `app:dev` | Install, migrate, then run scheduling and worker threads together |

`make` provides aliases for these entry points. `make dev` uses `devenv up` to supervise the
application; `make ci` runs the complete graph. `devenv test` connects its environment hook to
that same graph and reports the selected tools. Direct commands such as `uv run --locked pytest`
remain available inside the environment.

The tests use local HTTP fixtures and fake credentials. Optional PostgreSQL/Redis integration
tests require `PM_TEST_DATABASE_URL`, `PM_TEST_REDIS_URL`, and the `distributed` extra; they are
skipped without those services. SQLite and the real memory worker lifecycle are covered by the
default suite. CI does not call the live PontoMais API.

## Artifacts and containers

`dist/` contains one application sdist, its wheel, `requirements.txt` with hashes, and
`SHA256SUMS`. The wheel contains the CLI, typing marker, and Alembic migrations. Application
builds use the locked development backend without isolated dependency resolution. Verification
uses hashed dependencies from the lock, clears source-path injection, and installs the wheel
without resolving a second dependency set.

GitHub Actions owns triggers, runner selection, the Python shell matrix, cache transport, and
artifact transfer. The dependent image job downloads the verified Python 3.14 distribution and
calls `app:image`; it does not rebuild Python source. Docker installs that wheel and its exported
runtime dependencies. Run `make docker` before building Compose locally. The runtime image starts
as an unprivileged user, stores SQLite under `/data`, and defaults to `serve`.

Environment evaluation, checks, and builds do not need account credentials. Devenv dotenv loading
is disabled; only development commands explicitly load `.env`. Tasks still inherit the caller's
environment, so run CI from a clean account/environment. Pinning tools and dependencies does not
make working-tree tasks hermetic or guarantee byte-identical artifacts across platforms.

## Cache and bootstrap boundaries

The flake declares the [official devenv binary cache and signing key](https://devenv.sh/guides/using-with-flakes/).
Local users review and accept those settings; no developer-wide configuration is changed. GitHub's
commit-pinned Nix installer explicitly accepts them on its disposable runner. The installer is a
bootstrap boundary outside the flake, and hosted runner images remain mutable.

The shared setup action restores/saves the Nix store and uv download cache through GitHub's cache
service. Keys include OS, architecture, selected interpreter shell, setup configuration, and the
Nix lock/environment files. The image job shares the Python 3.14 key. A fallback reuses unchanged
store paths across lock updates. Checks always execute regardless of cache hits.

CI retains a shell profile under `RUNNER_TEMP` until post-job cache saving. This keeps the runtime
closure, including the native task runner, reachable during cache garbage collection. The 6 GiB
target cannot evict referenced paths and is not a hard size cap. No developer-wide GC runs here.
Branch access rules, successful-job saving, cache quotas, and eviction determine remote reuse.
Review cache restore/save logs and task timings separately when comparing cold and warm CI runs;
local store reuse does not establish remote cache behavior.

## Updating and rollback

Update Nix inputs explicitly with `nix flake update`, review `flake.lock`, and run `app:ci` for both
Python shells. Update application dependencies with `uv lock --upgrade`, review `uv.lock`, then
run the same graph. Review changes to the build-backend pin and both lockfiles together. Update
GitHub action SHAs and container image digests at their own boundaries. Routine commands must
preserve both locks.

SQLite is the fresh-install default. Existing PostgreSQL installations retain their explicit URL
and use the optional dependencies; changing defaults does not migrate persisted records between
database engines. Follow the [application instructions](../README.md) for SQLite backups and the
[legacy upgrade runbook](runbooks/pontomaisoumenos-upgrade.md) for PostgreSQL data. Restore a verified
database backup with the matching package/configuration for rollback, then reconcile remote
submissions before restarting workers.
