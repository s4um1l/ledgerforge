from factory.schemas import Plan
from factory.trace import FILES, Trace


def test_trace_round_trips_a_model(tmp_path):
    trace = Trace("RUN-1", root=tmp_path)
    plan = Plan(
        understanding="u",
        root_cause_hypothesis="r",
        files_to_modify=["a.py"],
        steps=["s"],
        smallest_change_rationale="because",
    )
    trace.write_model("plan.json", plan)
    assert trace.read_json("plan.json")["steps"] == ["s"]


def test_missing_reports_what_a_complete_trace_still_needs(tmp_path):
    trace = Trace("RUN-2", root=tmp_path)
    assert trace.present() == []
    assert set(trace.missing()) == set(FILES)

    trace.write_text("diff.patch", "diff --git a/x b/x\n")
    assert trace.present() == ["diff.patch"]
    assert "diff.patch" not in trace.missing()


def test_the_nine_documented_artefacts_are_the_contract():
    assert FILES == (
        "task.yaml",
        "context.json",
        "plan.json",
        "builder.json",
        "diff.patch",
        "validation.json",
        "review.json",
        "result.json",
        "metadata.json",
    )
