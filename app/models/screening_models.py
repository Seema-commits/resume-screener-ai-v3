from pydantic import BaseModel
from typing import List, Optional


# ---------------------------------------------------
# LAYER 1: PARSED ENTITIES (facts only, no judgment)
# ---------------------------------------------------

class RoleEntry(BaseModel):

    title: Optional[str] = None
    company: Optional[str] = None
    start_date: Optional[str] = None  # normalized "YYYY-MM"
    end_date: Optional[str] = None    # "YYYY-MM" or "present"


class EducationEntry(BaseModel):

    degree: Optional[str] = None
    institution: Optional[str] = None
    end_year: Optional[str] = None


class ParsedProfile(BaseModel):

    candidate_name: str
    location: Optional[str] = None
    education: List[EducationEntry] = []
    roles: List[RoleEntry] = []
    skills: List[str] = []


class ParsedProfilesResponse(BaseModel):

    profiles: List[ParsedProfile]


# ---------------------------------------------------
# LAYER 2: FLAGS (inconsistencies / embellishments)
# ---------------------------------------------------

class Flag(BaseModel):

    flag_type: str            # "date_overlap" | "contradictory_claim" | "unverifiable_skill"
    severity: str = "medium"  # "low" | "medium" | "high"
    description: str
    evidence: Optional[str] = None


# ---------------------------------------------------
# LAYER 3: SCORING RECORD (never a single opaque number)
# ---------------------------------------------------

class ScoredCriterion(BaseModel):

    criterion: str
    max_score: float
    score: float
    reason: str        # mandatory - every score carries a reason


class CandidateEvaluation(BaseModel):

    candidate_name: str
    score: float
    criteria: List[ScoredCriterion] = []
    matched_skills: List[str] = []
    missing_skills: List[str] = []
    strengths: List[str] = []
    weaknesses: List[str] = []
    flags: List[Flag] = []
    recommendation: str
    summary: str = ""                     # one line for the recruiter
    missing_must_haves: List[str] = []    # JD-required skills not held
    phone_screen_questions: List[str] = []

    # Set by code, never by the LLM
    decision: Optional[str] = None        # "Advance" | "Hold" | "Reject"
    decision_reason: Optional[str] = None
    email: Optional[str] = None           # from the unmasked resume,
    phone: Optional[str] = None           # for the recruiter only


class CandidateScoringResponse(BaseModel):

    candidates: List[CandidateEvaluation]


class ScreeningResponse(BaseModel):

    shortlisted_candidates: List[CandidateEvaluation]
    rejected_candidates: List[CandidateEvaluation]