import pytest

from researchflow.errors import ResearchFlowError
from researchflow.io import append_jsonl, read_jsonl
from researchflow.project import ResearchProject, add_project
from researchflow.records import add_decision, add_hypothesis, add_observation, show_record


def test_registry_append_and_read(tmp_path):
    path = tmp_path / "registry.jsonl"
    append_jsonl(path, {"id": "A"})
    append_jsonl(path, {"id": "B"})
    assert read_jsonl(path) == [{"id": "A"}, {"id": "B"}]


def test_memory_records_validate_references(rf_env):
    add_project("toy", rf_env["repo"])
    project = ResearchProject.open("toy")
    obs = add_observation(project, "Deterministic output", "The fixture returned 2.", confidence="high")
    hyp = add_hypothesis(project, "Scaling", "Doubling input doubles output.", [obs], falsification="Output is not doubled.")
    decision = add_decision(project, "Run a bounded pilot", "The observation supports a falsifiable test.", [obs, hyp])
    assert show_record(project, obs)[0]["id"] == obs
    assert show_record(project, hyp)[0]["status"] == "proposed"
    assert show_record(project, decision)[0]["based_on"] == [obs, hyp]
    with pytest.raises(ResearchFlowError, match="Broken evidence reference"):
        add_decision(project, "Unsupported", "Missing basis", ["EXP-9999"])

