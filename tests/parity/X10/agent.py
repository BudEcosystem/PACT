"""02P X10: the harness's capability creation is named: PACT's `learning:` only proposes."""

from pydantic_ai import Agent
from pathlib import Path

from pydantic_ai_harness.capability_creation import CapabilityCreation

agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", capabilities=[CapabilityCreation(Path("capabilities"))])
