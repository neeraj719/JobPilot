"""Shared fixtures for the ``tests/test_ats_*`` files (ats stream).

Three job descriptions and three resumes of matching kinds (backend, frontend, devops), users
and tokens, and a guard that routes the ATS page fetcher to a refusing transport so no test
ever reaches a real website (the board APIs are already refused by ``conftest``).
"""
from __future__ import annotations

import copy

import httpx
import pytest
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.user import User

TEST_PUBLIC_IP = "93.184.215.14"

BACKEND_JD = """Senior Backend Engineer

About Acme
Acme builds payments infrastructure for merchants. We love Ruby and use React on the web.

What you'll do
- Design and build REST APIs in Python and Go for the payments platform
- Run services on Kubernetes and improve latency and observability
- Review code and mentor engineers on the payments team

Requirements
- 5+ years of experience building backend services
- Strong proficiency in Python and PostgreSQL
- Experience with Docker and CI/CD pipelines
- Bachelor's degree in Computer Science or equivalent experience

Nice to have
- Experience with Kafka or RabbitMQ
- Familiarity with Terraform

Benefits
- Health insurance, remote stipend and a learning budget
"""

FRONTEND_JD = """Frontend Engineer (React)

The role
You will build the customer dashboard of our analytics product with React and TypeScript.

What we're looking for
- 3-5 years of experience in frontend development
- Must have React, TypeScript, HTML and CSS
- Experience with Redux and Jest
- Good eye for accessibility and design systems

Bonus points
- Next.js
- Cypress end-to-end tests
"""

DEVOPS_JD = """DevOps Engineer

Responsibilities
- Own our AWS infrastructure with Terraform
- Run Kubernetes clusters and Docker images in production
- Build CI/CD pipelines and on-call tooling on Linux

Requirements
- At least 4 years of experience in DevOps or SRE roles
- Required: AWS, Terraform, Kubernetes, Docker, Linux

Preferred
- Python scripting is a plus
- Experience with Nginx
"""


def backend_resume() -> dict:
    return {
        "name": "Asha Rao",
        "email": "asha@example.com",
        "phone": "+91 90000 00000",
        "summary": "Backend developer.",
        "skills": ["Python", "Django", "PostgreSQL", "Docker", "Git"],
        "experience": [
            {
                "company": "Globex",
                "title": "Backend Engineer",
                "start": "2021-01",
                "end": "Present",
                "description": (
                    "- Worked on REST APIs for the billing service using Python and Django\n"
                    "- Reduced report generation time by 40% by adding PostgreSQL indexes\n"
                    "- Responsible for deployments with Docker and GitHub Actions"
                ),
                "technologies": ["Python", "Django", "PostgreSQL"],
            },
            {
                "company": "Initech",
                "title": "Software Engineer",
                "start": "2019-06",
                "end": "2020-12",
                "description": "- Built internal tools in Python\n- Helped with Kafka consumers for event processing",
                "technologies": [],
            },
        ],
        "education": [{"institution": "IIT Delhi", "degree": "B.Tech", "field": "Computer Science", "start": "2015", "end": "2019"}],
        "projects": [
            {"name": "Portfolio site", "description": "Personal site in plain HTML and CSS.", "technologies": ["HTML", "CSS"]},
            {"name": "Ledger API", "description": "A double-entry ledger service in Python with PostgreSQL.", "technologies": ["Python", "PostgreSQL"]},
        ],
        "certifications": [],
        "total_experience_years": 4.5,
        "links": {"linkedin": None, "github": "https://github.com/asha", "portfolio": None},
    }


def frontend_resume() -> dict:
    return {
        "name": "Ravi Kumar",
        "email": "ravi@example.com",
        "phone": "+91 91111 11111",
        "summary": "Frontend engineer with 4 years of experience building React and TypeScript dashboards for analytics products.",
        "skills": ["React", "TypeScript", "HTML", "CSS", "Redux", "Jest"],
        "experience": [
            {
                "company": "Umbrella",
                "title": "Frontend Engineer",
                "start": "2020-03",
                "end": "Present",
                "description": (
                    "- Built a React and TypeScript analytics dashboard used by 3,000 customers\n"
                    "- Cut bundle size by 35% with code splitting and Redux store cleanup\n"
                    "- Raised Jest coverage from 40% to 85% across the design system"
                ),
                "technologies": ["React", "TypeScript", "Redux", "Jest"],
            }
        ],
        "education": [{"institution": "NIT Trichy", "degree": "B.E.", "field": "Electronics", "start": "2016", "end": "2020"}],
        "projects": [],
        "certifications": [],
        "total_experience_years": 4.0,
        "links": {"linkedin": "https://linkedin.com/in/ravi", "github": None, "portfolio": None},
    }


def devops_resume() -> dict:
    return {
        "name": "Meera Iyer",
        "email": "meera@example.com",
        "phone": "+91 92222 22222",
        "summary": "DevOps engineer with 6 years of experience running AWS, Terraform and Kubernetes platforms.",
        "skills": ["AWS", "Terraform", "Kubernetes", "Docker", "Linux", "CI/CD", "Python"],
        "experience": [
            {
                "company": "Hooli",
                "title": "DevOps Engineer",
                "start": "2018-01",
                "end": "Present",
                "description": (
                    "- Migrated 40 services to Kubernetes on AWS with Terraform modules\n"
                    "- Reduced deploy time from 30 to 8 minutes with Docker layer caching in CI/CD\n"
                    "- Automated Linux patching with Python, cutting incidents by half"
                ),
                "technologies": ["AWS", "Terraform", "Kubernetes", "Docker"],
            }
        ],
        "education": [{"institution": "BITS Pilani", "degree": "B.E.", "field": "Computer Science", "start": "2013", "end": "2017"}],
        "projects": [],
        "certifications": [],
        "total_experience_years": 6.0,
        "links": {"linkedin": "https://linkedin.com/in/meera", "github": None, "portfolio": None},
    }


PAIRS = {"backend": (BACKEND_JD, backend_resume), "frontend": (FRONTEND_JD, frontend_resume), "devops": (DEVOPS_JD, devops_resume)}


def make_user(db: Session, email: str) -> User:
    user = User(email=email, hashed_password=hash_password("StrongPass123!"), full_name="ATS Tester", is_active=True)
    db.add(user)
    db.flush()
    return user


def headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role.value)}"}


def make_resume(db: Session, user: User, parsed: dict | None = None, *, name: str = "Backend resume"):
    from app.models.enums import ResumeChangeSource, ResumeKind
    from app.modules.ai.schemas import ParsedResume
    from app.modules.resumes import service as resume_service

    data = ParsedResume.model_validate(copy.deepcopy(parsed or backend_resume()))
    resume = resume_service.create_resume_from_parsed(
        db, user.id, data, name=name, kind=ResumeKind.CREATED, change_source=ResumeChangeSource.USER
    )
    db.flush()
    return resume


@pytest.fixture
def no_page_network():
    """The ATS page fetcher refuses every request and every host resolves to a public address."""
    from app.modules.ats import fetch

    def _refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"network access to {request.url.host} is disabled in tests", request=request)

    fetch.set_transport(httpx.MockTransport(_refuse))
    fetch.set_resolver(lambda host: [TEST_PUBLIC_IP])
    yield fetch
    fetch.set_transport(None)
    fetch.set_resolver(None)
