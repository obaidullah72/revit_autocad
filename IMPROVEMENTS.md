# Code Improvements Summary

## Overview
This document summarizes the improvements made to the AutoCAD electrical component placement system, specifically focusing on better handling of 2D DWG files and improved switch placement along doors where they open.

## Key Improvements

### 1. Enhanced DWG/DXF Parsing with ezdxf
**File**: `automation/services/geometry_parser.py`

- **Added ezdxf support**: The parser now uses the `ezdxf` library for more accurate and robust parsing of DWG/DXF files
- **Dual parsing mode**: Falls back to text-based parsing if ezdxf is unavailable or fails
- **Better entity detection**: Improved detection of rooms, walls, doors, and windows using proper CAD entity structures
- **3D detection**: Better detection of 3D entities in the file

**New Methods**:
- `_parse_with_ezdxf()`: Main parsing method using ezdxf
- `_parse_rooms_ezdxf()`: Parse rooms using ezdxf entities
- `_parse_walls_ezdxf()`: Parse walls (including polylines) using ezdxf
- `_parse_doors_ezdxf()`: Parse door blocks with better attribute extraction
- `_parse_windows_ezdxf()`: Parse window blocks

### 2. Improved Door Swing Detection
**Files**: 
- `automation/services/geometry_parser.py` (Door class)
- `automation/services/spatial_analyzer.py`

- **Swing side detection**: New method `get_door_swing_side()` determines which side of the door opens
- **Room-aware placement**: Uses room boundaries to determine the correct swing side
- **Swing direction vector**: Added `get_swing_direction_vector()` to Door class for better swing calculations
- **Enhanced swing zone**: Improved calculation of door swing zones

**Key Features**:
- Automatically detects which side of the door opens based on room geometry
- Handles both left and right opening doors
- Falls back to rotation-based estimation if room detection fails

### 3. Smart Switch Placement on Door Swing Side
**File**: `automation/services/placement_rules.py`

- **Swing-side placement**: Switches are now placed on the side where the door opens (swing side)
- **Standard positioning**: Places switches 150-200mm from door frame on the swing side
- **Wall alignment**: Ensures switches are properly aligned along the wall
- **Multiple switches**: Supports placing multiple switches with proper spacing (300mm)

**Placement Rules**:
- Standard distance: 200mm from door frame
- Height: 1400mm from finished floor level
- Spacing: 300mm between multiple switches
- Avoids door swing zone and window zones
- Verifies placement is on the correct swing side using vector alignment

### 4. Better DWG File Handling
**File**: `automation/services/processor.py`

- **Direct DWG support**: Attempts to read DWG files directly using ezdxf
- **Improved conversion**: Better fallback conversion logic
- **Error handling**: More informative error messages with helpful hints
- **Multiple conversion methods**: Tries ezdxf first, then external converter if needed

## Technical Details

### Switch Placement Algorithm

1. **Find nearest wall** to the door
2. **Determine swing side** using room geometry:
   - Tests both sides of the wall
   - Identifies which side is inside the room
   - Uses that as the swing side
3. **Project door onto wall** to get base position
4. **Calculate placement direction** along wall:
   - Determines which direction along the wall aligns with swing side
   - Uses vector dot product to verify alignment
5. **Place switches**:
   - 200mm from door frame
   - On wall surface (10mm inside room)
   - At 1400mm height
   - Verifies alignment with swing side (cosine > 0.3)

### Door Swing Detection

The system determines door swing side by:
1. Finding the wall the door is on
2. Getting the wall's normal vector (perpendicular to wall)
3. Testing both sides of the wall to see which is inside the room
4. The side inside the room is where the door opens
5. Falls back to rotation-based estimation if needed

## Usage

The improved code maintains backward compatibility. Existing functionality continues to work, with these enhancements:

1. **Better DWG support**: DWG files are now handled more reliably
2. **Improved switch placement**: Switches are automatically placed on the correct side of doors
3. **More accurate geometry**: Better detection of rooms, walls, and doors

## Requirements

- `ezdxf >= 1.3` (already in requirements.txt)
- For DWG support, ensure ezdxf is installed with DWG capabilities

## Testing Recommendations

1. Test with various DWG files to ensure proper parsing
2. Verify switch placement is on the correct side of doors
3. Test with doors opening in different directions
4. Verify multiple switches per door are spaced correctly
5. Test edge cases: doors near corners, multiple doors in one room, etc.

## Future Enhancements

Potential improvements for future versions:
- Support for sliding doors
- Configurable switch placement distances
- Better handling of door width for more accurate placement
- Support for door swing angle detection from block attributes
- Visual preview of placements before output
