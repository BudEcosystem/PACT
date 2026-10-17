"""02P O3: a choice between answer shapes is named, not cut to one."""

from pydantic_ai import Agent
from pydantic import BaseModel


class Shipped(BaseModel):
    carrier: str


class Lost(BaseModel):
    claim: str


agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", output_type=[Shipped, Lost])
