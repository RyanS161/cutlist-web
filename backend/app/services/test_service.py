"""Test service for validating CadQuery designs against constraints."""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum

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


def _get_bounding_box(solid) -> Optional[Dict[str, float]]:
    """Get the bounding box dimensions of a solid."""
    try:
        bb = solid.BoundingBox()
        return {
            'x': round(bb.xlen, 2),
            'y': round(bb.ylen, 2),
            'z': round(bb.zlen, 2),
            'xmin': round(bb.xmin, 2),
            'xmax': round(bb.xmax, 2),
            'ymin': round(bb.ymin, 2),
            'ymax': round(bb.ymax, 2),
            'zmin': round(bb.zmin, 2),
            'zmax': round(bb.zmax, 2),
        }
    except Exception as e:
        logger.warning(f"Failed to get bounding box: {e}")
        return None


def _classify_part(dims: Dict[str, float]) -> Dict[str, Any]:
    """Classify a part based on its dimensions."""
    x, y, z = dims['x'], dims['y'], dims['z']
    sorted_dims = sorted([x, y, z])
    
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
    """Extract individual solids from a CadQuery result."""
    solids = []
    
    try:
        # If it's a Workplane with val()
        if hasattr(result, 'val') and callable(result.val):
            val = result.val()
            if hasattr(val, 'Solids'):
                solids.extend(val.Solids())
            else:
                solids.append(val)
        # If it's a Compound
        elif hasattr(result, 'Solids'):
            solids.extend(result.Solids())
        # If it's an Assembly
        elif hasattr(result, 'toCompound'):
            compound = result.toCompound()
            if hasattr(compound, 'Solids'):
                solids.extend(compound.Solids())
    except Exception as e:
        logger.warning(f"Failed to extract solids: {e}")
    
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


def test_part_constraints(result) -> TestResult:
    """Test 2: Check if all parts meet the design constraints."""
    solids = _extract_solids(result)
    
    if not solids:
        return TestResult(
            name="Part Constraints",
            status=TestStatus.SKIPPED,
            message="No individual parts found to analyze",
        )
    
    parts_info = []
    violations = []
    
    for i, solid in enumerate(solids):
        dims = _get_bounding_box(solid)
        if dims is None:
            continue
            
        classification = _classify_part(dims)
        part_info = {
            'index': i + 1,
            'dimensions': dims,
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
            name="Part Constraints",
            status=TestStatus.FAILED,
            message=f"{len(violations)} constraint violation(s) found",
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
        name="Part Constraints",
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
        constraint_result = test_part_constraints(result)
        tests.append(constraint_result)
    else:
        tests.append(TestResult(
            name="Part Constraints",
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
