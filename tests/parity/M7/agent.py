"""02P M7: a wrapper around a model is named, and the model inside is carried."""

from pydantic_ai import Agent
from pydantic_ai.models.instrumented import InstrumentedModel
from pydantic_ai.models.test import TestModel

agent = Agent(InstrumentedModel(TestModel()), name="desk", description="Answers order questions.", instructions="Answer briefly.")
