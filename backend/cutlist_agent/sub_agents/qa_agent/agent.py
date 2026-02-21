"""QA sub-agent definition."""

from google.adk.agents import Agent

from .prompt import QA_INSTRUCTION
from .tools import validate_design

qa_agent = Agent(
    model="gemini-2.5-flash",
    name="qa_agent",
    description="Reviews and validates CadQuery woodworking designs for correctness and quality.",
    instruction=QA_INSTRUCTION,
    # tools=[validate_design],
)
