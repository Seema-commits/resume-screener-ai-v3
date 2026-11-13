from app.services.llm_client import call_ai
from app.prompts.enhancement_prompts import ENHANCEMENT_PROMPT


class EnhancementAgent:

    def enhance_resume(
        self,
        resume_text,
        job_description
    ):

        prompt = f"""
        Job Description:
        {job_description}

        Resume:
        {resume_text}
        """

        return call_ai(
            prompt,
            system_prompt=ENHANCEMENT_PROMPT
        )