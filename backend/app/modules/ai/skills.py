"""Shared skill taxonomy: canonical names, aliases and a text extractor.

Used by resume parsing (mock provider), the matching engine and the field mapper so
"ReactJS", "React.js" and "react" are all the same skill.
"""
from __future__ import annotations

import re
from functools import lru_cache

# canonical -> aliases (lowercase). Keep canonical names human-readable.
SKILL_ALIASES: dict[str, list[str]] = {
    # languages
    "JavaScript": ["javascript", "js", "es6", "ecmascript"],
    "TypeScript": ["typescript", "ts"],
    "Python": ["python", "python3", "py"],
    "Java": ["java", "java 8", "java 11", "java 17", "core java"],
    "Go": ["go", "golang"],
    "C++": ["c++", "cpp"],
    "C#": ["c#", "csharp", ".net", "dotnet", "asp.net"],
    "Ruby": ["ruby", "ruby on rails", "rails"],
    "PHP": ["php", "laravel"],
    "Kotlin": ["kotlin"],
    "Swift": ["swift", "swiftui"],
    "Rust": ["rust"],
    "Scala": ["scala"],
    "SQL": ["sql", "plsql", "pl/sql", "t-sql"],
    "HTML": ["html", "html5"],
    "CSS": ["css", "css3", "scss", "sass", "less"],
    # frontend
    "React": ["react", "reactjs", "react.js", "react js"],
    "Next.js": ["next.js", "nextjs", "next js"],
    "Angular": ["angular", "angularjs", "angular.js"],
    "Vue.js": ["vue", "vuejs", "vue.js", "nuxt"],
    "Redux": ["redux", "redux toolkit", "rtk"],
    "Tailwind CSS": ["tailwind", "tailwindcss", "tailwind css"],
    "React Native": ["react native", "react-native"],
    "Flutter": ["flutter", "dart"],
    # backend
    "Node.js": ["node", "nodejs", "node.js", "node js"],
    "Express.js": ["express", "expressjs", "express.js"],
    "NestJS": ["nestjs", "nest.js", "nest"],
    "Django": ["django", "drf", "django rest framework"],
    "FastAPI": ["fastapi", "fast api"],
    "Flask": ["flask"],
    "Spring Boot": ["spring", "spring boot", "springboot"],
    "GraphQL": ["graphql", "apollo"],
    "REST APIs": ["rest", "rest api", "rest apis", "restful", "restful apis"],
    "gRPC": ["grpc"],
    "Microservices": ["microservices", "micro services", "microservice"],
    # data
    "PostgreSQL": ["postgres", "postgresql", "psql"],
    "MySQL": ["mysql", "mariadb"],
    "MongoDB": ["mongo", "mongodb"],
    "Redis": ["redis"],
    "Elasticsearch": ["elasticsearch", "elastic search", "opensearch"],
    "Kafka": ["kafka", "apache kafka"],
    "RabbitMQ": ["rabbitmq", "rabbit mq"],
    "DynamoDB": ["dynamodb", "dynamo db"],
    "Cassandra": ["cassandra"],
    "Snowflake": ["snowflake"],
    "Spark": ["spark", "pyspark", "apache spark"],
    "Airflow": ["airflow"],
    # cloud / devops
    "AWS": ["aws", "amazon web services", "ec2", "s3", "lambda", "aws lambda"],
    "Azure": ["azure", "microsoft azure"],
    "GCP": ["gcp", "google cloud", "google cloud platform"],
    "Docker": ["docker", "containers", "docker compose"],
    "Kubernetes": ["kubernetes", "k8s", "eks", "gke", "aks"],
    "Terraform": ["terraform", "iac"],
    "CI/CD": ["ci/cd", "cicd", "ci cd", "github actions", "gitlab ci", "jenkins", "circleci"],
    "Linux": ["linux", "unix", "bash", "shell scripting"],
    "Git": ["git", "github", "gitlab", "bitbucket"],
    "Nginx": ["nginx"],
    # testing
    "Jest": ["jest"],
    "Cypress": ["cypress"],
    "Playwright": ["playwright"],
    "Selenium": ["selenium"],
    "Pytest": ["pytest"],
    "Unit Testing": ["unit testing", "tdd", "test driven development"],
    # ml / ai
    "Machine Learning": ["machine learning", "ml"],
    "Deep Learning": ["deep learning", "neural networks"],
    "TensorFlow": ["tensorflow"],
    "PyTorch": ["pytorch", "torch"],
    "LLMs": ["llm", "llms", "large language models", "openai api", "langchain", "rag"],
    "Data Structures & Algorithms": ["dsa", "data structures", "algorithms", "data structures and algorithms"],
    # practices / misc
    "System Design": ["system design", "distributed systems", "scalability"],
    "Agile": ["agile", "scrum", "kanban"],
    "OOP": ["oop", "object oriented", "object-oriented"],
    "Design Patterns": ["design patterns"],
    "WebSockets": ["websockets", "websocket", "socket.io"],
    "OAuth": ["oauth", "oauth2", "jwt", "authentication"],
    "Prisma": ["prisma"],
    "SQLAlchemy": ["sqlalchemy", "alembic"],
    "Celery": ["celery"],
}

SKILL_CATEGORIES: dict[str, str] = {
    **{k: "language" for k in ["JavaScript", "TypeScript", "Python", "Java", "Go", "C++", "C#", "Ruby", "PHP", "Kotlin", "Swift", "Rust", "Scala", "SQL", "HTML", "CSS"]},
    **{k: "frontend" for k in ["React", "Next.js", "Angular", "Vue.js", "Redux", "Tailwind CSS", "React Native", "Flutter"]},
    **{k: "backend" for k in ["Node.js", "Express.js", "NestJS", "Django", "FastAPI", "Flask", "Spring Boot", "GraphQL", "REST APIs", "gRPC", "Microservices", "Prisma", "SQLAlchemy", "Celery", "WebSockets", "OAuth"]},
    **{k: "database" for k in ["PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch", "Kafka", "RabbitMQ", "DynamoDB", "Cassandra", "Snowflake", "Spark", "Airflow"]},
    **{k: "cloud" for k in ["AWS", "Azure", "GCP", "Docker", "Kubernetes", "Terraform", "CI/CD", "Linux", "Git", "Nginx"]},
    **{k: "testing" for k in ["Jest", "Cypress", "Playwright", "Selenium", "Pytest", "Unit Testing"]},
    **{k: "ai" for k in ["Machine Learning", "Deep Learning", "TensorFlow", "PyTorch", "LLMs"]},
    **{k: "practice" for k in ["Data Structures & Algorithms", "System Design", "Agile", "OOP", "Design Patterns"]},
}


@lru_cache(maxsize=1)
def _alias_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for canonical, aliases in SKILL_ALIASES.items():
        index[canonical.lower()] = canonical
        for a in aliases:
            index[a.lower()] = canonical
    return index


def normalize_skill(raw: str) -> str:
    """Map any alias to its canonical skill name. Unknown skills are title-cased and trimmed."""
    key = re.sub(r"\s+", " ", raw.strip().lower())
    key = key.strip(" .,;:-")
    if not key:
        return ""
    idx = _alias_index()
    if key in idx:
        return idx[key]
    # try without trailing "js"/".js" noise: "reactjs" handled above, generic fallback
    stripped = re.sub(r"[\.\s]?js$", "", key)
    if stripped in idx:
        return idx[stripped]
    return raw.strip()[:60] if raw.strip().isupper() else raw.strip().title()[:60]


def normalize_skills(raw_list: list[str] | None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in raw_list or []:
        if not isinstance(raw, str):
            continue
        canonical = normalize_skill(raw)
        if canonical and canonical.lower() not in seen:
            seen.add(canonical.lower())
            out.append(canonical)
    return out


@lru_cache(maxsize=1)
def _alias_patterns() -> list[tuple[re.Pattern[str], str]]:
    pats: list[tuple[re.Pattern[str], str]] = []
    for alias, canonical in _alias_index().items():
        # word boundaries that tolerate symbols like c++ / c# / .net
        escaped = re.escape(alias)
        pats.append((re.compile(rf"(?<![a-z0-9+#]){escaped}(?![a-z0-9+#])", re.IGNORECASE), canonical))
    # longest aliases first so "react native" wins over "react"
    pats.sort(key=lambda p: -len(p[0].pattern))
    return pats


def extract_skills(text: str) -> list[str]:
    """Find canonical skills mentioned anywhere in free text (job description or resume)."""
    if not text:
        return []
    found: dict[str, int] = {}
    lowered = text.lower()
    for pattern, canonical in _alias_patterns():
        m = pattern.search(lowered)
        if m and canonical not in found:
            found[canonical] = m.start()
    return [k for k, _ in sorted(found.items(), key=lambda kv: kv[1])]


def skill_category(canonical: str) -> str:
    return SKILL_CATEGORIES.get(canonical, "other")


def skills_overlap(required: list[str], candidate: list[str]) -> tuple[list[str], list[str]]:
    """Return (matched, missing) using canonical normalisation."""
    cand = {s.lower() for s in normalize_skills(candidate)}
    matched, missing = [], []
    for s in normalize_skills(required):
        (matched if s.lower() in cand else missing).append(s)
    return matched, missing
