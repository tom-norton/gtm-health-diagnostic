from advisor.tools import PLAYS, STAGE_ORDER, execute_tool, recommend_play


def test_every_stage_except_commit_has_a_play():
    for stage in STAGE_ORDER:
        if stage == "Commit":
            assert stage not in PLAYS
        else:
            assert stage in PLAYS, f"{stage} is missing a canonical play"


def test_recommend_play_commit_has_no_play_and_says_why():
    result = recommend_play("Commit")
    assert result["play"] is None
    assert "pinch point" in result["note"]


def test_recommend_play_returns_a_caveat_for_a_real_stage():
    result = recommend_play("Renewal")
    assert result["play"]
    assert "caveat" in result


def test_execute_tool_dispatches_recommend_play(real_data):
    _, deal = real_data
    result = execute_tool("recommend_play", {"leak_stage": "Adoption"}, deal, None)
    assert result["leak_stage"] == "Adoption"
    assert result["play"]


def test_execute_tool_dispatches_get_stage_health(real_data):
    agg, deal = real_data
    result = execute_tool("get_stage_health", {"stage": "Onboarding"}, deal, agg)
    assert result["stage"] == "Onboarding"
    assert result["volume_entering"] > 0


def test_execute_tool_unknown_name_returns_error(real_data):
    agg, deal = real_data
    result = execute_tool("not_a_real_tool", {}, deal, agg)
    assert "error" in result
