"""Main orchestration script for the cutlist agentic workflow.

Demonstrates a Carpenter → compute → QA → Carpenter loop using ADK Runner.
Each agent gets its own Runner instance so we can drive the conversation
programmatically rather than relying on automatic sub-agent routing.

Usage:
    cd backend
    uv run python main.py                           # Interactive mode
    uv run python main.py -p "Design a chair"      # Non-interactive with prompt
"""

import argparse
import asyncio
import time
import math
from pathlib import Path
import logging

from dotenv import load_dotenv
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# Import the individual agents (not the root coordinator)
from cutlist_agent.sub_agents.carpenter_agent import carpenter_agent
from cutlist_agent.sub_agents.qa_agent import qa_agent
from code_utils import extract_code, validate_code_safety, sandbox_code_execution
from output_utils import _try_render_views, _try_export_stl, _try_render_assembly_gif, _try_export_code, setup_output_directories

import cadquery as cq

# Load .env (GOOGLE_API_KEY, etc.)
load_dotenv()


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cutlist")

CACHED_MODULES = {
    "cq": cq,
    "cadquery": cq,
    "math": math,
}

OUTPUT_PATH = Path("/Users/ryanslocum/Documents/current_courses/semesterProject/cutlist-web/_output")

CODE_ERROR_RETRY_LIMIT = 1

current_time = int(time.time())
APP_NAME = "cutlist_code"
USER_ID = "user_id"
CARPENTER_SESSION = f"carpenter_session_{current_time}"
QA_SESSION = f"qa_session_{current_time}"


async def call_agent(runner: Runner, session_id: str, message: str) -> str:
    """Send a message to an agent and collect the full text response.

    Args:
        runner: The ADK Runner bound to a specific agent.
        session_id: The session ID to use for this conversation.
        message: The user message to send.

    Returns:
        The agent's final text response.
    """
    content = types.Content(
        role="user",
        parts=[types.Part(text=message)],
    )

    final_response = ""
    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=session_id,
        new_message=content,
    ):
        if event.is_final_response():
            if event.content and event.content.parts:
                final_response = event.content.parts[0].text
    return final_response


async def carpenter_result_with_retries(prompt: str, carpenter_runner: Runner) -> cq.Workplane | None:
    cad_query_obj = None
    carpenter_response = None
    for i in range(CODE_ERROR_RETRY_LIMIT):
        logger.info(f"--- Carpenter Attempt {i+1} ---")
        logger.info(f"Prompt:\n{prompt}")
        carpenter_response = await call_agent(
            carpenter_runner, CARPENTER_SESSION, prompt
        )
        # --- Step 3: Deal with carpenter output ---
        logger.info(f"{'='*20} Carpenter: {'='*20}\n{carpenter_response}")

        extracted_code = extract_code(carpenter_response)
        if not extracted_code:
            logger.warning("--- Code Extraction Failed ---")
            logger.warning("No code block found in the response.")
            prompt = "I couldn't find any code in your response. Please provide the CadQuery code for the design in a markdown fenced code block (```python ... ```)."
            continue

        ## Validate code safety before executing
        code_is_safe, reason = validate_code_safety(extracted_code)
        if not code_is_safe:
            logger.warning("--- Code Safety Check Failed ---")
            logger.warning(f"Reason: {reason}")
            prompt = f"The code you provided failed safety checks:\n{reason}\nPlease fix the code to address these issues and provide an updated version."
            continue
        
        ## Execute the code, extract cadquery result
        result = sandbox_code_execution(extracted_code, CACHED_MODULES)
        if not result.success:
            logger.error("--- Code Execution Failed ---")
            logger.error(f"Error: {result.msg}")
            prompt = f"The code you provided has issues:\n{result.msg}\nPlease fix the code and provide an updated version."
            continue

        cad_query_obj = result.result
    
    if not cad_query_obj:
        logger.error(f"Failed to get a valid design after {CODE_ERROR_RETRY_LIMIT} attempts.")

    return cad_query_obj, extracted_code

async def main(user_prompt = None):
    """Run the Carpenter → compute → QA → Carpenter orchestration loop."""

    # Shared session service (in-memory for now)
    session_service = InMemorySessionService()

    # Create separate sessions for each agent
    await session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=CARPENTER_SESSION
    )
    await session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=QA_SESSION
    )

    # Create runners — each targets a specific agent
    carpenter_runner = Runner(
        agent=carpenter_agent,
        app_name=APP_NAME,
        session_service=session_service,
    )
    qa_runner = Runner(
        agent=qa_agent,
        app_name=APP_NAME,
        session_service=session_service,
    )
    logger.info("=" * 20 + "  Cutlist Carpenter — Agentic Workflow Demo" + "=" * 20)
    
    
    # Get prompt from args or interactive input
    if not user_prompt:
        user_prompt = input("\nDescribe your woodworking project:\n> ")


    # --- Step 2: Send to Carpenter agent ---
    cad_query_obj, result_code = await carpenter_result_with_retries(user_prompt, carpenter_runner)

    if not cad_query_obj:
        return
    
    # --- Step 3: Process Carpenter output ---

    logger.info(f"Rendered Views: {_try_render_views(cad_query_obj, CARPENTER_SESSION, OUTPUT_PATH)}")
    logger.info(f"Exported STL: {_try_export_stl(cad_query_obj, CARPENTER_SESSION, OUTPUT_PATH)}")
    logger.info(f"Rendered GIF: {_try_render_assembly_gif(cad_query_obj, CARPENTER_SESSION, OUTPUT_PATH)}")
    logger.info(f"Exported Code: {_try_export_code(result_code, CARPENTER_SESSION, OUTPUT_PATH)}")

    return

    # --- Step 4: Send computed result to QA agent ---
    # print("\n--- QA Agent ---")
    # qa_message = (
    #     f"Please review this design.\n\n"
    #     f"User's original request: {user_prompt}\n\n"
    #     f"{computed_result}"
    # )
    # qa_response = await call_agent(qa_runner, QA_SESSION, qa_message)
    # print(f"\nQA:\n{qa_response}")

    # # --- Step 5: Send QA feedback back to Carpenter ---
    # print("\n--- Carpenter Agent (revision) ---")
    # revision_message = (
    #     f"The QA reviewer provided the following feedback on your design. "
    #     f"Please address their concerns and provide an updated design.\n\n"
    #     f"QA Feedback:\n{qa_response}"
    # )
    # carpenter_revision = await call_agent(
    #     carpenter_runner, CARPENTER_SESSION, revision_message
    # )
    # print(f"\nCarpenter (revised):\n{carpenter_revision}")

    # print("\n" + "=" * 60)
    # print("  Workflow complete!")
    # print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cutlist Carpenter agentic workflow")
    parser.add_argument(
        "-p", "--prompt",
        type=str,
        default=None,
        help="Design prompt (if not provided, prompts interactively)"
    )
    args = parser.parse_args()
    user_prompt = args.prompt

    ## Output setup: create output directories if they don't exist
    setup_output_directories(OUTPUT_PATH)

    # Run the main loop
    asyncio.run(main(user_prompt=user_prompt))