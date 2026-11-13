import hashlib
import json
import re

from app.services.llm_client import call_ai, current_models
from app.prompts.screening_prompts import SCREENING_PROMPT
from app.prompts.parsing_prompts import PARSE_PROMPT
from app.utils.json_parser import extract_json
from app.utils.date_utils import run_integrity_checks
from app.utils.weight_rules import derive_criteria_weights
from app.utils.decision_rules import decide
from app.utils.pii_masking import mask_resume, unmask
from app.utils.injection_guard import detect_injection, wrap_as_data
from app.utils.location_rules import (
    parse_jd_location,
    check_location_mismatch
)
from app.models.screening_models import (
    CandidateEvaluation,
    CandidateScoringResponse,
    Flag,
    ParsedProfile,
    ParsedProfilesResponse
)
from app.services.logging_service import log_event


# Candidates per batch, for BOTH parsing and scoring calls. Kept
# small so a batch's JSON response never gets close to the model's
# max_tokens limit, regardless of how many resumes are uploaded in
# total (this is what fixes the truncation/JSON-decode-error issue
# at scale).
BATCH_SIZE = 4

# Thinking tokens count toward these caps too (Haiku 5.5 thinks
# before answering), so they leave room above the JSON itself.
PARSE_MAX_TOKENS_PER_BATCH = 12000
SCORING_MAX_TOKENS_PER_BATCH = 8000


def _split_into_candidate_chunks(candidate_text):
    """
    parser_service.py formats combined_text with
    "--- Candidate N: name ---" markers before each resume's text.
    Split back into one chunk per candidate so parsing can be
    batched instead of sent as one giant request.
    """

    parts = re.split(r"(?=--- Candidate \d+:)", candidate_text)
    return [p.strip() for p in parts if p.strip()]


def _fingerprint(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _resume_key(chunk):
    """
    Identity of one uploaded resume: its file-derived name and its
    text. The "Candidate N" number is left out because it shifts
    when more files are added.
    """

    return _fingerprint(re.sub(r"^--- Candidate \d+:", "---", chunk))


class ScreeningAgent:

    # -----------------------------------------------
    # STAGE 1: parse raw resume text into structured
    # entities (roles with dates, education, skills).
    # Facts only - no scoring/judgment happens here.
    # Done in batches so large resume counts can't
    # truncate the response.
    #
    # Returns (index, profile) pairs, where index is the
    # position in `chunks` the profile came from, or None
    # when a batch returned a different number of
    # profiles than it was sent and they can't be matched.
    # -----------------------------------------------

    def parse_resumes(self, session_id, chunks):

        if not chunks:
            return []

        all_profiles = []

        for i in range(0, len(chunks), BATCH_SIZE):

            batch_chunks = chunks[i:i + BATCH_SIZE]
            batch_text = "\n\n".join(
                wrap_as_data(chunk) for chunk in batch_chunks
            )

            # Exactly what the LLM receives (already masked) - lets
            # anyone verify on the Logs page that no name, email or
            # phone number is sent.
            log_event(
                session_id=session_id,
                agent_name="ScreeningAgent",
                event_type="llm_input",
                data={"stage": "parse", "text": batch_text}
            )

            # Retry up to 3 total attempts - a malformed/truncated
            # JSON response from the model is often a one-off
            # glitch, not tied to specific resume content (we've
            # seen the same candidate succeed alone but fail when
            # batched, and vice versa) - retrying immediately
            # usually resolves it without losing the whole batch.
            max_attempts = 3
            last_exception = None
            last_response = None

            for attempt in range(1, max_attempts + 1):

                response = call_ai(
                    batch_text,
                    system_prompt=PARSE_PROMPT,
                    max_tokens=PARSE_MAX_TOKENS_PER_BATCH,
                    stage="parse",
                    session_id=session_id
                )

                last_response = response

                try:

                    parsed = extract_json(response)
                    validated = ParsedProfilesResponse(**parsed)

                    # The model returns profiles in the order the
                    # resumes were sent; if the count doesn't match,
                    # keep them but don't guess which is which.
                    if len(validated.profiles) == len(batch_chunks):
                        indexes = range(i, i + len(batch_chunks))
                    else:
                        indexes = [None] * len(validated.profiles)

                    all_profiles.extend(
                        zip(indexes, validated.profiles)
                    )
                    last_exception = None
                    break  # success - no need to retry

                except Exception as e:

                    last_exception = e

                    print(
                        f"\n===== PARSE BATCH ATTEMPT "
                        f"{attempt}/{max_attempts} FAILED =====\n"
                    )
                    print(
                        f"Batch {i // BATCH_SIZE + 1}: {str(e)}"
                    )
                    print("\n==============================\n")

            if last_exception is not None:

                log_event(
                    session_id=session_id,
                    agent_name="ScreeningAgent",
                    event_type="parse_batch_error",
                    data={
                        "batch_index": i // BATCH_SIZE,
                        "attempts_made": max_attempts,
                        "error": str(last_exception),
                        "raw_response": last_response
                    }
                )

                # all retries exhausted - one failed parse batch
                # shouldn't sink the whole run - those candidates
                # just won't get flags/scored against structured
                # facts, skip and continue
                continue

        log_event(
            session_id=session_id,
            agent_name="ScreeningAgent",
            event_type="parsed_profiles",
            data={
                "profile_count": len(all_profiles),
                # Full roles/dates per candidate - this is what
                # lets you compare what Stage 1 actually extracted
                # between two runs if a flag (e.g. date overlap)
                # unexpectedly appears or disappears.
                "profiles": [
                    p.model_dump() for _, p in all_profiles
                ]
            }
        )

        return all_profiles

    # -----------------------------------------------
    # STAGE 2: deterministic integrity checks. Pure
    # Python, NO LLM call - this is what makes these
    # flags defensible/explainable in the demo.
    # -----------------------------------------------

    def detect_flags(self, profiles, job_description):

        jd_location_info = parse_jd_location(job_description)

        flags_by_candidate = {}

        for profile in profiles:

            flags = run_integrity_checks(profile)

            flags += check_location_mismatch(
                profile.location,
                jd_location_info
            )

            if flags:
                flags_by_candidate[profile.candidate_name] = flags

        return flags_by_candidate

    # -----------------------------------------------
    # STAGE 3: score against the JD using the
    # structured profiles + deterministic flags as
    # input. Per-criterion breakdown, never a single
    # opaque number. Done in small BATCHES so the
    # response never gets large enough to be truncated,
    # no matter how many resumes are uploaded.
    # -----------------------------------------------

    def score_batch(
        self,
        session_id,
        job_description,
        profiles_batch,
        deterministic_flags,
        criteria_weights
    ):

        profiles_json = json.dumps(
            [p.model_dump() for p in profiles_batch],
            indent=2
        )

        batch_flags = {
            p.candidate_name: deterministic_flags[p.candidate_name]
            for p in profiles_batch
            if p.candidate_name in deterministic_flags
        }

        flags_json = json.dumps(batch_flags, indent=2)

        criteria_json = json.dumps(criteria_weights, indent=2)

        prompt = f"""
        Job Description:
        {job_description}

        Use EXACTLY these 4 criteria and point caps for every
        candidate in this batch (derived deterministically from
        the job description above - do not change them):
        {criteria_json}

        Structured Candidate Profiles in this batch (already
        parsed - facts, trust these, do not re-parse from scratch):
        {profiles_json}

        Integrity flags already detected by deterministic code for
        these candidates, keyed by candidate_name (copy these into
        each candidate's flags list exactly as given, then add your
        own if you find contradictions or unverifiable skills):
        {flags_json}
        """

        max_attempts = 3
        last_exception = None
        last_response = None

        for attempt in range(1, max_attempts + 1):

            response = call_ai(
                prompt,
                system_prompt=SCREENING_PROMPT,
                max_tokens=SCORING_MAX_TOKENS_PER_BATCH,
                stage="score",
                session_id=session_id
            )

            last_response = response

            try:

                parsed_response = extract_json(response)

                validated_response = CandidateScoringResponse(
                    **parsed_response
                )

                return validated_response.candidates

            except Exception as e:

                last_exception = e

                print(
                    f"\n===== SCORE BATCH ATTEMPT "
                    f"{attempt}/{max_attempts} FAILED =====\n"
                )
                print(str(e))
                print("\n==================================\n")

        raise RuntimeError(
            f"{str(last_exception)} | "
            f"RAW RESPONSE: {last_response[:500]}"
        )

    # -----------------------------------------------
    # Deterministic classification: shortlist/reject
    # is decided here, in code, not by the LLM. This
    # also scales correctly to any number of resumes.
    # -----------------------------------------------

    def classify_candidates(self, candidates, top_n, score_threshold_100):

        def _criterion_score(candidate, criterion_name):
            for crit in candidate.criteria:
                if crit.criterion == criterion_name:
                    return crit.score
            return 0

        def _sort_key(candidate):
            # Primary: overall score. Tie-breakers (deterministic,
            # not arbitrary list order): higher Skills sub-score
            # wins, then higher Experience sub-score, then name
            # alphabetically as a final, fully deterministic
            # fallback so ranking never depends on input order.
            return (
                -candidate.score,
                -_criterion_score(candidate, "Skills"),
                -_criterion_score(candidate, "Experience"),
                candidate.candidate_name
            )

        # A Reject (e.g. a missing must-have) is never shortlisted,
        # whatever its score.
        qualified = [
            c for c in candidates
            if c.score >= score_threshold_100 and c.decision != "Reject"
        ]

        qualified.sort(key=_sort_key)

        if top_n == "All qualified":
            shortlisted = qualified
        else:
            shortlisted = qualified[:int(top_n)]

        shortlisted_names = {
            c.candidate_name for c in shortlisted
        }

        not_shortlisted = [
            c for c in candidates
            if c.candidate_name not in shortlisted_names
        ]

        not_shortlisted.sort(key=_sort_key)

        return shortlisted, not_shortlisted

    # -----------------------------------------------
    # MAIN ENTRY POINT
    # -----------------------------------------------

    def screen_candidates(
        self,
        session_id,
        job_description,
        candidate_text,
        top_n,
        score_threshold,
        cache=None
    ):

        # cache: a dict the caller keeps between runs (the UI
        # keeps one per screening session). Resumes parsed in an
        # earlier run, and their scores against the same job
        # description, are reused from it, so adding resumes only
        # sends the new ones to Claude. None screens everything.
        if cache is None:
            cache = {}

        # Results from a different model are never reused - after the
        # org's model changes, everything is screened again.
        models = list(current_models())
        if cache.get("models") != models:
            cache.clear()
            cache["models"] = models

        profile_cache = cache.setdefault("profiles", {})
        score_cache = cache.setdefault("scores", {})
        jd_key = _fingerprint(job_description)

        # One entry per distinct resume, in upload order - the
        # same file uploaded twice is only screened once. Each is
        # masked (name/email/phone) before it can reach the LLM;
        # `contacts` restores the real details in the output.
        resumes = {}
        contacts = {}
        injection_flags = {}
        for chunk in _split_into_candidate_chunks(candidate_text):
            key = _resume_key(chunk)
            if key not in resumes:
                token = f"CANDIDATE_{key[:6].upper()}"
                resumes[key], contacts[token] = mask_resume(chunk, token)
                injection_flags[token] = detect_injection(resumes[key])

        names = {token: c["name"] for token, c in contacts.items()}

        # ---------------------------------------
        # Stage 1 - parse resumes not parsed before
        # ---------------------------------------

        new_resumes = [
            (key, chunk) for key, chunk in resumes.items()
            if key not in profile_cache
        ]

        try:

            parsed = self.parse_resumes(
                session_id,
                [chunk for _, chunk in new_resumes]
            )

        except Exception as e:

            log_event(
                session_id=session_id,
                agent_name="ScreeningAgent",
                event_type="parse_error",
                data={"error": str(e)}
            )

            return {
                "error": "Resume parsing failed",
                "details": str(e)
            }

        unmatched_profiles = []

        for index, profile in parsed:
            if index is None:
                unmatched_profiles.append(profile)
            else:
                profile_cache[new_resumes[index][0]] = (
                    profile.model_dump()
                )

        # (resume key, profile) for every resume in this run; key
        # is None for profiles that couldn't be matched to a file,
        # which are screened this run but never cached.
        keyed_profiles = [
            (key, ParsedProfile(**profile_cache[key]))
            for key in resumes if key in profile_cache
        ] + [(None, p) for p in unmatched_profiles]

        profiles = [p for _, p in keyed_profiles]

        # ---------------------------------------
        # Stage 2
        # ---------------------------------------

        deterministic_flags = self.detect_flags(
            profiles,
            job_description
        )

        for profile in profiles:
            if injection_flags.get(profile.candidate_name):
                deterministic_flags.setdefault(
                    profile.candidate_name, []
                ).extend(injection_flags[profile.candidate_name])

        # Derived ONCE per run (per job description), reused
        # identically across every candidate/batch - this is what
        # keeps the ranking apples-to-apples within a single run,
        # even though different JDs can produce different weights.
        weight_result = derive_criteria_weights(job_description)
        criteria_weights = weight_result["weights"]

        log_event(
            session_id=session_id,
            agent_name="ScreeningAgent",
            event_type="request",
            data={
                "job_description": job_description,
                "top_n": top_n,
                "score_threshold": score_threshold,
                "deterministic_flags": deterministic_flags,
                "candidate_count": len(profiles),
                "criteria_weights": criteria_weights,
                "matched_weight_signals": weight_result[
                    "matched_signals"
                ]
            }
        )

        # ---------------------------------------
        # Stage 3 - score, in batches, only the
        # resumes without a score for this JD yet
        # ---------------------------------------

        def score_key(key):
            return f"{jd_key}:{key}"

        to_score = [
            (key, profile) for key, profile in keyed_profiles
            if key is None or score_key(key) not in score_cache
        ]

        reused_count = len(keyed_profiles) - len(to_score)

        unmatched_candidates = []
        last_error = None

        for i in range(0, len(to_score), BATCH_SIZE):

            batch = to_score[i:i + BATCH_SIZE]

            try:

                batch_candidates = self.score_batch(
                    session_id,
                    job_description,
                    [profile for _, profile in batch],
                    deterministic_flags,
                    criteria_weights
                )

                key_by_name = {
                    profile.candidate_name: key
                    for key, profile in batch
                }

                for candidate in batch_candidates:
                    key = key_by_name.get(candidate.candidate_name)
                    if key is None:
                        unmatched_candidates.append(candidate)
                    else:
                        score_cache[score_key(key)] = (
                            candidate.model_dump()
                        )

            except Exception as e:

                last_error = str(e)

                print("\n===== BATCH SCORING ERROR =====\n")
                print(f"Batch {i // BATCH_SIZE + 1}: {last_error}")
                print("\n================================\n")

                log_event(
                    session_id=session_id,
                    agent_name="ScreeningAgent",
                    event_type="batch_error",
                    data={
                        "batch_index": i // BATCH_SIZE,
                        "error": last_error
                    }
                )

                # one failed batch shouldn't sink the whole run -
                # skip it and keep going with the rest (its
                # resumes aren't cached, so the next run retries)
                continue

        all_candidates = [
            CandidateEvaluation(**score_cache[score_key(key)])
            for key, _ in keyed_profiles
            if key is not None and score_key(key) in score_cache
        ] + unmatched_candidates

        if not all_candidates:

            return {
                "error": "Validation failed",
                "details": (
                    "No candidates could be scored - "
                    "all batches failed"
                ),
                "raw_response": (
                    last_error or "No error details captured"
                )
            }

        # ---------------------------------------
        # Classify (deterministic, in code)
        # ---------------------------------------

        for candidate in all_candidates:

            # Rule-based flags must reach the decision even if the
            # LLM didn't copy them (e.g. an injected resume told it
            # not to), so add back any that are missing.
            present = {(f.flag_type, f.description) for f in candidate.flags}
            candidate.flags += [
                Flag(**f)
                for f in deterministic_flags.get(candidate.candidate_name, [])
                if (f["flag_type"], f["description"]) not in present
            ]

            candidate.decision, candidate.decision_reason = (
                decide(candidate)
            )

        score_threshold_100 = score_threshold * 10

        shortlisted, rejected = self.classify_candidates(
            all_candidates,
            top_n,
            score_threshold_100
        )

        output = {
            "shortlisted_candidates": [
                c.model_dump() for c in shortlisted
            ],
            "rejected_candidates": [
                c.model_dump() for c in rejected
            ],
            "parsed_profiles": [
                p.model_dump() for p in profiles
            ],
            "criteria_weights": criteria_weights,
            "matched_weight_signals": weight_result[
                "matched_signals"
            ],
            "run_stats": {
                "resumes": len(resumes),
                "screened_now": len(all_candidates) - reused_count,
                "reused": reused_count,
                "suspicious": sum(
                    1 for token in names if injection_flags.get(token)
                )
            }
        }

        # Logged while still masked, so the Logs page never shows a
        # real name, email or phone number.
        log_event(
            session_id=session_id,
            agent_name="ScreeningAgent",
            event_type="response",
            data=output
        )

        # Real contact details and names, for the recruiter's screen
        for candidate in (
            output["shortlisted_candidates"]
            + output["rejected_candidates"]
        ):
            contact = contacts.get(candidate["candidate_name"], {})
            candidate["email"] = contact.get("email")
            candidate["phone"] = contact.get("phone")

        return unmask(output, names)