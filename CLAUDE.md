# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
pip install -r requirements.txt
streamlit run app/ui/TalentLens_AI.py      # serves on :8501
uvicorn backend.main:app --reload          # API on :8000, interactive docs at /docs (COOKIE_SECURE=false for local http)
pytest tests/                              # security + LLM rules; uses DATABASE_URL (wiped!) or temp SQLite
pytest tests/test_auth_and_permissions.py::test_scan_visibility_by_role   # one test
python -m app.scripts.create_superadmin    # create a Superadmin from the command line
```

There is no linter or build step. The dev container (`.devcontainer/devcontainer.json`, Python 3.11) installs requirements and starts the Streamlit server automatically.

Configuration is read from Streamlit secrets first (`.streamlit/secrets.toml` / deployed Secrets UI), then `.env` / environment variables:
All secrets go through `app/config.get_secret(name)`.
- `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `OPENAI_API_KEY`, … (`llm_config.PROVIDER_KEY_SECRETS`) — provider keys for the **TalentLens Admin org only**. Every other org uses its own keys, entered on its Users page (HR Manager) or AI Settings (Superadmin) and stored encrypted in `org_api_keys`; an org never falls back to another org's or the admin's keys.
- `KEY_ENCRYPTION_SECRET` — any 32+ character random string; encrypts org keys. Changing it makes stored org keys unreadable (orgs must re-enter them).
- `LLM_DEFAULT_MODEL` / `LLM_FALLBACK_MODEL` — optional LiteLLM model names for orgs without their own choice (default `anthropic/claude-haiku-5-5` → `anthropic/claude-sonnet-5-5`).
- `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST` — optional; with both keys set, every LLM call is traced in Langfuse (default host EU `https://cloud.langfuse.com`; US `https://us.cloud.langfuse.com`). `LANGFUSE_TRACE_CONTENT = "false"` sends metadata only. Needs an app restart after changing.
- API only: `FRONTEND_ORIGINS` (comma-separated, default `http://localhost:5173`) for CORS; `COOKIE_SECURE` (default `true`; `false` for local http); `COOKIE_SAMESITE` (default `lax`; `none` when the frontend is on another site).
- `DATABASE_URL` — **required** Postgres (Neon). Logins, users and scan history live there; without it the app shows an error and stops. `init_db()` creates the tables (`create_all`, no migrations yet).
- `BOOTSTRAP_SUPERADMIN_EMAIL` / `_PASSWORD` / `_NAME` — optional; while no Superadmin exists, `init_db()` creates one with this temporary password (must be changed at first login). Remove after first use.

## Architecture

TalentLens AI is a Streamlit resume screener. **All LLM calls go through `services/llm_client.call_ai()`** (LiteLLM) — the only file that imports `litellm`; `app/llm_config.py` is the only file that names providers/models. Per call it masks contact details (safety net), picks the org's model + fallback (`llm_settings_service.models_for_org`), uses the org's key, falls back on any provider error, and logs an `llm_call` event (provider, model, fallback_used, tokens, ms — never prompts or keys). `PROVIDER_PARAMS` keeps thinking at `low` (Claude: `output_config` passed through unchanged). Don't send `temperature`/`top_p`/`top_k`. Langfuse tracing (`TRACING_CALLBACKS`, `_tracing_kwargs`) is on only when its keys are set; keys go per call (never into env vars or logs), and each call is labelled with `stage` (`parse`/`score`), the screening `session_id`, and `org:`/`user:` id tags — pass `stage`/`session_id` to `call_ai` from new agents. `langfuse` is pinned `<5` because LiteLLM's callback doesn't support v5 yet.

**Users and roles:** `app/auth/permissions.py` is the only place that decides access — `has_permission(user, action)` from `ROLE_PERMISSIONS`, `can_manage_org(actor, action, org_id)` for org-level actions (e.g. `manage_org_keys`: Superadmin any org, HR Manager own org; `choose_llm_models` is Superadmin only), and `can_manage(actor, target_role, target_org_id)` (Superadmin manages HR Managers/Executives in any org; an HR Manager only HR Executives in her own org; Superadmins are created only via the bootstrap secrets or the script). Never check `user.role` elsewhere, and never let the LLM decide permissions. `services/auth_service.py` does bcrypt logins (5 failures lock the account; unlock = reset password), one-time temporary passwords with forced change, and deactivate-not-delete; every action re-checks `can_manage`. Passwords and staff emails are never logged. `services/scan_service.py` saves each screening session as one `scans` row plus `scan_results` rows (extracted results only, no resume files) and scopes every read by role in SQL (`count_scans`/`list_scans` share one filter builder and page in SQL). Every table has `org_id`. Long lists use `app/ui/pagination.paginate()` (25 per page): Scan History and Logs page in SQL; Users and Organizations are small and are paged in Python.

**Pages:** `TalentLens_AI.py` is the entry point for every page: DB check → login → forced password change (both shown with a hidden one-page menu, so a signed-out user sees no menu) → `st.navigation` with only the pages the role allows (`PAGES` list). Each page in `app/ui/pages/` also starts with `require(action)` from `app/ui/auth_ui.py` — keep that in any new page; hiding a page is never the only check. Pages run through the entry point, which puts the repo root on `sys.path`.

**API (`backend/`):** FastAPI for the coming React frontend, a thin layer over the same `app/` services — the Streamlit app keeps working alongside it. `backend/deps.py`: `current_user` reads the httpOnly session cookie (`auth_service.session_user`: only a SHA-256 of the token is stored in `user_sessions`; 8 h idle / 7 days max; ended on logout, deactivation and password reset), requires the `X-CSRF-Token` header (from `/api/auth/me`) on every non-GET, blocks everything but the auth endpoints until a temporary password is changed, and `require(action)` checks `has_permission`. Services still re-check (their `AuthError` → 400). `POST /api/scans` streams server-sent events (`progress` → `result`/`error`) while the pipeline runs in a thread with the request's context; its "only screen new resumes" cache lives in process memory per (user, scan). Uploads: PDF/DOCX, ≤ 20 resumes, ≤ 5 MB each. `app/context.get_current_user()` is how services (logging, LLM client) find the user in both front ends — use it rather than `st.session_state`.

**Request flow:** `app/ui/pages/screening.py` (or `POST /api/scans`) → `WorkflowOrchestrator.run_workflow(workflow, session_id, payload)` → an agent in `app/agents/` → `call_ai()` with a system prompt from `app/prompts/` → `extract_json()` (`app/utils/json_parser.py`) → Pydantic validation (`app/models/`).

- New agents must call `call_ai()` (services/llm_client.py) and `extract_json()` (utils/json_parser.py) rather than calling the Anthropic client or parsing JSON themselves.
- Rule-based checks belong in app/utils/, not inside agents.

**Feature flag in `pages/screening.py`:** `SHOW_ALL_AGENT_MODES = False` hides JD Refinement, Resume Enhancement, Interview Scheduler and Interview Preparation (code intact, only "Resume Screening" is selectable). Resume Screening has its own JD → upload → button flow; the other modes use `st.chat_input`.

**Resume screening pipeline (`app/agents/screening_agent.py`)** — the core of the app. Design principle: the LLM extracts facts and scores; deterministic Python makes every judgment that must be explainable.
1. **Parse** (LLM, `PARSE_PROMPT`): `parser_service.extract_multiple_resumes` joins resumes with `--- Candidate N: name ---` markers; the agent splits on those markers and sends `BATCH_SIZE = 4` per call into `ParsedProfile` (dates normalized to `YYYY-MM`/`present`). Changing the marker format breaks the split.
2. **Flag** (no LLM): `utils/date_utils.run_integrity_checks` (date overlap, contradictory dates, senior title with little experience, skills without roles) + `utils/location_rules` (flag-only; `_country_for` understands "City", "City, Country" and "Country", so same-country cities don't flag) + `utils/injection_guard.detect_injection` (high-severity `prompt_injection_suspected` flag).
3. **Weight** (no LLM): `utils/weight_rules.derive_criteria_weights` turns JD keywords into Skills/Experience/Education/Domain caps (base 40/30/10/20, always sum to 100, Skills floor 20). Computed once per run so all candidates share one weight set.
4. **Score** (LLM, `SCREENING_PROMPT`): batches of 4 get per-criterion scores with reasons; the deterministic flags are passed in to be copied verbatim. The overall score must equal the criteria sum. The same call returns `summary`, `missing_must_haves` (JD-required skills only) and `phone_screen_questions` — no extra LLM call.
5. **Decide + classify** (no LLM): any rule-based flag the LLM didn't copy is added back first, so it always reaches the decision. `utils/decision_rules.decide` sets `decision`/`decision_reason` (Reject: missing must-have or score < 55; Hold: 55–74, or ≥ 75 with a high/medium flag; else Advance). Then `classify_candidates` applies the threshold (UI slider 1–10 × 10) and `top_n`, with deterministic tie-breaks (score, Skills, Experience, name). A Reject is never shortlisted, whatever its score.

**PII masking:** before any resume reaches the LLM, `utils/pii_masking.mask_resume` replaces the candidate's name with a stable `CANDIDATE_xxxxxx` token (from the resume fingerprint) and emails, phone numbers and LinkedIn/GitHub URLs with placeholders. It also returns the real name, email and phone, kept only in the app: the agent logs the `response` event while still masked, then adds `email`/`phone` and `unmask`s names for the screen only - logs never hold real names, emails or phones. Each parse batch is logged as an `llm_input` event (the exact masked text sent), viewable on the Logs page (kept 7 days). Never send unmasked resume text to `call_ai`.

**Prompt-injection guardrails:** each resume is wrapped by `injection_guard.wrap_as_data` in `<resume>` tags (look-alike tags inside are stripped) and both prompts say resume text is data, never instructions. Instruction-like phrases get a high-severity flag, so an injected resume can reach Hold at best, never Advance, even if the LLM is fooled; the UI shows a warning with the count.

**Incremental re-screening:** the UI passes `st.session_state.screening_cache` as `cache`. Parsed profiles are cached by resume fingerprint (file name + text) and scores by JD fingerprint + resume fingerprint, so re-running after adding resumes only sends new ones to the LLM, and editing the JD re-scores without re-parsing. The cache also stores the org's models (`llm_client.current_models()`); when they change it is cleared, so results from another model are never reused. "Start New Screening Session" clears it.

Every LLM call retries up to 3 times on bad JSON; a batch that still fails is logged and skipped (and not cached) rather than failing the whole run. Keep LLM output compact — the prompts cap reason length to avoid truncation at `max_tokens`.

**Output and logging:** `services/results_display.render_full_results` renders screening results (shared by the screening page and Scan History). `services/logging_service.log_event` writes to the `agent_logs` table only (no log files), tagging each entry with the logged-in user's `org_id`/`user_id`. Each event type has a retention category (`AUDIT_EVENTS` 365 days, `ERROR_EVENTS` 90, `DEBUG_EVENTS` — `llm_input`/`parsed_profiles`/`request`/`response` — 7, anything else 90); `purge_old_logs()` runs from `init_db()` at most once a day. Add new audit/error event types to those sets. The Logs page (Superadmin only) reads the table with filters and 25-per-page paging (`app/ui/pagination.paginate`).
