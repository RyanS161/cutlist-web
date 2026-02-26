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
import json
import time
import math
from pathlib import Path
import os
from typing import Optional

from dotenv import load_dotenv
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
import cadquery

# Import the individual agents (not the root coordinator)
from cutlist_agent.sub_agents.carpenter_agent import carpenter_agent
from cutlist_agent.sub_agents.qa_agent import qa_agent
from code_utils import extract_code, validate_code_safety, sandbox_code_execution
from output_utils import save_output_files
from test_suite import run_test_suite
from sim_env import setup_sim_environment, shutdown_sim_environment, wait_for_sim_ready

from logger import make_logger_child, RunMetrics

# Load .env (GOOGLE_API_KEY, etc.)
load_dotenv()

logger = make_logger_child("main")
parser = argparse.ArgumentParser(description="Cutlist Carpenter agentic workflow")
parser.add_argument(
    "-p", "--prompt",
    type=str,
    default=None,
    help="Design prompt (if not provided, prompts interactively)"
)
parser.add_argument(
    "-m", "--method",
    type=str,
    default="carpenter_only",
    choices=["carpenter_only", "carpenter_qa_loop"],
    help="Which workflow method to run"
)
parser.add_argument(
    "--sim",
    action="store_true",
    help="Use the simulation environment test in the test suite (requires sim server to be running)"
)
args = parser.parse_args()
USER_PROMPT = args.prompt
METHOD = args.method
USE_SIM = args.sim

CACHED_MODULES = {
    "cq": cadquery,
    "cadquery": cadquery,
    "math": math,
}

OUTPUT_PATH = Path(os.environ.get("OUTPUT_PATH"))
if not OUTPUT_PATH:
    logger.warning("OUTPUT_PATH not set in environment variables. Using current directory.")
    OUTPUT_PATH = Path.cwd()

CODE_ERROR_RETRY_LIMIT = 2
MAX_QA_ITERATIONS = 3

SESSION_ID = int(time.time())
APP_NAME = "cutlist_code"
USER_ID = "user_id"
CARPENTER_SESSION = f"carpenter_session_{SESSION_ID}"
QA_SESSION = f"qa_session_{SESSION_ID}"


def _count_parts(cad_query_obj) -> int:
    """Count the number of named parts in a CadQuery object."""
    if hasattr(cad_query_obj, 'objects') and isinstance(cad_query_obj.objects, dict):
        return len(cad_query_obj.objects)
    if hasattr(cad_query_obj, 'vals') and callable(cad_query_obj.vals):
        try:
            return len(cad_query_obj.vals())
        except Exception:
            pass
    return 1


async def setup_runner(session_service, session_id, agent):
    """Set up separate sessions and runners for each agent."""
    # Create separate sessions for each agent
    await session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=session_id
    )
    return Runner(
        agent=agent,
        app_name=APP_NAME,
        session_service=session_service,
    )


async def call_agent_with_content(runner: Runner, session_id: str, content,
                                  metrics: Optional[RunMetrics] = None,
                                  agent_role: Optional[str] = None) -> str:
    """Send a message to an agent and collect the full text response.

    Args:
        runner: The ADK Runner bound to a specific agent.
        session_id: The session ID to use for this conversation.
        content: The Content object to send.
        metrics: Optional RunMetrics object to record inference time.
        agent_role: 'carpenter' or 'qa' to route timing to the correct counter.

    Returns:
        The agent's final text response (all text parts concatenated).
    """
    final_response = ""
    t0 = time.perf_counter()
    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=session_id,
        new_message=content,
    ):
        if event.is_final_response():
            if event.content and event.content.parts:
                # Concatenate all text parts in the response
                text_parts = []
                for part in event.content.parts:
                    if hasattr(part, 'text') and part.text:
                        text_parts.append(part.text)
                final_response = "\n".join(text_parts)
    elapsed = time.perf_counter() - t0
    if metrics is not None:
        if agent_role == "carpenter":
            metrics.carpenter_inference_time_s += elapsed
        elif agent_role == "qa":
            metrics.qa_inference_time_s += elapsed
    return final_response

async def call_agent(runner: Runner, session_id: str, message: str,
                     metrics: Optional[RunMetrics] = None,
                     agent_role: Optional[str] = None) -> str:
    """Helper to send a text message and get a text response."""
    content = types.Content(
        role="user",
        parts=[types.Part(text=message)],
    )
    return await call_agent_with_content(runner, session_id, content, metrics=metrics, agent_role=agent_role)

async def dump_agent_context(session_service, session_id):
        ## Dump context here for debugging
    session = await session_service.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=session_id
    )
    if session and session.events:
        debug_path = OUTPUT_PATH / f"{SESSION_ID}" / f"{session_id}_context.json"
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        
        debug_data = []
        for event in session.events:
            event_data = {
                "author": event.author if hasattr(event, 'author') else None,
                "timestamp": str(event.timestamp) if hasattr(event, 'timestamp') else None,
            }
            if hasattr(event, 'content') and event.content:
                parts_data = []
                for part in event.content.parts:
                    part_info = {}
                    if hasattr(part, 'text') and part.text:
                        part_info['text'] = part.text
                    if hasattr(part, 'function_call') and part.function_call:
                        part_info['function_call'] = str(part.function_call)
                    if hasattr(part, 'function_response') and part.function_response:
                        part_info['function_response'] = str(part.function_response)
                    parts_data.append(part_info)
                event_data['parts'] = parts_data
            debug_data.append(event_data)
        
        with open(debug_path, 'w') as f:
            json.dump(debug_data, f, indent=2)
        logger.info(f"Dumped session context to {debug_path}")


async def generate_carpenter_result_with_retries(prompt: str,
                                                 carpenter_runner: Runner,
                                                 iteration: Optional[int] = None,
                                                 retries: int = CODE_ERROR_RETRY_LIMIT,
                                                 metrics: Optional[RunMetrics] = None) -> cadquery.Workplane | None:
    cad_query_obj = None
    carpenter_response = None
    for i in range(retries):
        logger.info(f"--- Carpenter Attempt {i+1} ---")
        logger.info(f"Prompt:\n{prompt}")
        carpenter_response = await call_agent(
            carpenter_runner, CARPENTER_SESSION, prompt, metrics=metrics, agent_role="carpenter"
        )
        # --- Step 3: Deal with carpenter output ---
        logger.info(f"{'='*20} Carpenter: {'='*20}\n{carpenter_response}")

        extracted_code = extract_code(carpenter_response)
        if not extracted_code:
            logger.warning("--- Code Extraction Failed ---")
            logger.warning("No code block found in the response.")
            if metrics is not None:
                metrics.carpenter_code_failures += 1
            prompt = "I couldn't find any code in your response. Please provide the CadQuery code for the design in a markdown fenced code block (```python ... ```)."
            continue

        ## Validate code safety before executing
        code_is_safe, reason = validate_code_safety(extracted_code)
        if not code_is_safe:
            logger.warning("--- Code Safety Check Failed ---")
            logger.warning(f"Reason: {reason}")
            if metrics is not None:
                metrics.carpenter_code_failures += 1
            prompt = f"The code you provided failed safety checks:\n{reason}\nPlease fix the code to address these issues and provide an updated version."
            continue
        
        ## Execute the code, extract cadquery result
        result = sandbox_code_execution(extracted_code, CACHED_MODULES)
        if not result.success:
            logger.error("--- Code Execution Failed ---")
            logger.error(f"Error: {result.msg}")
            if metrics is not None:
                metrics.carpenter_code_failures += 1
            prompt = f"The code you provided has issues:\n{result.msg}\nPlease fix the code and provide an updated version."
            continue
        else:
            cad_query_obj = result.result
            break # If we got here, we have a valid design and can exit the retry loop
    
    if not cad_query_obj:
        logger.error(f"Failed to get a valid design after {retries} attempts.")
        return None, carpenter_response
    else:
        # Export output files first so parts.json exists for the sim test
        iter_dir = save_output_files(OUTPUT_PATH,
                                    SESSION_ID,
                                    iteration=iteration,
                                    cad_query_obj=cad_query_obj,
                                    code=extracted_code)

        if USE_SIM:
            parts_json_path = str(iter_dir / "parts.json")
        else: 
            parts_json_path = None

        test_result = run_test_suite(cad_query_obj, parts_json_path=parts_json_path)

        # Save the test results alongside the other outputs
        save_output_files(OUTPUT_PATH,
                        SESSION_ID,
                        iteration=iteration,
                        test_result_obj=test_result)

    return cad_query_obj, extracted_code


async def QA_agent_response(qa_runner: Runner, qa_session_id: str, iteration: int, user_prompt: str,
                             metrics: Optional[RunMetrics] = None) -> str:
    """Send design artifacts to the QA agent for review.
    
    Loads the views.png and test_results.json from the iteration folder
    and sends them along with the user's original prompt to the QA agent.
    """
    # Build path to iteration folder
    iteration_path = OUTPUT_PATH / f"{SESSION_ID}" / f"iteration_{iteration}"
    views_path = iteration_path / "views.png"
    test_results_path = iteration_path / "test_results.json"
    
    # Load the views image
    parts = []
    
    if views_path.exists():
        with open(views_path, "rb") as f:
            image_data = f.read()
        parts.append(types.Part.from_bytes(data=image_data, mime_type="image/png"))
        logger.info(f"Loaded views image from {views_path}")
    else:
        logger.warning(f"Views image not found at {views_path}")
    
    # Load test results
    test_results_text = ""
    if test_results_path.exists():
        with open(test_results_path, "r") as f:
            test_results = json.load(f)
        test_results_text = f"Test Results:\n{json.dumps(test_results, indent=2)}"
        logger.info(f"Loaded test results from {test_results_path}")
    else:
        logger.warning(f"Test results not found at {test_results_path}")
        test_results_text = "Test Results: Not available"
    
    # Build the text prompt
    qa_text = (
        f"Iteration {iteration} Design Review\n"
        f"User's original request: {user_prompt}\n\n"
        f"{test_results_text}\n\n"
        f"Please review the design and image and provide your feedback."
    )
    parts.append(types.Part.from_text(text=qa_text))
    
    # Create content with image and text
    content = types.Content(role="user", parts=parts)
    
    # Send to QA agent
    if metrics is not None:
        metrics.qa_calls += 1
    final_response = await call_agent_with_content(qa_runner, qa_session_id, content, metrics=metrics, agent_role="qa")
    return final_response



def save_run_metrics(metrics: RunMetrics):
    """Save run metrics to a JSON file in the session output directory."""
    metrics_path = OUTPUT_PATH / f"{SESSION_ID}" / "run_metrics.json"
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    with open(metrics_path, 'w') as f:
        json.dump(metrics.to_dict(), f, indent=2)
    logger.info(f"Saved run metrics to {metrics_path}")


async def carpenter_only(user_prompt):
    """Run only the carpenter agent without QA review."""
    metrics = RunMetrics(
        carpenter_model=carpenter_agent.model,
        qa_model="N/A",
    )
    session_service = InMemorySessionService()

    carpenter_runner = await setup_runner(session_service, CARPENTER_SESSION, carpenter_agent)

    cad_query_obj, result_code = await generate_carpenter_result_with_retries(user_prompt, carpenter_runner, metrics=metrics)

    if cad_query_obj:
        metrics.num_parts_final = _count_parts(cad_query_obj)
    save_run_metrics(metrics)
    await dump_agent_context(session_service, CARPENTER_SESSION)



async def carpenter_qa_loop(user_prompt = None, max_iterations=MAX_QA_ITERATIONS):
    metrics = RunMetrics(
        carpenter_model=carpenter_agent.model,
        qa_model=qa_agent.model,
    )
    session_service = InMemorySessionService()

    carpenter_runner = await setup_runner(session_service, CARPENTER_SESSION, carpenter_agent)
    qa_runner = await setup_runner(session_service, QA_SESSION, qa_agent)

    # --- Initial carpenter response
    cad_query_obj, result_code = await generate_carpenter_result_with_retries(user_prompt, carpenter_runner, iteration=0, metrics=metrics)

    for iteration in range(max_iterations):
        logger.info(f"\n\n{'#' * 10} QA Iteration {iteration} {'#' * 10}\n\n")

        qa_response = await QA_agent_response(qa_runner, QA_SESSION, iteration, user_prompt, metrics=metrics)

        if "QA_PASSED" in qa_response:
            logger.info("QA agent approved the design. Ending loop.")
            break

        refinement_prompt = (
            f"The QA agent has reviewed your design and provided the following feedback:\n\n"
            f"{qa_response}\n\n"
            f"Please revise your design to address the QA's feedback and provide updated CadQuery code"
        )

        cad_query_obj, result_code = await generate_carpenter_result_with_retries(refinement_prompt, carpenter_runner, iteration=iteration + 1, metrics=metrics)

    if cad_query_obj:
        metrics.num_parts_final = _count_parts(cad_query_obj)
    save_run_metrics(metrics)
    await dump_agent_context(session_service, CARPENTER_SESSION)
    await dump_agent_context(session_service, QA_SESSION)


if __name__ == "__main__":
    logger.info("=" * 20 + "  Cutlist Carpenter — Agentic Workflow Demo" + "=" * 20)
    # Get prompt from args or interactive input
    if not USER_PROMPT:
        USER_PROMPT = input("\nDescribe your woodworking project:\n> ")

    if USE_SIM:
        start_config = {
                        "num_envs": 1,
                        "task": "Template-Pose-Orientation-Two-Robots-Direct-v0"
                        }
        setup_sim_environment(config=start_config)
        # # Wait until /start has actually finished to avoid queuing /test too early.
        if not wait_for_sim_ready(timeout_s=60.0, poll_interval_s=0.5):
            logger.warning("Simulation server did not become ready within 90s")
        else:
            logger.info("Simulation server is ready.")

    # Run the main loop
    if METHOD == "carpenter_only":
        asyncio.run(carpenter_only(USER_PROMPT))
    elif METHOD == "carpenter_qa_loop":
        asyncio.run(carpenter_qa_loop(USER_PROMPT))
    else:
        logger.error(f"Unknown method: {METHOD}")

    if USE_SIM:
        # Shut down the sim environment after the run
        shutdown_sim_environment()