"""Job catalogue for the demo ATS.

These are **fictional postings on a local mock careers site** used to demonstrate the
Playwright autofill flow end to end without touching any third-party website. The three
"(Demo Careers)" entries are clearly labelled mirrors on ``*.example`` domains -- they
are not, and must never be presented as, the real Google / Microsoft / Amazon sites.

The roles are tuned to the seeded demo candidate (about 2 years of
React / Node.js / TypeScript / PostgreSQL / AWS experience in India):

* most postings are a good match,
* ``acme-cloud-platform-engineer`` requires Kubernetes + Terraform to demo *missing skills*,
* ``microsoft-demo-careers-senior-software-engineer`` needs 6+ years to demo *UNDER experience*.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import settings

NOTICE_PERIOD_OPTIONS: list[str] = ["Immediate", "15 days", "30 days", "60 days", "90 days"]

START_DATE_QUESTION: dict[str, Any] = {
    "key": "start_date",
    "label": "What is your preferred start date?",
    "type": "text",
    "options": [],
    "required": True,
    "placeholder": "e.g. 15 October 2026",
}

KUBERNETES_QUESTION: dict[str, Any] = {
    "key": "kubernetes_experience",
    "label": "Describe your experience with Kubernetes in production",
    "type": "textarea",
    "options": [],
    "required": True,
    "placeholder": "Clusters you have operated, workloads, incidents you handled...",
}


def _logo(domain: str | None) -> str | None:
    """Real-looking logo URL for the fictional companies; mirrors get no logo."""
    if not domain or domain.endswith(".example"):
        return None
    return f"https://logo.clearbit.com/{domain}"


DEMO_JOBS: list[dict[str, Any]] = [
    {
        "slug": "northwind-labs-full-stack-engineer",
        "title": "Full Stack Engineer",
        "company": "Northwind Labs",
        "company_domain": "northwindlabs.dev",
        "location": "Bangalore, India",
        "work_mode": "HYBRID",
        "employment_type": "FULL_TIME",
        "salary_min": 1200000,
        "salary_max": 1800000,
        "salary_currency": "INR",
        "experience_min": 2.0,
        "experience_max": 4.0,
        "required_skills": ["React", "TypeScript", "Node.js", "PostgreSQL"],
        "preferred_skills": ["AWS", "Docker", "GraphQL", "Jest"],
        "posted_hours_ago": 5,
        "is_mirror": False,
        "description": (
            "Northwind Labs builds workflow tooling for mid-market logistics companies. "
            "Our product team is small, ships daily, and owns features end to end -- from the "
            "Postgres schema through the Node.js API to the React front end.\n\n"
            "What you will do:\n"
            "- Build and own customer-facing features across the React + TypeScript front end and the Node.js API.\n"
            "- Design pragmatic PostgreSQL schemas and keep queries fast as the data grows.\n"
            "- Write the tests that let us deploy several times a day without drama.\n"
            "- Pair with design and support to turn rough edges into fixes within the same week.\n\n"
            "What we are looking for:\n"
            "- 2-4 years building production web applications with JavaScript or TypeScript.\n"
            "- Comfort on both sides of the API boundary; you do not need to be an expert in both.\n"
            "- Working knowledge of relational databases and HTTP fundamentals.\n"
            "- Clear written communication -- we are hybrid and write things down."
        ),
        "custom_questions": [START_DATE_QUESTION],
    },
    {
        "slug": "northwind-labs-frontend-engineer-react",
        "title": "Frontend Engineer (React)",
        "company": "Northwind Labs",
        "company_domain": "northwindlabs.dev",
        "location": "Remote (India)",
        "work_mode": "REMOTE",
        "employment_type": "FULL_TIME",
        "salary_min": 1000000,
        "salary_max": 1600000,
        "salary_currency": "INR",
        "experience_min": 1.5,
        "experience_max": 3.0,
        "required_skills": ["React", "TypeScript", "Redux", "CSS"],
        "preferred_skills": ["Next.js", "Jest", "Tailwind CSS", "Cypress"],
        "posted_hours_ago": 11,
        "is_mirror": False,
        "description": (
            "We are looking for a frontend engineer to take ownership of the Northwind dashboard: "
            "the screen our customers keep open all day.\n\n"
            "What you will do:\n"
            "- Ship accessible, fast React interfaces in TypeScript, with Redux Toolkit for shared state.\n"
            "- Turn dense operational data into views that a dispatcher can read in two seconds.\n"
            "- Grow our component library and keep the design system honest.\n"
            "- Measure real user performance and fix what is slow.\n\n"
            "What we are looking for:\n"
            "- 1.5-3 years of focused React work, ideally with TypeScript.\n"
            "- A feel for CSS and layout that survives contact with real data.\n"
            "- Testing habits: unit tests for logic, a few end-to-end tests for the paths that matter."
        ),
        "custom_questions": [START_DATE_QUESTION],
    },
    {
        "slug": "acme-cloud-backend-engineer-node",
        "title": "Backend Engineer (Node.js)",
        "company": "Acme Cloud",
        "company_domain": "acmecloud.io",
        "location": "Hyderabad, India",
        "work_mode": "HYBRID",
        "employment_type": "FULL_TIME",
        "salary_min": 1400000,
        "salary_max": 2000000,
        "salary_currency": "INR",
        "experience_min": 2.0,
        "experience_max": 5.0,
        "required_skills": ["Node.js", "Express.js", "PostgreSQL", "REST APIs"],
        "preferred_skills": ["Docker", "AWS", "Redis", "Microservices"],
        "posted_hours_ago": 20,
        "is_mirror": False,
        "description": (
            "Acme Cloud runs the billing and metering platform behind several developer tools you have "
            "probably used. Correctness matters here: our numbers end up on invoices.\n\n"
            "What you will do:\n"
            "- Build and operate Node.js services that ingest and aggregate usage events.\n"
            "- Model data carefully in PostgreSQL and defend it with constraints, not hope.\n"
            "- Design REST APIs that other teams can integrate against without asking questions.\n"
            "- Take part in a light on-call rotation for the services you own.\n\n"
            "What we are looking for:\n"
            "- 2-5 years with Node.js and a relational database in production.\n"
            "- Solid understanding of HTTP, idempotency and retries.\n"
            "- Bonus: Docker, AWS, Redis, or experience with event-driven systems."
        ),
        "custom_questions": [START_DATE_QUESTION],
    },
    {
        "slug": "acme-cloud-platform-engineer",
        "title": "Platform Engineer (Kubernetes)",
        "company": "Acme Cloud",
        "company_domain": "acmecloud.io",
        "location": "Bangalore, India",
        "work_mode": "HYBRID",
        "employment_type": "FULL_TIME",
        "salary_min": 1800000,
        "salary_max": 2600000,
        "salary_currency": "INR",
        "experience_min": 3.0,
        "experience_max": 6.0,
        "required_skills": ["Kubernetes", "Terraform", "Docker", "AWS", "Linux"],
        "preferred_skills": ["Go", "CI/CD", "Prometheus"],
        "posted_hours_ago": 30,
        "is_mirror": False,
        "description": (
            "Our platform team keeps every Acme Cloud service running on EKS. You will own the paved "
            "road that product engineers deploy onto.\n\n"
            "What you will do:\n"
            "- Operate multi-tenant Kubernetes clusters: upgrades, autoscaling, cost, and blast radius.\n"
            "- Write Terraform for everything; nothing is configured by hand.\n"
            "- Build deployment pipelines that make the safe path the fast path.\n"
            "- Debug the hard ones: networking, DNS, noisy neighbours, expired certificates.\n\n"
            "What we are looking for:\n"
            "- 3+ years running containerised workloads in production, with real Kubernetes experience.\n"
            "- Infrastructure as code discipline (Terraform preferred).\n"
            "- Comfort in Linux internals and at least one systems language."
        ),
        "custom_questions": [KUBERNETES_QUESTION],
    },
    {
        "slug": "bluefin-analytics-software-engineer",
        "title": "Software Engineer - Product",
        "company": "Bluefin Analytics",
        "company_domain": "bluefinanalytics.co",
        "location": "Pune, India",
        "work_mode": "ONSITE",
        "employment_type": "FULL_TIME",
        "salary_min": 1100000,
        "salary_max": 1700000,
        "salary_currency": "INR",
        "experience_min": 2.0,
        "experience_max": 4.0,
        "required_skills": ["Python", "FastAPI", "PostgreSQL", "React"],
        "preferred_skills": ["Airflow", "Docker", "AWS", "Pytest"],
        "posted_hours_ago": 44,
        "is_mirror": False,
        "description": (
            "Bluefin Analytics turns messy retail data into decisions store managers actually trust. "
            "The product team sits with analysts and ships the tools they ask for.\n\n"
            "What you will do:\n"
            "- Build FastAPI services and the React screens on top of them.\n"
            "- Work with analysts to turn one-off notebooks into repeatable product features.\n"
            "- Keep query latency predictable as datasets grow past the comfortable size.\n"
            "- Write tests, run the deploy, watch the dashboards.\n\n"
            "What we are looking for:\n"
            "- 2-4 years with Python in production, plus enough frontend to be dangerous.\n"
            "- SQL you are not afraid of; you can read an EXPLAIN plan.\n"
            "- This role is onsite in Pune, four days a week."
        ),
        "custom_questions": [START_DATE_QUESTION],
    },
    {
        "slug": "google-demo-careers-software-engineer-ii",
        "title": "Software Engineer II, Full Stack",
        "company": "Google (Demo Careers)",
        "company_domain": "careers-demo.google.example",
        "location": "Bangalore, India",
        "work_mode": "HYBRID",
        "employment_type": "FULL_TIME",
        "salary_min": 2400000,
        "salary_max": 3600000,
        "salary_currency": "INR",
        "experience_min": 2.0,
        "experience_max": 5.0,
        "required_skills": ["JavaScript", "TypeScript", "React", "Data Structures & Algorithms"],
        "preferred_skills": ["Go", "System Design", "GCP", "Microservices"],
        "posted_hours_ago": 8,
        "is_mirror": True,
        "description": (
            "DEMO POSTING -- this is a fictional mirror served by the JobPilot demo ATS. It is not a "
            "real Google job posting and no application reaches Google.\n\n"
            "A large-company style posting used to demonstrate priority companies (P1) and "
            "cross-platform duplicate detection in JobPilot.\n\n"
            "What you will do:\n"
            "- Build user-facing features in a large TypeScript/React codebase.\n"
            "- Design and review APIs used by several teams.\n"
            "- Participate in design reviews and raise the quality bar through code review.\n\n"
            "What we are looking for:\n"
            "- 2-5 years of software engineering experience.\n"
            "- Strong fundamentals in data structures, algorithms and system design.\n"
            "- Experience shipping and operating production services."
        ),
        "custom_questions": [START_DATE_QUESTION],
    },
    {
        "slug": "microsoft-demo-careers-senior-software-engineer",
        "title": "Senior Software Engineer, Cloud Platform",
        "company": "Microsoft (Demo Careers)",
        "company_domain": "careers-demo.microsoft.example",
        "location": "Hyderabad, India",
        "work_mode": "HYBRID",
        "employment_type": "FULL_TIME",
        "salary_min": 3500000,
        "salary_max": 5000000,
        "salary_currency": "INR",
        "experience_min": 6.0,
        "experience_max": 10.0,
        "required_skills": ["C#", "Azure", "System Design", "Microservices", "Kubernetes"],
        "preferred_skills": ["Terraform", "Kafka", "Go"],
        "posted_hours_ago": 26,
        "is_mirror": True,
        "description": (
            "DEMO POSTING -- this is a fictional mirror served by the JobPilot demo ATS. It is not a "
            "real Microsoft job posting and no application reaches Microsoft.\n\n"
            "A deliberately senior posting (6+ years) used to demonstrate how JobPilot scores a "
            "candidate as UNDER-experienced instead of quietly applying anyway.\n\n"
            "What you will do:\n"
            "- Lead the design of multi-region services on Azure.\n"
            "- Mentor engineers and own the technical direction of a subsystem.\n"
            "- Drive reliability work: SLOs, capacity planning, incident reviews.\n\n"
            "What we are looking for:\n"
            "- 6+ years of backend engineering, including distributed systems at scale.\n"
            "- Depth in C# or an equivalent statically typed language.\n"
            "- Track record of leading projects across teams."
        ),
        "custom_questions": [START_DATE_QUESTION],
    },
    {
        "slug": "amazon-demo-careers-sde-i",
        "title": "Software Development Engineer I",
        "company": "Amazon (Demo Careers)",
        "company_domain": "careers-demo.amazon.example",
        "location": "Bangalore, India",
        "work_mode": "ONSITE",
        "employment_type": "FULL_TIME",
        "salary_min": 1800000,
        "salary_max": 2600000,
        "salary_currency": "INR",
        "experience_min": 1.0,
        "experience_max": 3.0,
        "required_skills": ["Java", "Data Structures & Algorithms", "AWS", "REST APIs"],
        "preferred_skills": ["Python", "Microservices", "DynamoDB"],
        "posted_hours_ago": 14,
        "is_mirror": True,
        "description": (
            "DEMO POSTING -- this is a fictional mirror served by the JobPilot demo ATS. It is not a "
            "real Amazon job posting and no application reaches Amazon.\n\n"
            "An entry-level posting used to demonstrate duplicate detection across mock job boards.\n\n"
            "What you will do:\n"
            "- Own components of a service used by internal and external customers.\n"
            "- Write design documents, then the code, then the operational runbook.\n"
            "- Improve latency and cost of the systems you own.\n\n"
            "What we are looking for:\n"
            "- 1-3 years of professional software development experience.\n"
            "- Strong coding fundamentals in Java or a similar language.\n"
            "- Familiarity with AWS services and distributed systems basics."
        ),
        "custom_questions": [START_DATE_QUESTION],
    },
]

for _job in DEMO_JOBS:
    _job.setdefault("logo_url", _logo(_job.get("company_domain")))

DEMO_JOBS_BY_SLUG: dict[str, dict[str, Any]] = {job["slug"]: job for job in DEMO_JOBS}


def list_demo_jobs() -> list[dict[str, Any]]:
    """Every demo posting, in catalogue order."""
    return list(DEMO_JOBS)


def get_demo_job(slug: str) -> dict[str, Any] | None:
    """One posting by slug, or ``None``."""
    return DEMO_JOBS_BY_SLUG.get(slug)


def demo_companies() -> list[dict[str, Any]]:
    """Companies with their postings, for the landing page."""
    grouped: dict[str, dict[str, Any]] = {}
    for job in DEMO_JOBS:
        entry = grouped.setdefault(
            job["company"],
            {
                "name": job["company"],
                "domain": job["company_domain"],
                "logo_url": job.get("logo_url"),
                "is_mirror": job.get("is_mirror", False),
                "jobs": [],
            },
        )
        entry["jobs"].append(job)
    return list(grouped.values())


def job_custom_questions(job: dict[str, Any]) -> list[dict[str, Any]]:
    return list(job.get("custom_questions") or [])


def posted_at(job: dict[str, Any]) -> datetime:
    """Absolute posting time derived from the catalogue offset (always fresh)."""
    return datetime.now(timezone.utc) - timedelta(hours=float(job.get("posted_hours_ago") or 0))


def job_url(job: dict[str, Any], base_url: str | None = None) -> str:
    base = (base_url or settings.DEMO_ATS_BASE_URL).rstrip("/")
    return f"{base}/demo-ats/jobs/{job['slug']}"


def job_payload(job: dict[str, Any], base_url: str | None = None) -> dict[str, Any]:
    """Normalised posting for ``GET /demo-ats/jobs.json`` and ``DemoAtsAdapter``.

    ``work_mode`` / ``employment_type`` / ``application_type`` / ``source`` are the
    string values of the matching enums in ``app.models.enums``.
    """
    url = job_url(job, base_url)
    return {
        "external_id": job["slug"],
        "slug": job["slug"],
        "title": job["title"],
        "company": job["company"],
        "company_name": job["company"],
        "company_domain": job["company_domain"],
        "company_logo_url": job.get("logo_url"),
        "logo_url": job.get("logo_url"),  # alias: DemoAtsAdapter reads either name
        "location": job["location"],
        "work_mode": job["work_mode"],
        "employment_type": job["employment_type"],
        "salary_min": job["salary_min"],
        "salary_max": job["salary_max"],
        "salary_currency": job["salary_currency"],
        "experience_min": job["experience_min"],
        "experience_max": job["experience_max"],
        "required_skills": list(job["required_skills"]),
        "preferred_skills": list(job["preferred_skills"]),
        "description": job["description"],
        "posted_at": posted_at(job).isoformat(),
        "posted_hours_ago": job["posted_hours_ago"],
        "url": url,
        "apply_url": f"{url}/apply",
        "application_type": "ATS_FORM",
        "source": "DEMO_ATS",
        "is_mirror": bool(job.get("is_mirror")),
        "custom_questions": [dict(q) for q in job.get("custom_questions") or []],
    }
