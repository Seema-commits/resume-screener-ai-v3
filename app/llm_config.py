"""
Which LLMs the app can use. The only file that names providers or
models - everything else goes through services/llm_client.py.

Models use LiteLLM's "provider/model" names. Any LiteLLM model can
also be entered as a custom model on the Settings page (e.g.
"groq/llama-3.3-70b-versatile"); its provider is the part before "/".
"""

from app.config import get_secret

# Built-in choices shown on the Settings page
MODELS = {
    "anthropic/claude-haiku-5-5": "Claude Haiku 5.5",
    "anthropic/claude-sonnet-5-5": "Claude Sonnet 5.5",
    "gemini/gemini-2.5-flash": "Gemini 2.5 Flash",
    "openai/gpt-5-mini": "GPT-5 mini",
}

# Provider -> the secret holding the TalentLens Admin org's own key
# (other orgs' keys are entered on their Users page, stored encrypted)
PROVIDER_KEY_SECRETS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "groq": "GROQ_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}

# Providers with free tiers that may use data for training
FREE_TIER_PROVIDERS = {"gemini", "groq"}
FREE_TIER_WARNING = (
    "Free tier may use data for training — use only with test resumes."
)

# Same thinking level the app has always used ("low": cheapest and
# fastest for structured extraction). Claude takes it as output_config,
# which LiteLLM passes through unchanged; most others as reasoning_effort.
PROVIDER_PARAMS = {
    "anthropic": {"output_config": {"effort": "low"}},
    "gemini": {"reasoning_effort": "low"},
    "openai": {"reasoning_effort": "low"},
}

DEFAULT_MODEL = get_secret("LLM_DEFAULT_MODEL") or "anthropic/claude-haiku-5-5"
DEFAULT_FALLBACK_MODEL = (
    get_secret("LLM_FALLBACK_MODEL") or "anthropic/claude-sonnet-5-5"
)


def provider_of(model):
    return (model or "").split("/", 1)[0].lower()


def label_of(model):
    return MODELS.get(model, model)
