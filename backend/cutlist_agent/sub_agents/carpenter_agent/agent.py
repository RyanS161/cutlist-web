"""Carpenter sub-agent definition."""

from google.adk.agents import Agent

from .prompt import CARPENTER_INSTRUCTION

carpenter_agent = Agent(
    model="gemini-2.5-pro",
    name="carpenter_agent",
    description="Designs woodworking projects and generates CadQuery code from user descriptions.",
    instruction=CARPENTER_INSTRUCTION,
    # tools=[generate_code],
)
