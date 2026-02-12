import asyncio
from pathlib import Path

from friday.config import Settings
from friday.planner import Planner
from friday.policy import PolicyEngine
from friday.schemas import AssistantMode, PlanRequest


def _planner(tmp_path: Path) -> Planner:
    settings = Settings(
        db_path=tmp_path / "planner.db",
        allowed_apps={"notepad": "notepad.exe"},
    )
    return Planner(settings=settings, policy=PolicyEngine(settings))


def test_planner_extracts_open_app(tmp_path: Path) -> None:
    planner = _planner(tmp_path)
    plan = asyncio.run(
        planner.create_plan(PlanRequest(goal="open notepad", mode=AssistantMode.ACTION))
    )
    assert any(step.tool == "open_app" for step in plan.steps)


def test_planner_extracts_reminder(tmp_path: Path) -> None:
    planner = _planner(tmp_path)
    plan = asyncio.run(
        planner.create_plan(
            PlanRequest(
                goal="set reminder to drink water in 10 minutes",
                mode=AssistantMode.ACTION,
            )
        )
    )
    assert any(step.tool == "reminder" for step in plan.steps)


def test_planner_code_mode(tmp_path: Path) -> None:
    planner = _planner(tmp_path)
    plan = asyncio.run(
        planner.create_plan(
            PlanRequest(goal="generate python code for fibonacci", mode=AssistantMode.CODE)
        )
    )
    assert len(plan.steps) == 1
    assert plan.steps[0].tool == "code_agent"

