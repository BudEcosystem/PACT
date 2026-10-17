"""02P M6: a decision model is a model: its id is carried."""

from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

agent = Agent(TestModel(model_name="router"), name="desk", description="Answers order questions.", instructions="Answer briefly.")
