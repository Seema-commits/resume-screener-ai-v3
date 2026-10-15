# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
pip install -r requirements.txt
streamlit run app/ui/TalentLens_AI.py      # serves on :8501
```

There is no test suite, linter, or build step. The dev container (`.devcontainer/devcontainer.json`, Python 3.11) installs requirements and starts the Streamlit server automatically.

Configuration is read from Streamlit secrets first (`.streamlit/secrets.toml` / deployed Secrets UI), then `.env` / environment variables:
- `ANTHROPIC_API_KEY` — default key; a visitor can override it per-session on the Settings page (held only in `st.session_state.user_api_key`, passed down as `api_key`). With no key, `ai_service.call_ai` falls back to a local Ollama `llama3.1` at `localhost:11434`, then raises.
- `DATABASE_URL` — Postgres for audit logs only; defaults to a local Postgres URL. The app must keep working when the DB is unreachable (`init_db()` returns False, `log_event` swallows errors).

## Architecture

TalentLens AI is a Streamlit resume screener backed by Claude (`claude-haiku-4-5-20251001`, temperature 0, set in `app/services/ai_service.py`).

**Request flow:** `app/ui/TalentLens_AI.py` → `WorkflowOrchestrator.run_workflow(workflow, session_id, payload)` → an agent in `app/agents/` → `call_ai()` with a system prompt from `app/prompts/` → `extract_json()` (`app/utils/json_parser.py`) → Pydantic validation (`app/models/`).

- New agents must call `call_ai()` (services/ai_service.py) and `extract_json()` (utils/json_parser.py) rather than calling the Anthropic client or parsing JSON themselves.
- Rule-based checks belong in app/utils/, not inside agents.

Streamlit pages run as scripts, so `TalentLens_AI.py` and `pages/dashboard.py` insert the repo root into `sys.path` before `from app...` imports — keep that pattern in any new page.

**Feature flags in `TalentLens_AI.py`:** `SHOW_ALL_AGENT_MODES = False` hides JD Refinement, Resume Enhancement, Interview Scheduler and Interview Preparation (code intact, only "Resume Screening" is selectable); `SHOW_APPROVAL_BUTTONS = False` hides approve/reject. Resume Screening has its own JD → upload → button flow; the other modes use `st.chat_input`.

**Resume screening pipeline (`app/agents/screening_agent.py`)** — the core of the app. Design principle: the LLM extracts facts and scores; deterministic Python makes every judgment that must be explainable.
1. **Parse** (LLM, `PARSE_PROMPT`): `parser_service.extract_multiple_resumes` joins resumes with `--- Candidate N: name ---` markers; the agent splits on those markers and sends `BATCH_SIZE = 4` per call into `ParsedProfile` (dates normalized to `YYYY-MM`/`present`). Changing the marker format breaks the split.
2. **Flag** (no LLM): `utils/date_utils.run_integrity_checks` (date overlap, contradictory dates, senior title with little experience, skills without roles) + `utils/location_rules` (flag-only, small city→country table so same-country cities don't flag).
3. **Weight** (no LLM): `utils/weight_rules.derive_criteria_weights` turns JD keywords into Skills/Experience/Education/Domain caps (base 40/30/10/20, always sum to 100, Skills floor 20). Computed once per run so all candidates share one weight set.
4. **Score** (LLM, `SCREENING_PROMPT`): batches of 4 get per-criterion scores with reasons; the deterministic flags are passed in to be copied verbatim. The overall score must equal the criteria sum.
5. **Classify** (no LLM): `classify_candidates` applies the threshold (UI slider 1–10 × 10) and `top_n`, with deterministic tie-breaks (score, Skills, Experience, name).

Every LLM call retries up to 3 times on bad JSON; a batch that still fails is logged and skipped rather than failing the whole run. Keep LLM output compact — the prompts cap reason length to avoid truncation at `max_tokens`.

**Output and logging:** `services/results_display.render_full_results` renders screening results (shared by the main page and Dashboard). `services/logging_service.log_event` writes to both `logs/<session_id>.log` (JSON lines) and the `agent_logs` table; the Logs page reads from these.
