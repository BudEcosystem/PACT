"""02P A7: a validation context is named, since PACT checks arguments and answers itself."""

from pydantic_ai import Agent
agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", validation_context={"strict": True})
