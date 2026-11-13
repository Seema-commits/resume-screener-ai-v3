from app.services.llm_client import call_ai
from app.prompts.jd_prompts import JD_REFINEMENT_PROMPT


class JDAgent:

    def refine_job_description(
        self,
        raw_jd,
        platform=None,
        length=None
    ):

        additional_instructions = ""

        if platform:
            additional_instructions += f"\nTarget Platform: {platform}"

        if length:
            additional_instructions += f"\nPreferred Length: {length}"


        prompt = f"""
        Raw Job Description:

        {raw_jd}

        {additional_instructions}
        """

        response = call_ai(
            prompt,
            system_prompt=JD_REFINEMENT_PROMPT
        )

        return response
