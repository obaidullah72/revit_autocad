"""
Comprehensive CAD geometry parser for 2D/3D entities.

This module parses native CAD entities directly from DWG/DXF files,
extracting exact coordinates, layer names, and entity metadata.
"""

from pathlib import Path
from typing import NamedTuple, Optional
from dataclasses import dataclass, field
from enum import Enum
import math

try:
    import ezdxf
    EZDXF_AVAILABLE = True
except ImportError:
    EZDXF_AVAILABLE = False

try:
    from shapely.geometry import LineString, Polygon
    from shapely.ops import polygonize
    SHAPELY_AVAILABLE = True
except ImportError:
    SHAPELY_AVAILABLE = False


class EntityType(Enum):
    """CAD entity types."""
    ROOM = "ROOM"
    WALL = "WALL"
    DOOR = "DOOR"
    WINDOW = "WINDOW"
    FLOOR = "FLOOR"
    CEILING = "CEILING"
    UNKNOWN = "UNKNOWN"


@dataclass
class Point3D:
    """3D point with X, Y, Z coordinates."""
    x: float
    y: float
    z: float = 0.0

    def to_2d(self) -> tuple[float, float]:
        """Return 2D (x, y) tuple."""
        return (self.x, self.y)

    def distance_to(self, other: "Point3D") -> float:
        """Calculate 3D distance to another point."""
        dx = self.x - other.x
        dy = self.y - other.y
        dz = self.z - other.z
        return math.sqrt(dx * dx + dy * dy + dz * dz)


@dataclass
class Room:
    """Represents a room as a closed boundary."""
    vertices: list[Point3D]
    layer: str
    floor_level: float = 0.0
    ceiling_height: Optional[float] = None
    room_type: Optional[str] = None  # e.g., "BATHROOM", "BEDROOM", etc.

    def get_centroid(self) -> Point3D:
        """Calculate room centroid."""
        if not self.vertices:
            return Point3D(0, 0, self.floor_level)
        
        x_sum = sum(v.x for v in self.vertices)
        y_sum = sum(v.y for v in self.vertices)
        z_sum = sum(v.z for v in self.vertices)
        n = len(self.vertices)
        
        return Point3D(
            x_sum / n,
            y_sum / n,
            z_sum / n if z_sum > 0 else self.floor_level
        )

    def get_bounds(self) -> tuple[float, float, float, float]:
        """Get 2D bounding box (min_x, min_y, max_x, max_y)."""
        if not self.vertices:
            return (0, 0, 0, 0)
        xs = [v.x for v in self.vertices]
        ys = [v.y for v in self.vertices]
        return (min(xs), min(ys), max(xs), max(ys))

    def get_area(self) -> float:
        """Calculate room area using shoelace formula."""
        if len(self.vertices) < 3:
            return 0.0
        
        area = 0.0
        n = len(self.vertices)
        for i in range(n):
            j = (i + 1) % n
            area += self.vertices[i].x * self.vertices[j].y
            area -= self.vertices[j].x * self.vertices[i].y
        return abs(area) / 2.0

    def contains_point_2d(self, point: Point3D) -> bool:
        """Check if 2D point is inside room boundary (ray casting algorithm)."""
        x, y = point.x, point.y
        vertices_2d = [(v.x, v.y) for v in self.vertices]
        n = len(vertices_2d)
        inside = False
        
        p1x, p1y = vertices_2d[0]
        for i in range(1, n + 1):
            p2x, p2y = vertices_2d[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
        
        return inside


@dataclass
class Wall:
    """Represents a wall segment."""
    start: Point3D
    end: Point3D
    layer: str
    thickness: float = 0.0
    height: Optional[float] = None

    def get_length(self) -> float:
        """Calculate wall length."""
        return self.start.distance_to(self.end)

    def get_direction(self) -> tuple[float, float]:
        """Get normalized direction vector (dx, dy)."""
        length = self.get_length()
        if length == 0:
            return (1.0, 0.0)
        dx = self.end.x - self.start.x
        dy = self.end.y - self.start.y
        return (dx / length, dy / length)

    def get_normal(self) -> tuple[float, float]:
        """Get normalized normal vector (perpendicular to wall)."""
        dx, dy = self.get_direction()
        return (-dy, dx)  # Rotate 90 degrees

    def distance_to_point(self, point: Point3D) -> float:
        """Calculate perpendicular distance from point to wall line."""
        # Vector from start to point
        vx = point.x - self.start.x
        vy = point.y - self.start.y
        
        # Wall direction vector
        wx = self.end.x - self.start.x
        wy = self.end.y - self.start.y
        
        wall_len_sq = wx * wx + wy * wy
        if wall_len_sq == 0:
            return math.sqrt(vx * vx + vy * vy)
        
        # Project point onto wall line
        t = (vx * wx + vy * wy) / wall_len_sq
        t = max(0, min(1, t))  # Clamp to segment
        
        # Closest point on wall
        closest_x = self.start.x + t * wx
        closest_y = self.start.y + t * wy
        
        # Distance
        dx = point.x - closest_x
        dy = point.y - closest_y
        return math.sqrt(dx * dx + dy * dy)


@dataclass
class Door:
    """Represents a door as a block insert."""
    position: Point3D
    rotation: float  # degrees
    layer: str
    block_name: str
    width: Optional[float] = None
    swing_angle: Optional[float] = None  # degrees
    swing_direction: Optional[int] = None  # -1 for left, 1 for right, None for auto-detect

    def get_swing_zone(self, swing_radius: float = 900.0) -> list[Point3D]:
        """Estimate door swing zone (arc of possible door positions)."""
        # Default swing is typically 90 degrees
        swing = self.swing_angle or 90.0
        theta = math.radians(self.rotation)
        
        # Door opens perpendicular to rotation
        # Typically opens to the right (clockwise) or left (counter-clockwise)
        swing_offset = 90.0  # Perpendicular to door rotation
        if self.swing_direction == -1:
            swing_offset = -90.0  # Opens to the left
        
        swing_start = math.radians(self.rotation + swing_offset - swing / 2)
        swing_end = math.radians(self.rotation + swing_offset + swing / 2)
        
        points = []
        steps = 10
        for i in range(steps + 1):
            angle = swing_start + (swing_end - swing_start) * i / steps
            x = self.position.x + swing_radius * math.cos(angle)
            y = self.position.y + swing_radius * math.sin(angle)
            points.append(Point3D(x, y, self.position.z))
        
        return points
    
    def get_swing_direction_vector(self) -> tuple[float, float]:
        """
        Get unit vector pointing in the direction where door opens.
        
        Returns:
            (dx, dy) unit vector pointing to swing side
        """
        # Door typically opens perpendicular to its rotation
        # Standard: opens to the right (clockwise) when facing door
        swing_angle = self.rotation + 90.0
        if self.swing_direction == -1:
            swing_angle = self.rotation - 90.0
        
        theta = math.radians(swing_angle)
        return (math.cos(theta), math.sin(theta))


@dataclass
class Window:
    """Represents a window as a block insert or line entity."""
    position: Point3D
    rotation: float  # degrees
    layer: str
    block_name: Optional[str] = None
    width: Optional[float] = None
    height: Optional[float] = None


@dataclass
class FloorLevel:
    """Represents a floor/level."""
    elevation: float
    layer: Optional[str] = None
    name: Optional[str] = None


@dataclass
class CADGeometry:
    """Container for all parsed CAD geometry."""
    rooms: list[Room] = field(default_factory=list)
    walls: list[Wall] = field(default_factory=list)
    doors: list[Door] = field(default_factory=list)
    windows: list[Window] = field(default_factory=list)
    floor_levels: list[FloorLevel] = field(default_factory=list)
    is_3d: bool = False


class GeometryParser:
    """Parser for CAD geometry from DWG/DXF files."""

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.lines: list[str] = []
        self.geometry = CADGeometry()
        self.doc = None

    def parse(self) -> CADGeometry:
        """Parse the CAD file and extract all geometry."""
        # Try using ezdxf first for better parsing
        if EZDXF_AVAILABLE:
            try:
                return self._parse_with_ezdxf()
            except Exception:
                # Fall back to text parsing if ezdxf fails
                pass
        
        # Fallback to text-based parsing
        self.lines = self.file_path.read_text(errors="ignore").splitlines()
        
        # Detect if file contains 3D entities
        self.geometry.is_3d = self._detect_3d()
        
        # Parse entities
        self._parse_rooms()
        self._parse_walls()

        # If no explicit rooms were found but we do have walls,
        # try to infer room polygons from the wall graph.
        if not self.geometry.rooms and self.geometry.walls:
            self._infer_rooms_from_walls()

        self._parse_doors()
        self._parse_windows()
        self._parse_floor_levels()
        
        return self.geometry
    
    def _parse_with_ezdxf(self) -> CADGeometry:
        """Parse using ezdxf library for better accuracy."""
        try:
            # Try to read as DXF first
            self.doc = ezdxf.readfile(str(self.file_path))
        except Exception:
            # If that fails, try reading as DWG (requires ezdxf with DWG support)
            try:
                self.doc = ezdxf.readfile(str(self.file_path))
            except Exception:
                raise
        
        modelspace = self.doc.modelspace()
        
        # Detect 3D
        self.geometry.is_3d = self._detect_3d_ezdxf(modelspace)
        
        # Parse rooms (closed polylines on ROOM layer)
        self._parse_rooms_ezdxf(modelspace)
        
        # Parse walls (lines/polylines on WALL layer)
        self._parse_walls_ezdxf(modelspace)
        
        # Parse doors (INSERT blocks on DOOR layer)
        self._parse_doors_ezdxf(modelspace)
        
        # Parse windows (INSERT blocks on WINDOW layer)
        self._parse_windows_ezdxf(modelspace)
        
        # Parse floor levels
        self._parse_floor_levels()
        
        return self.geometry
    
    def _detect_3d_ezdxf(self, modelspace) -> bool:
        """Detect if file contains 3D entities using ezdxf."""
        for entity in modelspace:
            if entity.dxftype() in ["3DPOLYLINE", "3DFACE", "SOLID", "EXTRUDED_SURFACE"]:
                return True
            # Check if entity has Z coordinates
            if hasattr(entity, "start") and hasattr(entity.start, "z"):
                if entity.start.z != 0:
                    return True
        return False
    
    def _is_room_layer(self, layer_name: str) -> bool:
        """
        Check if layer name indicates a room / space.

        This is intentionally generous – many architects use various
        naming conventions for architectural spaces.
        """
        layer_upper = layer_name.upper()
        room_keywords = [
            "ROOM",
            "SPACE",
            "AREA",
            "ZONE",
            "RM_",
            "A-AREA",
            "A-SPACE",
            "חדר",   # Hebrew: room
            "מרחב",  # Hebrew: space
        ]
        non_room_keywords = [
            "DOOR",
            "WINDOW",
            "WALL",
            "GRID",
            "COL",
            "COLUMN",
            "STAIR",
            "CORE",
            "AXIS",
            "DIM",
            "TEXT",
        ]
        if any(bad in layer_upper for bad in non_room_keywords):
            return False
        return any(keyword in layer_upper for keyword in room_keywords)
    
    def _parse_rooms_ezdxf(self, modelspace) -> None:
        """Parse rooms using ezdxf - flexible layer detection."""
        for entity in modelspace:
            layer_name = entity.dxf.layer.upper()
            entity_type = entity.dxftype()
            
            # Check if it's a potential room entity
            if entity_type not in ["LWPOLYLINE", "POLYLINE", "LINE", "SPLINE"]:
                continue
            
            # Try to detect rooms: either on ROOM layer OR closed polylines
            is_room_layer = self._is_room_layer(layer_name)
            
            if entity_type in ["LWPOLYLINE", "POLYLINE"]:
                try:
                    # Get vertices
                    vertices = []
                    if entity_type == "LWPOLYLINE":
                        for point in entity.vertices():
                            vertices.append(Point3D(point[0], point[1], point[2] if len(point) > 2 else 0.0))
                    else:
                        for vertex in entity.vertices:
                            vertices.append(Point3D(vertex.dxf.location.x, vertex.dxf.location.y, vertex.dxf.location.z))
                    
                    if len(vertices) >= 3:
                        # Check if closed
                        is_closed = False
                        if hasattr(entity.dxf, "flags"):
                            is_closed = bool(entity.dxf.flags & 1)
                        
                        # Check if first and last vertices are close (within 10mm)
                        if not is_closed and len(vertices) >= 3:
                            if vertices[0].distance_to(vertices[-1]) < 10.0:
                                is_closed = True
                        
                        # Accept if: (1) on room layer OR (2) closed polyline with reasonable area
                        if is_room_layer or (is_closed and len(vertices) >= 4):
                            # Calculate area to filter out very small shapes
                            room = Room(
                                vertices=vertices,
                                layer=entity.dxf.layer,
                                floor_level=0.0
                            )
                            area = room.get_area()
                            
                            # Only add if area is reasonable (at least 1 m² = 1,000,000 mm²)
                            if area > 1000000.0:  # 1 square meter minimum
                                floor_level = 0.0
                                if hasattr(entity.dxf, "elevation"):
                                    floor_level = entity.dxf.elevation
                                room.floor_level = floor_level
                                self.geometry.rooms.append(room)
                except Exception:
                    continue
    
    def _is_wall_layer(self, layer_name: str) -> bool:
        """Check if layer name indicates a wall."""
        layer_upper = layer_name.upper()
        wall_keywords = ["WALL", "קיר", "מחיצה"]  # Hebrew: wall, partition
        return any(keyword in layer_upper for keyword in wall_keywords)
    
    def _parse_walls_ezdxf(self, modelspace) -> None:
        """Parse walls using ezdxf - flexible detection."""
        for entity in modelspace:
            layer_name = entity.dxf.layer.upper()
            entity_type = entity.dxftype()
            
            # Check if it's a wall layer
            is_wall_layer = self._is_wall_layer(layer_name)
            
            if entity_type == "LINE" and is_wall_layer:
                try:
                    start = Point3D(
                        entity.dxf.start.x,
                        entity.dxf.start.y,
                        entity.dxf.start.z if hasattr(entity.dxf.start, "z") else 0.0
                    )
                    end = Point3D(
                        entity.dxf.end.x,
                        entity.dxf.end.y,
                        entity.dxf.end.z if hasattr(entity.dxf.end, "z") else 0.0
                    )
                    # Only add if line has reasonable length (at least 100mm)
                    if start.distance_to(end) > 100.0:
                        wall = Wall(
                            start=start,
                            end=end,
                            layer=entity.dxf.layer
                        )
                        self.geometry.walls.append(wall)
                except Exception:
                    continue
            elif entity_type in ["LWPOLYLINE", "POLYLINE"] and is_wall_layer:
                try:
                    # Convert polyline segments to wall segments
                    vertices = []
                    if entity_type == "LWPOLYLINE":
                        for point in entity.vertices():
                            vertices.append((point[0], point[1], point[2] if len(point) > 2 else 0.0))
                    else:
                        for vertex in entity.vertices:
                            vertices.append((vertex.dxf.location.x, vertex.dxf.location.y, vertex.dxf.location.z))
                    
                    for i in range(len(vertices) - 1):
                        v1 = vertices[i]
                        v2 = vertices[i + 1]
                        # Only add if segment has reasonable length
                        if math.sqrt((v2[0]-v1[0])**2 + (v2[1]-v1[1])**2) > 100.0:
                            wall = Wall(
                                start=Point3D(v1[0], v1[1], v1[2]),
                                end=Point3D(v2[0], v2[1], v2[2]),
                                layer=entity.dxf.layer
                            )
                            self.geometry.walls.append(wall)
                except Exception:
                    continue
    
    def _is_door_layer(self, layer_name: str) -> bool:
        """Check if layer name indicates a door."""
        layer_upper = layer_name.upper()
        door_keywords = ["DOOR", "דלת", "פתח"]  # Hebrew: door, opening
        return any(keyword in layer_upper for keyword in door_keywords)
    
    def _is_door_block(self, block_name: str) -> bool:
        """Check if block name indicates a door."""
        block_upper = block_name.upper()
        door_keywords = ["DOOR", "דלת", "פתח"]
        return any(keyword in block_upper for keyword in door_keywords)
    
    def _parse_doors_ezdxf(self, modelspace) -> None:
        """Parse doors using ezdxf - flexible detection."""
        for entity in modelspace:
            if entity.dxftype() != "INSERT":
                continue
            
            layer_name = entity.dxf.layer.upper()
            block_name = entity.dxf.name.upper()
            
            # Check if it's a door: on DOOR layer OR has door in block name
            is_door_layer = self._is_door_layer(layer_name)
            is_door_block = self._is_door_block(block_name)
            
            if is_door_layer or is_door_block:
                try:
                    insert_point = entity.dxf.insert
                    rotation = entity.dxf.rotation if hasattr(entity.dxf, "rotation") else 0.0
                    
                    # Try to get door width from attributes or block definition
                    width = None
                    if hasattr(entity, "attribs"):
                        for attrib in entity.attribs:
                            if attrib.dxf.tag.upper() in ["WIDTH", "W", "רוחב"]:
                                try:
                                    width = float(attrib.dxf.text)
                                except ValueError:
                                    pass
                    
                    # If width not found, try to get from block scale
                    if width is None and hasattr(entity.dxf, "xscale"):
                        # Sometimes door width is encoded in scale
                        scale = entity.dxf.xscale
                        if 0.5 < scale < 2.0:  # Reasonable door width range
                            width = scale * 1000.0  # Approximate conversion
                    
                    door = Door(
                        position=Point3D(insert_point.x, insert_point.y, insert_point.z if hasattr(insert_point, "z") else 0.0),
                        rotation=math.degrees(rotation) if rotation else 0.0,
                        layer=entity.dxf.layer,
                        block_name=entity.dxf.name,
                        width=width
                    )
                    self.geometry.doors.append(door)
                except Exception:
                    continue
    
    def _parse_windows_ezdxf(self, modelspace) -> None:
        """Parse windows using ezdxf."""
        for entity in modelspace:
            layer_name = entity.dxf.layer.upper()
            if "WINDOW" not in layer_name:
                continue
            
            if entity.dxftype() == "INSERT":
                try:
                    insert_point = entity.dxf.insert
                    rotation = entity.dxf.rotation if hasattr(entity.dxf, "rotation") else 0.0
                    block_name = entity.dxf.name
                    
                    window = Window(
                        position=Point3D(insert_point.x, insert_point.y, insert_point.z if hasattr(insert_point, "z") else 0.0),
                        rotation=math.degrees(rotation) if rotation else 0.0,
                        layer=entity.dxf.layer,
                        block_name=block_name
                    )
                    self.geometry.windows.append(window)
                except Exception:
                    continue

    def _detect_3d(self) -> bool:
        """Detect if file contains 3D entities."""
        for i, line in enumerate(self.lines):
            if line.strip() == "0":
                if i + 1 < len(self.lines):
                    entity_type = self.lines[i + 1].strip().upper()
                    if entity_type in ["3DPOLYLINE", "3DFACE", "SOLID", "EXTRUDED_SURFACE"]:
                        return True
        return False

    def _parse_rooms(self) -> None:
        """Parse room entities (closed LWPOLYLINE/POLYLINE on ROOM layer or any closed polyline)."""
        i = 0
        current_entity = None
        current_layer = None
        vertices: list[Point3D] = []
        pending_x: Optional[float] = None
        pending_y: Optional[float] = None
        pending_z: Optional[float] = None
        floor_level = 0.0
        is_closed = False
        
        while i < len(self.lines) - 1:
            code = self.lines[i].strip()
            value = self.lines[i + 1].strip()
            
            if code == "0":
                # Finalize previous room
                if current_entity in ["LWPOLYLINE", "POLYLINE"]:
                    is_room_layer = current_layer and self._is_room_layer(current_layer)
                    if len(vertices) >= 3 and (is_room_layer or (is_closed and len(vertices) >= 4)):
                        room = Room(
                            vertices=list(vertices),
                            layer=current_layer or "UNKNOWN",
                            floor_level=floor_level
                        )
                        # Avoid tiny artifacts but be generous on area threshold
                        if room.get_area() > 1.0:
                            self.geometry.rooms.append(room)
                
                # Start new entity
                current_entity = value
                current_layer = None
                vertices = []
                pending_x = pending_y = pending_z = None
                floor_level = 0.0
                is_closed = False
            
            elif code == "8":  # Layer
                current_layer = value
            
            elif code == "70":  # Flags (for closed polyline)
                try:
                    flags = int(value)
                    is_closed = bool(flags & 1)  # Bit 1 = closed polyline
                except ValueError:
                    pass
            
            elif code == "38":  # Elevation (Z for 2D)
                try:
                    floor_level = float(value)
                except ValueError:
                    pass
            
        # Collect vertices
        if current_entity in ["LWPOLYLINE", "POLYLINE"]:
            # Many 2D LWPOLYLINEs only provide 10/20 (X/Y) pairs; Z is optional.
            if code == "10":  # X
                try:
                    pending_x = float(value)
                except ValueError:
                    pending_x = None
            elif code == "20":  # Y
                try:
                    pending_y = float(value)
                except ValueError:
                    pending_y = None
                # When we have an X/Y pair, create a vertex immediately.
                if pending_x is not None:
                    z = pending_z if pending_z is not None else floor_level
                    vertices.append(Point3D(pending_x, pending_y if pending_y is not None else 0.0, z))
                    pending_x = pending_y = pending_z = None
            elif code == "30":  # Z (optional)
                try:
                    pending_z = float(value)
                except ValueError:
                    pending_z = None
            
            i += 2
        
        # Finalize last room
        if current_entity in ["LWPOLYLINE", "POLYLINE"]:
            is_room_layer = current_layer and self._is_room_layer(current_layer)
            if len(vertices) >= 3 and (is_room_layer or (is_closed and len(vertices) >= 4)):
                room = Room(
                    vertices=list(vertices),
                    layer=current_layer or "UNKNOWN",
                    floor_level=floor_level
                )
                if room.get_area() > 1.0:
                    self.geometry.rooms.append(room)

    def _parse_walls(self) -> None:
        """Parse wall entities (LINE on WALL layer)."""
        i = 0
        current_entity = None
        current_layer = None
        start_point: Optional[Point3D] = None
        end_point: Optional[Point3D] = None
        pending_x: Optional[float] = None
        pending_y: Optional[float] = None
        pending_z: Optional[float] = None
        
        while i < len(self.lines) - 1:
            code = self.lines[i].strip()
            value = self.lines[i + 1].strip()
            
            if code == "0":
                # Finalize previous wall
                if current_entity == "LINE" and current_layer and self._is_wall_layer(current_layer):
                    if start_point and end_point:
                        # Only add if line has reasonable length
                        if start_point.distance_to(end_point) > 100.0:
                            wall = Wall(
                                start=start_point,
                                end=end_point,
                                layer=current_layer
                            )
                            self.geometry.walls.append(wall)
                
                # Start new entity
                current_entity = value
                current_layer = None
                start_point = end_point = None
                pending_x = pending_y = pending_z = None
            
            elif code == "8":  # Layer
                current_layer = value
            
            # Collect LINE endpoints
            if current_entity == "LINE":
                if code == "10":  # Start X
                    try:
                        pending_x = float(value)
                    except ValueError:
                        pass
                elif code == "20":  # Start Y
                    try:
                        pending_y = float(value)
                    except ValueError:
                        pass
                elif code == "30":  # Start Z
                    try:
                        pending_z = float(value)
                    except ValueError:
                        pass
                    if pending_x is not None and pending_y is not None:
                        z = pending_z if pending_z is not None else 0.0
                        start_point = Point3D(pending_x, pending_y, z)
                        pending_x = pending_y = pending_z = None
                elif code == "11":  # End X
                    try:
                        pending_x = float(value)
                    except ValueError:
                        pass
                elif code == "21":  # End Y
                    try:
                        pending_y = float(value)
                    except ValueError:
                        pass
                elif code == "31":  # End Z
                    try:
                        pending_z = float(value)
                    except ValueError:
                        pass
                    if pending_x is not None and pending_y is not None:
                        z = pending_z if pending_z is not None else 0.0
                        end_point = Point3D(pending_x, pending_y, z)
                        pending_x = pending_y = pending_z = None
            
            i += 2
        
        # Finalize last wall
        if current_entity == "LINE" and current_layer and self._is_wall_layer(current_layer):
            if start_point and end_point and start_point.distance_to(end_point) > 100.0:
                wall = Wall(
                    start=start_point,
                    end=end_point,
                    layer=current_layer
                )
                self.geometry.walls.append(wall)

    def _infer_rooms_from_walls(self) -> None:
        """
        Infer room polygons from the wall network using shapely.polygonize.

        This is a best-effort heuristic for architectural plans that don't
        contain explicit room polylines. It:
        - Builds line strings from wall segments
        - Polygonizes them into closed cells
        - Filters out very small polygons
        - Skips the outermost boundary polygon (overall building outline)
        """
        if not SHAPELY_AVAILABLE:
            return

        if not self.geometry.walls:
            return

        # Build LineStrings from wall segments (2D only).
        lines: list[LineString] = []
        for wall in self.geometry.walls:
            p1 = (wall.start.x, wall.start.y)
            p2 = (wall.end.x, wall.end.y)
            # Skip degenerate segments
            if p1 == p2:
                continue
            lines.append(LineString([p1, p2]))

        if not lines:
            return

        try:
            polys = list(polygonize(lines))
        except Exception:
            return

        if not polys:
            return

        # Heuristics:
        # - Ignore polygons that are extremely tiny (noise)
        #   Use a very small threshold so halls, toilets, and other areas
        #   are all considered rooms.
        MIN_ROOM_AREA = 1000.0

        for poly in polys:
            area = poly.area
            if area < MIN_ROOM_AREA:
                continue

            # Convert polygon exterior to a Room.
            coords = list(poly.exterior.coords)
            vertices = [Point3D(x=c[0], y=c[1], z=0.0) for c in coords]
            if len(vertices) < 3:
                continue

            room = Room(
                vertices=vertices,
                layer="INFERRED_ROOM",
                floor_level=0.0,
            )
            self.geometry.rooms.append(room)

    def _parse_doors(self) -> None:
        """Parse door entities (INSERT blocks on DOOR layer or with door in block name)."""
        i = 0
        current_entity = None
        current_layer = None
        insert_x: Optional[float] = None
        insert_y: Optional[float] = None
        insert_z: Optional[float] = None
        rotation: float = 0.0
        block_name: str = ""
        
        while i < len(self.lines) - 1:
            code = self.lines[i].strip()
            value = self.lines[i + 1].strip()
            
            if code == "0":
                # Finalize previous door
                if current_entity == "INSERT":
                    is_door_layer = current_layer and self._is_door_layer(current_layer)
                    is_door_block = self._is_door_block(block_name)
                    
                    if (is_door_layer or is_door_block) and insert_x is not None and insert_y is not None:
                        z = insert_z if insert_z is not None else 0.0
                        door = Door(
                            position=Point3D(insert_x, insert_y, z),
                            rotation=rotation,
                            layer=current_layer or "UNKNOWN",
                            block_name=block_name
                        )
                        self.geometry.doors.append(door)
                
                # Start new entity
                current_entity = value
                current_layer = None
                insert_x = insert_y = insert_z = None
                rotation = 0.0
                block_name = ""
            
            elif code == "8":  # Layer
                current_layer = value
            
            elif code == "2":  # Block name
                block_name = value
            
            elif code == "10":  # Insert X
                try:
                    insert_x = float(value)
                except ValueError:
                    pass
            elif code == "20":  # Insert Y
                try:
                    insert_y = float(value)
                except ValueError:
                    pass
            elif code == "30":  # Insert Z
                try:
                    insert_z = float(value)
                except ValueError:
                    pass
            elif code == "50":  # Rotation
                try:
                    rotation = float(value)
                except ValueError:
                    pass
            
            i += 2
        
        # Finalize last door
        if current_entity == "INSERT":
            is_door_layer = current_layer and self._is_door_layer(current_layer)
            is_door_block = self._is_door_block(block_name)
            
            if (is_door_layer or is_door_block) and insert_x is not None and insert_y is not None:
                z = insert_z if insert_z is not None else 0.0
                door = Door(
                    position=Point3D(insert_x, insert_y, z),
                    rotation=rotation,
                    layer=current_layer or "UNKNOWN",
                    block_name=block_name
                )
                self.geometry.doors.append(door)

    def _parse_windows(self) -> None:
        """Parse window entities (INSERT blocks on WINDOW layer)."""
        i = 0
        current_entity = None
        current_layer = None
        insert_x: Optional[float] = None
        insert_y: Optional[float] = None
        insert_z: Optional[float] = None
        rotation: float = 0.0
        block_name: str = ""
        
        while i < len(self.lines) - 1:
            code = self.lines[i].strip()
            value = self.lines[i + 1].strip()
            
            if code == "0":
                # Finalize previous window
                if current_entity == "INSERT" and current_layer and "WINDOW" in current_layer.upper():
                    if insert_x is not None and insert_y is not None:
                        z = insert_z if insert_z is not None else 0.0
                        window = Window(
                            position=Point3D(insert_x, insert_y, z),
                            rotation=rotation,
                            layer=current_layer,
                            block_name=block_name
                        )
                        self.geometry.windows.append(window)
                
                # Start new entity
                current_entity = value
                current_layer = None
                insert_x = insert_y = insert_z = None
                rotation = 0.0
                block_name = ""
            
            elif code == "8":  # Layer
                current_layer = value
            
            elif code == "2":  # Block name
                block_name = value
            
            elif code == "10":  # Insert X
                try:
                    insert_x = float(value)
                except ValueError:
                    pass
            elif code == "20":  # Insert Y
                try:
                    insert_y = float(value)
                except ValueError:
                    pass
            elif code == "30":  # Insert Z
                try:
                    insert_z = float(value)
                except ValueError:
                    pass
            elif code == "50":  # Rotation
                try:
                    rotation = float(value)
                except ValueError:
                    pass
            
            i += 2
        
        # Finalize last window
        if current_entity == "INSERT" and current_layer and "WINDOW" in current_layer.upper():
            if insert_x is not None and insert_y is not None:
                z = insert_z if insert_z is not None else 0.0
                window = Window(
                    position=Point3D(insert_x, insert_y, z),
                    rotation=rotation,
                    layer=current_layer,
                    block_name=block_name
                )
                self.geometry.windows.append(window)

    def _parse_floor_levels(self) -> None:
        """Parse floor levels from Z elevations, layers, or groups."""
        # Collect unique Z elevations from rooms
        elevations = set()
        layer_to_elevation: dict[str, float] = {}
        
        for room in self.geometry.rooms:
            if room.floor_level != 0.0:
                elevations.add(room.floor_level)
            if room.layer:
                # Try to extract level from layer name (e.g., "LEVEL_1", "FLOOR_2")
                layer_upper = room.layer.upper()
                if "LEVEL" in layer_upper or "FLOOR" in layer_upper:
                    # Store layer association
                    layer_to_elevation[room.layer] = room.floor_level
        
        # Create floor level objects
        for elevation in sorted(elevations):
            level = FloorLevel(elevation=elevation)
            # Find associated layer
            for layer, elev in layer_to_elevation.items():
                if elev == elevation:
                    level.layer = layer
                    break
            self.geometry.floor_levels.append(level)
        
        # If no levels found, create default ground level
        if not self.geometry.floor_levels:
            self.geometry.floor_levels.append(FloorLevel(elevation=0.0, name="Ground Level"))

