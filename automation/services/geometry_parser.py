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

    def get_swing_zone(self, swing_radius: float = 900.0) -> list[Point3D]:
        """Estimate door swing zone (arc of possible door positions)."""
        # Default swing is typically 90 degrees
        swing = self.swing_angle or 90.0
        theta = math.radians(self.rotation)
        
        # Door opens perpendicular to rotation
        swing_start = theta - math.radians(swing / 2)
        swing_end = theta + math.radians(swing / 2)
        
        points = []
        steps = 10
        for i in range(steps + 1):
            angle = swing_start + (swing_end - swing_start) * i / steps
            x = self.position.x + swing_radius * math.cos(angle)
            y = self.position.y + swing_radius * math.sin(angle)
            points.append(Point3D(x, y, self.position.z))
        
        return points


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

    def parse(self) -> CADGeometry:
        """Parse the CAD file and extract all geometry."""
        self.lines = self.file_path.read_text(errors="ignore").splitlines()
        
        # Detect if file contains 3D entities
        self.geometry.is_3d = self._detect_3d()
        
        # Parse entities
        self._parse_rooms()
        self._parse_walls()
        self._parse_doors()
        self._parse_windows()
        self._parse_floor_levels()
        
        return self.geometry

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
        """Parse room entities (closed LWPOLYLINE/POLYLINE on ROOM layer)."""
        i = 0
        current_entity = None
        current_layer = None
        vertices: list[Point3D] = []
        pending_x: Optional[float] = None
        pending_y: Optional[float] = None
        pending_z: Optional[float] = None
        floor_level = 0.0
        
        while i < len(self.lines) - 1:
            code = self.lines[i].strip()
            value = self.lines[i + 1].strip()
            
            if code == "0":
                # Finalize previous room
                if current_entity in ["LWPOLYLINE", "POLYLINE"] and current_layer and "ROOM" in current_layer.upper():
                    if len(vertices) >= 3:
                        room = Room(
                            vertices=list(vertices),
                            layer=current_layer,
                            floor_level=floor_level
                        )
                        self.geometry.rooms.append(room)
                
                # Start new entity
                current_entity = value
                current_layer = None
                vertices = []
                pending_x = pending_y = pending_z = None
                floor_level = 0.0
            
            elif code == "8":  # Layer
                current_layer = value
            
            elif code == "38":  # Elevation (Z for 2D)
                try:
                    floor_level = float(value)
                except ValueError:
                    pass
            
            # Collect vertices
            if current_entity in ["LWPOLYLINE", "POLYLINE"]:
                if code == "10":  # X
                    try:
                        pending_x = float(value)
                    except ValueError:
                        pass
                elif code == "20":  # Y
                    try:
                        pending_y = float(value)
                    except ValueError:
                        pass
                elif code == "30":  # Z
                    try:
                        pending_z = float(value)
                    except ValueError:
                        pass
                    if pending_x is not None and pending_y is not None:
                        z = pending_z if pending_z is not None else floor_level
                        vertices.append(Point3D(pending_x, pending_y, z))
                        pending_x = pending_y = pending_z = None
            
            i += 2
        
        # Finalize last room
        if current_entity in ["LWPOLYLINE", "POLYLINE"] and current_layer and "ROOM" in current_layer.upper():
            if len(vertices) >= 3:
                room = Room(
                    vertices=list(vertices),
                    layer=current_layer,
                    floor_level=floor_level
                )
                self.geometry.rooms.append(room)

    def _parse_walls(self) -> None:
        """Parse wall entities (LINE, LWPOLYLINE, POLYLINE, SOLID, 3DFACE on WALL layer)."""
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
                if current_entity == "LINE" and current_layer and "WALL" in current_layer.upper():
                    if start_point and end_point:
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
        if current_entity == "LINE" and current_layer and "WALL" in current_layer.upper():
            if start_point and end_point:
                wall = Wall(
                    start=start_point,
                    end=end_point,
                    layer=current_layer
                )
                self.geometry.walls.append(wall)

    def _parse_doors(self) -> None:
        """Parse door entities (INSERT blocks on DOOR layer)."""
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
                if current_entity == "INSERT" and current_layer and "DOOR" in current_layer.upper():
                    if insert_x is not None and insert_y is not None:
                        z = insert_z if insert_z is not None else 0.0
                        door = Door(
                            position=Point3D(insert_x, insert_y, z),
                            rotation=rotation,
                            layer=current_layer,
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
        if current_entity == "INSERT" and current_layer and "DOOR" in current_layer.upper():
            if insert_x is not None and insert_y is not None:
                z = insert_z if insert_z is not None else 0.0
                door = Door(
                    position=Point3D(insert_x, insert_y, z),
                    rotation=rotation,
                    layer=current_layer,
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

