"""
Saves screening results as scans and reads them back. Every read is
scoped in the SQL query by the viewer's permissions, so scans the
viewer may not see are never loaded. Only extracted results are
stored - no resume files or full resume text.
"""

from datetime import datetime, time

from sqlalchemy import false

from app.auth.permissions import has_permission
from app.database.db import SessionLocal
from app.database.models import Organization, Scan, ScanResult, User


def _scoped(query, viewer):
    """All scans for the Superadmin, the own org for an HR Manager,
    the viewer's own scans for an HR Executive."""

    if has_permission(viewer, "view_all_scans"):
        return query
    if has_permission(viewer, "view_team_scans"):
        return query.filter(Scan.org_id == viewer.org_id)
    if has_permission(viewer, "view_own_scans"):
        return query.filter(Scan.user_id == viewer.id)
    return query.filter(false())


def save_scan(user, scan_id, jd_text, result):
    """
    Creates a scan (scan_id None) or, after a re-run in the same
    screening session, replaces its results. Returns the scan id.
    """

    candidates = (
        [(c, True) for c in result["shortlisted_candidates"]]
        + [(c, False) for c in result["rejected_candidates"]]
    )
    profiles = {
        p.get("candidate_name"): p
        for p in result.get("parsed_profiles", [])
    }

    with SessionLocal() as db:

        scan = db.get(Scan, scan_id) if scan_id else None

        if scan is None or scan.user_id != user.id:
            scan = Scan(org_id=user.org_id, user_id=user.id)
            db.add(scan)
        else:
            db.query(ScanResult).filter_by(scan_id=scan.id).delete()

        scan.jd_text = jd_text
        scan.resume_count = len(candidates)
        scan.shortlisted_count = sum(1 for _, s in candidates if s)
        scan.weights = {
            "criteria_weights": result.get("criteria_weights"),
            "matched_weight_signals": result.get("matched_weight_signals", []),
        }
        scan.updated_at = datetime.utcnow()
        db.flush()

        for rank, (c, shortlisted) in enumerate(candidates):
            db.add(ScanResult(
                org_id=user.org_id, scan_id=scan.id, rank=rank,
                candidate_name=c.get("candidate_name"),
                email=c.get("email"), phone=c.get("phone"),
                score=c.get("score"), decision=c.get("decision"),
                shortlisted=shortlisted,
                result={
                    "candidate": c,
                    "profile": profiles.get(c.get("candidate_name")),
                },
            ))

        db.commit()
        return scan.id


def list_scans(viewer, org_id=None, user_id=None, date_from=None,
               date_to=None, jd_query=None, limit=200):
    """Scans the viewer may see, newest first. Filters only narrow
    the viewer's scope - they can never widen it."""

    with SessionLocal() as db:

        query = _scoped(
            db.query(Scan, User.name, Organization.name)
            .join(User, Scan.user_id == User.id)
            .join(Organization, Scan.org_id == Organization.id),
            viewer,
        )

        if org_id:
            query = query.filter(Scan.org_id == org_id)
        if user_id:
            query = query.filter(Scan.user_id == user_id)
        if date_from:
            query = query.filter(
                Scan.created_at >= datetime.combine(date_from, time.min))
        if date_to:
            query = query.filter(
                Scan.created_at <= datetime.combine(date_to, time.max))
        if jd_query:
            query = query.filter(Scan.jd_text.ilike(f"%{jd_query}%"))

        return [{
            "id": scan.id,
            "created_at": scan.created_at,
            "run_by": run_by,
            "org": org,
            "jd_text": scan.jd_text,
            "resume_count": scan.resume_count,
            "shortlisted_count": scan.shortlisted_count,
        } for scan, run_by, org in
            query.order_by(Scan.created_at.desc()).limit(limit).all()]


def load_scan(viewer, scan_id):
    """A scan's results in the shape render_full_results() expects,
    or None if it doesn't exist or the viewer may not see it."""

    with SessionLocal() as db:

        scan = _scoped(db.query(Scan), viewer).filter(
            Scan.id == scan_id).first()

        if scan is None:
            return None

        rows = (db.query(ScanResult).filter_by(scan_id=scan.id)
                .order_by(ScanResult.rank).all())

        return {
            "jd_text": scan.jd_text,
            "shortlisted_candidates": [
                r.result["candidate"] for r in rows if r.shortlisted],
            "rejected_candidates": [
                r.result["candidate"] for r in rows if not r.shortlisted],
            "parsed_profiles": [
                r.result["profile"] for r in rows if r.result.get("profile")],
            **(scan.weights or {}),
        }
