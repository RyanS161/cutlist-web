"""Dummy generate_code tool for the Carpenter agent."""


def generate_code(description: str) -> dict:
    """Generate CadQuery Python code for a woodworking design.

    Takes a natural language description of a furniture piece or woodworking
    project and returns executable CadQuery Python code that models it.

    Args:
        description: A description of the woodworking design to generate code for.

    Returns:
        dict: A dictionary with 'status' and 'code' keys. Status is 'success'
              or 'error'. Code contains the generated CadQuery Python source.
    """
    # TODO: Replace with real CadQuery code generation logic
    placeholder_code = f"""\
import cadquery as cq

# Placeholder design for: {description}
result = (
    cq.Workplane("XY")
    .box(100, 50, 30)
)
"""
    return {
        "status": "success",
        "code": placeholder_code,
    }
