from types import SimpleNamespace

from researchflow.gitops import git


def test_git_trusts_only_the_selected_repository_for_one_command(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stdout="true\n", stderr="")

    monkeypatch.setattr("researchflow.gitops.subprocess.run", fake_run)
    assert git(repo, "rev-parse", "--is-inside-work-tree") == "true"
    assert captured["command"][:3] == [
        "git",
        "-c",
        f"safe.directory={repo.resolve().as_posix()}",
    ]
    assert captured["command"][3:] == ["-C", str(repo), "rev-parse", "--is-inside-work-tree"]
    assert captured["kwargs"]["encoding"] == "utf-8"
    assert captured["kwargs"]["errors"] == "surrogateescape"
