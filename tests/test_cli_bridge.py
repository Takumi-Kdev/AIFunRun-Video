from __future__ import annotations


def test_factory_forwards_stable_output_directory(monkeypatch, tmp_path):
    import run as cli
    from core import factory

    seen = {}

    def fake_run(instruction, template=None, out_dir=None, label=""):
        seen.update(instruction=instruction, template=template, out_dir=out_dir)
        return {"ok": True, "artifacts": []}

    monkeypatch.setattr(factory, "run", fake_run)
    result = cli._factory("作品を作る", "short_explainer", 1, str(tmp_path))
    assert result["ok"]
    assert seen["out_dir"] == str(tmp_path)
