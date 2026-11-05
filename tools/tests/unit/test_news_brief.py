

def test_a_brief_with_no_stories_is_a_failed_generation():
    """26 Sept's brief: every section 'No verified developments', logged as generated successfully."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("_ukn", "tools/maintenance/update_kaia_news.py")
    ukn = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ukn)
    empty = ("---\nkeywords:\n- news brief\n- no developments\n---\n# NEWS_BRIEF: 2026-09-26\n\n"
             "## EXECUTIVE_SUMMARY\nThe news landscape remains quiet.\n\n"
             "## GENERAL_NEWS\n- No verified developments today.\n\n## US_POLITICS\n- No verified developments today.\n")
    assert ukn.story_count(empty) == 0
    assert ukn.story_count(empty + "\n## SECURITY_INCIDENTS\n- A real breach.\n- QUOTE: \"x\" - Someone\n") == 1


def test_grounding_retries_503_with_capped_exponential_backoff(monkeypatch):
    """A brief 503 must get a useful recovery window without dropping grounding."""
    import importlib.util
    from types import SimpleNamespace

    spec = importlib.util.spec_from_file_location(
        "_ukn_retry", "tools/maintenance/update_kaia_news.py"
    )
    ukn = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ukn)

    class TemporaryUnavailable(Exception):
        pass

    class FlakyModels:
        def __init__(self):
            self.attempts = 0

        def generate_content(self, **kwargs):
            self.attempts += 1
            assert kwargs["config"].tools  # Google Search grounding remains mandatory.
            if self.attempts < 5:
                raise TemporaryUnavailable("503 UNAVAILABLE: model is busy")
            return SimpleNamespace(text=(
                "# NEWS_BRIEF: 2026-11-03\n\n"
                "## EXECUTIVE_SUMMARY\nA verified report was published.\n\n"
                "## GENERAL_NEWS\n- A verified report was published today. - *AP*\n"
            ))

    models = FlakyModels()
    updater = ukn.KaiaNewsUpdater.__new__(ukn.KaiaNewsUpdater)
    updater.client = SimpleNamespace(models=models)
    updater.model_name = "gemini-2.5-flash"
    updater.today = "2026-11-03"
    sleeps = []

    monkeypatch.setattr(ukn, "ServerError", TemporaryUnavailable)
    monkeypatch.setattr(ukn.random, "uniform", lambda _low, high: high)
    monkeypatch.setattr(ukn.time, "sleep", sleeps.append)

    brief = updater.generate_daily_brief()

    assert "A verified report was published today" in brief
    assert models.attempts == 5
    assert sleeps == [10, 20, 40, 60]
    assert [ukn.grounding_retry_delay(n) for n in range(1, 7)] == [
        10, 20, 40, 60, 60, 60
    ]


def test_grounding_retry_delay_uses_full_jitter(monkeypatch):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_ukn_jitter", "tools/maintenance/update_kaia_news.py"
    )
    ukn = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ukn)

    bounds = []
    def midpoint(low, high):
        bounds.append((low, high))
        return (low + high) / 2

    monkeypatch.setattr(ukn.random, "uniform", midpoint)
    assert [ukn.grounding_retry_delay(n) for n in range(1, 7)] == [
        5, 10, 20, 30, 30, 30
    ]
    assert bounds == [
        (0.0, 10.0), (0.0, 20.0), (0.0, 40.0),
        (0.0, 60.0), (0.0, 60.0), (0.0, 60.0),
    ]


def test_permanent_api_error_is_not_retried(monkeypatch, capsys):
    import importlib.util
    from types import SimpleNamespace

    spec = importlib.util.spec_from_file_location(
        "_ukn_permanent", "tools/maintenance/update_kaia_news.py"
    )
    ukn = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ukn)

    class PermanentAPIError(Exception):
        code = 400

    class FailingModels:
        attempts = 0
        def generate_content(self, **_kwargs):
            self.attempts += 1
            raise PermanentAPIError("invalid request")

    models = FailingModels()
    updater = ukn.KaiaNewsUpdater.__new__(ukn.KaiaNewsUpdater)
    updater.client = SimpleNamespace(models=models)
    updater.model_name = "gemini-2.5-flash"
    updater.today = "2026-11-05"
    sleeps = []

    monkeypatch.setattr(ukn, "APIError", PermanentAPIError)
    monkeypatch.setattr(ukn.time, "sleep", sleeps.append)

    import pytest
    with pytest.raises(Exception, match="Grounding failed after 1 attempt"):
        updater.generate_daily_brief()

    assert models.attempts == 1
    assert sleeps == []
    assert "[NEWS_RETRYABLE_EXHAUSTED]" not in capsys.readouterr().out



def test_empty_grounded_response_records_candidate_diagnostics_without_content():
    import importlib.util
    from types import SimpleNamespace

    spec = importlib.util.spec_from_file_location(
        "_ukn_empty", "tools/maintenance/update_kaia_news.py"
    )
    ukn = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ukn)

    response = SimpleNamespace(
        candidates=[SimpleNamespace(
            finish_reason="STOP",
            finish_message="Model returned no user-visible text.",
            content=SimpleNamespace(parts=[
                SimpleNamespace(text=None, function_call=None, inline_data=None)
            ]),
        )],
        prompt_feedback=SimpleNamespace(block_reason=None),
        usage_metadata=SimpleNamespace(prompt_token_count=900, candidates_token_count=0),
        model_version="gemini-2.5-flash-test",
        response_id="resp-123",
    )
    details = ukn._empty_response_diagnostics(response)
    assert "finish_reason" in details and "STOP" in details
    assert "finish_message" in details and "no user-visible text" in details
    assert "part_count" in details and "has_text" in details
    assert "output_tokens=0" in details
    assert "model_version=gemini-2.5-flash-test" in details
    assert "resp-123" in details
    assert "private prompt" not in details



def test_candidate_text_parts_are_joined_as_real_lines():
    import importlib.util
    from types import SimpleNamespace

    spec = importlib.util.spec_from_file_location(
        "_ukn_parts", "tools/maintenance/update_kaia_news.py"
    )
    ukn = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ukn)

    response = SimpleNamespace(
        text=None,
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=[
            SimpleNamespace(text="First verified story."),
            SimpleNamespace(text="Second verified story."),
        ]))],
    )
    assert ukn._extract_response_text(response) == (
        "First verified story.\nSecond verified story."
    )


def test_exhausted_transient_grounding_failure_emits_followup_marker(monkeypatch, capsys):
    import importlib.util
    from types import SimpleNamespace
    import pytest

    spec = importlib.util.spec_from_file_location(
        "_ukn_followup_signal", "tools/maintenance/update_kaia_news.py"
    )
    ukn = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ukn)

    class TemporaryUnavailable(Exception):
        pass

    class BusyModels:
        def generate_content(self, **_kwargs):
            raise TemporaryUnavailable("503 UNAVAILABLE")

    updater = ukn.KaiaNewsUpdater.__new__(ukn.KaiaNewsUpdater)
    updater.client = SimpleNamespace(models=BusyModels())
    updater.model_name = "gemini-2.5-flash"
    updater.today = "2026-11-05"

    monkeypatch.setattr(ukn, "ServerError", TemporaryUnavailable)
    monkeypatch.setattr(ukn, "GROUNDING_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(ukn.random, "uniform", lambda _low, _high: 0)
    monkeypatch.setattr(ukn.time, "sleep", lambda _seconds: None)

    with pytest.raises(Exception, match="Grounding failed after 2 attempt"):
        updater.generate_daily_brief()

    assert "[NEWS_RETRYABLE_EXHAUSTED]" in capsys.readouterr().out
