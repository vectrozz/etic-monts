# Shortcuts — everything also works without make (see README).
.PHONY: ci ci-fast ci-dump dev migrate hooks

ci:            ## full local CI (lint, tests, migrations, prod image)
	scripts/ci.sh

ci-fast:       ## CI without the Docker image build
	scripts/ci.sh --fast

ci-dump:       ## CI + migration of a real dump: make ci-dump DUMP=backups/prod.sql
	scripts/ci.sh --dump $(DUMP)

dev:           ## run the app locally (all modules) on http://localhost:5003
	docker compose up --build

migrate:       ## apply migrations to the dev database
	docker compose run --rm app-flask alembic upgrade head

hooks:         ## run the CI automatically before each git push
	scripts/install-git-hooks.sh
