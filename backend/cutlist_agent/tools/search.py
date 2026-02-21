"""Agentic search tool — a lightweight Agent wrapped as a tool via AgentTool.

Other agents can invoke this tool to search for woodworking techniques,
standard dimensions, joinery methods, etc.
"""

from google.adk.agents import Agent
from google.adk.tools.agent_tool import AgentTool


def web_search(query: str) -> dict:
    """Search the web for woodworking and design information.

    Searches for woodworking techniques, standard lumber dimensions,
    joinery methods, furniture design references, and CadQuery documentation.

    Args:
        query: The search query string.

    Returns:
        dict: A dictionary with 'status' and 'results' keys.
    """
    # TODO: Replace with real search implementation (e.g., Google Search API, SerpAPI)
    return {
        "status": "success",
        "results": [
            {
                "title": f"Search result for: {query}",
                "snippet": "This is a placeholder search result. Replace with real search integration.",
                "url": "https://example.com",
            }
        ],
    }


# Define a lightweight search agent
_search_agent = Agent(
    model="gemini-2.5-flash",
    name="search_agent",
    description="Searches the web for woodworking and CadQuery information.",
    instruction=(
        "You are a search assistant. Use the web_search tool to find relevant "
        "information and return a concise summary of the results."
    ),
    tools=[web_search],
)

# Wrap as an AgentTool so other agents can invoke it
search_tool = AgentTool(agent=_search_agent)
