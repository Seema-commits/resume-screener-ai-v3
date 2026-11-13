from app.services.llm_client import call_ai
from app.prompts.scheduler_prompts import SCHEDULER_PROMPT


class SchedulerAgent:

    def schedule_interview(
        self,
        request_text,
        candidate_text
    ):

        prompt = f"""
        Request:
        {request_text}

        Candidate Info:
        {candidate_text}
        """

        return call_ai(
            prompt,
            system_prompt=SCHEDULER_PROMPT
        )