"""Carpenter sub-agent definition."""

from google.adk.agents import Agent

from .prompt import CARPENTER_INSTRUCTION
from part_library import generate_part_table

system_prompt = CARPENTER_INSTRUCTION.format(part_table=generate_part_table())

carpenter_agent = Agent(
    model="gemini-2.5-flash",
    name="carpenter_agent",
    description="Designs woodworking projects and generates CadQuery code from user descriptions.",
    instruction=system_prompt,
    # tools=[generate_code],
)
