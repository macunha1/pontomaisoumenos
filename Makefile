DEVELOP = nix develop --impure --no-update-lock-file --command

.PHONY: install check lint format typecheck tests build ci benchmark benchmark-http docker dev

install check lint typecheck build ci:
	$(DEVELOP) devenv tasks run app:$@

tests:
	$(DEVELOP) devenv tasks run app:test

format:
	$(DEVELOP) sh -c 'uv run --locked ruff check --fix . && uv run --locked ruff format . && nixfmt flake.nix devenv.nix shell.nix'

benchmark:
	$(DEVELOP) uv run --locked python scripts/benchmark_schedule.py

benchmark-http:
	$(DEVELOP) uv run --locked python scripts/benchmark_http.py

docker: ci
	$(DEVELOP) devenv tasks run app:image

dev:
	$(DEVELOP) devenv up
