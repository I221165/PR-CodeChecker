from crewai import LLM

_llm = None


def main_llm() -> LLM:
    """Lazy-init Groq Llama 3.3 70B for all reviewer agents."""
    global _llm
    if _llm is None:
        _llm = LLM(model="groq/llama-3.3-70b-versatile")
    return _llm
