PART_LIBRARY = {}

# Add lengths from 100mm to 500mm in 50mm increments
for z in range(100, 501, 50):
    # Add 28x28 beams
    part_name = f"beam_28x28x{z}"
    PART_LIBRARY[part_name] = {'x': 28, 'y': 28, 'z': z}

    # Add 48x24 beams
    part_name = f"beam_48x24x{z}"
    PART_LIBRARY[part_name] = {'x': 48, 'y': 24, 'z': z}


PART_LIBRARY['plywood_7mm'] = {'z': 7, 'max_width': 500, 'max_height': 500}

def generate_part_table():
    """Generate a markdown table of available parts from the PART_LIBRARY."""
    
    table = "Parts with fixed dimensions\n"
    table += "| Part Name | Dimensions (mm) |\n"
    table += "|-----------|-----------------|\n"
    for part_name, specs in PART_LIBRARY.items():
        if 'x' in specs and 'y' in specs and 'z' in specs:
            dimensions = f"{specs['x']} x {specs['y']} x {specs['z']}"
        table += f"| {part_name} | {dimensions} |\n"

    table += "\nParts with variable dimensions (plywood sheets)\n"
    table += "| Part Name | Thickness (mm) | Max Width (mm) | Max Height (mm) |\n"
    table += "|-----------|----------------|----------------|----------------|\n"
    for part_name, specs in PART_LIBRARY.items():
        if 'z' in specs and 'max_width' in specs and 'max_height' in specs:
            thickness = specs['z']
            max_width = specs['max_width']
            max_height = specs['max_height']
            table += f"| {part_name} | {thickness} | {max_width} | {max_height} |\n"
    return table