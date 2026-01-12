"""Defines constants for the application."""

# Task States
# Diese Werte entsprechen dem, was wir lesen und (vor der Formatierung) schreiben wollen.
TASK_STATE_OPEN = "Open"
TASK_STATE_IN_REVIEW = "In Review"
TASK_STATE_IN_PROGRESS = "In Progress"
TASK_STATE_DONE = "Done"

LLM_PROVIDER_API_ENV = {
    "mistral": "MISTRAL_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
    "gemini": "GOOGLE_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "ollama": "OLLAMA_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}
