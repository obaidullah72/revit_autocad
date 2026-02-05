"""
Spatial understanding module for CAD geometry.

Identifies spatial relationships between rooms, walls, doors, windows,
and floor levels to support electrical component placement.
"""

from typing import Optional
import math

from .geometry_parser import (
    Room, Wall, Door, Window, FloorLevel, CADGeometry, Point3D
)


class SpatialAnalyzer:
    """Analyzes spatial relationships in CAD geometry."""

    def __init__(self, geometry: CADGeometry):
        self.geometry = geometry

    # ------------------------------------------------------------------
    # Room classification helpers
    # ------------------------------------------------------------------
    def classify_room_type(self, room: Room) -> str:
        """
        Classify a room as 'ROOM', 'HALL', or 'OPEN_AREA'.

        This is a heuristic based primarily on:
        - Layer name keywords (HALL, CORRIDOR, LOBBY, etc.)
        - 2D area (small/medium/very large)
        - Aspect ratio (very long and narrow → hall/corridor)

        Returns:
            One of: "ROOM", "HALL", "OPEN_AREA"
        """
        # 1) Layer-name driven classification (strongest signal)
        layer_upper = (room.layer or "").upper()
        hall_keywords = [
            "HALL",
            "CORRIDOR",
            "CORR",
            "PASSAGE",
            "LOBBY",
            "FOYER",
            "LIFTL",  # lift lobby variants
            "LOBBY",
        ]
        open_area_keywords = [
            "OPEN",
            "ATRIUM",
            "COURT",
            "VOID",
        ]

        if any(k in layer_upper for k in hall_keywords):
            return "HALL"
        if any(k in layer_upper for k in open_area_keywords):
            return "OPEN_AREA"

        # 2) Geometric heuristics
        area = room.get_area()  # in mm²
        min_x, min_y, max_x, max_y = room.get_bounds()
        width = max_x - min_x
        height = max_y - min_y
        longer = max(width, height) or 1.0
        shorter = min(width, height) or 1.0
        aspect_ratio = longer / shorter

        # Rough thresholds (can be tuned per project):
        # - Very large & fairly regular → open area
        # - Very elongated → hall / corridor
        # - Everything else → room
        VERY_LARGE_AREA = 80_000_000.0   # ~80 m²
        ELONGATED_RATIO = 3.0

        if area >= VERY_LARGE_AREA:
            return "OPEN_AREA"

        if aspect_ratio >= ELONGATED_RATIO:
            return "HALL"

        return "ROOM"

    def find_room_for_point(self, point: Point3D) -> Optional[Room]:
        """Find the room containing a given point."""
        for room in self.geometry.rooms:
            if room.contains_point_2d(point):
                return room
        return None

    def find_nearest_wall(self, point: Point3D) -> Optional[Wall]:
        """Find the nearest wall to a given point."""
        if not self.geometry.walls:
            return None
        
        nearest_wall = None
        min_distance = float('inf')
        
        for wall in self.geometry.walls:
            distance = wall.distance_to_point(point)
            if distance < min_distance:
                min_distance = distance
                nearest_wall = wall
        
        return nearest_wall

    def find_doors_for_room(self, room: Room) -> list[Door]:
        """Find all doors associated with a room."""
        doors = []
        for door in self.geometry.doors:
            # Check if door is near room boundary or inside room
            if room.contains_point_2d(door.position):
                doors.append(door)
            else:
                # Check if door is near room boundary (within 500mm)
                min_dist_to_boundary = self._distance_to_room_boundary(room, door.position)
                if min_dist_to_boundary < 500.0:
                    doors.append(door)
        return doors

    def find_windows_for_room(self, room: Room) -> list[Window]:
        """Find all windows associated with a room."""
        windows = []
        for window in self.geometry.windows:
            if room.contains_point_2d(window.position):
                windows.append(window)
        return windows

    def find_walls_for_room(self, room: Room) -> list[Wall]:
        """Find walls that form the boundary of a room."""
        walls = []
        room_vertices = room.vertices
        
        # Match walls that align with room boundary segments
        for i in range(len(room_vertices)):
            v1 = room_vertices[i]
            v2 = room_vertices[(i + 1) % len(room_vertices)]
            
            # Find walls that match this segment
            for wall in self.geometry.walls:
                # Check if wall endpoints are close to room vertices
                dist1_to_start = math.sqrt(
                    (wall.start.x - v1.x) ** 2 + (wall.start.y - v1.y) ** 2
                )
                dist2_to_end = math.sqrt(
                    (wall.end.x - v2.x) ** 2 + (wall.end.y - v2.y) ** 2
                )
                
                # Also check reverse direction
                dist1_to_end = math.sqrt(
                    (wall.end.x - v1.x) ** 2 + (wall.end.y - v1.y) ** 2
                )
                dist2_to_start = math.sqrt(
                    (wall.start.x - v2.x) ** 2 + (wall.start.y - v2.y) ** 2
                )
                
                # If wall aligns with room boundary (within 100mm tolerance)
                tolerance = 100.0
                if (dist1_to_start < tolerance and dist2_to_end < tolerance) or \
                   (dist1_to_end < tolerance and dist2_to_start < tolerance):
                    if wall not in walls:
                        walls.append(wall)
        
        return walls

    def get_ceiling_height(self, room: Room) -> float:
        """Get ceiling height for a room (default 2700mm if not specified)."""
        if room.ceiling_height is not None:
            return room.ceiling_height
        
        # Default ceiling height: 2700mm (standard residential)
        return 2700.0

    def get_floor_level(self, room: Room) -> float:
        """Get floor level elevation for a room."""
        return room.floor_level

    def get_wall_surface_point(
        self,
        wall: Wall,
        point_on_wall: Point3D,
        offset_from_wall: float = 0.0,
        height: float = 1400.0
    ) -> Point3D:
        """
        Get a point on the wall surface at specified height.
        
        Args:
            wall: The wall segment
            point_on_wall: Point along the wall line
            offset_from_wall: Offset perpendicular to wall (positive = inside room)
            height: Height from floor level (default 1400mm for switches)
        """
        # Calculate position along wall
        wall_dir = wall.get_direction()
        wall_normal = wall.get_normal()
        
        # Project point onto wall line
        vx = point_on_wall.x - wall.start.x
        vy = point_on_wall.y - wall.start.y
        wx = wall.end.x - wall.start.x
        wy = wall.end.y - wall.start.y
        
        wall_len_sq = wx * wx + wy * wy
        if wall_len_sq == 0:
            t = 0.0
        else:
            t = (vx * wx + vy * wy) / wall_len_sq
            t = max(0, min(1, t))
        
        # Position along wall
        x = wall.start.x + t * wx
        y = wall.start.y + t * wy
        
        # Apply perpendicular offset
        x += offset_from_wall * wall_normal[0]
        y += offset_from_wall * wall_normal[1]
        
        # Z is floor level + height
        z = wall.start.z + height
        
        return Point3D(x, y, z)

    def get_ceiling_center(self, room: Room) -> Point3D:
        """Get center point on ceiling plane for a room."""
        centroid = room.get_centroid()
        ceiling_height = self.get_ceiling_height(room)
        floor_level = self.get_floor_level(room)
        
        return Point3D(
            centroid.x,
            centroid.y,
            floor_level + ceiling_height
        )

    def is_bathroom(self, room: Room) -> bool:
        """Infer if room is a bathroom based on layer name or size."""
        layer_upper = room.layer.upper()
        if "BATH" in layer_upper or "WC" in layer_upper or "TOILET" in layer_upper:
            return True
        
        # Small rooms (< 5 sqm) might be bathrooms
        area = room.get_area()
        if area < 5000000.0:  # 5 sqm in mm²
            return False  # Don't assume small = bathroom
        
        return False

    def is_small_space(self, room: Room, min_area: float = 10000000.0) -> bool:
        """Check if room is a small space (default < 10 sqm)."""
        return room.get_area() < min_area

    def _distance_to_room_boundary(self, room: Room, point: Point3D) -> float:
        """Calculate minimum distance from point to room boundary."""
        min_dist = float('inf')
        vertices = room.vertices
        
        for i in range(len(vertices)):
            v1 = vertices[i]
            v2 = vertices[(i + 1) % len(vertices)]
            
            # Distance to line segment
            vx = point.x - v1.x
            vy = point.y - v1.y
            wx = v2.x - v1.x
            wy = v2.y - v1.y
            
            wall_len_sq = wx * wx + wy * wy
            if wall_len_sq == 0:
                dist = math.sqrt(vx * vx + vy * vy)
            else:
                t = (vx * wx + vy * wy) / wall_len_sq
                t = max(0, min(1, t))
                closest_x = v1.x + t * wx
                closest_y = v1.y + t * wy
                dist = math.sqrt(
                    (point.x - closest_x) ** 2 + (point.y - closest_y) ** 2
                )
            
            min_dist = min(min_dist, dist)
        
        return min_dist

    def get_door_swing_side(self, door: Door, room: Room) -> tuple[float, float]:
        """
        Determine which side of the door opens (swing side).
        
        Returns:
            Normal vector pointing to the swing side (where door opens)
        """
        # Find the wall the door is on
        nearest_wall = self.find_nearest_wall(door.position)
        if not nearest_wall:
            # Fallback: use door rotation + 90 degrees
            theta = math.radians(door.rotation + 90.0)
            return (math.cos(theta), math.sin(theta))
        
        # Get wall normal (perpendicular to wall)
        wall_normal = nearest_wall.get_normal()
        
        # Determine which side of the wall is inside the room
        # Test both normals to see which points into the room
        test_point_1 = Point3D(
            door.position.x + wall_normal[0] * 100.0,
            door.position.y + wall_normal[1] * 100.0,
            door.position.z
        )
        test_point_2 = Point3D(
            door.position.x - wall_normal[0] * 100.0,
            door.position.y - wall_normal[1] * 100.0,
            door.position.z
        )
        
        # The side inside the room is where the door opens
        if room.contains_point_2d(test_point_1):
            return wall_normal
        elif room.contains_point_2d(test_point_2):
            return (-wall_normal[0], -wall_normal[1])
        
        # Fallback: use door rotation to estimate swing
        # Door typically opens perpendicular to its rotation
        swing_angle = door.rotation + 90.0
        theta = math.radians(swing_angle)
        return (math.cos(theta), math.sin(theta))
    
    def avoid_door_swing_zone(
        self,
        door: Door,
        candidate_point: Point3D,
        clearance: float = 1000.0
    ) -> bool:
        """Check if point is in door swing zone."""
        swing_zone = door.get_swing_zone(swing_radius=clearance)
        
        # Check if candidate point is inside swing zone polygon
        # Simple check: distance to door position
        dist_to_door = door.position.distance_to(candidate_point)
        if dist_to_door < clearance:
            # Check angle - if point is in swing arc
            dx = candidate_point.x - door.position.x
            dy = candidate_point.y - door.position.y
            angle = math.degrees(math.atan2(dy, dx))
            door_angle = door.rotation
            
            # Normalize angles
            angle_diff = abs(angle - door_angle)
            if angle_diff > 180:
                angle_diff = 360 - angle_diff
            
            # If within 90 degrees of door rotation, likely in swing zone
            if angle_diff < 90:
                return True
        
        return False

    def avoid_window_zone(
        self,
        window: Window,
        candidate_point: Point3D,
        clearance: float = 500.0
    ) -> bool:
        """Check if point is too close to window."""
        return window.position.distance_to(candidate_point) < clearance

