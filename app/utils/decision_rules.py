"""
Deterministic Advance / Hold / Reject label for a scored candidate.

Same philosophy as date_utils.py: plain Python, no LLM. The LLM
supplies the score, flags and missing must-have skills; this code
alone decides the label, so every decision has a stated reason.
"""

ADVANCE_MIN_SCORE = 75
HOLD_MIN_SCORE = 55

# Flags that stop an otherwise strong candidate from advancing.
# "low" (e.g. a location mismatch) only needs confirming.
SERIOUS_SEVERITIES = {"high", "medium"}


def decide(candidate):
    """Returns (decision, reason) for a CandidateEvaluation."""

    score = candidate.score

    if candidate.missing_must_haves:
        return "Reject", (
            "Missing must-have: "
            + ", ".join(candidate.missing_must_haves)
        )

    if score < HOLD_MIN_SCORE:
        return "Reject", f"Score {score:g} is below {HOLD_MIN_SCORE}"

    if score < ADVANCE_MIN_SCORE:
        return "Hold", (
            f"Score {score:g} is between {HOLD_MIN_SCORE} "
            f"and {ADVANCE_MIN_SCORE - 1}"
        )

    serious = sorted({
        f.flag_type.replace("_", " ")
        for f in candidate.flags
        if f.severity in SERIOUS_SEVERITIES
    })

    if serious:
        return "Hold", f"Score {score:g} but flagged: {', '.join(serious)}"

    return "Advance", f"Score {score:g}, no serious flags"
