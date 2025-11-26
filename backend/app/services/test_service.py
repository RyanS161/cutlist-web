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
    long_message: Optional[str] = None  # Detailed message for agent, not displayed in UI
    
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


def _extract_solids(result) -> List[Dict[str, Any]]:
    """Extract individual solids from a CadQuery result.
    
    Handles various CadQuery types:
    - Assembly: iterate through children and extract each part's solid with name
    - Workplane: use .vals() to get all objects, then extract solids from each
    - Compound: call .Solids() directly
    - Individual Solid: return as single-item list
    
    Returns a list of dicts with 'solid' and 'name' keys.
    """
    parts = []
    
    try:
        # Log the type for debugging
        logger.info(f"Extracting solids from type: {type(result).__name__}")
        logger.debug(f"Result attributes: {[a for a in dir(result) if not a.startswith('_')][:20]}")
        
        # Case 1: Assembly object - detect by checking for 'objects' attribute
        # CadQuery Assembly has: obj, name, loc, color, children (dict), objects (dict)
        # The 'objects' dict maps names to child Assembly nodes
        if hasattr(result, 'objects') and hasattr(result, 'toCompound'):
            objects_attr = getattr(result, 'objects', None)
            
            logger.info(f"Assembly detected - objects: {type(objects_attr)}")
            
            # objects can be a dict (name -> Assembly) or list
            objects_dict = {}
            if isinstance(objects_attr, dict):
                objects_dict = objects_attr
            elif objects_attr is not None:
                # Try to convert to dict if it has items()
                try:
                    if hasattr(objects_attr, 'items'):
                        objects_dict = dict(objects_attr.items())
                    else:
                        # It's a list-like, create dict with index keys
                        objects_dict = {f"part_{i+1}": obj for i, obj in enumerate(objects_attr)}
                except Exception as e:
                    logger.warning(f"Could not process objects: {e}")
            
            if objects_dict:
                logger.info(f"Processing Assembly with {len(objects_dict)} objects")
                
                # Log what's in objects for debugging
                for i, (obj_name, obj_asm) in enumerate(list(objects_dict.items())[:5]):  # Log first 5
                    logger.info(f"  objects['{obj_name}']: type={type(obj_asm).__name__}")
                
                def apply_location_to_solid(solid, loc):
                    """Apply a CadQuery Location transform to a solid."""
                    if loc is None:
                        return solid
                    try:
                        # Get the transformation from the Location
                        if hasattr(loc, 'IsIdentity') and loc.IsIdentity():
                            return solid  # No transformation needed
                        
                        # CadQuery Location wraps an OCP gp_Trsf transform
                        # We can use .IsIdentity() to check if it's the identity transform
                        if hasattr(loc, 'IsIdentity') and callable(loc.IsIdentity):
                            if loc.IsIdentity():
                                return solid
                        
                        # Apply the transform - solid.move() or solid.located()
                        if hasattr(solid, 'move') and callable(solid.move):
                            return solid.move(loc)
                        elif hasattr(solid, 'located') and callable(solid.located):
                            return solid.located(loc)
                        elif hasattr(solid, 'Moved') and callable(solid.Moved):
                            # OCC-level transform
                            if hasattr(loc, 'IsIdentity'):
                                return solid.Moved(loc)
                        
                        return solid
                    except Exception as e:
                        logger.debug(f"Could not apply location transform: {e}")
                        return solid
                
                # Extract from objects dict - keys are names, values are Assembly nodes
                for obj_name, obj_asm in objects_dict.items():
                    # Get the location transform for this part
                    loc = getattr(obj_asm, 'loc', None)
                    
                    # Get the solid from this assembly node
                    obj = getattr(obj_asm, 'obj', None)
                    if obj is not None:
                        # If it's a Workplane, get the solid from it
                        if hasattr(obj, 'val') and callable(obj.val):
                            try:
                                val = obj.val()
                                if hasattr(val, 'Solids') and callable(val.Solids):
                                    val_solids = val.Solids()
                                    if val_solids:
                                        for idx, s in enumerate(val_solids):
                                            s_name = f"{obj_name}_{idx+1}" if len(val_solids) > 1 else obj_name
                                            transformed = apply_location_to_solid(s, loc)
                                            parts.append({'solid': transformed, 'name': s_name})
                                    else:
                                        transformed = apply_location_to_solid(val, loc)
                                        parts.append({'solid': transformed, 'name': obj_name})
                                elif hasattr(val, 'BoundingBox'):
                                    transformed = apply_location_to_solid(val, loc)
                                    parts.append({'solid': transformed, 'name': obj_name})
                            except Exception as e:
                                logger.warning(f"Failed to extract solid from '{obj_name}': {e}")
                        elif hasattr(obj, 'Solids') and callable(obj.Solids):
                            obj_solids = obj.Solids()
                            if obj_solids:
                                for idx, s in enumerate(obj_solids):
                                    s_name = f"{obj_name}_{idx+1}" if len(obj_solids) > 1 else obj_name
                                    transformed = apply_location_to_solid(s, loc)
                                    parts.append({'solid': transformed, 'name': s_name})
                            else:
                                transformed = apply_location_to_solid(obj, loc)
                                parts.append({'solid': transformed, 'name': obj_name})
                        elif hasattr(obj, 'BoundingBox'):
                            transformed = apply_location_to_solid(obj, loc)
                            parts.append({'solid': transformed, 'name': obj_name})
                    else:
                        logger.debug(f"Object '{obj_name}' has no obj attribute")
                
                logger.info(f"Extracted {len(parts)} parts from Assembly.objects")
                for p in parts:
                    logger.info(f"  Part: name='{p['name']}'")
            
            # Fallback: if we didn't find any solids via objects list, use toCompound()
            if not parts and hasattr(result, 'toCompound'):
                logger.info("No solids found via objects, trying toCompound() fallback")
                try:
                    compound = result.toCompound()
                    if hasattr(compound, 'Solids') and callable(compound.Solids):
                        solids = list(compound.Solids())
                        parts = [{'solid': s, 'name': f'part_{i+1}'} for i, s in enumerate(solids)]
                        logger.info(f"Extracted {len(parts)} solids via toCompound() fallback")
                except Exception as e:
                    logger.warning(f"toCompound() fallback failed: {e}")
            
        # Case 2: Workplane object (legacy support)
        elif hasattr(result, 'vals') and callable(result.vals):
            # Use .vals() to get ALL objects in the workplane, not just the last one
            vals = result.vals()
            logger.info(f"Workplane contains {len(vals)} objects")
            
            part_idx = 0
            for val in vals:
                # Each val could be a Compound, Solid, or other shape
                if hasattr(val, 'Solids') and callable(val.Solids):
                    val_solids = val.Solids()
                    if val_solids:
                        for s in val_solids:
                            part_idx += 1
                            parts.append({'solid': s, 'name': f'part_{part_idx}'})
                    else:
                        part_idx += 1
                        parts.append({'solid': val, 'name': f'part_{part_idx}'})
                elif hasattr(val, 'wrapped'):
                    part_idx += 1
                    parts.append({'solid': val, 'name': f'part_{part_idx}'})
                    
            logger.info(f"Extracted {len(parts)} solids from Workplane")
            
        # Case 3: Assembly with toCompound (fallback)
        elif hasattr(result, 'toCompound') and callable(result.toCompound):
            compound = result.toCompound()
            if hasattr(compound, 'Solids') and callable(compound.Solids):
                solids = list(compound.Solids())
                parts = [{'solid': s, 'name': f'part_{i+1}'} for i, s in enumerate(solids)]
            logger.info(f"Extracted {len(parts)} solids from Assembly.toCompound()")
            
        # Case 4: Compound or shape with Solids method
        elif hasattr(result, 'Solids') and callable(result.Solids):
            solids = list(result.Solids())
            parts = [{'solid': s, 'name': f'part_{i+1}'} for i, s in enumerate(solids)]
            logger.info(f"Extracted {len(parts)} solids from Compound")
            
        # Case 5: Direct solid
        elif hasattr(result, 'BoundingBox'):
            parts.append({'solid': result, 'name': 'part_1'})
            logger.info("Result appears to be a single solid")
            
        else:
            logger.warning(f"Unknown result type: {type(result)}, attributes: {dir(result)[:10]}...")
            
    except Exception as e:
        logger.warning(f"Failed to extract solids: {e}", exc_info=True)
    
    return parts


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
    parts = _extract_solids(result)
    
    if not parts:
        return TestResult(
            name="Parts in Library",
            status=TestStatus.SKIPPED,
            message="No individual parts found to analyze",
        )
    
    parts_info = []
    violations = []
    
    for i, part_data in enumerate(parts):
        solid = part_data['solid']
        name = part_data['name']
        
        sorted_dims = _get_oriented_dims(solid)
        if sorted_dims is None:
            continue
            
        classification = _classify_part(sorted_dims)
        part_info = {
            'index': i + 1,
            'name': name,
            'dimensions': sorted_dims,
            'classification': classification,
        }
        parts_info.append(part_info)
        
        # Check for violations
        if classification['type'] == 'beam_28x28':
            if not classification['valid_length']:
                violations.append(
                    f"Part '{name}': 28x28 beam length {classification['length']:.1f}mm "
                    f"is not in valid range (100-500mm, 50mm increments)"
                )
        elif classification['type'] == 'beam_48x24':
            if not classification['valid_length']:
                violations.append(
                    f"Part '{name}': 48x24 beam length {classification['length']:.1f}mm "
                    f"is not in valid range (100-500mm, 50mm increments)"
                )
        elif classification['type'] == 'plywood':
            if not classification['valid_size']:
                violations.append(
                    f"Part '{name}': Plywood size {classification['width']:.1f}x{classification['height']:.1f}mm "
                    f"exceeds maximum 500x500mm"
                )
        elif classification['type'] == 'unknown':
            violations.append(
                f"Part '{name}': Unrecognized part with dimensions "
                f"{classification['dimensions'][0]:.1f}x{classification['dimensions'][1]:.1f}x{classification['dimensions'][2]:.1f}mm"
            )
    
    if violations:
        return TestResult(
            name="Parts in Library",
            status=TestStatus.FAILED,
            message=f"{len(violations)} part violation(s) found: ",
            long_message="\n".join(violations),
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


def _get_solid_volume(solid) -> float:
    """Get the volume of a solid, returns 0 if unable to calculate."""
    try:
        if hasattr(solid, 'Volume') and callable(solid.Volume):
            return solid.Volume()
        elif hasattr(solid, 'val') and callable(solid.val):
            return solid.val().Volume()
    except Exception:
        pass
    return 0.0


def _compute_intersection(solid1, solid2) -> Optional[Any]:
    """Compute the boolean intersection of two solids.
    
    Returns the intersection solid, or None if no intersection or error.
    """
    try:
        # Import cadquery for boolean operations
        import cadquery as cq
        
        # Get the underlying shape objects
        shape1 = solid1
        shape2 = solid2
        
        # If they're wrapped in Workplane, extract the solid
        if hasattr(solid1, 'val') and callable(solid1.val):
            shape1 = solid1.val()
        if hasattr(solid2, 'val') and callable(solid2.val):
            shape2 = solid2.val()
        
        # Perform boolean intersection using CadQuery
        # We need to wrap in a Workplane to use CQ operations
        wp = cq.Workplane("XY").add(shape1)
        intersection = wp.intersect(cq.Workplane("XY").add(shape2))
        
        # Check if the intersection produced any solids
        try:
            result = intersection.val()
            if result is not None:
                return result
        except Exception:
            pass
            
        return None
        
    except Exception as e:
        logger.debug(f"Intersection computation failed: {e}")
        return None


def test_no_intersections(result) -> TestResult:
    """Test 3: Check if any parts intersect with each other."""
    parts = _extract_solids(result)
    
    if len(parts) < 2:
        return TestResult(
            name="No Part Intersections",
            status=TestStatus.PASSED,
            message="Less than 2 parts, no intersections possible",
        )
    
    intersections = []
    checked_pairs = 0
    
    # Check each pair of solids for intersection
    for i in range(len(parts)):
        for j in range(i + 1, len(parts)):
            checked_pairs += 1
            part1 = parts[i]
            part2 = parts[j]
            solid1 = part1['solid']
            solid2 = part2['solid']
            name1 = part1['name']
            name2 = part2['name']
            
            try:
                # Compute the intersection
                intersection = _compute_intersection(solid1, solid2)
                
                if intersection is not None:
                    # Get the volume of the intersection
                    volume = _get_solid_volume(intersection)
                    
                    # Use a small threshold to account for floating point errors
                    # and minor touching surfaces (1 cubic mm threshold)
                    if volume > 1.0:
                        intersections.append({
                            'part1': i + 1,
                            'part2': j + 1,
                            'name1': name1,
                            'name2': name2,
                            'volume': round(volume, 2),
                        })
                        logger.info(f"Found intersection between '{name1}' and '{name2}': volume={volume:.2f}mm³")
                        
            except Exception as e:
                logger.warning(f"Error checking intersection between '{name1}' and '{name2}': {e}")
    
    if intersections:
        # Build human-readable intersection descriptions
        intersection_descriptions = []
        for isect in intersections:
            intersection_descriptions.append(
                f"'{isect['name1']}' intersects with '{isect['name2']}' "
                f"(overlap volume: {isect['volume']}mm³)"
            )
        
        return TestResult(
            name="No Part Intersections",
            status=TestStatus.FAILED,
            message=f"{len(intersections)} intersection(s) found between parts: ",
            long_message="\n".join(intersection_descriptions),
            details={
                'intersections': intersections,
                'intersection_descriptions': intersection_descriptions,
                'pairs_checked': checked_pairs,
            }
        )
    
    return TestResult(
        name="No Part Intersections",
        status=TestStatus.PASSED,
        message=f"No intersections found ({checked_pairs} pairs checked)",
        details={
            'pairs_checked': checked_pairs,
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
        
        # Test 3: Check for part intersections
        intersection_result = test_no_intersections(result)
        tests.append(intersection_result)
    else:
        tests.append(TestResult(
            name="Parts in Library",
            status=TestStatus.SKIPPED,
            message="Skipped because code execution failed",
        ))
        tests.append(TestResult(
            name="No Part Intersections",
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
