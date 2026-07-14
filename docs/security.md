# Security

## Threat model (summary)

This is a local, single-user tool that (a) fetches and renders content from the open internet
(website crawling) and (b) sends retrieved context to a third-party model API (OpenRouter). The
two things worth defending hardest are: the crawler being turned into an SSRF vector, and crawled
or uploaded content being used to smuggle instructions into the model ("prompt injection").

## Local-network binding

- `docker-compose.yml` publishes `frontend` and `api` on `${APP_HOST:-127.0.0.1}` — not
  `0.0.0.0` — so the stack is not reachable from other machines on your LAN by default.
- `ALLOW_LAN_ACCESS` exists as an explicit, off-by-default opt-in for the (documented, not yet
  enforced pre-Milestone-9) LAN-exposure path. Setting it does not itself change the compose
  binding — you must also change `APP_HOST` — by design, so a single flag flip can't silently
  expose the app.

## Secrets

- `OPENROUTER_API_KEY` is read by the `api`/`worker`/`scheduler` containers only; the frontend has
  no environment access to it and the `/api/v1/settings` endpoint never echoes the raw key back —
  only a masked `****last4` preview (see `backend/app/services/storage/settings_store.py` and
  `backend/app/api/v1/settings.py`).
- `.env` is gitignored. `.env.example` contains no real secrets.
- Runtime settings (including the key, once set through the UI) are stored in a local JSON file
  under `data/storage/config/app_settings.json`, itself gitignored via the `data/storage/**`
  exclusion in `.gitignore`.

## SSRF protections (crawler — Milestone 4, implemented)

`app/services/crawling/ssrf.py` blocks `file://`/`ftp://` schemes, `localhost` and other literal
blocked hostnames, loopback/private/link-local/multicast/reserved IPv4 and IPv6 ranges, and known
cloud-metadata addresses (`169.254.169.254`, AWS IMDSv2 IPv6). Every fetch resolves DNS and
validates the resulting IP immediately before connecting
(`app/services/crawling/fetch.py::safe_fetch`), and — critically — **every redirect hop is
independently revalidated**, since the classic real-world SSRF exploitation path is an
attacker-controlled open redirect rather than a literal internal URL (see
`tests/test_fetch.py::test_safe_fetch_blocks_redirect_into_private_ip`).

**Honest residual limitation**: this closes the common vectors above but does not fully eliminate
a theoretical DNS-rebinding race between our validation and the underlying TCP connect a moment
later, since it validates-then-connects rather than pinning the validated IP into the socket
layer. Full elimination needs a custom transport that connects to the exact validated IP while
still presenting the original hostname for TLS SNI/certificate checks — tracked as a future
hardening item, not silently assumed solved.

The crawler additionally: respects `robots.txt` per-user-agent group semantics (including that a
more specific agent group replaces the wildcard group entirely, not adds to it —
`app/services/crawling/robots.py`), restricts to the same registrable domain by default
(`app/services/crawling/url_utils.py`), and applies a politeness delay honoring both the
configured `CRAWL_DELAY_MS` and any `Crawl-delay` directive from robots.txt.

## Prompt-injection defense (Milestone 5, implemented)

Crawled and uploaded content is treated as untrusted data, never as instructions, once it reaches
the LLM analysis pipeline:

- Every retrieved chunk is wrapped with explicit `BEGIN/END UNTRUSTED SOURCE CONTENT` boundaries
  before being placed in a model request (`app/services/analysis/prompt_composer.py`), and is
  placed only in the user-message region — verified by
  `tests/test_prompt_composer.py::test_compose_messages_never_puts_untrusted_content_in_system_prompt`,
  which asserts a simulated injection string never appears in the composed system prompt.
- The immutable security preamble (also in `prompt_composer.py`, not DB-editable — separate from
  the versioned master prompt) explicitly instructs the model to ignore embedded instructions and
  to reflect suspected injection attempts as a finding rather than act on them. The master
  compliance prompt (`prompts/master_system_prompt.md` §9.3) reinforces the same instruction as
  controlling policy.
- The LLM is never given the ability to execute shell commands, SQL, or arbitrary network
  requests derived from crawled or uploaded content — `structured_completion` returns data only,
  there is no tool-calling/function-execution surface in this pipeline.

**Known gap**: the model is asked to flag injection attempts as a finding, but there is no
separate automated detector independent of the model's own judgment (e.g. a regex/heuristic
pre-scan for common injection phrasing) — if a sufficiently capable injection fooled the model
itself, nothing downstream would catch it. Not implemented; noted as a residual risk rather than
silently assumed handled.

## Upload security (Milestone 2)

Planned controls: size limits (`MAX_UPLOAD_MB`), content-sniffed MIME validation (not just file
extension), sanitized + randomized stored filenames, rejection of executables/unsupported
archives, and a quarantine directory (`data/storage/quarantine/`) for anything that fails
validation.

## Frontend security

- Strict `Content-Security-Policy: default-src 'none'`, `X-Frame-Options: DENY`,
  `X-Content-Type-Options: nosniff`, and `Referrer-Policy: no-referrer` are set on every API
  response (`backend/app/main.py`).
- CORS is restricted to the local frontend origin; no cookies are used, so CSRF is not applicable
  to the current no-auth, single-user design.
- Markdown/HTML rendering of crawled or uploaded content must be sanitized before render
  (Milestone 7) — raw HTML from crawled pages is never injected via `dangerouslySetInnerHTML`
  without sanitization.

## Data deletion

Deferred to Milestone 9: delete company/project/document/model-response-history endpoints, and a
documented "delete all local data" path (`make reset` already removes the Postgres volume; full
per-entity cascading delete needs the Milestone 2+ data model first).

## What is NOT yet true (be honest about current state)

As of Milestone 1: there is no authentication, no upload pipeline, no crawler, and no LLM traffic
at all yet. The only network egress the app currently performs is the browser talking to the
local API container. This file will be updated as each control above is actually implemented —
treat unchecked items as **not yet enforced**, not as already-shipped guarantees.
