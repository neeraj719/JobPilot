"""Field mapper rules (CONTRACTS.md section 12) - pure unit tests, no browser needed."""
from __future__ import annotations

import pytest

from app.models.enums import FieldType
from app.modules.browser.mapper import FieldMapper, is_sensitive_key, map_form, slugify
from app.modules.browser.schemas import DetectedField, DetectedForm, FieldOption

mapper = FieldMapper()


def field(
    label: str | None = None,
    *,
    name: str | None = None,
    field_type: FieldType = FieldType.TEXT,
    placeholder: str | None = None,
    options: list[str] | None = None,
    required: bool = False,
) -> DetectedField:
    return DetectedField(
        selector=f"#{name or 'f'}",
        label=label,
        name=name,
        id=name,
        placeholder=placeholder,
        field_type=field_type,
        required=required,
        options=[FieldOption(value=o, label=o) for o in options or []],
    )


# --------------------------------------------------------------------------- label variants

LABEL_CASES: list[tuple[str, str, bool]] = [
    # (label as a human sees it, expected canonical key, expected is_sensitive)
    ("First Name", "first_name", False),
    ("Given Name", "first_name", False),
    ("Last Name", "last_name", False),
    ("Surname", "last_name", False),
    ("Full Name", "full_name", False),
    ("Email Address", "email", False),
    ("Mobile Number", "phone", False),
    ("Contact Number", "phone", False),
    ("Phone", "phone", False),
    ("Current CTC", "current_salary", False),
    ("Current Salary (per annum)", "current_salary", False),
    ("Expected CTC", "expected_salary", False),
    ("Salary Expectation", "expected_salary", False),
    ("Desired Salary", "desired_salary", False),
    ("Minimum Salary", "min_salary", False),
    ("Total Years of Experience", "years_of_experience", False),
    ("Overall Experience", "years_of_experience", False),
    ("LinkedIn Profile URL", "linkedin_url", False),
    ("GitHub", "github_url", False),
    ("Portfolio Website", "portfolio_url", False),
    ("Personal Website", "portfolio_url", False),
    ("Company Website", "website", False),
    ("Street Address", "address", False),
    ("State", "state", False),
    ("Headline", "headline", False),
    ("Education", "education", False),
    ("Tech Stack you work with", "technologies", False),
    ("Cover Letter", "cover_letter", False),
    ("Are you legally authorized to work in India?", "work_authorization", True),
    ("Do you have a valid work permit?", "work_authorization", True),
    ("Will you now or in the future require sponsorship?", "requires_sponsorship", True),
    ("Are you willing to relocate?", "willing_to_relocate", False),
    ("Gender", "custom:demographic_gender", True),
    ("Race / Ethnicity", "custom:demographic_race", True),
    ("Veteran Status", "custom:demographic_veteran", True),
    ("Disability Status", "custom:demographic_disability", True),
    ("Preferred Pronouns", "custom:demographic_pronouns", True),
    ("What is your preferred start date?", "custom:start_date", False),
    ("When can you join?", "custom:start_date", False),
    ("Why do you want to work at Acme Cloud?", "custom:why_us", False),
    ("Why are you interested in this role?", "custom:why_us", False),
    ("Current Company", "current_company", False),
    ("Current Designation", "current_designation", False),
    ("City", "city", False),
    ("Current Location", "city", False),
    ("Country", "country", False),
    ("PIN Code", "postal_code", False),
    ("Highest Qualification", "highest_degree", False),
    ("University", "university", False),
    ("Key Skills", "skills", False),
    ("Tell us about yourself", "summary", False),
]


@pytest.mark.parametrize("label,expected_key,sensitive", LABEL_CASES)
def test_label_variants_map_to_canonical_keys(label: str, expected_key: str, sensitive: bool) -> None:
    mapping = mapper.map(field(label))
    assert mapping.canonical_key == expected_key, f"{label!r} -> {mapping.canonical_key} ({mapping.reason})"
    assert mapping.is_sensitive is sensitive
    assert mapping.confidence > 0.5


def test_at_least_25_distinct_label_variants_are_covered() -> None:
    assert len(LABEL_CASES) >= 25
    assert len({key for _, key, _ in LABEL_CASES}) >= 20


def test_every_canonical_key_of_section_11_has_a_rule() -> None:
    from app.modules.browser.mapper import RULES

    keys = {rule.canonical_key for rule in RULES}
    section_11 = {
        "first_name", "last_name", "full_name", "email", "phone", "address", "city", "state",
        "country", "postal_code", "linkedin_url", "github_url", "portfolio_url", "website",
        "current_designation", "current_company", "years_of_experience", "current_salary",
        "expected_salary", "desired_salary", "min_salary", "notice_period_days", "notice_period_text",
        "willing_to_relocate", "requires_sponsorship", "work_authorization", "skills", "technologies",
        "summary", "headline", "education", "highest_degree", "university", "resume_file", "cover_letter",
    }
    assert not section_11 - keys, f"canonical keys without a mapping rule: {sorted(section_11 - keys)}"
    # the two dynamic families produce their key from the match itself
    assert {"skill_years", "custom:demographic"} <= keys


# --------------------------------------------------------------------------- type-aware rules


def test_resume_upload_maps_to_resume_file() -> None:
    assert mapper.map(field("Upload your Resume", name="resume", field_type=FieldType.FILE)).canonical_key == "resume_file"
    assert mapper.map(field("CV", field_type=FieldType.FILE)).canonical_key == "resume_file"


def test_notice_period_select_is_days_and_free_text_is_text() -> None:
    select = field("Notice Period", name="notice_period", field_type=FieldType.SELECT, options=["Immediate", "30 days"])
    assert mapper.map(select).canonical_key == "notice_period_days"
    assert mapper.map(field("Notice period", field_type=FieldType.TEXT)).canonical_key == "notice_period_text"


def test_consent_checkbox_is_not_sensitive() -> None:
    for label in ("I agree to the terms and conditions", "I consent to Acme storing my data"):
        mapping = mapper.map(field(label, name="consent", field_type=FieldType.CHECKBOX))
        assert mapping.canonical_key == "custom:consent"
        assert mapping.is_sensitive is False


# --------------------------------------------------------------------------- skill_years


@pytest.mark.parametrize(
    "label,name,expected",
    [
        ("Years of experience with React", None, "skill_years:react"),
        ("How many years of experience do you have with Kubernetes?", None, "skill_years:kubernetes"),
        ("Node.js experience (years)", None, "skill_years:node.js"),
        ("Years of experience with ReactJS", None, "skill_years:react"),
        (None, "react_experience", "skill_years:react"),
        (None, "kubernetes_experience", "skill_years:kubernetes"),
        ("Describe your experience with Postgres", None, "skill_years:postgresql"),
    ],
)
def test_skill_years_uses_the_shared_skill_taxonomy(label: str | None, name: str | None, expected: str) -> None:
    assert mapper.map(field(label, name=name)).canonical_key == expected


def test_generic_experience_is_not_mistaken_for_a_skill() -> None:
    assert mapper.map(field("Total Years of Experience", name="total_experience")).canonical_key == "years_of_experience"
    assert mapper.map(field("Work experience in years", name="work_experience")).canonical_key == "years_of_experience"


# --------------------------------------------------------------------------- fallbacks


def test_unknown_question_becomes_a_custom_slug() -> None:
    mapping = mapper.map(field("What is your favourite programming paradigm?"))
    assert mapping.canonical_key == "custom:favourite_programming_paradigm"
    assert mapping.confidence < 0.5
    assert mapping.is_sensitive is False


def test_field_without_any_text_maps_to_nothing() -> None:
    mapping = mapper.map(DetectedField(selector="div > input:nth-of-type(1)"))
    assert mapping.canonical_key is None
    assert mapping.confidence == 0.0


def test_name_attribute_outranks_an_unrelated_section_heading() -> None:
    hijacked = field("Yes", name="why_company")
    hijacked.section = "Are you legally authorized to work in India?"
    assert mapper.map(hijacked).canonical_key == "custom:why_us"


def test_slugify_drops_stopwords_and_stays_short() -> None:
    assert slugify("What is your preferred start date?") == "preferred_start_date"
    assert slugify("") == "question"
    assert len(slugify("a very " + "long " * 30 + "question")) <= 40


def test_is_sensitive_key_matches_the_contract_list() -> None:
    assert is_sensitive_key("work_authorization")
    assert is_sensitive_key("requires_sponsorship")
    assert is_sensitive_key("custom:demographic_gender")
    assert is_sensitive_key("custom:legal_declaration")
    assert not is_sensitive_key("custom:why_us")
    assert not is_sensitive_key(None)


# --------------------------------------------------------------------------- map_form


def test_map_form_returns_one_mapping_per_field() -> None:
    form = DetectedForm(
        url="http://demo/apply",
        fields=[field("First Name", name="first_name"), field("Email", name="email"), field("Gender", name="gender")],
    )
    mapped = map_form(form)
    assert [m.mapping.canonical_key for m in mapped] == ["first_name", "email", "custom:demographic_gender"]
    assert [m.field.selector for m in mapped] == [f.selector for f in form.fields]
    assert mapped[2].mapping.is_sensitive is True
