from typing import Optional
from pathlib import Path
import os
import json

import pyvista as pv
from PIL import Image
import cadquery as cq

from logger import make_logger_child
logger = make_logger_child("output")

def save_output_files(output_path: Path, 
                      base_id: str,
                      iteration: Optional[int] = None,
                      cad_query_obj = None,
                      code: str = None,
                      test_result_obj = None):
    """Save output files for the given result and generated code.
    
    Tries to export STL, render views, create assembly GIF, and save code.
    Each type of output is optional and failures are logged but do not raise exceptions.
    """

    if iteration is None:
        iteration_path = output_path / str(base_id) / "final"
    else:
        iteration_path = output_path / str(base_id) / f"iteration_{iteration}"

    os.makedirs(iteration_path, exist_ok=True)

    if cad_query_obj:
        views_success = _try_render_views(cad_query_obj, iteration_path)
        if views_success:
            logger.info(f"View rendering successful for {base_id}")
        else:
            logger.error(f"View rendering not applicable for {base_id}")
        
        gif_success = _try_render_assembly_gif(cad_query_obj, iteration_path)
        if gif_success:
            logger.info(f"Assembly GIF rendering successful for {base_id}")
        else:
            logger.error(f"Assembly GIF rendering not applicable for {base_id}")
        
        stl_success = _try_export_stl(cad_query_obj, iteration_path)
        if stl_success:
            logger.info(f"STL export successful for {base_id}")
        else:
            logger.error(f"STL export not applicable for {base_id}")

        parts_json_success = _try_export_parts_json(cad_query_obj, iteration_path)
        if parts_json_success:
            logger.info(f"Parts JSON export successful for {base_id}")
        else:
            logger.error(f"Parts JSON export not applicable for {base_id}")
    
    if code:
        code_success = _try_export_code(code, iteration_path)
        if code_success:
            logger.info(f"Code export successful for {base_id}")
        else:
            logger.error(f"Code export failed for {base_id}")

    if test_result_obj:
        test_result_success = _try_export_test_suite_results(test_result_obj, iteration_path)
        if test_result_success:
            logger.info(f"Test result export successful for {base_id}")
        else:
            logger.error(f"Test result export failed for {base_id}")


def _try_render_assembly_gif(result, output_path: Path) -> bool:
    """Render an animated GIF showing parts being assembled one by one.
    
    Uses PyVista for headless STL-based rendering.
    Returns the URL to access the GIF file, or None if not an Assembly object.
    """
    
    # Only works for Assembly objects with children
    if not hasattr(result, 'children') or not hasattr(result, 'objects'):
        return False
    
    # Get the objects dict (name -> Assembly node)
    objects_dict = getattr(result, 'objects', None)
    if not objects_dict or not isinstance(objects_dict, dict):
        return False
    
    part_names = list(objects_dict.keys())
    num_parts = len(part_names)
    
    logger.info(f"Generating assembly GIF with {num_parts} parts")
    
    try:
        # Configure PyVista for offscreen rendering
        pv.OFF_SCREEN = True
        
        # Pre-export all parts to temporary STL files and load as meshes
        part_meshes = {}
        part_stl_files = []
        
        for part_name in part_names:
            part_asm = objects_dict[part_name]
            part_obj = getattr(part_asm, 'obj', None)
            part_loc = getattr(part_asm, 'loc', None)
            
            if part_obj is None:
                continue
            
            # Get the underlying shape (without assembly location)
            if hasattr(part_obj, 'val'):
                shape = part_obj.val()
            else:
                shape = part_obj
            
            if shape is None:
                continue
            
            # Export to temporary STL
            tmp_path = output_path / f"{part_name}_temp.stl"
            part_stl_files.append(tmp_path)
            
            try:
                # Export the shape directly (preserves local orientation like YZ plane)
                # We wrap in Workplane to ensure export compatibility
                if hasattr(shape, 'wrapped'): # It's a Shape
                    export_obj = cq.Workplane().add(shape)
                else:
                    export_obj = shape
                    
                cq.exporters.export(export_obj, str(tmp_path))
                mesh = pv.read(str(tmp_path))
                
                # Apply assembly location transform to the mesh directly
                if part_loc is not None:
                    try:
                        # Convert cq.Location to 4x4 matrix
                        T = part_loc.wrapped.Transformation()
                        matrix = [[0.0]*4 for _ in range(4)]
                        for r in range(3):
                            for c in range(4):
                                matrix[r][c] = T.Value(r+1, c+1)
                        matrix[3][3] = 1.0
                        
                        mesh.transform(matrix, inplace=True)
                    except Exception as e:
                        logger.warning(f"Failed to apply transform to mesh for {part_name}: {e}")
                
                part_meshes[part_name] = mesh
            except Exception as e:
                logger.warning(f"Failed to export part {part_name}: {e}")
                continue
        
        frames = []
        temp_files = []
        
        # Dark background color matching website
        bg_color = [0.1, 0.1, 0.15]
        
        # Generate a frame for each step of assembly
        for i in range(num_parts):
            plotter = pv.Plotter(off_screen=True, window_size=[500, 500])
            plotter.set_background(bg_color)
            
            # Add parts up to current step
            for j, part_name in enumerate(part_names):
                if part_name not in part_meshes:
                    continue
                
                mesh = part_meshes[part_name]
                
                # Parts already assembled are solid, future parts are transparent
                if j > i:
                    opacity = 0.15
                else:
                    opacity = 1.0
                
                plotter.add_mesh(mesh, color='tan', opacity=opacity)
            
            # Set camera position
            plotter.camera_position = 'iso'
            plotter.camera.azimuth = 180
            plotter.camera.elevation = 0
            plotter.reset_camera()
            plotter.camera.zoom(1.0)
            
            # Render this frame
            temp_filename = f"frame_{i:04d}.png"
            temp_path = output_path / temp_filename
            temp_files.append(temp_path)
            
            plotter.screenshot(str(temp_path))
            plotter.close()
        
        # Clean up temporary STL files
        for stl_path in part_stl_files:
            try:
                stl_path.unlink()
            except Exception:
                pass
        
        # Load frames and create GIF
        for temp_path in temp_files:
            img = Image.open(temp_path)
            frames.append(img.copy())
            img.close()
        
        # Save as animated GIF
        gif_filename = f"assembly.gif"
        gif_path = output_path / gif_filename
        
        if frames:
            frames[0].save(
                gif_path,
                save_all=True,
                append_images=frames[1:],
                duration=400,  # 400ms per frame
                loop=0,  # Loop forever
            )
        
        # Clean up temp files
        for temp_path in temp_files:
            try:
                temp_path.unlink()
            except Exception:
                pass
        
        # Clean up frame images
        for frame in frames:
            frame.close()
        
        logger.info(f"Rendered assembly GIF to {gif_path}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to render assembly GIF: {e}")
        import traceback
        traceback.print_exc()
        return False
    


def _try_export_stl(result, output_path: Path) -> bool:
    """Try to export a CadQuery object to STL file.
    
    Returns the URL to access the STL file, or None if not a CadQuery object.
    """
    # Check if result is a CadQuery Workplane or Assembly
    exportable = None
    
    # Case 1: Assembly - convert to compound for STL export
    if hasattr(result, 'toCompound') and hasattr(result, 'children'):
        try:
            # STL export requires a compound, not an assembly
            exportable = result.toCompound()
            logger.debug("Converted Assembly to Compound for STL export")
        except Exception as e:
            logger.error(f"Failed to convert assembly to compound: {e}")
    # Case 2: Workplane - export directly
    elif hasattr(result, 'val') and callable(result.val):
        try:
            exportable = result
        except Exception:
            pass
    # Case 3: Compound - can also be exported
    elif hasattr(result, 'Solids'):
        exportable = result
    
    if exportable is None:
        return False
    
    try:
        filename = f"assembly.stl"
        file_path = output_path / filename
        
        # Export to STL
        cq.exporters.export(exportable, str(file_path))
        
        logger.info(f"Exported STL to {file_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to export STL: {e}")
        return False
    



def _try_render_views(result, output_path: Path) -> bool:
    """Render a combined 2x2 grid PNG image of a CadQuery object from 4 different isometric views.
    
    Uses PyVista for headless STL-based rendering.
    Returns the URL to access the combined PNG file, or None if not a CadQuery object.
    """
    
    stl_success = _try_export_stl(result, output_path)
    if not stl_success:
        return False
    
    try:
        # Export to temporary STL file
        temp_stl = output_path / "assembly.stl"
        
        # Load STL with PyVista
        mesh = pv.read(str(temp_stl))
        
        # Clean up temp STL
        temp_stl.unlink()
        
        # Configure PyVista for offscreen rendering
        pv.OFF_SCREEN = True
        pv.global_theme.allow_empty_mesh = True
        
        # Define 4 isometric camera positions (azimuth, elevation)
        # These give views from each "corner" of the object
        views = [
            ("View 1", 0, 0),
            ("View 2", 180, 0),
            ("View 3", 135, -90),
            ("View 4", 215, -90),
        ]
        
        view_size = 400
        temp_files = []
        
        # Dark background color matching website
        bg_color = [0.1, 0.1, 0.15]
        
        # Render each view
        for view_name, azimuth, elevation in views:
            temp_filename = f"{view_name.lower().replace('-', '_')}_temp.png"
            temp_path = output_path / temp_filename
            temp_files.append((view_name, temp_path))
            
            # Create plotter with clean settings
            plotter = pv.Plotter(off_screen=True, window_size=[view_size, view_size])
            plotter.add_mesh(mesh, color='tan', opacity=1.0)
            plotter.set_background(bg_color)
            plotter.camera_position = 'iso'
            plotter.camera.azimuth = azimuth
            plotter.camera.elevation = elevation
            plotter.reset_camera()
            plotter.camera.zoom(1.0)
            
            # Save screenshot
            plotter.screenshot(str(temp_path))
            plotter.close()
        
        # Create combined 2x2 grid image
        grid_size = view_size * 2
        combined = Image.new('RGB', (grid_size, grid_size), color=(26, 26, 38))
        
        # Positions for 2x2 grid: top-left, top-right, bottom-left, bottom-right
        positions = [(0, 0), (view_size, 0), (0, view_size), (view_size, view_size)]
        
        for i, (view_name, temp_path) in enumerate(temp_files):
            # Load and paste the view image
            view_img = Image.open(temp_path)
            x, y = positions[i]
            combined.paste(view_img, (x, y))
            
            # Clean up temp file
            view_img.close()
            temp_path.unlink()
        
        # Save combined image
        combined_filename = f"views.png"
        combined_path = output_path / combined_filename
        combined.save(combined_path, 'PNG')
        combined.close()
        
        logger.debug(f"Rendered combined views to {combined_path}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to render views: {e}")
        import traceback
        traceback.print_exc()
        return False

def _try_export_code(code, output_path: Path) -> bool:
    """Try to save the generated code to a .py file for debugging purposes."""
    try:
        filename = f"code.py"
        file_path = output_path / filename
        with open(file_path, 'w') as f:
            f.write(code)
        logger.debug(f"Saved generated code to {file_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to save generated code: {e}")
        return False
    
def _try_export_parts_json(result, output_path: Path) -> bool:
    """Try to export a JSON file listing the parts in an Assembly.
    
    Exports JSON with part names, dimensions (L, W, H), positions (x, y, z),
    and rotations (quaternion: i, j, k, c) in assembly order.
    """
    
    # Only works for Assembly objects with children
    if not hasattr(result, 'children') or not hasattr(result, 'objects'):
        return False
    
    # Get the objects dict (name -> Assembly node)
    objects_dict = getattr(result, 'objects', None)
    if not objects_dict or not isinstance(objects_dict, dict):
        return False
    
    parts_list = []
    
    for part_name in objects_dict.keys():
        part_asm = objects_dict[part_name]
        part_obj = getattr(part_asm, 'obj', None)
        part_loc = getattr(part_asm, 'loc', None)
        
        if part_obj is None:
            continue
        
        # Get the underlying shape
        if hasattr(part_obj, 'val'):
            shape = part_obj.val()
        else:
            shape = part_obj
        
        if shape is None:
            continue
        
        # Get bounding box dimensions (L, W, H)
        try:
            if hasattr(shape, 'BoundingBox'):
                bb = shape.BoundingBox()
            elif hasattr(shape, 'val') and hasattr(shape.val(), 'BoundingBox'):
                bb = shape.val().BoundingBox()
            else:
                bb = None
            
            if bb is not None:
                dims = [
                    round(bb.xlen, 4),
                    round(bb.ylen, 4),
                    round(bb.zlen, 4)
                ]
            else:
                dims = [0, 0, 0]
        except Exception as e:
            logger.warning(f"Failed to get bounding box for {part_name}: {e}")
            dims = [0, 0, 0]
        
        # Get position and rotation from location
        pos = [0.0, 0.0, 0.0]
        rot = [0.0, 0.0, 0.0, 1.0]  # Quaternion (i, j, k, w) - identity
        
        if part_loc is not None:
            try:
                # Extract translation (position)
                T = part_loc.wrapped.Transformation()
                translation = T.TranslationPart()
                pos = [
                    round(translation.X(), 4),
                    round(translation.Y(), 4),
                    round(translation.Z(), 4)
                ]
                
                # Extract rotation as quaternion
                from OCP.gp import gp_Quaternion
                quat = T.GetRotation()
                rot = [
                    round(quat.X(), 6),  # i
                    round(quat.Y(), 6),  # j
                    round(quat.Z(), 6),  # k
                    round(quat.W(), 6)   # c (scalar/real part)
                ]
            except Exception as e:
                logger.warning(f"Failed to extract transform for {part_name}: {e}")
        
        parts_list.append({
            'name': part_name,
            'dims': dims,
            'pos': pos,
            'rot': rot
        })
    
    try:
        output_data = {'parts': parts_list}
        filename = f"parts.json"
        file_path = output_path / filename
        
        with open(file_path, 'w') as f:
            json.dump(output_data, f, indent=2)
        
        logger.debug(f"Exported parts JSON to {file_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to export parts JSON: {e}")
        return False
    
def _try_export_test_suite_results(test_result_obj, output_path):
    with open(output_path / f"test_results.json", 'w') as f:
        json.dump(test_result_obj.to_dict(), f, indent=2)

    return True