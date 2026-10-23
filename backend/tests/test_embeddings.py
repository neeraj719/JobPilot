"""Local embeddings (``ai.embeddings``) and how ``load_target_jobs`` uses them.

Ollama is never contacted: the HTTP layer is an ``httpx.MockTransport`` and the
``load_target_jobs`` tests replace ``embed`` with a deterministic fake.
"""
from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models.company import Company
from app.models.enums import EmploymentType, WorkMode
from app.models.job import Job
from app.models.user import User
from app.modules.ai import embeddings
from app.modules.jobs.dedupe import compute_dedupe_hash
from app.modules.resumes import recommendations as rec


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    embeddings.clear_cache()
    monkeypatch.setattr(settings, "EMBEDDINGS_ENABLED", True)
    monkeypatch.setattr(settings, "EMBEDDING_MODEL", "embeddinggemma")
    yield
    embeddings.clear_cache()


def _vector_for(text: str) -> list[float]:
    """A stable fake vector: letter counts of the text."""
    counts = [0.0] * 26
    for ch in text.lower():
        if "a" <= ch <= "z":
            counts[ord(ch) - 97] += 1
    return counts or [1.0]


class _Server:
    def __init__(self, *, status: int = 200, broken: bool = False) -> None:
        self.requests: list[dict] = []
        self.status = status
        self.broken = broken

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        assert request.url.path == "/api/embed"
        if self.status != 200:
            return httpx.Response(self.status, json={"error": "model not found"})
        if self.broken:
            return httpx.Response(200, json={"embeddings": []})
        return httpx.Response(200, json={"model": body["model"], "embeddings": [_vector_for(t) for t in body["input"]]})

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)


# --------------------------------------------------------------------------- embed()


def test_embed_returns_one_vector_per_text_in_order():
    server = _Server()
    vectors = embeddings.embed(["python developer", "frontend engineer"], transport=server.transport)
    assert vectors == [_vector_for("python developer"), _vector_for("frontend engineer")]
    assert server.requests[0]["model"] == "embeddinggemma"
    assert server.requests[0]["keep_alive"] == settings.OLLAMA_KEEP_ALIVE


def test_embed_batches_large_inputs(monkeypatch):
    monkeypatch.setattr(embeddings, "BATCH_SIZE", 3)
    server = _Server()
    texts = [f"job title {chr(97 + i)}" for i in range(7)]
    vectors = embeddings.embed(texts, transport=server.transport)
    assert vectors is not None and len(vectors) == 7
    assert [len(r["input"]) for r in server.requests] == [3, 3, 1]


def test_embed_serves_repeats_from_the_cache():
    server = _Server()
    first = embeddings.embed(["a", "b"], transport=server.transport)
    second = embeddings.embed(["b", "a", "c", "c"], transport=server.transport)
    assert second == [first[1], first[0], _vector_for("c"), _vector_for("c")]
    # Only "c" was new, and it was sent once even though it appeared twice.
    assert [r["input"] for r in server.requests] == [["a", "b"], ["c"]]


def test_cache_is_keyed_by_model(monkeypatch):
    server = _Server()
    embeddings.embed(["same text"], transport=server.transport)
    monkeypatch.setattr(settings, "EMBEDDING_MODEL", "nomic-embed-text")
    embeddings.embed(["same text"], transport=server.transport)
    assert [r["model"] for r in server.requests] == ["embeddinggemma", "nomic-embed-text"]


def test_cache_is_bounded(monkeypatch):
    monkeypatch.setattr(embeddings, "CACHE_MAX_VECTORS", 3)
    server = _Server()
    embeddings.embed(["a", "b", "c", "d"], transport=server.transport)
    assert embeddings.cache_size() == 3


@pytest.mark.parametrize("server", [_Server(status=404), _Server(broken=True)], ids=["http-error", "bad-reply"])
def test_embed_failure_returns_none(server):
    assert embeddings.embed(["python"], transport=server.transport) is None


def test_embed_connection_refused_returns_none():
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    assert embeddings.embed(["python"], transport=httpx.MockTransport(refuse)) is None


def test_embed_disabled_returns_none_without_a_request(monkeypatch):
    monkeypatch.setattr(settings, "EMBEDDINGS_ENABLED", False)
    server = _Server()
    assert embeddings.embed(["python"], transport=server.transport) is None
    assert server.requests == []


def test_cosine():
    assert embeddings.cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert embeddings.cosine([1, 0], [0, 1]) == pytest.approx(0.0)
    assert embeddings.cosine([1, 1], [1, 0]) == pytest.approx(1 / math.sqrt(2))
    assert embeddings.cosine([], [1]) == 0.0
    assert embeddings.cosine([0, 0], [1, 1]) == 0.0


# --------------------------------------------------------------------------- role kinds


def test_different_role_is_proved_only_by_incompatible_kinds():
    assert rec.different_role("Frontend Engineer", ["Backend Engineer"])
    assert rec.different_role("React Developer", ["Python Developer"])
    assert rec.different_role("DevOps Engineer", ["Full Stack Engineer"])
    assert not rec.different_role("Backend Engineer", ["Python Developer"])
    assert not rec.different_role("Senior Backend Engineer", ["Full Stack Engineer"])
    assert not rec.different_role("Software Engineer", ["Python Developer"])  # names no kind
    assert not rec.different_role("Frontend Engineer", ["Software Engineer II"])  # role names no kind


# --------------------------------------------------------------------------- load_target_jobs


#: Fake embedding space: each text is placed by the words it contains.
_AXES = ("python", "backend", "django", "react", "frontend", "devops", "kubernetes", "data", "fullstack", "software")


def _fake_vector(text: str) -> list[float]:
    tokens = rec._role_tokens(text)
    vector = [1.0 if axis in tokens else 0.0 for axis in _AXES]
    return vector + [0.05]  # never all-zero


def _fake_embed(calls: list[list[str]] | None = None):
    def embed(texts, **_kw):
        if calls is not None:
            calls.append(list(texts))
        return [_fake_vector(t) for t in texts]

    return embed


def _user(db: Session) -> User:
    user = User(
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("StrongPass123!"),
        full_name="Test User",
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def _job(db: Session, title: str, *, required: list[str] | None = None, description: str = "", age_days: int = 0) -> Job:
    name = f"Co {uuid.uuid4().hex[:6]}"
    company = Company(name=name, normalized_name=name.lower())
    db.add(company)
    db.flush()
    job = Job(
        company_id=company.id,
        title=title,
        normalized_title=title.lower(),
        description=description or f"{title} role.",
        location="Bangalore",
        normalized_location="bangalore",
        work_mode=WorkMode.HYBRID,
        employment_type=EmploymentType.FULL_TIME,
        required_skills=required or [],
        preferred_skills=[],
        posted_at=datetime.now(timezone.utc) - timedelta(days=age_days),
        dedupe_hash=compute_dedupe_hash(name.lower(), title.lower(), f"bangalore-{uuid.uuid4().hex[:6]}"),
    )
    db.add(job)
    db.flush()
    return job


def test_role_matched_jobs_are_ranked_by_similarity_to_the_resume(db: Session, monkeypatch):
    user = _user(db)
    for i in range(6):
        _job(db, "Python Developer", required=["Flask"], description="Python services.", age_days=i)
    for i in range(6):
        _job(db, "Python Developer", required=["Django"], description="Django backend work.", age_days=10 + i)
    monkeypatch.setattr(embeddings, "embed", _fake_embed())

    jobs = rec.load_target_jobs(db, user.id, top_n=6, roles=["Python Developer"], resume_text="Python Django backend")
    assert len(jobs) == 6
    # The older Django posts are closer to the resume, so they win over the newer Flask ones.
    assert all("Django" in job.required_skills for job in jobs)


def test_without_embeddings_the_selection_is_the_deterministic_one(db: Session, monkeypatch):
    user = _user(db)
    for i in range(6):
        _job(db, "Python Developer", required=["Flask"], age_days=i)
    for i in range(6):
        _job(db, "Python Developer", required=["Django"], age_days=10 + i)
    _job(db, "Backend Engineer", age_days=1)  # would only be admitted semantically
    monkeypatch.setattr(embeddings, "embed", lambda texts, **kw: None)

    jobs = rec.load_target_jobs(db, user.id, top_n=6, roles=["Python Developer"], resume_text="Python Django backend")
    assert [job.required_skills for job in jobs] == [("Flask",)] * 6  # newest pool jobs first, as before
    assert all(job.title == "Python Developer" for job in jobs)


#: Explicit vectors for titles in the semantic-admission tests; anything else sits on the role's axis.
_TITLE_VECTORS = {
    "Python Developer": [1.0, 0.0, 0.0],
    "Django Engineer": [0.95, 0.2, 0.0],  # cosine ~0.98 to the role: admitted
    "Data Engineer": [0.3, 0.95, 0.0],  # cosine ~0.3: rejected
    "React Developer": [0.95, 0.0, 0.3],  # close, but a frontend title is provably another role
}


def _table_embed(texts, **_kw):
    table = {key.lower(): vector for key, vector in _TITLE_VECTORS.items()}  # titles arrive as core titles
    return [table.get(t.lower(), [1.0, 0.0, 0.0]) for t in texts]


def test_semantic_admission_fills_a_short_token_list(db: Session, monkeypatch):
    user = _user(db)
    for i in range(3):
        _job(db, "Python Developer", age_days=i)
    for title in ("Django Engineer", "Data Engineer", "React Developer"):
        _job(db, title)
    monkeypatch.setattr(embeddings, "embed", _table_embed)

    jobs = rec.load_target_jobs(db, user.id, top_n=25, roles=["Python Developer"], resume_text="Python")
    assert sorted(job.title for job in jobs) == ["Django Engineer", "Python Developer", "Python Developer", "Python Developer"]


def test_semantic_admission_never_admits_a_provably_different_role(db: Session, monkeypatch):
    user = _user(db)
    _job(db, "Backend Engineer")
    _job(db, "Frontend Engineer")
    # Every title looks identical to the role in this fake space; only the token rule can say no.
    monkeypatch.setattr(embeddings, "embed", lambda texts, **kw: [[1.0, 0.0] for _ in texts])
    jobs = rec.load_target_jobs(db, user.id, top_n=25, roles=["Backend Engineer"], resume_text="Backend")
    assert [job.title for job in jobs] == ["Backend Engineer"]


def test_semantic_admission_threshold_is_respected(monkeypatch):
    def embed(texts, **kw):
        # role first, then the title at a 0.6 cosine
        return [[1.0, 0.0]] + [[0.6, 0.8] for _ in texts[1:]]

    monkeypatch.setattr(embeddings, "embed", embed)
    assert rec.semantic_title_matches(["Software Developer"], ["Python Developer"], threshold=0.75) == [False]
    assert rec.semantic_title_matches(["Software Developer"], ["Python Developer"], threshold=0.55) == [True]


def test_no_semantic_admission_when_the_token_rule_finds_enough(db: Session, monkeypatch):
    user = _user(db)
    for i in range(rec.MIN_TARGET_JOBS):
        _job(db, "Python Developer", age_days=i)
    _job(db, "Software Engineer", age_days=0)  # not a token match; only embeddings could admit it
    calls: list[list[str]] = []
    monkeypatch.setattr(embeddings, "embed", _fake_embed(calls))
    jobs = rec.load_target_jobs(db, user.id, top_n=25, roles=["Python Developer"], resume_text="Python")
    assert {job.title for job in jobs} == {"Python Developer"}
    assert len(calls) == 1  # only the ranking call; no title embeddings were needed


def test_fingerprint_follows_the_selection(db: Session, monkeypatch):
    user = _user(db)
    for i in range(3):
        _job(db, "Python Developer", age_days=i)
    _job(db, "Django Engineer")
    inputs = rec.MatchInputs()

    monkeypatch.setattr(embeddings, "embed", lambda texts, **kw: None)
    plain = rec.load_target_jobs(db, user.id, roles=["Python Developer"], resume_text="Python")
    monkeypatch.setattr(embeddings, "embed", _table_embed)
    semantic = rec.load_target_jobs(db, user.id, roles=["Python Developer"], resume_text="Python")
    assert len(semantic) == len(plain) + 1
    assert rec.jobs_fingerprint(plain, inputs) != rec.jobs_fingerprint(semantic, inputs)


def test_resume_rank_text_falls_back_to_parsed_fields():
    from app.models.resume import Resume

    resume = Resume(
        text_content=None,
        parsed_data={"summary": "Python developer", "skills": ["Django"], "experience": [{"title": "Engineer", "description": "APIs"}]},
    )
    assert rec.resume_rank_text(resume) == "Python developer\nDjango\nEngineer\nAPIs"
    resume.text_content = "Full text"
    assert rec.resume_rank_text(resume) == "Full text"


def test_inactive_pool_jobs_are_never_candidates(db: Session, monkeypatch):
    user = _user(db)
    job = _job(db, "Python Developer")
    job.is_active = False
    db.flush()
    monkeypatch.setattr(embeddings, "embed", _fake_embed())
    assert rec.load_target_jobs(db, user.id, roles=["Python Developer"], resume_text="Python") == []
