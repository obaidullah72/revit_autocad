# Fixes and Improvements for DWG File Processing

## Issues Fixed

### 1. **Flexible Layer Detection**
The parser now handles various layer naming conventions:
- **Rooms**: Detects layers with "ROOM", "SPACE", "AREA", "ZONE" (and Hebrew: "חדר", "מרחב")
- **Doors**: Detects layers with "DOOR" (and Hebrew: "דלת", "פתח") OR blocks with door in the name
- **Walls**: Detects layers with "WALL" (and Hebrew: "קיר", "מחיצה")

### 2. **Smart Room Detection**
- Now detects rooms from **closed polylines** even if not on a "ROOM" layer
- Filters out very small shapes (minimum 1 m² area)
- Handles both LWPOLYLINE and POLYLINE entities

### 3. **Better Door Detection**
- Detects doors from INSERT blocks on DOOR layers OR blocks with "door" in the name
- Supports Hebrew layer names
- Extracts door width from attributes when available

### 4. **Improved Switch Placement**
- Switches are placed **200mm from door frame** on the **swing side** (where door opens)
- Automatically determines which side the door opens using room geometry
- Height: 1400mm from floor level
- Multiple switches spaced 300mm apart

### 5. **Light Placement**
- Lights placed at **center of every room**
- For multiple lights, arranges in a grid pattern
- Height: At ceiling level (2700mm default)

## How It Works

### Processing Flow:
1. **File Upload**: User uploads DWG or DXF file via web interface
2. **Parsing**: 
   - Tries to use `ezdxf` library first (more accurate)
   - Falls back to text-based parsing if needed
3. **Detection**:
   - Finds all rooms (closed polylines with reasonable area)
   - Finds all doors (INSERT blocks)
   - Finds walls (optional, improves placement)
4. **Placement**:
   - **Lights**: One per room at centroid
   - **Switches**: One per door, 200mm from door on swing side
5. **Output**: Generates new DXF file with LIGHT_BLOCK and SWITCH_BLOCK inserts

## Requirements

- Django 5.1+
- ezdxf >= 1.3 (for better DWG support)
- Python 3.8+

## Usage

### Via Web Interface:
1. Navigate to the upload page
2. Select your DWG/DXF file
3. Set parameters:
   - Lights per room: 1 (default)
   - Switches per door: 1 (default)
4. Click "Run automation"
5. Download the processed file

### File Requirements:
- **Rooms**: Closed LWPOLYLINE or POLYLINE entities (preferably on ROOM layer, but not required)
- **Doors**: INSERT blocks (preferably on DOOR layer or with "door" in block name)
- **Units**: Should be in millimeters for proper spacing

## Testing with Your Files

The system has been tested and improved to handle:
- `1.dwg` - Standard DWG file
- `תוכניות למכרז - יוספטל 8 בת ים-Sheet - 0-1 - מרתף -2.dwg` - Hebrew filename support

## Troubleshooting

### If no rooms are detected:
- Check that rooms are closed polylines (first and last vertex should be close)
- Ensure rooms have reasonable area (> 1 m²)
- Check layer names - try renaming to include "ROOM" or "SPACE"

### If no doors are detected:
- Ensure doors are INSERT blocks (not lines or polylines)
- Check layer name includes "DOOR" or block name includes "door"
- Verify door blocks are not too small

### If switches are not placed correctly:
- Ensure doors are associated with rooms (doors should be near room boundaries)
- Check that walls are detected (helps with placement accuracy)
- Verify door rotation is correct in the CAD file

## Next Steps

For production use, consider:
1. Installing `ezdxf` with DWG support: `pip install ezdxf[drawings]`
2. Setting up background task processing for large files
3. Adding preview/visualization of placements before download
4. Supporting more component types (sockets, fans, etc.)
