from app.skills.router import SkillName, heuristic_route


def test_heuristic_routing() -> None:
    assert heuristic_route("Write a Ship30for30 post about retention") is SkillName.SHIP30
    assert heuristic_route("Create an HTML landing page") is SkillName.ARTIFACT
    assert heuristic_route("How do teams measure activation?") is SkillName.QA
