"""Deterministic mock job catalogue for the Indian + remote software market.

Everything here is generated from a stable seed so the same source always returns the
same postings (ids, salaries, skills) — only ``posted_at`` moves, because it is
expressed relative to a ``now`` passed in by the caller.

The catalogue deliberately contains **cross-platform duplicates**: the postings in
:data:`SHARED_POSTINGS` are published by LinkedIn, Naukri, Indeed *and* the company
careers site with different ids, different URLs and slightly reworded descriptions, so
``jobs.service.ingest_discovered`` has something real to merge.

No network access, no credentials, no scraping — this module exists so the whole
product can be demoed without touching a third-party site.
"""
from __future__ import annotations

import hashlib
import logging
import random
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import settings
from app.models.enums import (
    AutomationState,
    EmploymentType,
    JobSourceType,
    PauseReason,
    WorkMode,
)
from app.modules.adapters.base import (
    AdapterInfo,
    ApplyContext,
    ApplyStepResult,
    AuthResult,
    DiscoveredJob,
    JobSourceAdapter,
    SearchQuery,
)

logger = logging.getLogger(__name__)

MOCK_TERMS_NOTE = (
    "Mock data — no request is made to the real platform. A production implementation must use the "
    "platform's official/partner API (or the user's own authenticated session with their explicit "
    "consent), respect its Terms of Service and robots.txt, stay within published rate limits, and "
    "must never bypass CAPTCHA, OTP or bot detection."
)


# --------------------------------------------------------------------------- stable helpers


def stable_int(value: str) -> int:
    """Process-independent hash (``hash()`` is salted per interpreter run)."""
    return int.from_bytes(hashlib.sha256(value.encode("utf-8")).digest()[:8], "big")


def slugify(value: str) -> str:
    out = []
    for ch in value.lower():
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != "-":
            out.append("-")
    return "".join(out).strip("-")


# --------------------------------------------------------------------------- reference data


@dataclass(frozen=True)
class CompanyProfile:
    name: str
    domain: str
    tags: tuple[str, ...] = ()
    industry: str = "Technology"


COMPANIES: tuple[CompanyProfile, ...] = (
    CompanyProfile("Google", "google.com", ("FAANG", "product"), "Internet"),
    CompanyProfile("Microsoft", "microsoft.com", ("FAANG", "product"), "Software"),
    CompanyProfile("Amazon", "amazon.com", ("FAANG", "product"), "E-commerce"),
    CompanyProfile("Meta", "meta.com", ("FAANG", "product"), "Social"),
    CompanyProfile("Apple", "apple.com", ("FAANG", "product"), "Consumer Hardware"),
    CompanyProfile("Netflix", "netflix.com", ("FAANG", "product"), "Streaming"),
    CompanyProfile("Flipkart", "flipkart.com", ("unicorn", "product"), "E-commerce"),
    CompanyProfile("Swiggy", "swiggy.com", ("unicorn", "product"), "Food Delivery"),
    CompanyProfile("Zomato", "zomato.com", ("unicorn", "product"), "Food Delivery"),
    CompanyProfile("Razorpay", "razorpay.com", ("unicorn", "fintech"), "Fintech"),
    CompanyProfile("CRED", "cred.club", ("unicorn", "fintech"), "Fintech"),
    CompanyProfile("PhonePe", "phonepe.com", ("unicorn", "fintech"), "Fintech"),
    CompanyProfile("Freshworks", "freshworks.com", ("product", "saas"), "SaaS"),
    CompanyProfile("Zoho", "zoho.com", ("product", "saas"), "SaaS"),
    CompanyProfile("Atlassian", "atlassian.com", ("product", "saas"), "SaaS"),
    CompanyProfile("Uber", "uber.com", ("product",), "Mobility"),
    CompanyProfile("Adobe", "adobe.com", ("product",), "Software"),
    CompanyProfile("Infosys", "infosys.com", ("service",), "IT Services"),
    CompanyProfile("TCS", "tcs.com", ("service",), "IT Services"),
    CompanyProfile("Wipro", "wipro.com", ("service",), "IT Services"),
    CompanyProfile("Northwind Labs", "northwindlabs.io", ("startup",), "Developer Tools"),
    CompanyProfile("Acme Cloud", "acmecloud.io", ("startup",), "Cloud Infrastructure"),
    CompanyProfile("Bluefin Analytics", "bluefinanalytics.in", ("startup",), "Data Analytics"),
    CompanyProfile("Lumina Health", "luminahealth.in", ("startup",), "Health Tech"),
    CompanyProfile("Peakform Systems", "peakform.dev", ("startup",), "B2B SaaS"),
)

COMPANIES_BY_NAME: dict[str, CompanyProfile] = {c.name: c for c in COMPANIES}

STARTUP_COMPANIES = tuple(c for c in COMPANIES if "startup" in c.tags)
PRODUCT_COMPANIES = tuple(c for c in COMPANIES if "product" in c.tags or "unicorn" in c.tags)
SERVICE_COMPANIES = tuple(c for c in COMPANIES if "service" in c.tags)

LOCATIONS: tuple[str, ...] = (
    "Bangalore",
    "Bengaluru",
    "Hyderabad",
    "Pune",
    "Delhi NCR",
    "Gurugram",
    "Noida",
    "Chennai",
    "Mumbai",
    "Remote",
)


@dataclass(frozen=True)
class TitleSpec:
    title: str
    required: tuple[str, ...]
    preferred: tuple[str, ...]
    exp_min: float
    exp_max: float
    salary_min: int
    salary_max: int
    team: str
    mission: str


TITLE_SPECS: tuple[TitleSpec, ...] = (
    TitleSpec(
        "Software Engineer",
        ("Python", "SQL", "Git", "Data Structures & Algorithms"),
        ("Docker", "AWS", "System Design"),
        2,
        5,
        1200000,
        2800000,
        "Core Platform",
        "design, build and operate services that thousands of engineers depend on every day",
    ),
    TitleSpec(
        "SDE I",
        ("Java", "Data Structures & Algorithms", "SQL"),
        ("Spring Boot", "AWS", "Unit Testing"),
        0,
        2,
        800000,
        1600000,
        "Platform Engineering",
        "ship well tested features end to end with guidance from senior engineers",
    ),
    TitleSpec(
        "SDE II",
        ("Java", "System Design", "SQL", "Microservices"),
        ("Kubernetes", "Kafka", "AWS"),
        3,
        6,
        2200000,
        4200000,
        "Distributed Systems",
        "own the design and delivery of services handling millions of requests per day",
    ),
    TitleSpec(
        "Full Stack Developer",
        ("React", "Node.js", "TypeScript", "MongoDB"),
        ("AWS", "Docker", "GraphQL"),
        2,
        5,
        1400000,
        2900000,
        "Product Engineering",
        "build customer facing features across the stack, from the API to the last pixel",
    ),
    TitleSpec(
        "Backend Engineer",
        ("Node.js", "PostgreSQL", "REST APIs", "Docker"),
        ("Redis", "Kafka", "AWS"),
        2,
        6,
        1600000,
        3200000,
        "Backend Services",
        "design resilient APIs and data models for a fast growing product",
    ),
    TitleSpec(
        "Frontend Engineer",
        ("React", "TypeScript", "CSS", "Redux"),
        ("Next.js", "Jest", "Tailwind CSS"),
        2,
        5,
        1400000,
        2700000,
        "Web Experience",
        "craft accessible, fast interfaces used by millions of people in India and beyond",
    ),
    TitleSpec(
        "Node.js Developer",
        ("Node.js", "Express.js", "MongoDB", "JavaScript"),
        ("TypeScript", "Redis", "AWS"),
        1,
        4,
        900000,
        2000000,
        "API Platform",
        "build and maintain the Node.js services behind our mobile and web clients",
    ),
    TitleSpec(
        "React Developer",
        ("React", "JavaScript", "Redux", "HTML"),
        ("TypeScript", "Next.js", "Jest"),
        1,
        4,
        900000,
        2100000,
        "Web Engineering",
        "turn design systems into reusable React components with a strong focus on performance",
    ),
    TitleSpec(
        "Python Developer",
        ("Python", "Django", "PostgreSQL", "REST APIs"),
        ("FastAPI", "Celery", "Docker"),
        2,
        5,
        1100000,
        2400000,
        "Applications",
        "build Python services that automate business critical workflows",
    ),
    TitleSpec(
        "Data Engineer",
        ("Python", "SQL", "Spark", "Airflow"),
        ("Kafka", "Snowflake", "AWS"),
        3,
        7,
        1800000,
        3600000,
        "Data Platform",
        "build the batch and streaming pipelines that power analytics and ML across the company",
    ),
    TitleSpec(
        "DevOps Engineer",
        ("Docker", "Kubernetes", "CI/CD", "Linux"),
        ("Terraform", "AWS", "Nginx"),
        3,
        7,
        1700000,
        3500000,
        "Infrastructure",
        "own the delivery pipeline and the reliability of our production environments",
    ),
)

TITLE_SPECS_BY_TITLE: dict[str, TitleSpec] = {t.title: t for t in TITLE_SPECS}

SENIORITY_PREFIXES: tuple[str, ...] = ("", "", "", "Senior ", "Sr. ", "Lead ")


# --------------------------------------------------------------------------- posting spec


@dataclass(frozen=True)
class PostingSpec:
    """A logical job posting, independent of the platform it is published on."""

    company: str
    title: str
    location: str
    work_mode: WorkMode
    employment_type: EmploymentType = EmploymentType.FULL_TIME
    exp_min: float | None = None
    exp_max: float | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    required: tuple[str, ...] = ()
    preferred: tuple[str, ...] = ()

    @property
    def key(self) -> str:
        return f"{self.company}|{self.title}|{self.location}"


#: Postings published on several platforms at once. These are what the dedupe cascade
#: has to merge into a single ``Job`` with several ``JobSource`` rows.
SHARED_POSTINGS: tuple[PostingSpec, ...] = (
    PostingSpec("Google", "Software Engineer", "Bangalore", WorkMode.HYBRID),
    PostingSpec("Microsoft", "SDE II", "Hyderabad", WorkMode.HYBRID),
    PostingSpec("Amazon", "SDE I", "Bangalore", WorkMode.ONSITE),
    PostingSpec("Flipkart", "Backend Engineer", "Bangalore", WorkMode.HYBRID),
    PostingSpec("Razorpay", "Full Stack Developer", "Remote", WorkMode.REMOTE),
    PostingSpec("Swiggy", "Frontend Engineer", "Bangalore", WorkMode.HYBRID),
    PostingSpec("Atlassian", "Python Developer", "Remote", WorkMode.REMOTE),
    PostingSpec("Adobe", "Data Engineer", "Noida", WorkMode.HYBRID),
)

#: The sources that publish every posting in :data:`SHARED_POSTINGS`.
CROSS_POST_SOURCES: tuple[JobSourceType, ...] = (
    JobSourceType.LINKEDIN,
    JobSourceType.NAUKRI,
    JobSourceType.INDEED,
    JobSourceType.COMPANY_CAREERS,
)


# --------------------------------------------------------------------------- source styling


@dataclass(frozen=True)
class SourceStyle:
    prefix: str
    url_template: str
    apply_template: str | None
    display_name: str


SOURCE_STYLES: dict[JobSourceType, SourceStyle] = {
    JobSourceType.LINKEDIN: SourceStyle(
        "LI-", "https://www.linkedin.com/jobs/view/{eid}", "https://www.linkedin.com/jobs/view/{eid}/apply", "LinkedIn"
    ),
    JobSourceType.NAUKRI: SourceStyle(
        "NK-", "https://www.naukri.com/job-listings-{slug}-{eid}", "https://www.naukri.com/job-listings-{slug}-{eid}/apply", "Naukri"
    ),
    JobSourceType.INDEED: SourceStyle(
        "IND-", "https://in.indeed.com/viewjob?jk={eid}", "https://in.indeed.com/viewjob?jk={eid}&apply=1", "Indeed"
    ),
    JobSourceType.HIRIST: SourceStyle("HRT-", "https://www.hirist.tech/j/{slug}-{eid}", "https://www.hirist.tech/j/{slug}-{eid}/apply", "Hirist"),
    JobSourceType.WELLFOUND: SourceStyle("WF-", "https://wellfound.com/jobs/{eid}-{slug}", "https://wellfound.com/jobs/{eid}-{slug}/apply", "Wellfound"),
    JobSourceType.INTERNSHALA: SourceStyle(
        "INTS-", "https://internshala.com/job/detail/{slug}-{eid}", "https://internshala.com/job/detail/{slug}-{eid}/apply", "Internshala"
    ),
    JobSourceType.GLASSDOOR: SourceStyle(
        "GD-", "https://www.glassdoor.co.in/job-listing/{slug}-JV{eid}.htm", "https://www.glassdoor.co.in/job-listing/{slug}-JV{eid}.htm?apply=1", "Glassdoor"
    ),
    JobSourceType.FOUNDIT: SourceStyle("FND-", "https://www.foundit.in/job/{slug}-{eid}", "https://www.foundit.in/job/{slug}-{eid}/apply", "Foundit"),
    JobSourceType.COMPANY_CAREERS: SourceStyle("CC-", "https://careers.{domain}/jobs/{eid}", "https://careers.{domain}/jobs/{eid}/apply", "Company Careers"),
}

#: Source specific description wording so cross-posted duplicates are not byte identical.
_INTRO_VARIANTS: tuple[str, ...] = (
    "About the role",
    "The opportunity",
    "Role overview",
    "About this opening",
)
_CTA_VARIANTS: tuple[str, ...] = (
    "Apply now to join a team that ships every week.",
    "If this sounds like you, we would love to hear from you.",
    "Interested? Send us your profile and we will get back within a week.",
    "Come build with us — we review every application.",
)


# --------------------------------------------------------------------------- generation


def _company_pool(source: JobSourceType) -> tuple[CompanyProfile, ...]:
    if source == JobSourceType.WELLFOUND:
        return STARTUP_COMPANIES + PRODUCT_COMPANIES
    if source == JobSourceType.INTERNSHALA:
        return STARTUP_COMPANIES + SERVICE_COMPANIES + PRODUCT_COMPANIES[:6]
    if source == JobSourceType.HIRIST:
        return PRODUCT_COMPANIES + STARTUP_COMPANIES
    return COMPANIES


def _catalogue_size(source: JobSourceType) -> int:
    """18–25 postings per platform, stable per source."""
    return 18 + stable_int(f"size|{source.value}") % 8


def _employment_type(source: JobSourceType, rng: random.Random) -> EmploymentType:
    if source == JobSourceType.INTERNSHALA:
        return EmploymentType.INTERNSHIP if rng.random() < 0.6 else EmploymentType.FULL_TIME
    roll = rng.random()
    if roll < 0.9:
        return EmploymentType.FULL_TIME
    if roll < 0.96:
        return EmploymentType.CONTRACT
    return EmploymentType.INTERNSHIP


def _work_mode_for(location: str, rng: random.Random) -> WorkMode:
    if location == "Remote":
        return WorkMode.REMOTE
    return WorkMode.HYBRID if rng.random() < 0.55 else WorkMode.ONSITE


def _salary_for(spec: TitleSpec, seniority: str, employment_type: EmploymentType, rng: random.Random) -> tuple[int, int]:
    low, high = spec.salary_min, spec.salary_max
    if seniority.strip() in {"Senior", "Sr.", "Lead"}:
        low = int(low * 1.45)
        high = int(high * 1.35)
    if employment_type == EmploymentType.INTERNSHIP:
        low, high = 300000, 700000
    jitter = rng.choice((-100000, -50000, 0, 50000, 100000, 150000))
    low = max(300000, low + jitter)
    high = max(low + 200000, min(4500000, high + jitter))
    return int(round(low, -4)), int(round(high, -4))


def _experience_for(spec: TitleSpec, seniority: str, employment_type: EmploymentType) -> tuple[float, float]:
    lo, hi = spec.exp_min, spec.exp_max
    if seniority.strip() in {"Senior", "Sr."}:
        lo, hi = lo + 3, hi + 3
    elif seniority.strip() == "Lead":
        lo, hi = lo + 5, hi + 4
    if employment_type == EmploymentType.INTERNSHIP:
        lo, hi = 0.0, 1.0
    return float(lo), float(hi)


def _format_inr(value: int) -> str:
    return f"INR {value / 100000:.1f} LPA".replace(".0 LPA", " LPA")


def build_description(
    *,
    company: str,
    title: str,
    location: str,
    work_mode: WorkMode,
    employment_type: EmploymentType,
    required: list[str],
    preferred: list[str],
    exp_min: float,
    exp_max: float,
    salary_min: int,
    salary_max: int,
    team: str,
    mission: str,
    variant: int,
) -> str:
    """A realistic multi-paragraph posting. ``variant`` only changes the wording."""
    intro = _INTRO_VARIANTS[variant % len(_INTRO_VARIANTS)]
    cta = _CTA_VARIANTS[variant % len(_CTA_VARIANTS)]
    mode = {WorkMode.REMOTE: "fully remote", WorkMode.HYBRID: "hybrid (3 days in office)", WorkMode.ONSITE: "on-site"}[work_mode]
    required_lines = "\n".join(f"- {s}" for s in required)
    preferred_lines = "\n".join(f"- {s}" for s in preferred)
    return (
        f"{intro}\n"
        f"{company} is hiring a {title} for our {team} team in {location}. "
        f"In this role you will {mission}. The position is {mode} and is a "
        f"{employment_type.value.replace('_', ' ').lower()} engagement.\n\n"
        f"What you will do\n"
        f"- Design, build and ship production services with a strong ownership mindset.\n"
        f"- Write clean, well tested code and take part in design and code reviews.\n"
        f"- Partner with product, design and data to turn requirements into working software.\n"
        f"- Monitor what you ship, debug production issues and improve reliability.\n"
        f"- Mentor teammates and raise the engineering bar across the {team} team.\n\n"
        f"Required skills\n{required_lines}\n\n"
        f"Good to have\n{preferred_lines}\n\n"
        f"Experience: {exp_min:.0f}-{exp_max:.0f} years. "
        f"Location: {location} ({mode}). "
        f"Compensation: {_format_inr(salary_min)} - {_format_inr(salary_max)} per annum.\n\n"
        f"{company} is an equal opportunity employer. {cta}"
    )


def _external_id(source: JobSourceType, spec: PostingSpec) -> str:
    style = SOURCE_STYLES[source]
    number = stable_int(f"{source.value}|{spec.key}") % 9_000_000 + 1_000_000
    return f"{style.prefix}{number}"


def _urls(source: JobSourceType, spec: PostingSpec, external_id: str) -> tuple[str, str]:
    style = SOURCE_STYLES[source]
    company = COMPANIES_BY_NAME.get(spec.company)
    domain = company.domain if company else f"{slugify(spec.company)}.com"
    slug = slugify(f"{spec.title}-{spec.company}-{spec.location}")
    url = style.url_template.format(eid=external_id, slug=slug, domain=domain)
    apply_url = (style.apply_template or style.url_template).format(eid=external_id, slug=slug, domain=domain)
    return url, apply_url


def _resolve_spec(spec: PostingSpec, rng: random.Random) -> PostingSpec:
    """Fill in skills / salary / experience from the title taxonomy when absent."""
    base_title = spec.title
    seniority = ""
    for prefix in ("Senior ", "Sr. ", "Lead "):
        if base_title.startswith(prefix):
            seniority, base_title = prefix, base_title[len(prefix) :]
            break
    title_spec = TITLE_SPECS_BY_TITLE.get(base_title, TITLE_SPECS[0])
    employment_type = spec.employment_type
    exp_min, exp_max = (spec.exp_min, spec.exp_max)
    if exp_min is None or exp_max is None:
        exp_min, exp_max = _experience_for(title_spec, seniority, employment_type)
    salary_min, salary_max = (spec.salary_min, spec.salary_max)
    if salary_min is None or salary_max is None:
        salary_min, salary_max = _salary_for(title_spec, seniority, employment_type, rng)
    return PostingSpec(
        company=spec.company,
        title=spec.title,
        location=spec.location,
        work_mode=spec.work_mode,
        employment_type=employment_type,
        exp_min=exp_min,
        exp_max=exp_max,
        salary_min=salary_min,
        salary_max=salary_max,
        required=spec.required or title_spec.required,
        preferred=spec.preferred or title_spec.preferred,
    )


def posting_to_discovered_job(
    spec: PostingSpec,
    source: JobSourceType,
    now: datetime,
    *,
    variant: int | None = None,
) -> DiscoveredJob:
    """Render one :class:`PostingSpec` as it would appear on ``source``."""
    from app.modules.adapters.base import detect_application_type as _detect

    rng = random.Random(stable_int(f"{source.value}|{spec.key}"))
    resolved = _resolve_spec(spec, rng)
    external_id = _external_id(source, spec)
    url, apply_url = _urls(source, spec, external_id)
    company = COMPANIES_BY_NAME.get(spec.company)
    base_title = resolved.title
    title_spec = TITLE_SPECS_BY_TITLE.get(
        base_title.replace("Senior ", "").replace("Sr. ", "").replace("Lead ", ""), TITLE_SPECS[0]
    )
    if variant is None:
        variant = stable_int(source.value) % len(_INTRO_VARIANTS)
    description = build_description(
        company=spec.company,
        title=resolved.title,
        location=resolved.location,
        work_mode=resolved.work_mode,
        employment_type=resolved.employment_type,
        required=list(resolved.required),
        preferred=list(resolved.preferred),
        exp_min=float(resolved.exp_min or 0),
        exp_max=float(resolved.exp_max or 0),
        salary_min=int(resolved.salary_min or 0),
        salary_max=int(resolved.salary_max or 0),
        team=title_spec.team,
        mission=title_spec.mission,
        variant=variant,
    )
    hours_ago = stable_int(f"posted|{source.value}|{spec.key}") % 73
    minutes_ago = stable_int(f"minutes|{source.value}|{spec.key}") % 60
    posted_at = now - timedelta(hours=hours_ago, minutes=minutes_ago)
    application_type = _detect(apply_url, source, url=url)
    return DiscoveredJob(
        source=source,
        external_id=external_id,
        url=url,
        title=resolved.title,
        company_name=spec.company,
        location=resolved.location,
        work_mode=resolved.work_mode,
        employment_type=resolved.employment_type,
        description=description,
        required_skills=list(resolved.required),
        preferred_skills=list(resolved.preferred),
        experience_min=float(resolved.exp_min) if resolved.exp_min is not None else None,
        experience_max=float(resolved.exp_max) if resolved.exp_max is not None else None,
        salary_min=resolved.salary_min,
        salary_max=resolved.salary_max,
        salary_currency="INR",
        posted_at=posted_at,
        apply_url=apply_url,
        application_type=application_type,
        company_domain=company.domain if company else None,
        company_logo_url=f"https://logo.clearbit.com/{company.domain}" if company else None,
        raw={
            "mock": True,
            "platform": SOURCE_STYLES[source].display_name,
            "tags": list(company.tags) if company else [],
            "industry": company.industry if company else None,
            "hours_ago": hours_ago,
        },
    )


def _source_specific_specs(source: JobSourceType, count: int) -> list[PostingSpec]:
    """Deterministic, collision-free postings unique to one platform."""
    rng = random.Random(stable_int(f"catalogue|{source.value}"))
    pool = _company_pool(source)
    taken = {spec.key for spec in SHARED_POSTINGS} if source in CROSS_POST_SOURCES else set()
    specs: list[PostingSpec] = []
    guard = 0
    while len(specs) < count and guard < count * 40:
        guard += 1
        company = rng.choice(pool)
        title_spec = rng.choice(TITLE_SPECS)
        seniority = rng.choice(SENIORITY_PREFIXES)
        title = f"{seniority}{title_spec.title}"
        location = rng.choice(LOCATIONS)
        if location == "Bengaluru" and rng.random() < 0.6:
            location = "Bangalore"
        key = f"{company.name}|{title}|{location}"
        if key in taken:
            continue
        taken.add(key)
        employment_type = _employment_type(source, rng)
        work_mode = _work_mode_for(location, rng)
        specs.append(
            PostingSpec(
                company=company.name,
                title=title,
                location=location,
                work_mode=work_mode,
                employment_type=employment_type,
            )
        )
    return specs


def build_catalogue(source: JobSourceType, now: datetime | None = None) -> list[DiscoveredJob]:
    """Full deterministic catalogue for ``source`` (18–25 postings).

    ``now`` anchors ``posted_at`` (0–72 hours ago); everything else is stable.
    """
    now = now or datetime.now(timezone.utc)
    total = _catalogue_size(source)
    jobs: list[DiscoveredJob] = []
    if source in CROSS_POST_SOURCES:
        for spec in SHARED_POSTINGS:
            jobs.append(posting_to_discovered_job(spec, source, now))
        total = max(total, len(SHARED_POSTINGS) + 10)
    for spec in _source_specific_specs(source, total - len(jobs)):
        jobs.append(posting_to_discovered_job(spec, source, now))
    return jobs


# --------------------------------------------------------------------------- query matching


def _norm(value: str) -> str:
    return " ".join(value.lower().split())


def _title_matches(job: DiscoveredJob, titles: list[str]) -> bool:
    if not titles:
        return True
    haystack = _norm(job.title)
    for wanted in titles:
        needle = _norm(wanted)
        if not needle:
            continue
        if needle in haystack or haystack in needle:
            return True
        wanted_tokens = set(needle.split())
        if wanted_tokens and wanted_tokens.issubset(set(haystack.split())):
            return True
    return False


def _keyword_matches(job: DiscoveredJob, keywords: list[str]) -> bool:
    if not keywords:
        return True
    haystack = _norm(
        " ".join([job.title, job.description, " ".join(job.required_skills), " ".join(job.preferred_skills), job.company_name])
    )
    return any(_norm(k) and _norm(k) in haystack for k in keywords)


def _location_matches(job: DiscoveredJob, locations: list[str]) -> bool:
    if not locations:
        return True
    from app.modules.jobs.normalize import normalize_location

    job_loc = normalize_location(job.location)
    is_remote = job.work_mode == WorkMode.REMOTE or job_loc == "remote"
    for wanted in locations:
        norm = normalize_location(wanted)
        if not norm:
            continue
        if norm == "remote" and is_remote:
            return True
        if job_loc and norm == job_loc:
            return True
    return False


def filter_catalogue(jobs: list[DiscoveredJob], query: SearchQuery, now: datetime | None = None) -> list[DiscoveredJob]:
    """Apply a :class:`SearchQuery` to a catalogue (used by every mock adapter)."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=query.posted_within_hours) if query.posted_within_hours else None
    wanted_modes = {WorkMode(m) if not isinstance(m, WorkMode) else m for m in (query.work_modes or [])}
    out: list[DiscoveredJob] = []
    for job in jobs:
        if query.titles or query.keywords:
            # OR semantics: "Software Engineer" jobs *or* anything mentioning React.
            title_ok = bool(query.titles) and _title_matches(job, query.titles)
            keyword_ok = bool(query.keywords) and _keyword_matches(job, query.keywords)
            if not (title_ok or keyword_ok):
                continue
        if not _location_matches(job, query.locations):
            continue
        if cutoff is not None and job.posted_at is not None and job.posted_at < cutoff:
            continue
        if wanted_modes and job.work_mode is not None and job.work_mode not in wanted_modes:
            continue
        out.append(job)
    limit = max(1, int(query.limit or 50))
    return out[:limit]


# --------------------------------------------------------------------------- the adapter


#: Standard easy-apply fields a platform pre-fills from the user's platform profile.
EASY_APPLY_FIELDS: tuple[tuple[str, str], ...] = (
    ("full_name", "Full name"),
    ("email", "Email address"),
    ("phone", "Mobile number"),
    ("current_company", "Current company"),
    ("current_designation", "Current designation"),
    ("years_of_experience", "Total years of experience"),
    ("current_salary", "Current CTC"),
    ("expected_salary", "Expected CTC"),
    ("notice_period_days", "Notice period"),
    ("resume_file", "Resume"),
)

#: The extra question a small, deterministic subset of postings asks.
CUSTOM_QUESTIONS: tuple[str, ...] = (
    "What is your preferred start date?",
    "Describe a production incident you personally resolved.",
    "Which of our products have you used, and what would you change?",
    "Do you have experience leading a migration to Kubernetes?",
)


def _simulate_delay() -> None:
    """Small human-like pause between simulated actions (skipped under tests)."""
    if settings.ENV == "test":
        return
    time.sleep(max(0.0, settings.BROWSER_ACTION_DELAY_MS / 1000.0))


class BaseMockAdapter(JobSourceAdapter):
    """Shared behaviour for every mock platform adapter."""

    is_mock = True
    supports_auto_apply = True
    requires_account = True
    uses_browser = False
    rate_limit_per_minute = 30
    terms_note = MOCK_TERMS_NOTE

    # -- discovery ---------------------------------------------------------

    def catalogue(self, now: datetime | None = None) -> list[DiscoveredJob]:
        return build_catalogue(self.source, now)

    def search_jobs(self, query: SearchQuery) -> list[DiscoveredJob]:
        now = datetime.now(timezone.utc)
        jobs = self.catalogue(now)
        results = filter_catalogue(jobs, query, now)
        logger.info("%s mock search returned %d/%d jobs", self.display_name, len(results), len(jobs))
        return results

    def get_job_details(self, external_id: str) -> DiscoveredJob | None:
        for job in self.catalogue():
            if job.external_id == external_id:
                return job
        return None

    # -- session -----------------------------------------------------------

    def authenticate(self, session: Any | None = None, credentials: dict[str, Any] | None = None) -> AuthResult:
        """Mock session: credentials are deliberately ignored and never logged."""
        return AuthResult(ok=True, message=f"Mock {self.display_name} session ready", is_mock=True)

    # -- application steps -------------------------------------------------

    def _external_id_for(self, ctx: ApplyContext) -> str:
        job = ctx.job
        for src in getattr(job, "sources", []) or []:
            if getattr(src, "source", None) == self.source:
                return str(getattr(src, "external_id", ""))
        return str(getattr(job, "id", "")) or "unknown"

    def _requires_user(self, external_id: str) -> bool:
        return stable_int(external_id) % 7 == 0

    def start_application(self, ctx: ApplyContext) -> ApplyStepResult:
        _simulate_delay()
        title = getattr(ctx.job, "title", "the role")
        return ApplyStepResult(
            state=AutomationState.SUCCESS,
            message=f"Opened {self.display_name} easy apply for {title}",
            form_snapshot={"url": getattr(ctx.job, "apply_url", None), "simulated": True},
        )

    def fill_application(self, ctx: ApplyContext) -> ApplyStepResult:
        _simulate_delay()
        external_id = self._external_id_for(ctx)
        answers_by_key = {
            str(getattr(a, "question_key", "")): getattr(a, "answer", None) for a in (ctx.answers or [])
        }
        fields: list[dict[str, Any]] = []
        for key, label in EASY_APPLY_FIELDS:
            fields.append(
                {
                    "key": key,
                    "label": label,
                    "mapped_to": key,
                    "value": answers_by_key.get(key),
                    "status": "filled",
                    "required": key in {"full_name", "email", "phone", "resume_file"},
                }
            )
        if self._requires_user(external_id):
            question = CUSTOM_QUESTIONS[stable_int(external_id) % len(CUSTOM_QUESTIONS)]
            question_key = f"custom:{slugify(question)[:60]}"
            fields.append(
                {
                    "key": question_key,
                    "label": question,
                    "mapped_to": None,
                    "value": answers_by_key.get(question_key),
                    "status": "filled" if answers_by_key.get(question_key) else "needs_user_input",
                    "required": True,
                }
            )
            if not answers_by_key.get(question_key):
                return ApplyStepResult(
                    state=AutomationState.REQUIRES_USER,
                    message=f"{self.display_name} asks a question we cannot answer from your profile",
                    pause_reason=PauseReason.UNKNOWN_QUESTION,
                    form_snapshot={"url": getattr(ctx.job, "apply_url", None), "fields": fields, "simulated": True},
                )
        return ApplyStepResult(
            state=AutomationState.SUCCESS,
            message=f"Filled {len(fields)} fields on the {self.display_name} easy apply form",
            form_snapshot={"url": getattr(ctx.job, "apply_url", None), "fields": fields, "simulated": True},
        )

    def submit_application(self, ctx: ApplyContext) -> ApplyStepResult:
        _simulate_delay()
        external_id = self._external_id_for(ctx)
        prefix = SOURCE_STYLES[self.source].prefix
        reference = f"{prefix}{stable_int('submit|' + external_id) % 900000 + 100000}"
        company = getattr(getattr(ctx.job, "company", None), "name", None) or "the company"
        return ApplyStepResult(
            state=AutomationState.SUCCESS,
            message=f"Submitted via {self.display_name} easy apply",
            external_application_id=reference,
            confirmation_message=f"Your application was sent to {company}. Reference {reference}.",
        )

    def get_application_status(self, external_application_id: str) -> None:
        """Mock platforms expose no status API — responses arrive by email."""
        return None

    def info(self) -> AdapterInfo:
        return AdapterInfo(
            source=self.source,
            display_name=self.display_name,
            is_mock=self.is_mock,
            supports_auto_apply=self.supports_auto_apply,
            requires_account=self.requires_account,
            terms_note=self.terms_note,
            rate_limit_per_minute=self.rate_limit_per_minute,
            uses_browser=self.uses_browser,
        )
