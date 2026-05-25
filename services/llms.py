from crewai import LLM

_main_llm = None
_lite_llm = None


def main_llm() -> LLM:
    """Lazy-init Groq Llama 3.3 70B for all reviewer agents."""
    global _main_llm
    if _main_llm is None:
        _main_llm = LLM(model="groq/llama-3.3-70b-versatile")
    return _main_llm


def lite_llm() -> LLM:
    """Smaller model for lightweight aggregation work (e.g. the consolidator agent).

    Why: Groq's 8B model has its own TPM bucket separate from the 70B model. Using
    it for the consolidator means it doesn't compete for tokens with the 5 parallel
    reviewers, which avoids rate-limit failures on free tier (12K TPM per model).
    Consolidation is structured merge work — 8B is plenty smart for it.
    """
    global _lite_llm
    if _lite_llm is None:
        _lite_llm = LLM(model="groq/llama-3.1-8b-instant")
    return _lite_llm
