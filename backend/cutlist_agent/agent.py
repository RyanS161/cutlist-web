"""Root agent definition for ADK CLI compatibility.

Exports root_agent so that `adk run cutlist_agent` and `adk web` work.
The root_agent acts as a coordinator that routes to Carpenter or QA sub-agents.
For programmatic use, you can also import the sub-agents directly.
"""

from google.adk.agents import Agent

from .sub_agents.carpenter_agent import carpenter_agent
from .sub_agents.qa_agent import qa_agent
from .tools import search_tool

root_agent = Agent(
    model="gemini-2.5-pro",
    name="root_agent",
    description="Cutlist design coordinator that routes tasks to Carpenter and QA agents.",
    instruction=(
        "You are a coordinator for a woodworking design system. "
        "Route design requests to the carpenter_agent and review/validation "
        "requests to the qa_agent. You can also use the search tool directly "
        "to look up information."
    ),
    sub_agents=[carpenter_agent, qa_agent],
    tools=[search_tool],
)
