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


def test_name_corrections_outlive_the_sidecar(tmp_path, monkeypatch):
    import importlib.util
    import json
    spec = importlib.util.spec_from_file_location("_pi", "tools/maintenance/process_ingress.py")
    pi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pi)
    monkeypatch.setattr(pi, "KB", tmp_path)
    log = tmp_path / "fixes.jsonl"
    monkeypatch.setattr("utils.infrastructure.monitoring.telemetry_paths.telemetry_path", lambda p: str(log))
    staged = tmp_path / "_ingress" / "Transcript - X.md"
    staged.parent.mkdir()
    staged.write_text("---\ntitle: X\n---\n\nbody")
    meta = {"folder": "transcripts", "title": "X", "submitted_by": "Ekco",
            "name_corrections": {"house ATT treaties": "House Atreides"}}
    staged.with_suffix(".meta.json").write_text(json.dumps(meta))
    ok, _ = pi._file_preformatted(staged, staged.read_text(), meta, dry_run=False)
    assert ok and not staged.with_suffix(".meta.json").exists()
    assert json.loads(log.read_text())["corrections"] == {"house ATT treaties": "House Atreides"}
