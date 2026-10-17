"""02P K4: the harness's dynamic workflow is named, with the PACT line to write."""

from pydantic_ai import Agent
from pydantic_ai_harness.dynamic_workflow import DynamicWorkflow

agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", capabilities=[DynamicWorkflow(agents=[Agent(name="helper", description="Looks things up.")])])
