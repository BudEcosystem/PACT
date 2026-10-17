"""02P H9: the harness's trajectory judge is named, with the PACT line to write."""

from pydantic_ai import Agent
from pydantic_ai_harness.trajectory_judge import TrajectoryJudge

agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", capabilities=[TrajectoryJudge(model="test")])
