"""
Deterministic location-mismatch flagging.

Same philosophy as date_utils.py: no LLM, fully inspectable. This
is intentionally a FLAG-ONLY signal ("location confirmation
required"), never an auto-reject - a resume alone can't settle
relocation willingness, visa status, or remote-work exceptions, so
a mismatch is something for a human to confirm, not disqualify on.
"""

REMOTE_KEYWORDS = ["remote", "work from home", "wfh"]

ONSITE_HYBRID_KEYWORDS = [
    "on-site", "onsite", "on site", "hybrid", "in-office",
    "in office"
]

# Small, deterministic city -> country lookup. NOT an exhaustive
# gazetteer - just enough to stop common same-country false
# positives (e.g. "Sharjah" vs a JD requiring "Dubai, UAE" -
# different city, same country, ~30 min apart). Cities not in
# this list fall back to plain text matching, same as before -
# this is an honest, narrow improvement, not full geo-intelligence.
CITY_TO_COUNTRY = {
    # UAE
    "dubai": "uae", "abu dhabi": "uae", "sharjah": "uae",
    "ajman": "uae", "fujairah": "uae", "ras al khaimah": "uae",
    "umm al quwain": "uae",
    # India
    "pune": "india", "mumbai": "india", "bangalore": "india",
    "bengaluru": "india", "delhi": "india", "new delhi": "india",
    "hyderabad": "india", "chennai": "india", "kolkata": "india",
    "jalandhar": "india", "mohali": "india", "chandigarh": "india",
    # Other Gulf/MENA cities common in regional resumes
    "riyadh": "saudi arabia", "jeddah": "saudi arabia",
    "doha": "qatar", "kuwait city": "kuwait",
    "manama": "bahrain", "muscat": "oman", "cairo": "egypt",
    # Philippines / common outsourcing hubs
    "manila": "philippines", "karachi": "pakistan",
    "lahore": "pakistan", "singapore": "singapore",
}

# Other spellings of a country, mapped to the names used above
COUNTRY_ALIASES = {
    "united arab emirates": "uae", "u.a.e": "uae", "u.a.e.": "uae",
    "ksa": "saudi arabia", "kingdom of saudi arabia": "saudi arabia",
}


def _country_for(location_text):
    """
    The country for "City", "City, Country" or "Country", if
    recognized. With an unrecognized "City, Country", the part after
    the last comma is taken as the country.
    """
    if not location_text:
        return None

    text = location_text.lower().strip()
    parts = [p.strip() for p in text.split(",")]
    known_countries = set(CITY_TO_COUNTRY.values())

    for part in [text] + parts:
        country = COUNTRY_ALIASES.get(part, part)
        if part in CITY_TO_COUNTRY:
            return CITY_TO_COUNTRY[part]
        if country in known_countries:
            return country

    if len(parts) > 1:
        return COUNTRY_ALIASES.get(parts[-1], parts[-1])

    return None


def parse_jd_location(job_description):
    """
    Best-effort, deterministic extraction of the JD's stated
    location and work mode. Designed for headers like:
    "Meridian Digital - Dubai, UAE - on-site/hybrid"

    Returns:
    {
        "location_text": "Dubai, UAE" or None,
        "work_mode": "remote" | "onsite_or_hybrid" | None
    }

    If the JD doesn't follow a recognizable header pattern, this
    returns location_text=None - the honest fallback is "no
    location requirement detected", not a guess.
    """

    if not job_description:
        return {"location_text": None, "work_mode": None}

    jd_lower = job_description.lower()

    work_mode = None

    if any(kw in jd_lower for kw in REMOTE_KEYWORDS):
        work_mode = "remote"
    elif any(kw in jd_lower for kw in ONSITE_HYBRID_KEYWORDS):
        work_mode = "onsite_or_hybrid"

    location_text = None

    # Look at the first few lines, where job headers typically
    # state "Company - City, Country - work mode". Only treat
    # an em-dash, or a hyphen WITH spaces on both sides, as a
    # real separator - a bare hyphen also appears inside words
    # like "Full-Stack" or "on-site" and must not be split on.
    for line in job_description.strip().split("\n")[:5]:

        if "—" in line:
            separator = "—"
        elif " - " in line:
            separator = " - "
        else:
            continue

        parts = [p.strip() for p in line.split(separator)]

        # Headers often further separate location and work-mode
        # with a middle-dot, e.g. "Dubai, UAE · on-site/hybrid" -
        # split those into separate candidate segments too.
        sub_parts = []
        for part in parts[1:]:
            sub_parts.extend(p.strip() for p in part.split("·"))

        for part in sub_parts:

            part_lower = part.lower()

            is_work_mode_segment = any(
                kw in part_lower
                for kw in REMOTE_KEYWORDS + ONSITE_HYBRID_KEYWORDS
            )

            if not is_work_mode_segment and 2 <= len(part) <= 40:
                location_text = part
                break

        if location_text:
            break

    return {"location_text": location_text, "work_mode": work_mode}


def check_location_mismatch(candidate_location, jd_location_info):
    """
    Returns a list with 0 or 1 flag dicts. Only flags when there's
    real signal in BOTH the JD and the candidate's resume - if
    either is missing/unclear, this stays silent rather than
    guessing (avoids false positives).
    """

    jd_location_text = jd_location_info.get("location_text")
    work_mode = jd_location_info.get("work_mode")

    # Remote roles have no location constraint to check.
    if work_mode == "remote":
        return []

    # Need a real signal on both sides to compare.
    if not jd_location_text or not candidate_location:
        return []

    jd_norm = jd_location_text.lower().strip()
    candidate_norm = candidate_location.lower().strip()

    # First check: do we recognize a country for both sides? If
    # so, trust country-level comparison over exact city matching -
    # this is what stops "Sharjah" being flagged against a
    # "Dubai, UAE" JD just because the city names differ.
    jd_country = _country_for(jd_norm)
    candidate_country = _country_for(candidate_norm)

    def _display_country(country):
        return country.upper() if len(country) <= 4 else country.title()

    if jd_country and candidate_country:

        if jd_country == candidate_country:
            return []  # same country - not a mismatch

        return [{
            "flag_type": "location_mismatch",
            "severity": "low",
            "description": (
                f"Candidate is based in {candidate_location} "
                f"({_display_country(candidate_country)}); role "
                f"requires on-site/hybrid presence in "
                f"{jd_location_text} "
                f"({_display_country(jd_country)}) - location "
                f"confirmation required."
            ),
            "evidence": (
                f"Candidate location: {candidate_location} | "
                f"JD location: {jd_location_text}"
            )
        }]

    # Fallback: neither side's country is recognized in our small
    # lookup - use plain text matching as before (best effort,
    # may occasionally flag same-country cities we don't know).
    if candidate_norm in jd_norm or jd_norm in candidate_norm:
        return []

    if candidate_norm in REMOTE_KEYWORDS:
        # Candidate explicitly states they're remote-based -
        # still worth a confirmation flag for an on-site/hybrid
        # role, but phrase it accordingly.
        description = (
            f"Candidate is remote-based; role is "
            f"on-site/hybrid in {jd_location_text} - "
            f"location confirmation required."
        )
    else:
        description = (
            f"Candidate is based in {candidate_location}; role "
            f"requires on-site/hybrid presence in "
            f"{jd_location_text} - location confirmation required."
        )

    return [{
        "flag_type": "location_mismatch",
        "severity": "low",
        "description": description,
        "evidence": (
            f"Candidate location: {candidate_location} | "
            f"JD location: {jd_location_text}"
        )
    }]