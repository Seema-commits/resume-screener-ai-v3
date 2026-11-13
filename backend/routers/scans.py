"""
Screening and scan history. POST /scans streams progress as
server-sent events (progress → result or error) while the existing
screening pipeline runs in a background thread.
"""

import contextvars
import io
import json
import queue
import threading
import uuid
from collections import OrderedDict
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.orchestrator.workflow_orchestrator import WorkflowOrchestrator
from app.services import scan_service
from app.services.logging_service import log_event
from app.services.parser_service import extract_multiple_resumes, extract_pdf_text
from backend.deps import require

router = APIRouter(prefix="/scans", tags=["scans"])

PAGE_SIZE = 25
MAX_RESUMES = 20
MAX_FILE_BYTES = 5 * 1024 * 1024
RESUME_TYPES = (".pdf", ".docx")
TOP_N_CHOICES = {"3": 3, "5": 5, "10": 10, "All qualified": "All qualified"}

orchestrator = WorkflowOrchestrator()

# "Only screen new resumes" memory per (user, scan), kept in this
# process - fine for one server instance; a restart just re-screens.
_caches = OrderedDict()
_caches_lock = threading.Lock()
MAX_CACHES = 100


def _cache_for(user_id, scan_id):
    with _caches_lock:
        return _caches.get((user_id, scan_id), {}) if scan_id else {}


def _remember_cache(user_id, scan_id, cache):
    with _caches_lock:
        _caches[(user_id, scan_id)] = cache
        _caches.move_to_end((user_id, scan_id))
        while len(_caches) > MAX_CACHES:
            _caches.popitem(last=False)


class _NamedFile(io.BytesIO):
    """The file-like shape parser_service expects (.name, .read)."""

    def __init__(self, data, name):
        super().__init__(data)
        self.name = name


async def _read_upload(upload, allowed_types):
    name = upload.filename or "file"
    if not name.lower().endswith(allowed_types):
        raise HTTPException(400, f"{name}: only {', '.join(allowed_types)} files are accepted.")
    data = await upload.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(413, f"{name} is larger than 5 MB.")
    return _NamedFile(data, name)


def _event(name, data):
    return f"event: {name}\ndata: {json.dumps(data, default=str)}\n\n"


@router.post("")
async def run_scan(
    resumes: List[UploadFile] = File(...),
    jd_text: str = Form(""),
    jd_file: Optional[UploadFile] = File(None),
    top_n: str = Form("5"),
    min_score: int = Form(7),
    scan_id: Optional[int] = Form(None),
    user=Depends(require("run_scan")),
):
    """Screens the resumes against the JD. Send scan_id from an
    earlier result to add resumes to that scan: only new ones go to
    the AI. Streams events: progress {stage, done, total}, then
    result {scan_id, result} or error {detail}."""

    if not 1 <= len(resumes) <= MAX_RESUMES:
        raise HTTPException(400, f"Upload between 1 and {MAX_RESUMES} resumes.")
    if top_n not in TOP_N_CHOICES or not 1 <= min_score <= 10:
        raise HTTPException(400, "top_n must be 3, 5, 10 or 'All qualified'; min_score 1-10.")

    files = [await _read_upload(r, RESUME_TYPES) for r in resumes]
    if jd_file is not None:
        jd_text = extract_pdf_text(await _read_upload(jd_file, (".pdf",)))
    jd_text = (jd_text or "").strip()
    if not jd_text or jd_text.startswith("Could not read PDF"):
        raise HTTPException(400, "Enter a job description or upload a readable JD PDF.")

    candidate_text = extract_multiple_resumes(files)["combined_text"]
    cache = _cache_for(user.id, scan_id)
    events = queue.Queue()

    def work():
        try:
            result = orchestrator.run_workflow(
                workflow="resume_screening",
                session_id=f"scan-{scan_id or uuid.uuid4().hex[:12]}",
                payload={
                    "job_description": jd_text,
                    "candidate_text": candidate_text,
                    "top_n": TOP_N_CHOICES[top_n],
                    "score_threshold": min_score,
                    "cache": cache,
                    "progress": lambda stage, done, total: events.put(
                        ("progress", {"stage": stage, "done": done, "total": total})),
                })
            if "shortlisted_candidates" not in result:
                events.put(("error", {"detail": result.get("details") or result.get("error")}))
                return
            saved_id = scan_service.save_scan(user, scan_id, jd_text, result)
            _remember_cache(user.id, saved_id, cache)
            events.put(("result", {"scan_id": saved_id, "result": result}))
        except Exception as e:
            log_event(session_id="api", agent_name="api", event_type="ui_error",
                      data={"error": str(e)})
            events.put(("error", {"detail": "Something went wrong while screening. "
                                            "It has been logged - try again."}))
        finally:
            events.put(None)

    # Run with this request's context, so logging and the LLM client
    # see the signed-in user
    context = contextvars.copy_context()
    threading.Thread(target=context.run, args=(work,), daemon=True).start()

    def stream():
        while (item := events.get()) is not None:
            yield _event(*item)

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.get("")
def list_scans(
    org_id: Optional[int] = None, user_id: Optional[int] = None,
    date_from: Optional[date] = None, date_to: Optional[date] = None,
    jd: Optional[str] = None, page: int = 1,
    user=Depends(require("view_own_scans")),
):
    """Scans the user may see (own / team / all, by role), newest
    first, 25 per page. Filters only narrow that scope."""

    filters = {"org_id": org_id, "user_id": user_id, "date_from": date_from,
               "date_to": date_to or date_from, "jd_query": (jd or "").strip() or None}
    page = max(page, 1)
    return {
        "total": scan_service.count_scans(user, **filters),
        "page": page, "page_size": PAGE_SIZE,
        "items": scan_service.list_scans(
            user, offset=(page - 1) * PAGE_SIZE, limit=PAGE_SIZE, **filters),
    }


@router.get("/{scan_id}")
def get_scan(scan_id: int, user=Depends(require("view_own_scans"))):
    scan = scan_service.load_scan(user, scan_id)
    if scan is None:
        raise HTTPException(404, "Scan not found.")
    return scan
