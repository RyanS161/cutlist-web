import os

BLOCKS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "blocks")

# Map logical name (for CSV/Agent) to filename and dimensions
BLOCK_DEFINITIONS = {
    "goki_block_1": {"filename": "goki_block_1.STL", "dims": (25.0, 25.0, 25.0)},
    "goki_block_2": {"filename": "goki_block_2.STL", "dims": (25.0, 50.0, 25.0)},
    "goki_block_3": {"filename": "goki_block_3.STL", "dims": (12.5, 50.0, 25.0)},
    "goki_block_4": {"filename": "goki_block_4.STL", "dims": (12.5, 75.0, 25.0)},
    "goki_block_5": {"filename": "goki_block_5.STL", "dims": (75.0, 25.0, 25.0)},
    "goki_block_6": {"filename": "goki_block_6.STL", "dims": (59.0, 25.0, 16.52)},
    "goki_block_7": {"filename": "goki_block_7.STL", "dims": (24.99, 50.0, 25.0)},
    "goki_block_8": {"filename": "goki_block_8.STL", "dims": (37.5, 25.0, 37.5)},
}

def get_block_path(block_name):
    if block_name in BLOCK_DEFINITIONS:
        return os.path.join(BLOCKS_DIR, BLOCK_DEFINITIONS[block_name]["filename"])
    return None
