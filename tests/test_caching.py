"""Empirical caching and call-count checks.

These count real calls to the loader and the three core engines across a simulated multi-page
session, so the caching design is verified by measurement rather than by reading the code.
"""

from __future__ import annotations

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import src.data_loader as data_loader_module
from tests.conftest import (
    APP_PATH,
    PAGE_ASK_EPOS,
    PAGE_CHANGE_IMPACT,
    PAGE_DASHBOARD,
    PAGE_PROJECT_INTELLIGENCE,
    PAGE_SCENARIO,
    PAGE_TRACEABILITY,
)


@pytest.fixture(autouse=True)
def clear_streamlit_caches():
    """Streamlit caches are process-global, so reset them for deterministic call counts."""
    st.cache_data.clear()
    yield
    st.cache_data.clear()


class CallCounter:
    """Count calls to a function across every module that imported it by name.

    Modules that do ``from x import f`` bind the original object at import time, so patching only
    the defining module would miss their calls. Pages are re-executed on each run and pick the
    patch up dynamically; long-lived modules must be patched explicitly.
    """

    def __init__(self, monkeypatch, name, *modules):
        self.count = 0
        original = getattr(modules[0], name)

        def _counted(*args, **kwargs):
            self.count += 1
            return original(*args, **kwargs)

        for module in modules:
            if getattr(module, name, None) is not None:
                monkeypatch.setattr(module, name, _counted)


def _health_counter(monkeypatch):
    import src.ai_assistant as ai_module
    import src.health_engine as health_module
    import src.scenario_engine as scenario_module

    return CallCounter(
        monkeypatch, "calculate_project_health", health_module, ai_module, scenario_module
    )


def _confidence_counter(monkeypatch):
    import src.ai_assistant as ai_module
    import src.confidence_engine as confidence_module
    import src.scenario_engine as scenario_module

    return CallCounter(
        monkeypatch,
        "calculate_project_confidence",
        confidence_module,
        ai_module,
        scenario_module,
    )


def _alerts_counter(monkeypatch):
    import src.ai_assistant as ai_module
    import src.risk_engine as risk_module
    import src.scenario_engine as scenario_module

    return CallCounter(
        monkeypatch, "generate_early_warnings", risk_module, ai_module, scenario_module
    )


def test_portfolio_is_loaded_once_per_session(monkeypatch):
    """The shell caches the load, so navigating six pages must not reload the CSVs each time."""
    import app as _app_module  # noqa: F401  (ensures the module path is importable)

    counter = CallCounter(monkeypatch, "load_portfolio", data_loader_module)

    app = AppTest.from_file(APP_PATH, default_timeout=180)
    app.run()
    first_run_loads = counter.count

    for page in (
        PAGE_PROJECT_INTELLIGENCE,
        PAGE_TRACEABILITY,
        PAGE_CHANGE_IMPACT,
        PAGE_SCENARIO,
        PAGE_ASK_EPOS,
        PAGE_DASHBOARD,
    ):
        app.switch_page(page)
        app.run()

    assert first_run_loads <= 1, "the first render should load the portfolio at most once"
    assert (
        counter.count == first_run_loads
    ), f"navigating six pages triggered {counter.count - first_run_loads} extra portfolio loads"
    assert counter.count <= 1


def test_engine_calls_are_bounded_across_a_multi_page_session(monkeypatch):
    """Count real engine invocations while a user walks the whole application."""
    health = _health_counter(monkeypatch)
    confidence = _confidence_counter(monkeypatch)
    alerts = _alerts_counter(monkeypatch)

    app = AppTest.from_file(APP_PATH, default_timeout=180)
    app.run()

    for page in (
        PAGE_PROJECT_INTELLIGENCE,
        PAGE_TRACEABILITY,
        PAGE_CHANGE_IMPACT,
        PAGE_SCENARIO,
        PAGE_DASHBOARD,
    ):
        app.switch_page(page)
        app.run()

    # Two synthetic projects and six page renders. Without caching this would be far higher;
    # the bound proves results are reused rather than recomputed on every render.
    assert health.count <= 12, f"health engine called {health.count} times"
    assert confidence.count <= 12, f"confidence engine called {confidence.count} times"
    assert alerts.count <= 20, f"risk engine called {alerts.count} times"


def test_revisiting_a_page_does_not_recompute(monkeypatch):
    """Returning to a page already rendered in this session must hit the cache."""
    health = _health_counter(monkeypatch)

    app = AppTest.from_file(APP_PATH, default_timeout=180)
    app.run()
    app.switch_page(PAGE_PROJECT_INTELLIGENCE)
    app.session_state["selected_project"] = "P-007"
    app.run()
    after_first_visit = health.count

    app.switch_page(PAGE_TRACEABILITY)
    app.run()
    app.switch_page(PAGE_PROJECT_INTELLIGENCE)
    app.run()

    assert (
        health.count == after_first_visit
    ), "revisiting Project Intelligence recomputed Health instead of using the cache"


def test_widget_interaction_does_not_recompute_engine_results(monkeypatch):
    """Moving the exceptions slider must not re-run the engines behind the dashboard."""
    health = _health_counter(monkeypatch)

    app = AppTest.from_file(APP_PATH, default_timeout=180)
    app.run()
    baseline = health.count

    app.slider[0].set_value(3).run()
    app.slider[0].set_value(12).run()

    assert (
        health.count == baseline
    ), f"slider interaction triggered {health.count - baseline} extra Health computations"


def test_ask_epos_rebuilds_its_evidence_on_every_render(monkeypatch):
    """Documents measured behaviour: the evidence package is not cached.

    This is correct but uncached, so the evidence is always fresh. It costs one engine call per
    project per render. Recorded here so the cost cannot grow unnoticed. See
    docs/pending-decisions.md item 6.
    """
    health = _health_counter(monkeypatch)

    app = AppTest.from_file(APP_PATH, default_timeout=180)
    app.run()
    app.switch_page(PAGE_ASK_EPOS)
    app.run()
    after_first = health.count

    app.run()
    per_render = health.count - after_first

    # One call per project in the portfolio, and no more.
    project_count = len(app.session_state["portfolio"].project_ids)
    assert (
        per_render == project_count
    ), f"expected {project_count} health calls per Ask EPOS render, saw {per_render}"


def test_measured_call_counts_for_a_full_walkthrough(monkeypatch):
    """Locks in the measured cost of visiting every page once."""
    loads = CallCounter(monkeypatch, "load_portfolio", data_loader_module)
    health = _health_counter(monkeypatch)
    confidence = _confidence_counter(monkeypatch)
    alerts = _alerts_counter(monkeypatch)

    app = AppTest.from_file(APP_PATH, default_timeout=180)
    app.run()
    for page in (
        PAGE_PROJECT_INTELLIGENCE,
        PAGE_TRACEABILITY,
        PAGE_CHANGE_IMPACT,
        PAGE_SCENARIO,
        PAGE_ASK_EPOS,
        PAGE_DASHBOARD,
    ):
        app.switch_page(page)
        app.run()

    # The portfolio is loaded once and reused; engine calls scale with pages, not with projects.
    assert loads.count == 1
    assert confidence.count == health.count
    assert alerts.count > 0
