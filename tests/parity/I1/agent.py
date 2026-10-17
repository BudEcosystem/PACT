"""02P I1: instrumentation is named: the host decides where spans go."""

from pydantic_ai import Agent
agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", )
agent.instrument = True
