"""Value-level UI tests for the Ask EPOS page.

Every test stubs the AI call path or the settings accessor. No test performs a network call.
"""

from __future__ import annotations

import json

import pytest
from streamlit.testing.v1 import AppTest

from src import ai_assistant as ai
from src.config import AzureOpenAISettings
from src.data_loader import load_portfolio
from src.schemas import CopilotResponse
from tests.conftest import APP_PATH, AS_OF, PAGE_ASK_EPOS, frame_named, rendered_text

DISCLAIMER = "AI-generated decision-support draft; human review required."

CONTEXT_FOR_QUESTION = {
    ai.QUESTION_PROJECTS_NEEDING_ATTENTION: {},
    ai.QUESTION_WHY_PROJECT_BAND: {"selected_project": "P-007"},
    ai.QUESTION_RISKS_WITHOUT_OWNER: {},
    ai.QUESTION_MILESTONES_AT_RISK: {},
    ai.QUESTION_REQUIREMENTS_WITHOUT_VERIFICATION: {},
    ai.QUESTION_CHANGE_REQUEST_IMPACT: {
        "selected_project": "P-007",
        "selected_change_request": "CR-042",
    },
    ai.QUESTION_WEEKLY_EXECUTIVE_UPDATE: {},
}


def _force_configured(monkeypatch, configured: bool = True) -> None:
    import src.config as config_module

    settings = (
        AzureOpenAISettings(api_key="stub", endpoint="https://example.invalid/chat")
        if configured
        else AzureOpenAISettings(api_key=None, endpoint=None)
    )
    # The page and ask_epos each hold their own reference to the accessor; both must agree.
    monkeypatch.setattr(config_module, "get_azure_settings", lambda: settings)
    monkeypatch.setattr(ai, "get_azure_settings", lambda: settings)


def _canned_response(source_ids: list[str] | None = None) -> CopilotResponse:
    return CopilotResponse(
        executive_summary="Two risks currently have no mitigation owner.",
        key_findings=["R-2001 has no mitigation owner.", "R-7001 has no mitigation owner."],
        recommended_actions=["Assign a mitigation owner to each risk."],
        source_ids=source_ids if source_ids is not None else ["R-2001", "R-7001"],
        human_review_required=True,
        disclaimer=DISCLAIMER,
    )


def _open_and_ask(monkeypatch, question_type, response, extra_state=None):
    _force_configured(monkeypatch)
    monkeypatch.setattr(ai, "ask_epos", lambda *args, **kwargs: response)

    app = AppTest.from_file(APP_PATH, default_timeout=120)
    app.run()
    app.switch_page(PAGE_ASK_EPOS)
    app.session_state["ask_question_type"] = question_type
    for key, value in (extra_state or {}).items():
        app.session_state[key] = value
    app.run()
    app.button[0].click().run()
    return app


# ------------------------------------------------------------------ evidence rendering
@pytest.mark.parametrize("question_type", list(ai.QUESTION_TYPES))
def test_evidence_renders_for_every_question_type(monkeypatch, question_type):
    """The deterministic evidence must be correct and rendered before any AI call."""
    _force_configured(monkeypatch)

    def _fail(*args, **kwargs):
        raise AssertionError("ask_epos must not be called before the Ask action")

    monkeypatch.setattr(ai, "ask_epos", _fail)

    app = AppTest.from_file(APP_PATH, default_timeout=120)
    app.run()
    app.switch_page(PAGE_ASK_EPOS)
    app.session_state["ask_question_type"] = question_type
    for key, value in CONTEXT_FOR_QUESTION[question_type].items():
        app.session_state[key] = value
    app.run()

    assert len(app.exception) == 0
    assert len(app.error) == 0
    assert any(sub.value == "Deterministic evidence" for sub in app.subheader)

    context = {}
    if question_type == ai.QUESTION_WHY_PROJECT_BAND:
        context = {"project_id": "P-007"}
    elif question_type == ai.QUESTION_CHANGE_REQUEST_IMPACT:
        context = {"change_request_id": "CR-042"}
    expected = ai.build_evidence_package(question_type, load_portfolio(), AS_OF, context)

    frame = frame_named(app, "Type", "ID", "Details")
    assert set(frame["ID"]) == {record.record_id for record in expected.records}
    assert set(frame["Type"]) == {record.record_type for record in expected.records}


# ------------------------------------------------------------------ AI draft rendering
@pytest.mark.parametrize("question_type", list(ai.QUESTION_TYPES))
def test_ai_draft_renders_for_every_question_type(monkeypatch, question_type):
    response = _canned_response()
    app = _open_and_ask(monkeypatch, question_type, response, CONTEXT_FOR_QUESTION[question_type])
    text = rendered_text(app)

    assert len(app.exception) == 0
    assert len(app.error) == 0
    assert response.executive_summary in text
    for finding in response.key_findings:
        assert finding in text
    for action in response.recommended_actions:
        assert action in text
    assert "R-2001, R-7001" in text
    assert DISCLAIMER in text


def test_ai_section_is_visually_distinguished(monkeypatch):
    app = _open_and_ask(monkeypatch, ai.QUESTION_RISKS_WITHOUT_OWNER, _canned_response())
    subheaders = [sub.value for sub in app.subheader]
    text = rendered_text(app)

    # Deterministic evidence is shown first, then a clearly labelled AI section.
    assert "Deterministic evidence" in subheaders
    assert "AI-generated draft" in subheaders
    assert subheaders.index("Deterministic evidence") < subheaders.index("AI-generated draft")
    assert "AI-generated section" in text
    assert DISCLAIMER in text


def test_grounding_warning_is_surfaced(monkeypatch):
    response = _canned_response()
    flagged = response.model_copy(
        update={"warnings": ["Removed source IDs not present in the supplied evidence: R-9999"]}
    )
    app = _open_and_ask(monkeypatch, ai.QUESTION_RISKS_WITHOUT_OWNER, flagged)
    text = rendered_text(app)
    assert "Grounding checks" in text
    assert "R-9999" in text


# ------------------------------------------------------------------ degraded paths
def test_ai_unavailable_path(monkeypatch):
    _force_configured(monkeypatch, configured=False)

    app = AppTest.from_file(APP_PATH, default_timeout=120)
    app.run()
    app.switch_page(PAGE_ASK_EPOS)
    app.session_state["ask_question_type"] = ai.QUESTION_RISKS_WITHOUT_OWNER
    app.run()

    text = rendered_text(app)
    assert len(app.exception) == 0
    assert "AI capability is unavailable" in text
    # The deterministic half of the page must still work.
    assert any(sub.value == "Deterministic evidence" for sub in app.subheader)
    frame = frame_named(app, "Type", "ID", "Details")
    assert not frame.empty
    assert app.button[0].disabled is True


@pytest.mark.parametrize(
    ("status", "expected_fragment"),
    [
        ("error", "could not be completed"),
        ("invalid_response", "did not match the required structure"),
        ("unavailable", "AI capability is unavailable"),
    ],
)
def test_degraded_statuses_render_safely(monkeypatch, status, expected_fragment):
    degraded = CopilotResponse(
        executive_summary="AI capability is unavailable because Azure OpenAI configuration "
        "is missing. Core deterministic portfolio analysis remains available.",
        key_findings=[],
        recommended_actions=[],
        source_ids=[],
        human_review_required=True,
        disclaimer=DISCLAIMER,
        status=status,
        warnings=["diagnostic detail"],
    )
    app = _open_and_ask(monkeypatch, ai.QUESTION_RISKS_WITHOUT_OWNER, degraded)
    text = rendered_text(app)

    assert len(app.exception) == 0
    assert expected_fragment in text
    assert DISCLAIMER in text


def test_timeout_through_the_real_ask_epos_with_a_fake_transport(monkeypatch):
    """Exercise the genuine ask_epos error path via an injected failing transport."""
    _force_configured(monkeypatch)

    def _boom(url, headers, payload, timeout):
        raise TimeoutError("simulated timeout")

    real_ask = ai.ask_epos
    monkeypatch.setattr(
        ai,
        "ask_epos",
        lambda question_type, portfolio, as_of_date, context=None, transport=None: real_ask(
            question_type, portfolio, as_of_date, context, _boom
        ),
    )

    app = AppTest.from_file(APP_PATH, default_timeout=120)
    app.run()
    app.switch_page(PAGE_ASK_EPOS)
    app.session_state["ask_question_type"] = ai.QUESTION_RISKS_WITHOUT_OWNER
    app.run()
    app.button[0].click().run()

    assert len(app.exception) == 0
    assert "could not be completed" in rendered_text(app)


def test_malformed_response_through_the_real_ask_epos(monkeypatch):
    _force_configured(monkeypatch)

    def _garbage(url, headers, payload, timeout):
        return {"choices": [{"message": {"content": json.dumps({"unexpected": True})}}]}

    real_ask = ai.ask_epos
    monkeypatch.setattr(
        ai,
        "ask_epos",
        lambda question_type, portfolio, as_of_date, context=None, transport=None: real_ask(
            question_type, portfolio, as_of_date, context, _garbage
        ),
    )

    app = AppTest.from_file(APP_PATH, default_timeout=120)
    app.run()
    app.switch_page(PAGE_ASK_EPOS)
    app.session_state["ask_question_type"] = ai.QUESTION_RISKS_WITHOUT_OWNER
    app.run()
    app.button[0].click().run()

    assert len(app.exception) == 0
    assert "did not match the required structure" in rendered_text(app)


def test_page_states_ai_never_calculates(monkeypatch):
    """The governance statement accompanies the AI output, where it is most relevant."""
    app = _open_and_ask(monkeypatch, ai.QUESTION_RISKS_WITHOUT_OWNER, _canned_response())
    text = rendered_text(app)
    assert "never calculates scores" in text
    assert "takes any action" in text


def test_page_header_states_grounding_before_any_ask(monkeypatch):
    _force_configured(monkeypatch)
    app = AppTest.from_file(APP_PATH, default_timeout=120)
    app.run()
    app.switch_page(PAGE_ASK_EPOS)
    app.run()
    text = rendered_text(app)
    assert "source-grounded" in text
    assert "deterministic" in text
    assert "requires human review" in text
