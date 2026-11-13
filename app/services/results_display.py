"""
Shared rendering for resume-screening results - used by both the
main screening page and the Dashboard page, so they always show
the identical table/breakdown format instead of two copies of the
same logic drifting apart over time.

Note: approve/reject UI was intentionally dropped from this shared
renderer during this refactor (it had been hidden behind a feature
flag for a while and wasn't part of the graded assignment scope) -
flag it if you want that functionality reintroduced.
"""

import csv
import io
import json
import re

import pandas as pd
import streamlit as st


def _slugify(name):
    """
    Turns a candidate name into a URL-fragment-safe id, e.g.
    "Karthik Nair" -> "candidate-karthik-nair". Used so a link in
    the results table can jump straight to that candidate's
    detail expander further down the page.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"candidate-{slug}"


def _html_escape(text):
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


DECISION_ICONS = {"Advance": "🟢", "Hold": "🟡", "Reject": "🔴"}


def _decision_badge(candidate):
    decision = candidate.get("decision") or "—"
    return f"{DECISION_ICONS.get(decision, '')} {decision}".strip()


def _contact_line(candidate, sep=" · "):
    return sep.join(
        _html_escape(v) for v in
        (candidate.get("email"), candidate.get("phone")) if v
    )


def _flag_summary(candidate, max_shown=2):
    """
    Compact, visible flag summary for the table - full detail
    (severity, evidence) lives in the per-candidate expander.
    """
    flags = candidate.get("flags", [])

    if not flags:
        return "None"

    labels = [
        f.get("description") or f.get("flag_type", "flag")
        for f in flags
    ]

    shown = "; ".join(f"⚠ {label}" for label in labels[:max_shown])

    remaining = len(labels) - max_shown

    if remaining > 0:
        shown += f" (+{remaining} more)"

    return shown


def _render_table(candidates, label):
    """
    Custom HTML table instead of st.dataframe - wraps long
    Recommendation/Flags text instead of truncating/scrolling.

    IMPORTANT: built as a single line with no leading whitespace
    before being passed to st.markdown - Markdown treats 4+
    leading spaces as a code block, which previously caused the
    raw tags to render as literal text instead of an actual table.
    """

    if not candidates:
        return

    st.write(f"**{label}**")

    row_parts = []

    for c in candidates:

        raw_name = c.get("candidate_name", "Unknown")
        name = _html_escape(raw_name)
        anchor_id = _slugify(raw_name)
        name_link = f'<a href="#{anchor_id}">{name}</a>'
        contact = _contact_line(c, sep="<br>")
        if contact:
            name_link += f"<br><small>{contact}</small>"
        score = _html_escape(f"{c.get('score', 'N/A')}/100")
        decision = (
            f"<b>{_html_escape(_decision_badge(c))}</b><br>"
            f"<small>{_html_escape(c.get('decision_reason') or '')}</small>"
        )
        summary = _html_escape(
            c.get("summary") or c.get("recommendation", "")
        )
        flags = _html_escape(_flag_summary(c))

        row_parts.append(
            "<tr>"
            f'<td class="col-name">{name_link}</td>'
            f'<td class="col-score">{score}</td>'
            f'<td class="col-decision">{decision}</td>'
            f'<td class="col-text">{summary}</td>'
            f'<td class="col-text">{flags}</td>'
            "</tr>"
        )

    rows_html = "".join(row_parts)

    style = (
        "<style>"
        ".screening-table{width:100%;"
        "border-collapse:collapse;table-layout:fixed;"
        "font-size:0.9rem;}"
        ".screening-table th{text-align:left;padding:8px;"
        "border-bottom:2px solid #444;}"
        ".screening-table td{padding:10px 8px;"
        "border-bottom:1px solid #444;vertical-align:top;"
        "white-space:normal;word-wrap:break-word;"
        "overflow-wrap:break-word;line-height:1.4;}"
        ".screening-table .col-name{width:19%;}"
        ".screening-table .col-score{width:9%;}"
        ".screening-table .col-decision{width:20%;}"
        ".screening-table .col-text{width:26%;}"
        "</style>"
    )

    table_html = (
        style
        + '<table class="screening-table"><thead><tr>'
        + '<th class="col-name">Candidate</th>'
        + '<th class="col-score">Score</th>'
        + '<th class="col-decision">Decision</th>'
        + '<th class="col-text">Summary</th>'
        + '<th class="col-text">Flags</th>'
        + "</tr></thead><tbody>"
        + rows_html
        + "</tbody></table>"
    )

    st.markdown(table_html, unsafe_allow_html=True)


def build_csv(all_results):

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Candidate", "Email", "Phone", "Status", "Score",
        "Decision", "Decision Reason",
        "Summary", "Recommendation", "Flags", "Matched Skills",
        "Missing Skills", "Phone-Screen Questions"
    ])

    for c in all_results:

        writer.writerow([
            c.get("candidate_name", ""),
            c.get("email") or "",
            c.get("phone") or "",
            c.get("status", ""),
            c.get("score", ""),
            c.get("decision") or "",
            c.get("decision_reason") or "",
            c.get("summary", ""),
            c.get("recommendation", ""),
            "; ".join(
                f.get("description", "") for f in c.get("flags", [])
            ),
            ", ".join(c.get("matched_skills", [])),
            ", ".join(c.get("missing_skills", [])),
            " | ".join(c.get("phone_screen_questions", [])),
        ])

    return output.getvalue()


SEVERITY_ICONS = {"high": "🔴", "medium": "🟠", "low": "🟡"}


def _bullets(items, empty="None"):
    st.markdown(
        "\n".join(f"- {i}" for i in items) if items else f"_{empty}_"
    )


def _table(rows):
    """Static table that wraps long text (unlike st.dataframe)."""
    st.table(pd.DataFrame(rows).style.hide(axis="index"))


def _render_candidate_details(candidate, profile):
    """One candidate's details: a summary strip, then tabs."""

    score_col, decision_col, contact_col = st.columns([1, 2, 2])
    score_col.metric("Score", f"{candidate.get('score', 'N/A')}/100")
    with decision_col:
        st.markdown(f"**{_decision_badge(candidate)}**")
        st.caption(candidate.get("decision_reason") or "")
    with contact_col:
        st.markdown("**Contact**")
        st.caption(_contact_line(candidate) or "Not found on resume")

    if candidate.get("summary"):
        st.info(candidate["summary"])

    flags = candidate.get("flags", [])
    overview, scores, phone, flags_tab, profile_tab = st.tabs([
        "📋 Overview", "📊 Scores", "📞 Phone screen",
        f"⚠️ Flags ({len(flags)})", "👤 Profile"
    ])

    with overview:
        strengths_col, gaps_col = st.columns(2)
        with strengths_col:
            st.markdown("##### :green[✅ Strengths]")
            _bullets(candidate.get("strengths", []), "None listed")
        with gaps_col:
            st.markdown("##### :orange[🔸 Gaps]")
            _bullets(
                list(candidate.get("missing_skills", []))
                + list(candidate.get("weaknesses", []))
            )

    with scores:
        criteria = candidate.get("criteria", [])
        if criteria:
            _table([{
                "Criterion": c.get("criterion", ""),
                "Points": f"{c.get('score', 0):g} / {c.get('max_score', 0):g}",
                "Reason": c.get("reason", ""),
            } for c in criteria])
        else:
            st.caption("No score breakdown returned.")

    with phone:
        st.markdown("##### :blue[📞 Ask on the phone screen]")
        questions = candidate.get("phone_screen_questions", [])
        st.markdown(
            "\n".join(f"{n}. {q}" for n, q in enumerate(questions, 1))
            if questions else "_None generated_"
        )

    with flags_tab:
        if flags:
            _table([{
                "Severity": (
                    f"{SEVERITY_ICONS.get(f.get('severity'), '⚪')} "
                    f"{(f.get('severity') or '').title()}"
                ),
                "Issue": f.get("description", ""),
                "Evidence": f.get("evidence") or "",
            } for f in flags])
        else:
            st.success("No flags")

    with profile_tab:
        if not profile:
            st.caption("Not available")
            return

        education = "; ".join(
            f"{e.get('degree') or 'Degree'} — "
            f"{e.get('institution') or 'Institution'} "
            f"({e.get('end_year') or 'N/A'})"
            for e in profile.get("education", [])
        )
        st.markdown(
            f"**📍 Location:** {profile.get('location') or 'Not stated'}  \n"
            f"**🎓 Education:** {education or 'None found'}"
        )

        roles = profile.get("roles", [])
        if roles:
            _table([{
                "Role": r.get("title") or "",
                "Company": r.get("company") or "",
                "From": r.get("start_date") or "?",
                "To": r.get("end_date") or "?",
            } for r in roles])

        skills = profile.get("skills", [])
        st.markdown(f"**🛠 Skills:** {', '.join(skills) or 'None found'}")


def render_full_results(result_to_render, show_downloads=False):
    """
    Renders the complete screening-results view: counts,
    (optionally) download buttons, the scoring-weights box, the
    Shortlisted/Rejected tables, and per-candidate detail
    expanders. Used identically by the main page and Scan History.
    """

    if not result_to_render or "shortlisted_candidates" not in result_to_render:
        st.info("No screening results yet - run a screening first.")
        return

    shortlisted = result_to_render.get("shortlisted_candidates", [])
    rejected = result_to_render.get("rejected_candidates", [])
    parsed_profiles = result_to_render.get("parsed_profiles", [])

    parsed_profile_lookup = {
        p.get("candidate_name", ""): p for p in parsed_profiles
    }

    if not (shortlisted or rejected):
        st.info("No screening results yet - run a screening first.")
        return

    st.subheader("📊 Screening Results")

    # --- Counts ---

    count_col1, count_col2, count_col3 = st.columns(3)

    with count_col1:
        st.metric("Total Screened", len(shortlisted) + len(rejected))
    with count_col2:
        st.metric("✅ Shortlisted", len(shortlisted))
    with count_col3:
        st.metric("❌ Not Shortlisted", len(rejected))

    # --- Downloads (only where explicitly requested) ---

    if show_downloads:

        all_results_for_export = (
            [{"status": "Shortlisted", **c} for c in shortlisted]
            + [{"status": "Not Shortlisted", **c} for c in rejected]
        )

        dl_col1, dl_col2, _dl_spacer = st.columns([1, 1.6, 3])

        with dl_col1:
            st.download_button(
                "⬇️ Download CSV",
                data=build_csv(all_results_for_export),
                file_name="screening_results.csv",
                mime="text/csv"
            )

        with dl_col2:
            st.download_button(
                "⬇️ Download Full JSON (incl. parsed profiles)",
                data=json.dumps(result_to_render, indent=2),
                file_name="screening_results_full.json",
                mime="application/json"
            )

    # --- Scoring weights box ---

    criteria_weights = result_to_render.get("criteria_weights")
    matched_signals = result_to_render.get("matched_weight_signals", [])

    if criteria_weights:

        weight_line = " · ".join(
            f"{cat} {pts}" for cat, pts in criteria_weights.items()
        )

        with st.expander(f"⚖️ Scoring weights for this JD: {weight_line}"):

            if matched_signals:

                st.caption(
                    "Detected in the job description (deterministic "
                    "keyword rules, computed once and applied "
                    "identically to every candidate below):"
                )

                for sig in matched_signals:
                    st.write(
                        f"- **{sig['category']}** → {sig['target']} pts "
                        f"(matched: \"{sig['phrase']}\" — {sig['reason']})"
                    )

            else:
                st.write(
                    "No specific education/experience/domain signals "
                    "detected in the JD - using base weights."
                )

    # --- Results tables ---

    _render_table(shortlisted, "✅ Shortlisted")
    _render_table(rejected, "❌ Not Shortlisted")

    # --- Per-candidate detail (one expander each) ---

    st.subheader("🔎 Candidate Analysis Details")

    all_candidates = shortlisted + rejected

    for candidate in all_candidates:

        candidate_name = candidate.get("candidate_name", "Unknown")
        flag_count = len(candidate.get("flags", []))

        # Anchor target for the clickable name link in the table
        # above - must use the same slug logic as _render_table.
        anchor_id = _slugify(candidate_name)
        st.markdown(
            f'<div id="{anchor_id}"></div>',
            unsafe_allow_html=True
        )

        expander_label = (
            f"📄 {candidate_name} — {_decision_badge(candidate)} · "
            f"{candidate.get('score', 'N/A')}/100"
        )
        if flag_count:
            expander_label += f" · {flag_count} flag(s) ⚠️"

        with st.expander(expander_label):
            _render_candidate_details(
                candidate, parsed_profile_lookup.get(candidate_name)
            )
