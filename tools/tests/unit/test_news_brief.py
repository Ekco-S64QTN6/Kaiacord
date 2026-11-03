

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
    monkeypatch.setattr(ukn.time, "sleep", sleeps.append)

    brief = updater.generate_daily_brief()

    assert "A verified report was published today" in brief
    assert models.attempts == 5
    assert sleeps == [10, 20, 40, 60]
    assert [ukn.grounding_retry_delay(n) for n in range(1, 7)] == [
        10, 20, 40, 60, 60, 60
    ]
