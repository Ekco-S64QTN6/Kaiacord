"""What a filed YouTube transcript says about itself."""


def test_a_cold_open_does_not_become_the_summary():
    import importlib.util
    spec = importlib.util.spec_from_file_location("_yt", "tools/maintenance/youtube_to_kb_md.py")
    yt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(yt)
    s = yt.transcript_summary("Kernel Exploits in the iOS App Store", "Three Buddy Problem",
                              "for our friends and censored models and give them access. Bitcoins, man.")
    assert s.startswith("Kernel Exploits in the iOS App Store, from Three Buddy Problem.")
    assert "for our friends" not in s
