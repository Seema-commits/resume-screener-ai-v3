"""
Screening rules that involve the pipeline: Rejects are never
shortlisted, and results from another model are never reused.
LiteLLM is replaced by a fake that returns valid JSON.
"""


from conftest import make_world
from app.agents.screening_agent import ScreeningAgent
from app.models.screening_models import CandidateEvaluation
from app.services import llm_client, llm_settings_service

RESUMES = "\n\n".join(
    f"--- Candidate {i}: {name} ---\n\n        {name}\nPython developer, 2018 - present"
    for i, name in enumerate(["Ann Lee", "Bob Ray"], 1))


def test_reject_is_never_shortlisted():
    agent = ScreeningAgent()
    strong_reject = CandidateEvaluation(
        candidate_name="A", score=95, recommendation="r", decision="Reject")
    advance = CandidateEvaluation(
        candidate_name="B", score=80, recommendation="r", decision="Advance")

    shortlisted, rest = agent.classify_candidates(
        [strong_reject, advance], "All qualified", 70)

    assert [c.candidate_name for c in shortlisted] == ["B"]
    assert [c.candidate_name for c in rest] == ["A"]


def test_changing_the_model_screens_everything_again(monkeypatch, fake_llm):
    admin, *_ = make_world()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-admin-test-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-admin-test-key")
    sent = fake_llm

    agent, cache = ScreeningAgent(), {}
    run = lambda: agent.screen_candidates(
        "s", "Python JD", RESUMES, "All qualified", 1, cache=cache)

    # call_ai resolves the org from the session; pin it to the admin org
    monkeypatch.setattr(llm_client, "_current_org_id", lambda: admin.org_id)

    run()
    first = len(sent)
    run()                                    # same model: all reused
    assert len(sent) == first

    llm_settings_service.set_models(admin, admin.org_id, "gemini/gemini-2.5-flash", None)
    result = run()                           # new model: screened again
    assert len(sent) == 2 * first
    assert set(sent[first:]) == {"gemini/gemini-2.5-flash"}
    assert result["run_stats"]["reused"] == 0
