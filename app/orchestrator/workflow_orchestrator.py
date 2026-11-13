from app.agents.screening_agent import ScreeningAgent
from app.agents.enhancement_agent import EnhancementAgent
from app.agents.scheduler_agent import SchedulerAgent
from app.agents.jd_agent import JDAgent
from app.agents.interview_preparation_agent import (
    InterviewPreparationAgent
)

from app.services.logging_service import log_event


class WorkflowOrchestrator:

    def __init__(self):

        self.screening_agent = ScreeningAgent()

        self.enhancement_agent = EnhancementAgent()

        self.scheduler_agent = SchedulerAgent()

        self.jd_agent = JDAgent()

        self.interview_preparation_agent = (
            InterviewPreparationAgent()
        )

    # ---------------------------------------------------
    # MAIN ROUTER
    # ---------------------------------------------------

    def run_workflow(
        self,
        workflow,
        session_id,
        payload
    ):

        # -----------------------------------------------
        # JD REFINEMENT
        # -----------------------------------------------

        if workflow == "jd_refinement":

            result = (
                self.jd_agent.refine_job_description(
                    raw_jd=payload["raw_jd"],
                    platform=payload["platform"],
                    length=payload["length"]
                )
            )

        # -----------------------------------------------
        # RESUME SCREENING
        # -----------------------------------------------

        elif workflow == "resume_screening":

            result = (
                self.screening_agent.screen_candidates(
                    session_id=session_id,
                    job_description=payload[
                        "job_description"
                    ],
                    candidate_text=payload[
                        "candidate_text"
                    ],
                    top_n=payload["top_n"],
                    score_threshold=payload[
                        "score_threshold"
                    ],
                    cache=payload.get("cache"),
                    progress=payload.get("progress")
                )
            )

        # -----------------------------------------------
        # RESUME ENHANCEMENT
        # -----------------------------------------------

        elif workflow == "resume_enhancement":

            result = (
                self.enhancement_agent.enhance_resume(
                    resume_text=payload[
                        "resume_text"
                    ],
                    job_description=payload[
                        "job_description"
                    ]
                )
            )

        # -----------------------------------------------
        # INTERVIEW SCHEDULER
        # -----------------------------------------------

        elif workflow == "interview_scheduler":

            result = (
                self.scheduler_agent.schedule_interview(
                    request_text=payload[
                        "request_text"
                    ],
                    candidate_text=payload[
                        "candidate_text"
                    ]
                )
            )

        # -----------------------------------------------
        # INTERVIEW PREPARATION
        # -----------------------------------------------

        elif workflow == "interview_preparation":

            result = (
                self.interview_preparation_agent.prepare_candidate(
                    session_id=session_id,
                    job_description=payload[
                        "job_description"
                    ],
                    candidate_text=payload[
                        "candidate_text"
                    ]
                )
            )

        else:

            result = {
                "error": "Invalid workflow"
            }

        # -----------------------------------------------
        # GLOBAL AUDIT LOG
        # -----------------------------------------------

        log_event(
            session_id=session_id,
            agent_name="WorkflowOrchestrator",
            event_type="workflow_execution",
            data={
                "workflow": workflow
            }
        )

        return result