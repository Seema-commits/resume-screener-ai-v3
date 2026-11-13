from app.services.llm_client import call_ai
from app.prompts.interview_preparation_prompts import (
    INTERVIEW_PREPARATION_PROMPT
)
from app.utils.json_parser import extract_json
from app.models.interview_preparation_models import (
    InterviewPreparationResponse
)
from app.services.logging_service import log_event


class InterviewPreparationAgent:

    def prepare_candidate(
        self,
        session_id,
        job_description,
        candidate_text
    ):

        prompt = f"""
        Job Description:
        {job_description}

        Candidate Resume:
        {candidate_text}

        Generate interview preparation guidance.
        """

        log_event(
            session_id=session_id,
            agent_name="InterviewPreparationAgent",
            event_type="request",
            data={
                "job_description": job_description
            }
        )

        response = call_ai(
            prompt,
            system_prompt=INTERVIEW_PREPARATION_PROMPT
        )

        print("\n===== INTERVIEW PREP RESPONSE =====\n")
        print(response)
        print("\n===================================\n")

        try:

            parsed_response = extract_json(response)

            validated_response = (
                InterviewPreparationResponse(
                    **parsed_response
                )
            )

            log_event(
                session_id=session_id,
                agent_name="ScreeningAgent",
                event_type="response",
                data=validated_response.model_dump()
            )

            return validated_response.model_dump()

        except Exception as e:

            log_event(
                session_id=session_id,
                agent_name="ScreeningAgent",
                event_type="error",
                data={
                    "error": str(e),
                    "raw_response": response
                }
            )

            return {
                "error": "Interview prep JSON parsing failed",
                "details": str(e),
                "raw_response": response
            }