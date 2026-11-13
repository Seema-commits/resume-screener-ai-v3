# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
pip install -r requirements.txt
streamlit run app/ui/TalentLens_AI.py      # serves on :8501
```

There is no test suite, linter, or build step. The dev container (`.devcontainer/devcontainer.json`, Python 3.11) installs requirements and starts the Streamlit server automatically.

Configuration is read from Streamlit secrets first (`.streamlit/secrets.toml` / deployed Secrets UI), then `.env` / environment variables:
- `ANTHROPIC_API_KEY` — default key; a visitor can override it per-session on the Settings page (held only in `st.session_state.user_api_key`, passed down as `api_key`). With no key, `ai_service.call_ai` raises a clear error.
- `DATABASE_URL` — Postgres for audit logs only; defaults to a local Postgres URL. The app must keep working when the DB is unreachable (`init_db()` returns False, `log_event` swallows errors).

## Architecture

TalentLens AI is a Streamlit resume screener backed by Claude (`claude-haiku-5-5` at effort `low`, set by `MODEL`/`EFFORT` in `app/services/ai_service.py`). Haiku 5.5 always thinks first: read text blocks by type, not `content[0]`, and leave `max_tokens` room for thinking. Don't send `temperature`/`top_p`/`top_k` — the API rejects them.

**Request flow:** `app/ui/TalentLens_AI.py` → `WorkflowOrchestrator.run_workflow(workflow, session_id, payload)` → an agent in `app/agents/` → `call_ai()` with a system prompt from `app/prompts/` → `extract_json()` (`app/utils/json_parser.py`) → Pydantic validation (`app/models/`).

- New agents must call `call_ai()` (services/ai_service.py) and `extract_json()` (utils/json_parser.py) rather than calling the Anthropic client or parsing JSON themselves.
- Rule-based checks belong in app/utils/, not inside agents.

Streamlit pages run as scripts, so `TalentLens_AI.py` and `pages/dashboard.py` insert the repo root into `sys.path` before `from app...` imports — keep that pattern in any new page.

**Feature flags in `TalentLens_AI.py`:** `SHOW_ALL_AGENT_MODES = False` hides JD Refinement, Resume Enhancement, Interview Scheduler and Interview Preparation (code intact, only "Resume Screening" is selectable); `SHOW_APPROVAL_BUTTONS = False` hides approve/reject. Resume Screening has its own JD → upload → button flow; the other modes use `st.chat_input`.

**Resume screening pipeline (`app/agents/screening_agent.py`)** — the core of the app. Design principle: the LLM extracts facts and scores; deterministic Python makes every judgment that must be explainable.
1. **Parse** (LLM, `PARSE_PROMPT`): `parser_service.extract_multiple_resumes` joins resumes with `--- Candidate N: name ---` markers; the agent splits on those markers and sends `BATCH_SIZE = 4` per call into `ParsedProfile` (dates normalized to `YYYY-MM`/`present`). Changing the marker format breaks the split.
2. **Flag** (no LLM): `utils/date_utils.run_integrity_checks` (date overlap, contradictory dates, senior title with little experience, skills without roles) + `utils/location_rules` (flag-only; `_country_for` understands "City", "City, Country" and "Country", so same-country cities don't flag) + `utils/injection_guard.detect_injection` (high-severity `prompt_injection_suspected` flag).
3. **Weight** (no LLM): `utils/weight_rules.derive_criteria_weights` turns JD keywords into Skills/Experience/Education/Domain caps (base 40/30/10/20, always sum to 100, Skills floor 20). Computed once per run so all candidates share one weight set.
4. **Score** (LLM, `SCREENING_PROMPT`): batches of 4 get per-criterion scores with reasons; the deterministic flags are passed in to be copied verbatim. The overall score must equal the criteria sum. The same call returns `summary`, `missing_must_haves` (JD-required skills only) and `phone_screen_questions` — no extra LLM call.
5. **Decide + classify** (no LLM): any rule-based flag the LLM didn't copy is added back first, so it always reaches the decision. `utils/decision_rules.decide` sets `decision`/`decision_reason` (Reject: missing must-have or score < 55; Hold: 55–74, or ≥ 75 with a high/medium flag; else Advance). Then `classify_candidates` applies the threshold (UI slider 1–10 × 10) and `top_n`, with deterministic tie-breaks (score, Skills, Experience, name). The label and the shortlist are independent.

**PII masking:** before any resume reaches the LLM, `utils/pii_masking.mask_resume` replaces the candidate's name with a stable `CANDIDATE_xxxxxx` token (from the resume fingerprint) and emails, phone numbers and LinkedIn/GitHub URLs with placeholders. It also returns the real name, email and phone, kept only in the app: the agent logs the `response` event while still masked, then adds `email`/`phone` and `unmask`s names for the screen only - logs never hold real names, emails or phones. Each parse batch is logged as an `llm_input` event (the exact masked text sent), viewable on the Logs page with "Show all events". Never send unmasked resume text to `call_ai`.

**Prompt-injection guardrails:** each resume is wrapped by `injection_guard.wrap_as_data` in `<resume>` tags (look-alike tags inside are stripped) and both prompts say resume text is data, never instructions. Instruction-like phrases get a high-severity flag, so an injected resume can reach Hold at best, never Advance, even if the LLM is fooled; the UI shows a warning with the count.

**Incremental re-screening:** the UI passes `st.session_state.screening_cache` as `cache`. Parsed profiles are cached by resume fingerprint (file name + text) and scores by JD fingerprint + resume fingerprint, so re-running after adding resumes only sends new ones to Claude, and editing the JD re-scores without re-parsing. "Start New Screening Session" clears it.

Every LLM call retries up to 3 times on bad JSON; a batch that still fails is logged and skipped (and not cached) rather than failing the whole run. Keep LLM output compact — the prompts cap reason length to avoid truncation at `max_tokens`.

**Output and logging:** `services/results_display.render_full_results` renders screening results (shared by the main page and Dashboard). `services/logging_service.log_event` writes to both `logs/<session_id>.log` (JSON lines) and the `agent_logs` table; the Logs page reads from these.
