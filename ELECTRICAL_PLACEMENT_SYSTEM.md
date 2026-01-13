# CAD-Based Electrical Auto-Placement System

## Overview

This system performs automatic electrical component placement using native AutoCAD CAD files (DWG/DXF). It works directly with CAD geometry coordinates and entities, without relying on computer vision or image processing.

## Architecture

The system is organized into several modules:

### 1. Geometry Parser (`geometry_parser.py`)

Parses native CAD entities directly from DWG/DXF files:

- **Rooms**: Closed LWPOLYLINE/POLYLINE entities on ROOM layer
- **Walls**: LINE, LWPOLYLINE, POLYLINE, SOLID, 3DFACE entities on WALL layer
- **Doors**: INSERT blocks on DOOR layer
- **Windows**: INSERT blocks on WINDOW layer
- **Floors**: Detected from Z elevations, layers, or groups

Supports both 2D and 3D geometry:
- 2D: X, Y coordinates with optional Z elevation
- 3D: Full 3D coordinates from 3DPOLYLINE, 3DFACE, SOLID entities

### 2. Spatial Analyzer (`spatial_analyzer.py`)

Analyzes spatial relationships:

- Finds rooms containing points
- Identifies nearest walls
- Associates doors and windows with rooms
- Calculates wall surfaces and directions
- Determines ceiling heights and floor levels
- Detects door swing zones and window clearance zones
- Identifies room types (bathrooms, small spaces)

### 3. Placement Rules (`placement_rules.py`)

Implements deterministic, engineering-grade placement rules:

#### Switches
- Place on wall surface
- Near corresponding door
- Height: ~1400mm from finished floor level
- Avoid door swing zones (1000mm clearance)
- Avoid window zones (300mm clearance)
- Spacing: 300mm between switches

#### Lights
- Place at room centroid (2D) or on ceiling plane (3D)
- Multiple lights arranged in grid pattern
- Maintain clearance from beams/obstructions
- Height: At ceiling level

#### Fans
- Centered in room ceiling
- Exclude bathrooms
- Exclude small spaces (< 10 sqm)
- Avoid overlap with light fixtures

#### Sockets/Outlets
- Place along walls at standard intervals (3000mm default)
- Avoid behind doors (500mm clearance)
- Avoid behind windows (500mm clearance)
- Height: 300mm from finished floor level
- Spacing configurable (minimum 500mm)

### 4. Placement Validator (`placement_validator.py`)

Validates all placements:

- **Boundary checks**: Ensures placements are within room boundaries
- **Clearance checks**: Maintains minimum clearances between components
  - Switch-to-switch: 200mm
  - Light-to-light: 1000mm
  - Fan-to-fan: 1500mm
  - Socket-to-socket: 500mm
  - Cross-type: 300mm
- **Floor level checks**: Ensures placements respect floor level constraints
- **Overlap prevention**: Prevents collisions between components

### 5. CAD Output Generator (`cad_output.py`)

Generates updated DWG/DXF files:

- Creates proper block definitions (SWITCH_BLOCK, LIGHT_BLOCK, FAN_BLOCK, SOCKET_BLOCK)
- Inserts blocks with exact X, Y, Z coordinates
- Sets correct rotation and orientation
- Assigns appropriate layers:
  - ELECTRICAL_SWITCHES
  - ELECTRICAL_LIGHTS
  - ELECTRICAL_FANS
  - ELECTRICAL_SOCKETS
- Includes metadata in extended data

### 6. Electrical Placer (`electrical_placer.py`)

Main orchestrator that coordinates all modules:

1. Parses CAD geometry
2. Performs spatial analysis
3. Applies placement rules
4. Validates placements
5. Generates output CAD file

## Usage

### Basic Usage

```python
from pathlib import Path
from automation.services.electrical_placer import ElectricalPlacer

# Initialize placer
placer = ElectricalPlacer(Path("input.dxf"))

# Process with default settings
stats = placer.process(
    output_path=Path("output.dxf"),
    lights_per_room=1,
    switches_per_door=1,
    fans_per_room=0,
    sockets_enabled=True,
    socket_spacing=3000.0  # mm
)

print(f"Placed {stats['total_placements']} components")
```

### Advanced Usage

```python
# Step-by-step processing
placer = ElectricalPlacer(Path("input.dxf"))

# Parse geometry
geometry = placer.parse_geometry()
print(f"Found {len(geometry.rooms)} rooms")

# Analyze spatial relationships
analyzer = placer.analyze_spatial()

# Initialize placement rules
rules = placer.initialize_placement_rules()

# Place components
placements = placer.place_components(
    lights_per_room=2,
    switches_per_door=2,
    fans_per_room=1,
    sockets_enabled=True,
    socket_spacing=2500.0
)

# Generate output
placer.generate_output(Path("output.dxf"), placements)
```

### Web Interface

The Django web interface supports all parameters:

- **Lights per room**: Number of lights to place in each room
- **Switches per door**: Number of switches per door
- **Fans per room**: Number of fans per room (0 to disable)
- **Enable sockets**: Checkbox to enable/disable socket placement
- **Socket spacing**: Custom spacing between sockets (mm)
- **Legacy mode**: Use simple placement logic for backward compatibility

## CAD File Requirements

### Required Layers

- **ROOM**: Closed LWPOLYLINE or POLYLINE entities defining room boundaries
- **DOOR**: INSERT blocks representing doors

### Optional Layers

- **WALL**: LINE entities representing walls (improves switch placement)
- **WINDOW**: INSERT blocks representing windows (avoids placement zones)

### Units

Plans should be in **millimetres** for sensible spacing and clearances.

### 3D Support

The system automatically detects 3D geometry:
- Uses Z coordinates for floor levels and ceiling heights
- Places lights and fans on ceiling planes
- Maintains proper height relationships

## Placement Standards

### Switch Placement
- **Height**: 1400mm from finished floor level
- **Location**: On wall surface, near door
- **Clearance**: 200mm from door swing zone, 300mm from windows
- **Spacing**: 300mm between switches

### Light Placement
- **Height**: At ceiling level (typically 2700mm above floor)
- **Location**: Room centroid or grid pattern
- **Clearance**: 1000mm between lights

### Fan Placement
- **Height**: At ceiling level
- **Location**: Room ceiling center
- **Exclusions**: Bathrooms, small spaces (< 10 sqm)
- **Clearance**: 1500mm between fans

### Socket Placement
- **Height**: 300mm from finished floor level
- **Location**: Along walls at standard intervals
- **Spacing**: 3000mm (configurable, minimum 500mm)
- **Clearance**: 500mm from doors and windows

## Validation

All placements are validated for:

1. **Boundary compliance**: Within room boundaries
2. **Clearance requirements**: Minimum distances maintained
3. **Floor level constraints**: Respects floor elevations
4. **Overlap prevention**: No collisions between components

Invalid placements are filtered out and logged.

## Output

The system generates an updated DXF file with:

- All original CAD geometry preserved
- New INSERT entities for placed components
- Proper block definitions for all component types
- Appropriate layer assignments
- Extended data with placement metadata

## Key Principles

1. **Deterministic**: Same input always produces same output
2. **Rule-based**: Uses engineering standards, not AI inference
3. **Native CAD**: Works directly with CAD coordinates, no image processing
4. **Standards-compliant**: Follows electrical installation standards
5. **Validated**: All placements checked for compliance

## Error Handling

The system includes robust error handling:

- Falls back to legacy mode if new system fails
- Gracefully handles malformed DXF files
- Provides detailed error messages in logs
- Continues processing even if some geometry is invalid

## Future Enhancements

Potential improvements:

- Support for more CAD entity types
- Regional electrical code variations
- Custom placement rule definitions
- Integration with BIM systems
- Export to other CAD formats

