"""
Research Agent for Nova.
Performs multi-source research on a given topic using the LLM router.
"""

from __future__ import annotations


def research(topic: str, depth: str = "standard") -> str:
    """Research a topic and return a structured summary.

    Args:
        topic: Subject to research.
        depth: "quick" | "standard" | "deep" — controls prompt verbosity.

    Returns:
        A string with the research results or an error message.
    """
    depth_instructions = {
        "quick":    "Provide a concise 3-5 sentence summary.",
        "standard": "Provide a structured summary with key points, context, and current state.",
        "deep":     "Provide a comprehensive analysis: background, key findings, open questions, and references.",
    }
    instruction = depth_instructions.get(depth, depth_instructions["standard"])

    prompt = (
        f"Investiga el siguiente tema y {instruction}\n\n"
        f"Tema: {topic}"
    )

    try:
        from nova.core.nova_router import NovaRouter
        router = NovaRouter()
        result = router.route([{"role": "user", "content": prompt}], max_tokens=1500)
        response = result.get("response", "Sin respuesta.")
        provider = result.get("provider", "?")
        return f"{response}\n\n[via {provider}]"
    except Exception as e:
        return (
            f"[research_agent] No se pudo completar la investigación sobre '{topic}': {e}\n"
            "Asegurate de que el router LLM esté disponible (Ollama/Groq/OpenRouter)."
        )
