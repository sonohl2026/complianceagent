# Operations

## Build sequence

The application is built in the milestone order below (see also the task list tracked for this
build). Each milestone must leave `docker compose up --build` working end to end before the next
begins.

1. **Foundation** — repo, Docker Compose, FastAPI, React, Postgres+pgvector, Redis, health checks.
2. **Projects & document ingestion** — companies/products/projects, uploads, parsers, chunking.
3. **Retrieval** — local embeddings, pgvector indexing, hybrid (vector + full-text) search.
4. **Website crawling** — crawl wizard, SSRF-guarded HTTPX/Playwright crawler, diffing.
5. **OpenRouter integration & structured analyses** — the staged compliance analysis pipeline.
6. **Synthesis & reporting** — verdicts, readiness scoring, citation audit, Markdown/JSON export.
7. **UI polish** — dashboards, scorecards, pathway matrix, claims register, chat.
8. **Monitoring** — Celery Beat scheduled recrawls and material-change alerts.
9. **Security, tests, docs, acceptance report** — SSRF/prompt-injection/file-security tests,
   backup/restore, full test suite, seeded SonoHL example project, final acceptance report.

## Common commands

See the root `Makefile`: `make setup|build|up|down|restart|logs|migrate|seed|test|lint|format|
backup|restore|reset`.

## Backups

`make backup` runs `scripts/backup.py` inside the `api` container: `pg_dump --clean --if-exists
--no-owner --no-privileges`s the database and tars the dump together with `data/storage/`
(excluding the backups directory itself) into
`data/storage/exports/backups/backup-<timestamp>.tar.gz`. `make restore FILE=<path>` reverses
this — it is destructive (overwrites current DB + storage with the archive's contents), so only
run it when you intend to discard current local state. Both scripts have been validated against a
real Postgres+pgvector round-trip (dump → drift → restore), including confirming vector columns
restore byte-for-byte and that restore merges into `data/storage/` rather than nesting or wiping
it.

**Backup archives contain the OpenRouter API key in plaintext.** Every archive includes
`data/storage/config/app_settings.json`, which holds the configured `openrouter_api_key`. Treat
backup files exactly like a secrets/`.env` file: store them somewhere access-controlled (encrypted
disk, permissioned directory), never attach them to tickets/chat/email, and never sync the backups
directory to a public or shared location without stripping or encrypting it first.

**Scheduling automated backups.** This app is locally hosted with no managed cloud backup service,
so periodic backups need to be scheduled on the host. On macOS, a `launchd` user agent is the
standard mechanism (`cron` also works if you prefer it). Example: run a daily backup at 2am via
`launchd` —

```xml
<!-- ~/Library/LaunchAgents/com.medtech.backup.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.medtech.backup</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/make</string>
    <string>-C</string>
    <string>/absolute/path/to/complianceagent</string>
    <string>backup</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>2</integer>
    <key>Minute</key><integer>0</integer>
  </dict>
  <key>StandardOutPath</key><string>/tmp/medtech-backup.log</string>
  <key>StandardErrorPath</key><string>/tmp/medtech-backup.log</string>
</dict>
</plist>
```

Load it with `launchctl load ~/Library/LaunchAgents/com.medtech.backup.plist` (requires the Docker
Compose stack to already be running at that hour, since `make backup` execs into the `api`
container). Prune old archives periodically — `scripts/backup.py` does not do this automatically —
e.g. `find data/storage/exports/backups -name 'backup-*.tar.gz' -mtime +30 -delete` to keep 30
days.

## Logs

`make logs` tails all service logs. Per-service: `docker compose logs -f api` (etc). The
application does not log full document contents or the OpenRouter API key by design
(`docs/security.md`).
