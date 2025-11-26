"""Test service for validating CadQuery designs against constraints."""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum

try:
    from OCP.BRepBndLib import BRepBndLib
    from OCP.Bnd import Bnd_OBB
    HAS_OCP = True
except ImportError:
    HAS_OCP = False

logger = logging.getLogger(__name__)


class TestStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class TestResult:
    """Result of a single test."""
    name: str
    status: TestStatus
    message: str
    details: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result['status'] = self.status.value
        return result


@dataclass
class TestSuiteResult:
    """Result of running the full test suite."""
    passed: int
    failed: int
    skipped: int
    errors: int
    tests: List[TestResult]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'passed': self.passed,
            'failed': self.failed,
            'skipped': self.skipped,
            'errors': self.errors,
            'tests': [t.to_dict() for t in self.tests],
            'success': self.failed == 0 and self.errors == 0,
        }


# Design constraints from system prompt
CONSTRAINTS = {
    # Beam dimensions (width x height)
    'beam_28x28': {
        'width': 28,
        'height': 28,
        'min_length': 100,
        'max_length': 500,
        'length_increment': 50,
    },
    'beam_48x24': {
        'width': 48,
        'height': 24,
        'min_length': 100,
        'max_length': 500,
        'length_increment': 50,
    },
    'plywood': {
        'thickness': 7,
        'max_width': 500,
        'max_height': 500,
    },
    'screw_max_length': 25,
}


def _get_oriented_dims(shape) -> Optional[List[float]]:
    """
    Calculates the dimensions (L, W, H) of the tightest-fitting
    oriented bounding box around a shape.
    
    Works for:
    - Arbitrarily rotated parts
    - Parts with holes, cutouts, or chamfers
    - Plywood sheets, beams, etc.
    
    Returns sorted dimensions [smallest, middle, largest] or None on error.
    """
    if not HAS_OCP:
        logger.warning("OCP not available, falling back to axis-aligned bounding box")
        return _get_axis_aligned_dims(shape)
    
    try:
        # Initialize the OpenCascade Oriented Bounding Box calculator
        obb = Bnd_OBB()
        
        # Get the underlying TopoDS_Shape
        if hasattr(shape, 'val') and callable(shape.val):
            # It's a Workplane
            topo_shape = shape.val().wrapped
        elif hasattr(shape, 'wrapped'):
            # It's a Shape (Solid, Compound, etc.)
            topo_shape = shape.wrapped
        else:
            logger.warning(f"Unknown shape type for OBB: {type(shape)}")
            return _get_axis_aligned_dims(shape)
        
        # Calculate the oriented bounding box
        # Args: shape, obb, isTriangulation, isOptimal, isShapeToleranceUsed
        BRepBndLib.AddOBB_s(topo_shape, obb, False, True, False)
        
        # Extract dimensions (OBB stores half-lengths)
        x_len = obb.XHSize() * 2
        y_len = obb.YHSize() * 2
        z_len = obb.ZHSize() * 2
        
        # Return sorted dimensions
        return sorted([round(x_len, 2), round(y_len, 2), round(z_len, 2)])
        
    except Exception as e:
        logger.warning(f"Failed to get oriented bounding box: {e}")
        return _get_axis_aligned_dims(shape)


def _get_axis_aligned_dims(solid) -> Optional[List[float]]:
    """Fallback: Get axis-aligned bounding box dimensions of a solid."""
    try:
        bb = solid.BoundingBox()
        dims = [round(bb.xlen, 2), round(bb.ylen, 2), round(bb.zlen, 2)]
        return sorted(dims)
    except Exception as e:
        logger.warning(f"Failed to get bounding box: {e}")
        return None


def _classify_part(sorted_dims: List[float]) -> Dict[str, Any]:
    """Classify a part based on its sorted dimensions [smallest, middle, largest]."""
    
    # Check for 28x28 beam
    if _is_beam_28x28(sorted_dims):
        return {
            'type': 'beam_28x28',
            'cross_section': (28, 28),
            'length': sorted_dims[2],
            'valid_length': _is_valid_beam_length(sorted_dims[2]),
        }
    
    # Check for 48x24 beam
    if _is_beam_48x24(sorted_dims):
        return {
            'type': 'beam_48x24',
            'cross_section': (48, 24),
            'length': sorted_dims[2],
            'valid_length': _is_valid_beam_length(sorted_dims[2]),
        }
    
    # Check for plywood (7mm thick)
    if _is_plywood(sorted_dims):
        return {
            'type': 'plywood',
            'thickness': sorted_dims[0],
            'width': sorted_dims[1],
            'height': sorted_dims[2],
            'valid_size': sorted_dims[1] <= 500 and sorted_dims[2] <= 500,
        }
    
    return {
        'type': 'unknown',
        'dimensions': sorted_dims,
    }


def _is_beam_28x28(sorted_dims: List[float], tolerance: float = 1.0) -> bool:
    """Check if dimensions match a 28x28 beam."""
    return (abs(sorted_dims[0] - 28) <= tolerance and 
            abs(sorted_dims[1] - 28) <= tolerance)


def _is_beam_48x24(sorted_dims: List[float], tolerance: float = 1.0) -> bool:
    """Check if dimensions match a 48x24 beam."""
    return ((abs(sorted_dims[0] - 24) <= tolerance and abs(sorted_dims[1] - 48) <= tolerance) or
            (abs(sorted_dims[0] - 48) <= tolerance and abs(sorted_dims[1] - 24) <= tolerance))


def _is_plywood(sorted_dims: List[float], tolerance: float = 0.5) -> bool:
    """Check if dimensions match plywood (7mm thick)."""
    return abs(sorted_dims[0] - 7) <= tolerance


def _is_valid_beam_length(length: float, tolerance: float = 1.0) -> bool:
    """Check if beam length is valid (100-500mm in 50mm increments)."""
    if length < 100 - tolerance or length > 500 + tolerance:
        return False
    # Check if it's a multiple of 50 within tolerance
    remainder = (length - 100) % 50
    return remainder <= tolerance or remainder >= 50 - tolerance


def _extract_solids(result) -> List[Any]:
    """Extract individual solids from a CadQuery result.
    
    Handles various CadQuery types:
    - Assembly: iterate through children and extract each part's solid
    - Workplane: use .vals() to get all objects, then extract solids from each
    - Compound: call .Solids() directly
    - Individual Solid: return as single-item list
    """
    solids = []
    
    try:
        # Log the type for debugging
        logger.info(f"Extracting solids from type: {type(result).__name__}")
        logger.debug(f"Result attributes: {[a for a in dir(result) if not a.startswith('_')][:20]}")
        
        # Case 1: Assembly object - detect by checking for 'children' dict attribute
        # CadQuery Assembly has: obj, name, loc, color, children (dict), objects (list)
        if hasattr(result, 'children') and isinstance(getattr(result, 'children', None), dict):
            # This is an Assembly - iterate through all parts
            children_count = len(result.children) if result.children else 0
            logger.info(f"Processing Assembly with {children_count} children")
            
            def extract_from_assembly(asm, depth=0):
                """Recursively extract solids from an assembly."""
                extracted = []
                indent = "  " * depth
                
                # Get the object at this assembly level (if any)
                obj = getattr(asm, 'obj', None)
                if obj is not None:
                    logger.debug(f"{indent}Assembly node has obj of type: {type(obj).__name__}")
                    
                    # If it's a Workplane, get the solid from it
                    if hasattr(obj, 'val') and callable(obj.val):
                        try:
                            val = obj.val()
                            logger.debug(f"{indent}Workplane.val() returned type: {type(val).__name__}")
                            if hasattr(val, 'Solids') and callable(val.Solids):
                                val_solids = val.Solids()
                                if val_solids:
                                    logger.debug(f"{indent}Found {len(val_solids)} solids in workplane")
                                    extracted.extend(val_solids)
                                else:
                                    extracted.append(val)
                            elif hasattr(val, 'BoundingBox'):
                                extracted.append(val)
                        except Exception as e:
                            logger.warning(f"{indent}Failed to extract solid from workplane: {e}")
                    elif hasattr(obj, 'Solids') and callable(obj.Solids):
                        obj_solids = obj.Solids()
                        if obj_solids:
                            logger.debug(f"{indent}Found {len(obj_solids)} solids directly")
                            extracted.extend(obj_solids)
                        else:
                            extracted.append(obj)
                    elif hasattr(obj, 'BoundingBox'):
                        extracted.append(obj)
                else:
                    logger.debug(f"{indent}Assembly node has no obj (root assembly)")
                
                # Recurse into children
                children = getattr(asm, 'children', {})
                if children:
                    logger.debug(f"{indent}Processing {len(children)} children")
                    for child_name, child_asm in children.items():
                        logger.debug(f"{indent}Processing child: {child_name}")
                        extracted.extend(extract_from_assembly(child_asm, depth + 1))
                
                return extracted
            
            solids = extract_from_assembly(result)
            logger.info(f"Extracted {len(solids)} solids from Assembly tree traversal")
            
            # Fallback: if we didn't find any solids via tree traversal, use toCompound()
            if not solids and hasattr(result, 'toCompound'):
                logger.info("No solids found via tree traversal, trying toCompound() fallback")
                try:
                    compound = result.toCompound()
                    if hasattr(compound, 'Solids') and callable(compound.Solids):
                        solids = list(compound.Solids())
                        logger.info(f"Extracted {len(solids)} solids via toCompound() fallback")
                except Exception as e:
                    logger.warning(f"toCompound() fallback failed: {e}")
            
        # Case 2: Workplane object (legacy support)
        elif hasattr(result, 'vals') and callable(result.vals):
            # Use .vals() to get ALL objects in the workplane, not just the last one
            vals = result.vals()
            logger.info(f"Workplane contains {len(vals)} objects")
            
            for val in vals:
                # Each val could be a Compound, Solid, or other shape
                if hasattr(val, 'Solids') and callable(val.Solids):
                    val_solids = val.Solids()
                    if val_solids:
                        solids.extend(val_solids)
                    else:
                        # It might be a single solid that doesn't contain sub-solids
                        solids.append(val)
                elif hasattr(val, 'wrapped'):
                    # It's a single shape
                    solids.append(val)
                    
            logger.info(f"Extracted {len(solids)} solids from Workplane")
            
        # Case 3: Assembly with toCompound (fallback)
        elif hasattr(result, 'toCompound') and callable(result.toCompound):
            compound = result.toCompound()
            if hasattr(compound, 'Solids') and callable(compound.Solids):
                solids.extend(compound.Solids())
            logger.info(f"Extracted {len(solids)} solids from Assembly.toCompound()")
            
        # Case 4: Compound or shape with Solids method
        elif hasattr(result, 'Solids') and callable(result.Solids):
            solids.extend(result.Solids())
            logger.info(f"Extracted {len(solids)} solids from Compound")
            
        # Case 5: Direct solid
        elif hasattr(result, 'BoundingBox'):
            solids.append(result)
            logger.info("Result appears to be a single solid")
            
        else:
            logger.warning(f"Unknown result type: {type(result)}, attributes: {dir(result)[:10]}...")
            
    except Exception as e:
        logger.warning(f"Failed to extract solids: {e}", exc_info=True)
    
    return solids


def test_code_executes(code: str, exec_globals: dict) -> TestResult:
    """Test 1: Check if the code executes without errors."""
    try:
        exec(code, exec_globals)
        
        # Check if result is defined
        if 'result' not in exec_globals:
            return TestResult(
                name="Code Execution",
                status=TestStatus.FAILED,
                message="Code executed but 'result' variable was not defined",
            )
        
        result = exec_globals['result']
        if result is None:
            return TestResult(
                name="Code Execution",
                status=TestStatus.FAILED,
                message="Code executed but 'result' is None",
            )
        
        return TestResult(
            name="Code Execution",
            status=TestStatus.PASSED,
            message="Code executed successfully and produced a result",
        )
        
    except SyntaxError as e:
        return TestResult(
            name="Code Execution",
            status=TestStatus.FAILED,
            message=f"Syntax error on line {e.lineno}: {e.msg}",
        )
    except Exception as e:
        return TestResult(
            name="Code Execution",
            status=TestStatus.ERROR,
            message=f"Runtime error: {str(e)}",
        )


def test_parts_in_library(result) -> TestResult:
    """Test 2: Check if all parts meet the design constraints."""
    solids = _extract_solids(result)
    
    if not solids:
        return TestResult(
            name="Parts in Library",
            status=TestStatus.SKIPPED,
            message="No individual parts found to analyze",
        )
    
    parts_info = []
    violations = []
    
    for i, solid in enumerate(solids):
        sorted_dims = _get_oriented_dims(solid)
        if sorted_dims is None:
            continue
            
        classification = _classify_part(sorted_dims)
        part_info = {
            'index': i + 1,
            'dimensions': sorted_dims,
            'classification': classification,
        }
        parts_info.append(part_info)
        
        # Check for violations
        if classification['type'] == 'beam_28x28':
            if not classification['valid_length']:
                violations.append(
                    f"Part {i+1}: 28x28 beam length {classification['length']:.1f}mm "
                    f"is not in valid range (100-500mm, 50mm increments)"
                )
        elif classification['type'] == 'beam_48x24':
            if not classification['valid_length']:
                violations.append(
                    f"Part {i+1}: 48x24 beam length {classification['length']:.1f}mm "
                    f"is not in valid range (100-500mm, 50mm increments)"
                )
        elif classification['type'] == 'plywood':
            if not classification['valid_size']:
                violations.append(
                    f"Part {i+1}: Plywood size {classification['width']:.1f}x{classification['height']:.1f}mm "
                    f"exceeds maximum 500x500mm"
                )
        elif classification['type'] == 'unknown':
            violations.append(
                f"Part {i+1}: Unrecognized part type with dimensions "
                f"{classification['dimensions'][0]:.1f}x{classification['dimensions'][1]:.1f}x{classification['dimensions'][2]:.1f}mm"
            )
    
    if violations:
        return TestResult(
            name="Parts in Library",
            status=TestStatus.FAILED,
            message=f"{len(violations)} part violation(s) found",
            details={
                'violations': violations,
                'parts_analyzed': len(parts_info),
                'parts': parts_info,
            }
        )
    
    # Summarize parts
    part_summary = {}
    for part in parts_info:
        ptype = part['classification']['type']
        part_summary[ptype] = part_summary.get(ptype, 0) + 1
    
    summary_str = ", ".join(f"{count} {ptype}" for ptype, count in part_summary.items())
    
    return TestResult(
        name="Parts in Library",
        status=TestStatus.PASSED,
        message=f"All {len(parts_info)} parts meet constraints ({summary_str})",
        details={
            'parts_analyzed': len(parts_info),
            'summary': part_summary,
            'parts': parts_info,
        }
    )


def run_test_suite(code: str, cached_modules: dict) -> TestSuiteResult:
    """Run the full test suite on the provided code."""
    tests: List[TestResult] = []
    
    # Create execution environment
    exec_globals = {
        "__builtins__": __builtins__,
        **cached_modules,
    }
    
    # Test 1: Code execution
    exec_result = test_code_executes(code, exec_globals)
    tests.append(exec_result)
    
    # Test 2: Part constraints (only if code executed successfully)
    if exec_result.status == TestStatus.PASSED:
        result = exec_globals.get('result')
        constraint_result = test_parts_in_library(result)
        tests.append(constraint_result)
    else:
        tests.append(TestResult(
            name="Parts in Library",
            status=TestStatus.SKIPPED,
            message="Skipped because code execution failed",
        ))
    
    # Count results
    passed = sum(1 for t in tests if t.status == TestStatus.PASSED)
    failed = sum(1 for t in tests if t.status == TestStatus.FAILED)
    skipped = sum(1 for t in tests if t.status == TestStatus.SKIPPED)
    errors = sum(1 for t in tests if t.status == TestStatus.ERROR)
    
    return TestSuiteResult(
        passed=passed,
        failed=failed,
        skipped=skipped,
        errors=errors,
        tests=tests,
    )
