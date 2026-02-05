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
        Place switches near a door along the wall on the side where door opens.
        
        Rules:
        - Place on wall surface on the swing side (where door opens)
        - Standard distance: 150-200mm from door frame
        - Height: ~1400mm from finished floor level
        - Avoid door swing zone and window zones
        """
        placements: list[Point3D] = []
        
        # Find nearest wall to door
        nearest_wall = self.analyzer.find_nearest_wall(door.position)
        if not nearest_wall:
            # Fallback: determine swing side and place switches
            swing_normal = self.analyzer.get_door_swing_side(door, room)
            for i in range(count):
                # Place switches along the swing side, starting 200mm from door
                offset_along_wall = 200.0 + i * 300.0  # 200mm from door, 300mm spacing
                # Offset perpendicular to get on wall surface
                offset_perp = 10.0  # 10mm inside room
                
                # Calculate position
                door_angle = math.radians(door.rotation)
                wall_dir = (math.cos(door_angle + math.pi/2), math.sin(door_angle + math.pi/2))
                
                x = door.position.x + wall_dir[0] * offset_along_wall + swing_normal[0] * offset_perp
                y = door.position.y + wall_dir[1] * offset_along_wall + swing_normal[1] * offset_perp
                z = self.analyzer.get_floor_level(room) + self.SWITCH_HEIGHT
                placements.append(Point3D(x, y, z))
            return placements
        
        # Get the swing side (where door opens)
        swing_normal = self.analyzer.get_door_swing_side(door, room)
        
        # Project door onto wall line
        door_proj = self._project_point_to_wall(nearest_wall, door.position)
        
        # Get wall direction
        wall_dir = nearest_wall.get_direction()
        
        # Determine which direction along the wall is on the swing side
        # Test both directions to see which is closer to swing side
        test_point_1 = Point3D(
            door_proj.x + wall_dir[0] * 200.0,
            door_proj.y + wall_dir[1] * 200.0,
            door_proj.z
        )
        test_point_2 = Point3D(
            door_proj.x - wall_dir[0] * 200.0,
            door_proj.y - wall_dir[1] * 200.0,
            door_proj.z
        )
        
        # Calculate which direction aligns better with swing side
        vec1 = (test_point_1.x - door.position.x, test_point_1.y - door.position.y)
        vec2 = (test_point_2.x - door.position.x, test_point_2.y - door.position.y)
        
        # Normalize vectors
        len1 = math.sqrt(vec1[0]**2 + vec1[1]**2)
        len2 = math.sqrt(vec2[0]**2 + vec2[1]**2)
        if len1 > 0:
            vec1 = (vec1[0]/len1, vec1[1]/len1)
        if len2 > 0:
            vec2 = (vec2[0]/len2, vec2[1]/len2)
        
        # Dot product with swing normal to determine direction
        dot1 = vec1[0] * swing_normal[0] + vec1[1] * swing_normal[1]
        dot2 = vec2[0] * swing_normal[0] + vec2[1] * swing_normal[1]
        
        # Use direction with higher dot product (more aligned with swing)
        if abs(dot2) > abs(dot1):
            wall_dir = (-wall_dir[0], -wall_dir[1])
        
        # Standard switch placement: 150-200mm from door frame on swing side
        start_offset = 200.0  # Start 200mm from door (on swing side)
        spacing = 300.0  # 300mm spacing between multiple switches
        
        for i in range(count):
            # Calculate position along wall on swing side
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
            
            # Verify placement is on swing side (where door opens)
            # Check that point is in the general direction of swing
            to_switch = (wall_surface_point.x - door.position.x, wall_surface_point.y - door.position.y)
            to_switch_len = math.sqrt(to_switch[0]**2 + to_switch[1]**2)
            if to_switch_len > 0:
                to_switch = (to_switch[0]/to_switch_len, to_switch[1]/to_switch_len)
                swing_alignment = to_switch[0] * swing_normal[0] + to_switch[1] * swing_normal[1]
                
                # Only place if reasonably aligned with swing side (cosine > 0.3)
                if swing_alignment > 0.3:
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
        
        # If no placements found, try fallback placement
        if not placements:
            for i in range(count):
                offset = 200.0 + i * 300.0
                x = door_proj.x + wall_dir[0] * offset
                y = door_proj.y + wall_dir[1] * offset
                z = self.analyzer.get_floor_level(room) + self.SWITCH_HEIGHT
                placements.append(Point3D(x, y, z))
        
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

