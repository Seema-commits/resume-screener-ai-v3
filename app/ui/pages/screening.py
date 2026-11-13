import streamlit as st
import uuid

# Shared results rendering (used by this page and Scan History)
from app.services.results_display import render_full_results

# Agents
from app.orchestrator.workflow_orchestrator import (
    WorkflowOrchestrator
)

# Services
from app.services.parser_service import (
    extract_multiple_resumes,
    extract_pdf_text
)
from app.services.logging_service import log_event
from app.services.scan_service import save_scan
from app.ui.auth_ui import require

# ---------------------------------------------------
# ACCESS (page config, login and the DB are handled by the
# entry point, TalentLens_AI.py)
# ---------------------------------------------------

user = require("run_scan")

# ---------------------------------------------------
# SESSION STATE
# ---------------------------------------------------

if "messages" not in st.session_state:
    st.session_state.messages = []

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "approval_status" not in st.session_state:
    st.session_state.approval_status = {}

if "latest_result" not in st.session_state:
    st.session_state.latest_result = None

if "latest_agent_mode" not in st.session_state:
    st.session_state.latest_agent_mode = None

if "screening_jd" not in st.session_state:
    st.session_state.screening_jd = ""

if "uploader_version" not in st.session_state:
    st.session_state.uploader_version = 0

if "current_scan_id" not in st.session_state:
    # The saved scan this screening session updates on each run
    st.session_state.current_scan_id = None

if "screening_cache" not in st.session_state:
    # Parsed resumes and their scores from earlier runs in this
    # screening session, so re-running after adding resumes only
    # sends the new ones to Claude.
    st.session_state.screening_cache = {}

# ---------------------------------------------------
# INITIALIZE AGENTS
# ---------------------------------------------------

orchestrator = WorkflowOrchestrator()

# ---------------------------------------------------
# HEADER
# ---------------------------------------------------

st.title("🎯 TalentLens AI")


# ---------------------------------------------------
# SIDEBAR
# ---------------------------------------------------

with st.sidebar:

    st.header("⚙️ Settings")

    # -------------------------------------------
    # FEATURE FLAG: other agent modes (JD Refinement,
    # Resume Enhancement, Interview Scheduler,
    # Interview Preparation) are hidden from the
    # dropdown for now - their code is untouched and
    # still works, just not selectable. Flip this to
    # True to bring them back.
    # -------------------------------------------
    SHOW_ALL_AGENT_MODES = False

    ALL_AGENT_MODES = [
        "JD Refinement",
        "Resume Screening",
        "Resume Enhancement",
        "Interview Scheduler",
        "Interview Preparation"
    ]

    agent_mode_options = (
        ALL_AGENT_MODES
        if SHOW_ALL_AGENT_MODES
        else ["Resume Screening"]
    )

    agent_mode = st.selectbox(
        "Choose Agent",
        agent_mode_options
    )

    top_n = st.selectbox(
        "Shortlist Count",
        [3, 5, 10, "All qualified"],
        index=1  # defaults to 5
    )

    score_threshold = st.slider(
        "Minimum Score",
        min_value=1,
        max_value=10,
        value=7
    )

    uploaded_files = st.file_uploader(
        "Upload Resumes",
        type=["pdf", "docx"],
        accept_multiple_files=True,
        key=f"resume_uploader_{st.session_state.uploader_version}"
    )

    st.caption(
        "To add candidates, upload more resumes here and click "
        "'Screen Resumes Now' again - the job description stays, "
        "and only the new resumes are sent to the AI. Everyone "
        "listed above is ranked together."
    )

    if st.session_state.latest_result is not None:

        if st.button("🔄 Start New Screening Session"):

            st.session_state.uploader_version += 1
            st.session_state.latest_result = None
            st.session_state.latest_agent_mode = None
            st.session_state.screening_jd = ""
            st.session_state.screening_cache = {}
            st.session_state.current_scan_id = None
            st.session_state.session_id = str(uuid.uuid4())

            st.rerun()

    if agent_mode == "JD Refinement":
        jd_platform = st.selectbox(
            "Target Platform",
            [
                "LinkedIn",
                "Indeed",
                "Internal Posting",
                "Company Careers Page"
            ]
        )
        jd_length = st.selectbox(
            "JD Length",
            [
                "Short",
                "Medium",
                "Detailed"
            ]
        )


# ---------------------------------------------------
# EXTRACT RESUME TEXT
# ---------------------------------------------------

candidate_text = ""
resume_data = []

if uploaded_files:
    
    parsed_resumes = extract_multiple_resumes(
        uploaded_files
    )

    candidate_text = parsed_resumes[
        "combined_text"
    ]

    resume_data = parsed_resumes[
        "resume_data"
    ]
    
    st.success(f"{len(uploaded_files)} resumes uploaded")

# ---------------------------------------------------
# RESUME SCREENING: JD -> UPLOAD -> SCREEN NOW
# ---------------------------------------------------
# This mode has its own dedicated flow instead of the
# chat box: enter JD, upload resumes (sidebar), then
# click the button below to run screening.
# ---------------------------------------------------

if agent_mode == "Resume Screening":

    st.subheader("📋 Step 1: Enter Job Description")

    jd_pdf = st.file_uploader(
        "Upload JD as PDF",
        type=["pdf"],
        key=f"jd_pdf_uploader_{st.session_state.uploader_version}"
    )

    if jd_pdf is not None:

        extracted_jd_text = extract_pdf_text(jd_pdf)

        if extracted_jd_text and not extracted_jd_text.startswith(
            "Could not read PDF"
        ):
            st.session_state.screening_jd = extracted_jd_text
            st.success("JD extracted from PDF - edit below if needed.")
        else:
            st.error(extracted_jd_text or "Could not read that PDF.")

    st.markdown(
        "<p style='text-align:center;color:gray;margin:4px 0;'>"
        "OR</p>",
        unsafe_allow_html=True
    )

    st.session_state.screening_jd = st.text_area(
        "Paste/type the Job Description here",
        value=st.session_state.screening_jd,
        height=180,
        placeholder="Paste or type the job description here..."
    )

    st.caption(
        "💡 Tip: after pasting, press **Cmd+Enter** (Mac) or "
        "**Ctrl+Enter** (Windows) while still in the box to "
        "continue immediately - no need to click elsewhere."
    )

    jd_entered = bool(st.session_state.screening_jd.strip())

    if jd_entered:

        st.caption(
            "📎 Step 2: Upload resumes using the "
            "**Upload Resumes** field in the sidebar."
        )

    st.subheader("🚀 Step 3: Run Screening")

    run_clicked = st.button(
        "🔍 Screen Resumes Now",
        type="primary"
    )

    if run_clicked:

        if not st.session_state.screening_jd.strip():
            st.error("Please enter a job description first.")

        elif not uploaded_files:
            st.error("Please upload at least one resume.")

        else:

            with st.spinner("Screening candidates..."):

                try:

                    result = orchestrator.run_workflow(
                        workflow="resume_screening",
                        session_id=st.session_state.session_id,
                        payload={
                            "job_description": (
                                st.session_state.screening_jd
                            ),
                            "candidate_text": candidate_text,
                            "top_n": top_n,
                            "score_threshold": score_threshold,
                            "cache": st.session_state.screening_cache
                        }
                    )

                    st.session_state.latest_result = result
                    st.session_state.latest_agent_mode = agent_mode

                except Exception as e:

                    result = None

                    log_event(
                        session_id=st.session_state.session_id,
                        agent_name="streamlit_app",
                        event_type="ui_error",
                        data={"error": str(e)}
                    )

                    st.error(
                        "Something went wrong while screening. "
                        "This has been logged for the admin - try "
                        "again, or with fewer resumes."
                    )

            if result and "shortlisted_candidates" in result:

                try:
                    st.session_state.current_scan_id = save_scan(
                        user,
                        st.session_state.current_scan_id,
                        st.session_state.screening_jd,
                        result
                    )
                except Exception as e:
                    log_event(
                        session_id=st.session_state.session_id,
                        agent_name="streamlit_app",
                        event_type="scan_save_error",
                        data={"error": str(e)}
                    )
                    st.warning(
                        "Results are shown below but couldn't be "
                        "saved to Scan History."
                    )

    st.divider()

# ---------------------------------------------------
# DISPLAY CHAT HISTORY
# ---------------------------------------------------

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# ---------------------------------------------------
# CHAT INPUT
# ---------------------------------------------------

if agent_mode != "Resume Screening":
    prompt = st.chat_input("Enter job description or request...")
else:
    prompt = None

# ---------------------------------------------------
# MAIN EXECUTION
# ---------------------------------------------------

if prompt:

    # ---------------------------------------------
    # Show user message
    # ---------------------------------------------

    with st.chat_message("user"):
        st.markdown(prompt)

    st.session_state.messages.append({
        "role": "user",
        "content": prompt
    })


    # ---------------------------------------------
    # Agent Execution
    # ---------------------------------------------

    with st.chat_message("assistant"):

        with st.spinner("Processing..."):

            try:

                if agent_mode == "JD Refinement":

                    result = orchestrator.run_workflow(
                        workflow="jd_refinement",
                        session_id=st.session_state.session_id,
                        payload={
                            "raw_jd": prompt,
                            "platform": jd_platform,
                            "length": jd_length
                        }
                    )

                elif agent_mode == "Resume Enhancement":

                    result = orchestrator.run_workflow(
                        workflow="resume_enhancement",
                        session_id=st.session_state.session_id,
                        payload={
                            "resume_text": candidate_text,
                            "job_description": prompt
                        }
                    )

                elif agent_mode == "Interview Scheduler":

                    result = orchestrator.run_workflow(
                        workflow="interview_scheduler",
                        session_id=st.session_state.session_id,
                        payload={
                            "request_text": prompt,
                            "candidate_text": candidate_text
                        }
                    )

                elif agent_mode == "Interview Preparation":

                    result = orchestrator.run_workflow(
                        workflow="interview_preparation",
                        session_id=st.session_state.session_id,
                        payload={
                            "job_description": prompt,
                            "candidate_text": candidate_text
                        }
                    )

                else:

                    result = {
                        "error": "Invalid agent selected"
                    }

            except Exception as e:

                log_event(
                    session_id=st.session_state.session_id,
                    agent_name="streamlit_app",
                    event_type="ui_error",
                    data={"error": str(e), "agent_mode": agent_mode}
                )

                result = {
                    "error": "Something went wrong",
                    "details": (
                        "This has been logged - check the Logs "
                        "page for details."
                    )
                }

            st.session_state.latest_result = result
            st.session_state.latest_agent_mode = agent_mode


    # ---------------------------------------------
    # Save assistant response
    # ---------------------------------------------

    st.session_state.messages.append({
        "role": "assistant",
        "content": result
    })

# ---------------------------------------------------
# ALWAYS RENDER RESULT
# ---------------------------------------------------

result_to_render = (
    st.session_state.get(
        "latest_result",
        None
    )
)

if result_to_render is not None:

    if isinstance(result_to_render, dict):

        # -----------------------------------
        # Resume Screening Candidate Workflow
        # -----------------------------------

        if (
            st.session_state.latest_agent_mode == "Resume Screening"
            and "shortlisted_candidates" in result_to_render
        ):

            run_stats = result_to_render.get("run_stats")

            if run_stats and run_stats["reused"]:
                st.caption(
                    f"Screened {run_stats['screened_now']} new "
                    f"resume(s) with AI; reused earlier results "
                    f"for {run_stats['reused']}."
                )

            if run_stats and run_stats.get("suspicious"):
                st.warning(
                    f"🛡 {run_stats['suspicious']} resume(s) contain text "
                    f"that looks like instructions to the AI. They are "
                    f"flagged for manual review - see the ⚠️ Flags tab."
                )

            render_full_results(result_to_render, show_downloads=False)


        # -----------------------------------
        # Interview Preparation
        # -----------------------------------

        elif (
            st.session_state.latest_agent_mode
            == "Interview Preparation"
        ):

            st.title("🎯 Interview Preparation Guide")

            technical_questions = (
                result_to_render.get(
                    "technical_questions",
                    []
                )
            )

            behavioral_questions = (
                result_to_render.get(
                    "behavioral_questions",
                    []
                )
            )

            topics_to_revise = (
                result_to_render.get(
                    "topics_to_revise",
                    []
                )
            )

            tips = result_to_render.get(
                "tips",
                []
            )

            if technical_questions:

                st.subheader(
                    "Technical Questions"
                )

                for question in technical_questions:

                    st.write(f"• {question}")

            if behavioral_questions:

                st.subheader(
                    "Behavioral Questions"
                )

                for question in behavioral_questions:

                    st.write(f"• {question}")

            if topics_to_revise:

                st.subheader(
                    "Topics To Revise"
                )

                for topic in topics_to_revise:

                    st.write(f"• {topic}")

            if tips:

                st.subheader("Interview Tips")

                for tip in tips:

                    st.write(f"• {tip}")

        # -----------------------------------
        # Other Agents
        # -----------------------------------

        else:

            st.json(result_to_render)

    else:

        st.warning(
            f"Response type: "
            f"{type(result_to_render)}"
        )

        st.write(result_to_render)