"""
Deterministic placement rules for electrical components.

Implements engineering-grade placement rules for switches, lights,
fans, and sockets based on CAD geometry and spatial analysis.
"""

from typing import Optional
import math

from .geometry_parser import Room, Wall, Door, Window, Point3D, CADGeometry
from .spatial_analyzer import SpatialAnalyzer


class PlacementRules:
    """Deterministic placement rules for electrical components."""

    # Standard dimensions (in mm)
    SWITCH_HEIGHT = 1400.0  # Standard switch height from finished floor
    SOCKET_HEIGHT = 300.0   # Standard socket height from finished floor
    MIN_CLEARANCE_SWITCH_DOOR = 200.0  # Minimum clearance from door
    MIN_CLEARANCE_SWITCH_WINDOW = 300.0  # Minimum clearance from window
    MIN_CLEARANCE_LIGHT_BEAM = 500.0  # Minimum clearance from beams/obstructions
    SOCKET_SPACING = 3000.0  # Standard socket spacing along walls
    MIN_ROOM_AREA_FOR_FAN = 10000000.0  # 10 sqm minimum for fan

    def __init__(self, geometry: CADGeometry, analyzer: SpatialAnalyzer):
        self.geometry = geometry
        self.analyzer = analyzer

    def place_switches_for_door(
        self,
        door: Door,
        room: Room,
        count: int = 1
    ) -> list[Point3D]:
        """
        Place switches near a door along the wall.
        
        Rules:
        - Place on wall surface
        - Near corresponding door
        - Height: ~1400mm from finished floor level
        - Avoid door swing and window zones
        """
        placements: list[Point3D] = []
        
        # Find nearest wall to door
        nearest_wall = self.analyzer.find_nearest_wall(door.position)
        if not nearest_wall:
            # Fallback: place switches offset from door
            wall_normal = self._get_door_wall_normal(door)
            for i in range(count):
                offset = 300.0 + i * 300.0  # 300mm spacing
                x = door.position.x + wall_normal[0] * offset
                y = door.position.y + wall_normal[1] * offset
                z = self.analyzer.get_floor_level(room) + self.SWITCH_HEIGHT
                placements.append(Point3D(x, y, z))
            return placements
        
        # Place switches along wall, avoiding door swing zone
        wall_dir = nearest_wall.get_direction()
        wall_normal = nearest_wall.get_normal()
        
        # Project door onto wall line
        door_proj = self._project_point_to_wall(nearest_wall, door.position)
        
        # Start placement offset from door (to the right side, typically)
        start_offset = 300.0  # Start 300mm from door
        spacing = 300.0  # 300mm between switches
        
        for i in range(count):
            # Calculate position along wall
            offset = start_offset + i * spacing
            
            # Position along wall direction
            x = door_proj.x + wall_dir[0] * offset
            y = door_proj.y + wall_dir[1] * offset
            
            # Ensure point is on wall surface (with small offset inside room)
            wall_surface_point = self.analyzer.get_wall_surface_point(
                nearest_wall,
                Point3D(x, y, 0),
                offset_from_wall=10.0,  # 10mm inside room
                height=self.SWITCH_HEIGHT
            )
            
            # Check if placement avoids door swing zone
            if not self.analyzer.avoid_door_swing_zone(
                door,
                wall_surface_point,
                clearance=1000.0
            ):
                # Check if placement avoids windows
                windows = self.analyzer.find_windows_for_room(room)
                too_close_to_window = False
                for window in windows:
                    if self.analyzer.avoid_window_zone(
                        window,
                        wall_surface_point,
                        clearance=self.MIN_CLEARANCE_SWITCH_WINDOW
                    ):
                        too_close_to_window = True
                        break
                
                if not too_close_to_window:
                    placements.append(wall_surface_point)
        
        return placements

    def place_lights_for_room(
        self,
        room: Room,
        count: int = 1
    ) -> list[Point3D]:
        """
        Place lights in a room.
        
        Rules:
        - Place at room centroid (2D) or on ceiling plane (3D)
        - For 3D: place on ceiling plane
        - Maintain clearance from beams or obstructions
        """
        placements: list[Point3D] = []
        
        if count == 1:
            # Single light at centroid
            if self.geometry.is_3d:
                ceiling_center = self.analyzer.get_ceiling_center(room)
                placements.append(ceiling_center)
            else:
                centroid = room.get_centroid()
                floor_level = self.analyzer.get_floor_level(room)
                ceiling_height = self.analyzer.get_ceiling_height(room)
                placements.append(Point3D(
                    centroid.x,
                    centroid.y,
                    floor_level + ceiling_height
                ))
        else:
            # Multiple lights: arrange in grid
            bounds = room.get_bounds()
            min_x, min_y, max_x, max_y = bounds
            width = max_x - min_x
            height = max_y - min_y
            
            # Calculate grid dimensions
            cols = int(math.ceil(math.sqrt(count)))
            rows = int(math.ceil(count / cols))
            
            # Spacing with margins
            margin_x = width * 0.15
            margin_y = height * 0.15
            step_x = (width - 2 * margin_x) / (cols + 1) if cols > 1 else 0
            step_y = (height - 2 * margin_y) / (rows + 1) if rows > 1 else 0
            
            floor_level = self.analyzer.get_floor_level(room)
            ceiling_height = self.analyzer.get_ceiling_height(room)
            z = floor_level + ceiling_height
            
            placed = 0
            for r in range(rows):
                for c in range(cols):
                    if placed >= count:
                        break
                    
                    x = min_x + margin_x + (c + 1) * step_x
                    y = min_y + margin_y + (r + 1) * step_y
                    
                    # Verify point is inside room
                    test_point = Point3D(x, y, z)
                    if room.contains_point_2d(test_point):
                        placements.append(test_point)
                        placed += 1
        
        return placements

    def place_fans_for_room(
        self,
        room: Room,
        count: int = 1
    ) -> list[Point3D]:
        """
        Place fans in a room.
        
        Rules:
        - Centered in room ceiling
        - Exclude bathrooms and small spaces
        - Avoid overlap with light fixtures
        """
        placements: list[Point3D] = []
        
        # Skip bathrooms
        if self.analyzer.is_bathroom(room):
            return placements
        
        # Skip small spaces
        if self.analyzer.is_small_space(room, min_area=self.MIN_ROOM_AREA_FOR_FAN):
            return placements
        
        # Place at ceiling center
        if self.geometry.is_3d:
            ceiling_center = self.analyzer.get_ceiling_center(room)
            placements.append(ceiling_center)
        else:
            centroid = room.get_centroid()
            floor_level = self.analyzer.get_floor_level(room)
            ceiling_height = self.analyzer.get_ceiling_height(room)
            
            # For multiple fans, offset slightly
            for i in range(count):
                offset_y = i * 200.0  # 200mm vertical offset
                placements.append(Point3D(
                    centroid.x,
                    centroid.y + offset_y,
                    floor_level + ceiling_height
                ))
        
        return placements

    def place_sockets_for_room(
        self,
        room: Room,
        spacing: Optional[float] = None
    ) -> list[Point3D]:
        """
        Place sockets/outlets along walls.
        
        Rules:
        - Place along walls at standard intervals (default 3000mm)
        - Avoid behind doors, windows, and fixtures
        - Follow regional electrical standards
        """
        placements: list[Point3D] = []
        
        if spacing is None:
            spacing = self.SOCKET_SPACING
        
        # Get walls for room
        walls = self.analyzer.find_walls_for_room(room)
        if not walls:
            # Fallback: use all walls
            walls = self.geometry.walls
        
        doors = self.analyzer.find_doors_for_room(room)
        windows = self.analyzer.find_windows_for_room(room)
        
        floor_level = self.analyzer.get_floor_level(room)
        
        for wall in walls:
            wall_length = wall.get_length()
            wall_dir = wall.get_direction()
            
            # Calculate number of sockets along this wall
            num_sockets = max(1, int(wall_length / spacing))
            
            # Place sockets along wall
            for i in range(num_sockets):
                # Position along wall
                t = (i + 1) / (num_sockets + 1)  # Avoid endpoints
                x = wall.start.x + t * (wall.end.x - wall.start.x)
                y = wall.start.y + t * (wall.end.y - wall.start.y)
                
                socket_point = Point3D(
                    x,
                    y,
                    floor_level + self.SOCKET_HEIGHT
                )
                
                # Check if placement avoids doors
                too_close_to_door = False
                for door in doors:
                    if door.position.distance_to(socket_point) < 500.0:
                        too_close_to_door = True
                        break
                
                # Check if placement avoids windows
                too_close_to_window = False
                for window in windows:
                    if window.position.distance_to(socket_point) < 500.0:
                        too_close_to_window = True
                        break
                
                # Only place if clear of doors and windows
                if not too_close_to_door and not too_close_to_window:
                    # Place on wall surface (slightly inside room)
                    wall_surface_point = self.analyzer.get_wall_surface_point(
                        wall,
                        socket_point,
                        offset_from_wall=10.0,
                        height=self.SOCKET_HEIGHT
                    )
                    placements.append(wall_surface_point)
        
        return placements

    def _project_point_to_wall(self, wall: Wall, point: Point3D) -> Point3D:
        """Project a point onto a wall line segment."""
        vx = point.x - wall.start.x
        vy = point.y - wall.start.y
        wx = wall.end.x - wall.start.x
        wy = wall.end.y - wall.start.y
        
        wall_len_sq = wx * wx + wy * wy
        if wall_len_sq == 0:
            return Point3D(wall.start.x, wall.start.y, wall.start.z)
        
        t = (vx * wx + vy * wy) / wall_len_sq
        t = max(0, min(1, t))
        
        x = wall.start.x + t * wx
        y = wall.start.y + t * wy
        z = wall.start.z
        
        return Point3D(x, y, z)

    def _get_door_wall_normal(self, door: Door) -> tuple[float, float]:
        """Get wall normal direction for a door (perpendicular to door rotation)."""
        theta = math.radians(door.rotation + 90.0)  # Perpendicular to door
        return (math.cos(theta), math.sin(theta))

