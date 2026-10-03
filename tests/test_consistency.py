"""Cross-cutting consistency checks.

These lock down the kind of subtle drift that accumulates silently across many sessions: wording,
colour conventions, identifier formatting and the exact AI disclaimer text.
"""

from __future__ import annotations

import re

import pytest

from src import config
from src import ui_formatting as ui
from src.data_loader import load_portfolio
from src.risk_engine import ALERT_REQUIREMENT_VERIFICATION, generate_early_warnings
from tests.conftest import (
    AS_OF,
    PAGE_ASK_EPOS,
    PAGE_CHANGE_IMPACT,
    PAGE_DASHBOARD,
    PAGE_PROJECT_INTELLIGENCE,
    PAGE_SCENARIO,
    PAGE_TRACEABILITY,
    rendered_text,
)

PAGES_DIR = config.PROJECT_ROOT / "pages"
SRC_DIR = config.PROJECT_ROOT / "src"
DOCS_DIR = config.PROJECT_ROOT / "docs"

ALL_PAGES = [
    PAGE_DASHBOARD,
    PAGE_PROJECT_INTELLIGENCE,
    PAGE_TRACEABILITY,
    PAGE_CHANGE_IMPACT,
    PAGE_SCENARIO,
    PAGE_ASK_EPOS,
]

DISCLAIMER = "AI-generated decision-support draft; human review required."


def _page_sources() -> dict[str, str]:
    return {path.name: path.read_text(encoding="utf-8") for path in sorted(PAGES_DIR.glob("*.py"))}


# ------------------------------------------------------------------ 1. reference date wording
def test_every_page_uses_identical_reference_date_wording():
    expected = 'f"Analysis reference date: {ui.format_date(AS_OF)} (fixed for Version 1). "'
    for name, source in _page_sources().items():
        assert expected in source, f"{name} does not use the standard reference-date wording"


@pytest.mark.parametrize("page_path", ALL_PAGES)
def test_reference_date_renders_identically_on_every_page(open_page, page_path):
    app = open_page(page_path)
    text = rendered_text(app)
    assert f"Analysis reference date: {ui.format_date(AS_OF)} (fixed for Version 1)." in text


@pytest.mark.parametrize("page_path", ALL_PAGES)
def test_every_page_states_data_is_synthetic(open_page, page_path):
    app = open_page(page_path)
    assert "All data is synthetic." in rendered_text(app)


def test_only_ask_epos_omits_the_no_ai_content_claim():
    """The five deterministic pages claim no AI content; Ask EPOS must not, since it has AI."""
    sources = _page_sources()
    claim = "No AI-generated content appears on this page."
    for name, source in sources.items():
        if name.startswith("6_"):
            assert claim not in source, "Ask EPOS must not claim it has no AI content"
        else:
            assert claim in source, f"{name} is missing the no-AI-content statement"


# ------------------------------------------------------------------ 2. colour conventions
def test_health_and_confidence_share_the_same_semantic_colours():
    assert ui.health_band_color("Green") == ui.confidence_band_color("High")
    assert ui.health_band_color("Amber") == ui.confidence_band_color("Medium")
    assert ui.health_band_color("Red") == ui.confidence_band_color("Low")


def test_trace_status_colours_reuse_the_existing_palette():
    """The trace badge must not introduce a new colour scheme."""
    allowed = set(ui.HEALTH_BAND_COLORS.values()) | set(ui.SEVERITY_COLORS.values())
    for status in ui.TRACE_STATUSES:
        assert ui.trace_status_color(status) in allowed

    assert ui.trace_status_color(ui.TRACE_VERIFIED) == ui.HEALTH_BAND_COLORS["Green"]
    assert ui.trace_status_color(ui.TRACE_NOT_RUN) == ui.SEVERITY_COLORS["Medium"]
    assert ui.trace_status_color(ui.TRACE_NOT_VERIFIED) == ui.SEVERITY_COLORS["High"]
    assert ui.trace_status_color(ui.TRACE_NO_LINK) == ui.SEVERITY_COLORS["Critical"]


def test_every_colour_is_defined_once_in_ui_formatting():
    """No page may hardcode a hex colour; the palette lives in one module."""
    hex_pattern = re.compile(r"#[0-9A-Fa-f]{6}")
    for name, source in _page_sources().items():
        assert not hex_pattern.search(source), f"{name} hardcodes a hex colour"


def test_severity_and_band_vocabularies_are_stable():
    assert ui.SEVERITIES == ("Critical", "High", "Medium", "Low")
    assert ui.HEALTH_BANDS == ("Green", "Amber", "Red")
    assert ui.CONFIDENCE_BANDS == ("High", "Medium", "Low")
    assert set(ui.SEVERITY_COLORS) == set(ui.SEVERITIES)
    assert set(ui.HEALTH_BAND_COLORS) == set(ui.HEALTH_BANDS)
    assert set(ui.CONFIDENCE_BAND_COLORS) == set(ui.CONFIDENCE_BANDS)


# ------------------------------------------------------------------ 3. identifier formatting
def test_record_ids_are_rendered_bare_everywhere():
    """Every page that renders identifier lists uses the one shared helper."""
    for name, source in _page_sources().items():
        if "source_ids" in source:
            assert (
                "ui.format_source_ids" in source
            ), f"{name} renders identifiers without the shared helper"


def test_no_page_formats_a_source_id_list_with_a_plain_join():
    """Identifier lists must go through the shared helper, so formatting cannot drift again."""
    plain_join_of_ids = re.compile(r"\.join\([^)]*source_ids")
    offenders = [
        name for name, source in _page_sources().items() if plain_join_of_ids.search(source)
    ]
    assert offenders == [], f"{offenders} format a source-id list with a plain join"


def test_every_data_quality_issue_cites_at_least_one_record():
    """The shared helper renders 'none' for an empty list; no issue should ever be empty."""
    from src.confidence_engine import calculate_project_confidence

    portfolio = load_portfolio()
    for project_id in sorted(portfolio.project_ids):
        result = calculate_project_confidence(project_id, portfolio, AS_OF)
        for issue in result.data_quality_issues:
            assert issue.source_ids, f"{issue.issue_type} cites no record"


def test_format_source_ids_is_the_single_identifier_formatter():
    assert ui.format_source_ids(["R-2001", "M-202"]) == "R-2001, M-202"
    assert ui.format_source_ids([]) == "none"


def test_identifiers_appear_without_type_prefixes(open_page):
    """A page must not decorate an ID as 'Risk R-2001' while others show 'R-2001'."""
    app = open_page(PAGE_PROJECT_INTELLIGENCE, selected_project="P-002")
    text = rendered_text(app)
    assert "R-2001" in text
    assert "Risk R-2001," not in text

    app = open_page(PAGE_TRACEABILITY, selected_project="P-002")
    trace_text = rendered_text(app)
    assert "REQ-2001" in trace_text or "REQ-2001" in str(
        [element.value.to_string() for element in app.dataframe]
    )


# ------------------------------------------------------------------ 4. disclaimer text
def test_disclaimer_constant_is_the_single_source():
    assert config.AI_DISCLAIMER == DISCLAIMER


def test_disclaimer_is_never_retyped_as_a_literal_outside_config_and_tests():
    """Code must reference the constant, not a copy of the string that could drift."""
    offenders = []
    for path in list(SRC_DIR.glob("*.py")) + list(PAGES_DIR.glob("*.py")):
        if path.name == "config.py":
            continue
        source = path.read_text(encoding="utf-8")
        if DISCLAIMER in source:
            offenders.append(path.name)
    assert offenders == [], f"disclaimer text is duplicated in {offenders}"


def test_disclaimer_is_character_identical_wherever_documented():
    for name in ("ai-governance.md", "ui-design-guide.md"):
        text = (DOCS_DIR / name).read_text(encoding="utf-8")
        if DISCLAIMER.rstrip(".") in text:
            assert DISCLAIMER in text, f"{name} has a drifted copy of the disclaimer"


def test_disclaimer_renders_verbatim_in_the_ai_section(monkeypatch):
    from streamlit.testing.v1 import AppTest

    import src.ai_assistant as ai
    import src.config as config_module
    from src.config import AzureOpenAISettings
    from src.schemas import CopilotResponse
    from tests.conftest import APP_PATH

    monkeypatch.setattr(
        config_module,
        "get_azure_settings",
        lambda: AzureOpenAISettings(api_key="stub", endpoint="https://example.invalid"),
    )
    monkeypatch.setattr(
        ai,
        "ask_epos",
        lambda *args, **kwargs: CopilotResponse(
            executive_summary="s",
            key_findings=[],
            recommended_actions=[],
            source_ids=[],
            human_review_required=True,
            disclaimer=DISCLAIMER,
        ),
    )

    app = AppTest.from_file(APP_PATH, default_timeout=120)
    app.run()
    app.switch_page(PAGE_ASK_EPOS)
    app.session_state["ask_question_type"] = ai.QUESTION_RISKS_WITHOUT_OWNER
    app.run()
    app.button[0].click().run()
    assert DISCLAIMER in rendered_text(app)


# ------------------------------------------------------------------ engine-level consistency
@pytest.mark.parametrize("project_id", ["P-002", "P-007"])
def test_trace_status_never_contradicts_rule8(project_id):
    """Raw trace/test data must never contradict the Risk engine's verification alerts."""
    portfolio = load_portfolio()
    test_cases = {t.test_case_id: t for t in portfolio.test_cases if t.project_id == project_id}
    links = [t for t in portfolio.trace_links if t.project_id == project_id]

    statuses = {}
    for requirement in (r for r in portfolio.requirements if r.project_id == project_id):
        linked = [
            test_cases[link.target_id]
            for link in links
            if link.link_type == "verified_by"
            and link.source_type == "Requirement"
            and link.source_id == requirement.requirement_id
            and link.target_type == "TestCase"
            and link.target_id in test_cases
        ]
        statuses[requirement.requirement_id] = ui.trace_status(
            (tc.status, tc.has_verification_evidence) for tc in linked
        )

    alerted = {
        source_id
        for alert in generate_early_warnings(project_id, portfolio, AS_OF)
        if alert.alert_type == ALERT_REQUIREMENT_VERIFICATION
        for source_id in alert.source_ids
        if source_id in statuses
    }

    for requirement_id in alerted:
        assert statuses[requirement_id] != ui.TRACE_VERIFIED
    for requirement_id, status in statuses.items():
        if status == ui.TRACE_VERIFIED:
            assert requirement_id not in alerted


# ------------------------------------------------------------------ house style
def test_no_emoji_anywhere_in_code_or_docs():
    """The project forbids emojis; this locks that in permanently."""
    emoji_pattern = re.compile("[\U0001f300-\U0001faff\U00002600-\U000027bf\U0001f1e6-\U0001f1ff]")
    checked = 0
    offenders: list[str] = []
    for directory in (SRC_DIR, PAGES_DIR, DOCS_DIR, config.PROJECT_ROOT / "tests"):
        for path in list(directory.glob("*.py")) + list(directory.glob("*.md")):
            checked += 1
            if emoji_pattern.search(path.read_text(encoding="utf-8")):
                offenders.append(str(path.relative_to(config.PROJECT_ROOT)))
    for name in ("README.md",):
        checked += 1
        if emoji_pattern.search((config.PROJECT_ROOT / name).read_text(encoding="utf-8")):
            offenders.append(name)

    assert checked > 30, "the emoji sweep should cover the whole project"
    assert offenders == [], f"emoji found in {offenders}"


def test_pages_contain_no_scoring_logic():
    """Pages must never recompute what an engine already calculates."""
    forbidden = ("HEALTH_WEIGHTS", "CONFIDENCE_WEIGHTS", "SEVERITY_ORDER", "FACTOR_BASE_SCORE")
    for name, source in _page_sources().items():
        for token in forbidden:
            assert token not in source, f"{name} references scoring internals ({token})"


def test_pages_never_read_environment_variables_directly():
    for name, source in _page_sources().items():
        assert "os.getenv" not in source, f"{name} reads the environment directly"
        assert "load_dotenv" not in source, f"{name} loads dotenv directly"
