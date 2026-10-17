"""02P M4: a fallback model's own test for falling back has no public read, and the import says so."""

from pydantic_ai import Agent
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.test import TestModel

agent = Agent(FallbackModel(TestModel(model_name="a"), TestModel(model_name="b"), fallback_on=lambda exc: True), name="desk", description="Answers order questions.", instructions="Answer briefly.")
