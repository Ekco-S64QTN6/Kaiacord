

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
