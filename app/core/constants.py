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

TECH_STACKS = {
    "backend": {
        "language": "Java 21",
        "framework": "Spring Boot 3.2 (Web, JPA)",
        "build_tool": "Maven",
        "database": "PostgreSQL",
        "other": ["Lombok"],
        "scripts": {
            "test": "mvn clean test -f <path/to/pom.xml>",
            "build": "mvn clean package -f <path/to/pom.xml>",
            "run": "mvn spring-boot:run",
        },
    },
    "frontend": {
        "language": "JavaScript (ES6+) / TypeScript",
        "framework": "React (Functional Components, Hooks)",
        "build_tool": "Vite",
        "structure": "HTML5 (Semantic)",
        "other": ["Bootstrap 5 CSS"],
        "scripts": {
            "test": "npm test",
            "build": "npm run build",
            "run": "npm run dev",
        },
    },
}
