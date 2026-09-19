"""Jobs module: discovery orchestration, normalisation, dedupe and job listings.

Public surface (``docs/CONTRACTS.md`` §9)::

    from app.modules.jobs.service import ingest_discovered, discover_jobs, list_jobs
    from app.modules.jobs.dedupe import compute_dedupe_hash
    from app.modules.jobs.normalize import normalize_title, normalize_location
"""
