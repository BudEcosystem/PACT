"""02P O4: `NativeOutput` is `answers-with-mode: native-json-schema`."""

from pydantic_ai import Agent
from pydantic import BaseModel
from pydantic_ai import NativeOutput


class Status(BaseModel):
    status: str


agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", output_type=NativeOutput(Status))
