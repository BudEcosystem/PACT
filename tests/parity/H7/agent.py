"""02P H7: the harness's ask-the-user is named, with the PACT line to write."""

from pydantic_ai import Agent
from pydantic_ai_harness.ask_user import AskUser

agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", capabilities=[AskUser(answerer=None)])
