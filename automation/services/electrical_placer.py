"""
Main orchestrator for CAD-based electrical auto-placement system.

Coordinates geometry parsing, spatial analysis, placement rules,
validation, and CAD output generation.
"""

from pathlib import Path
from typing import Optional

from .geometry_parser import GeometryParser, CADGeometry
from .spatial_analyzer import SpatialAnalyzer
from .placement_rules import PlacementRules
from .placement_validator import PlacementValidator, Placement
from .cad_output import CADOutputGenerator


class ElectricalPlacer:
    """
    Main class for automatic electrical component placement.
    
    Performs deterministic, rule-based placement using native CAD geometry.
    """

    def __init__(self, input_path: Path):
        self.input_path = input_path
        self.geometry: Optional[CADGeometry] = None
        self.analyzer: Optional[SpatialAnalyzer] = None
        self.rules: Optional[PlacementRules] = None
        self.validator = PlacementValidator()

    def parse_geometry(self) -> CADGeometry:
        """Parse CAD geometry from input file."""
        parser = GeometryParser(self.input_path)
        self.geometry = parser.parse()
        return self.geometry

    def analyze_spatial(self) -> SpatialAnalyzer:
        """Perform spatial analysis on parsed geometry."""
        if not self.geometry:
            raise RuntimeError("Geometry must be parsed before spatial analysis")
        
        self.analyzer = SpatialAnalyzer(self.geometry)

        # Classify each detected room as ROOM / HALL / OPEN_AREA so that
        # downstream placement and reporting can distinguish them.
        for room in self.geometry.rooms:
            try:
                room.room_type = self.analyzer.classify_room_type(room)
            except Exception:
                # Best-effort classification only; never break the pipeline.
                room.room_type = room.room_type or None
        return self.analyzer

    def initialize_placement_rules(self) -> PlacementRules:
        """Initialize placement rules engine."""
        if not self.geometry or not self.analyzer:
            raise RuntimeError("Geometry and analyzer must be initialized")
        
        self.rules = PlacementRules(self.geometry, self.analyzer)
        return self.rules

    def place_components(
        self,
        lights_per_room: int = 1,
        switches_per_door: int = 1,
        fans_per_room: int = 0,
        sockets_enabled: bool = True,
        socket_spacing: Optional[float] = None
    ) -> list[Placement]:
        """
        Place electrical components using deterministic rules.
        
        Args:
            lights_per_room: Number of lights per room
            switches_per_door: Number of switches per door
            fans_per_room: Number of fans per room
            sockets_enabled: Whether to place sockets
            socket_spacing: Spacing between sockets (mm), None for default
        
        Returns:
            List of validated placements
        """
        if not self.rules:
            raise RuntimeError("Placement rules must be initialized")
        
        all_placements: list[Placement] = []

        # ------------------------------------------------------------------
        # 1) LIGHTS
        # ------------------------------------------------------------------
        if self.geometry.rooms:
            # Standard behaviour: lights driven by detected rooms.
            for room in self.geometry.rooms:
                light_positions = self.rules.place_lights_for_room(room, count=lights_per_room)
                for pos in light_positions:
                    placement = Placement(
                        position=pos,
                        component_type="LIGHT",
                        room=room,
                        metadata={
                            "room_type": getattr(room, "room_type", None),
                            "room_layer": room.layer,
                            "floor_level": room.floor_level,
                            "rule": "centroid_or_grid",
                        },
                    )
                    all_placements.append(placement)
        else:
            # Fallback behaviour when no rooms are available:
            # a) place one ceiling light above each door
            # b) optionally place a simple grid of lights across the plan extents.
            DEFAULT_CEILING_HEIGHT = 2700.0  # mm

            # (a) one light per door
            for door in self.geometry.doors:
                pos = door.position
                light_pos = type(pos)(
                    x=pos.x,
                    y=pos.y,
                    z=DEFAULT_CEILING_HEIGHT,
                )
                placement = Placement(
                    position=light_pos,
                    component_type="LIGHT",
                    room=None,
                    metadata={
                        "floor_level": 0.0,
                        "rule": "one_light_per_door_fallback",
                    },
                )
                all_placements.append(placement)

            # (b) simple grid covering overall wall extents
            if self.geometry.walls:
                xs = []
                ys = []
                for w in self.geometry.walls:
                    xs.extend([w.start.x, w.end.x])
                    ys.extend([w.start.y, w.end.y])

                min_x, max_x = min(xs), max(xs)
                min_y, max_y = min(ys), max(ys)

                width = max_x - min_x
                height = max_y - min_y

                # Choose a coarse grid: aim for about 3–5 lights across each side.
                # Protect against zero division / tiny extents.
                import math

                target_cells = 4
                step_x = width / (target_cells + 1) if width > 0 else 0
                step_y = height / (target_cells + 1) if height > 0 else 0

                if step_x > 0 and step_y > 0:
                    for i in range(1, target_cells + 1):
                        for j in range(1, target_cells + 1):
                            gx = min_x + step_x * i
                            gy = min_y + step_y * j
                            grid_pos = self.geometry.walls[0].start.__class__(
                                x=gx,
                                y=gy,
                                z=DEFAULT_CEILING_HEIGHT,
                            )
                            placement = Placement(
                                position=grid_pos,
                                component_type="LIGHT",
                                room=None,
                                metadata={
                                    "floor_level": 0.0,
                                    "rule": "fallback_grid_over_plan",
                                },
                            )
                            all_placements.append(placement)

        # ------------------------------------------------------------------
        # 2) SWITCHES
        # ------------------------------------------------------------------
        for door in self.geometry.doors:
            room = None
            if self.geometry.rooms:
                # Try to associate door with a room when rooms exist.
                room = self.analyzer.find_room_for_point(door.position)
                if not room:
                    for r in self.geometry.rooms:
                        doors_in_room = self.analyzer.find_doors_for_room(r)
                        if door in doors_in_room:
                            room = r
                            break

            if room:
                switch_positions = self.rules.place_switches_for_door(
                    door,
                    room,
                    count=switches_per_door,
                )
                for pos in switch_positions:
                    placement = Placement(
                        position=pos,
                        component_type="SWITCH",
                        room=room,
                        rotation=door.rotation,
                        metadata={
                            "door_position": (door.position.x, door.position.y),
                            "door_rotation": door.rotation,
                            "height": 1400.0,
                            "rule": "near_door_on_wall",
                        },
                    )
                    all_placements.append(placement)
            else:
                # Fallback: simple offset from the door based on its rotation.
                import math

                theta = math.radians(door.rotation + 90.0)
                offset_along = 200.0  # 200 mm from door along "wall"
                sx = door.position.x + math.cos(theta) * offset_along
                sy = door.position.y + math.sin(theta) * offset_along
                sz = 1400.0

                switch_pos = type(door.position)(x=sx, y=sy, z=sz)
                placement = Placement(
                    position=switch_pos,
                    component_type="SWITCH",
                    room=None,
                    rotation=door.rotation,
                    metadata={
                        "door_position": (door.position.x, door.position.y),
                        "door_rotation": door.rotation,
                        "height": 1400.0,
                        "rule": "one_switch_per_door_fallback",
                    },
                )
                all_placements.append(placement)

        # ------------------------------------------------------------------
        # 3) FANS & SOCKETS
        # ------------------------------------------------------------------
        # When no rooms are detected, we skip fans and sockets entirely,
        # because they are strongly room/room-boundary dependent.
        if self.geometry.rooms:
            # Place fans
            for room in self.geometry.rooms:
                fan_positions = self.rules.place_fans_for_room(room, count=fans_per_room)
                for pos in fan_positions:
                    placement = Placement(
                        position=pos,
                        component_type="FAN",
                        room=room,
                        metadata={
                            "room_type": getattr(room, "room_type", None),
                            "room_layer": room.layer,
                            "floor_level": room.floor_level,
                            "rule": "ceiling_center",
                        },
                    )
                    all_placements.append(placement)

            # Place sockets
            if sockets_enabled:
                for room in self.geometry.rooms:
                    socket_positions = self.rules.place_sockets_for_room(
                        room,
                        spacing=socket_spacing,
                    )
                    for pos in socket_positions:
                        placement = Placement(
                            position=pos,
                            component_type="SOCKET",
                            room=room,
                            metadata={
                                "room_type": getattr(room, "room_type", None),
                                "room_layer": room.layer,
                                "floor_level": room.floor_level,
                                "height": 300.0,
                                "rule": "along_walls_standard_spacing",
                            },
                        )
                        all_placements.append(placement)
        
        # Validate all placements
        validation_results = self.validator.validate_all(all_placements)
        
        # Filter out invalid placements
        valid_placements = []
        for placement, result in zip(all_placements, validation_results):
            if result.is_valid:
                valid_placements.append(placement)
            # Log invalid placements (could be added to log output)
        
        return valid_placements

    def generate_output(
        self,
        output_path: Path,
        placements: list[Placement]
    ) -> None:
        """Generate output CAD file with placements."""
        generator = CADOutputGenerator(self.input_path)
        
        for placement in placements:
            generator.add_placement(placement)
        
        generator.generate_output(output_path)

    def process(
        self,
        output_path: Path,
        lights_per_room: int = 1,
        switches_per_door: int = 1,
        fans_per_room: int = 0,
        sockets_enabled: bool = True,
        socket_spacing: Optional[float] = None
    ) -> dict:
        """
        Complete processing pipeline: parse, analyze, place, validate, output.
        
        Returns:
            Dictionary with processing results and statistics
        """
        # Parse geometry
        geometry = self.parse_geometry()
        
        # Analyze spatial relationships
        analyzer = self.analyze_spatial()
        
        # Initialize placement rules
        rules = self.initialize_placement_rules()
        
        # Place components
        placements = self.place_components(
            lights_per_room=lights_per_room,
            switches_per_door=switches_per_door,
            fans_per_room=fans_per_room,
            sockets_enabled=sockets_enabled,
            socket_spacing=socket_spacing
        )
        
        # Generate output
        self.generate_output(output_path, placements)
        
        # Compile statistics
        stats = {
            "rooms_detected": len(geometry.rooms),
            "walls_detected": len(geometry.walls),
            "doors_detected": len(geometry.doors),
            "windows_detected": len(geometry.windows),
            "floor_levels": len(geometry.floor_levels),
            "is_3d": geometry.is_3d,
            "placements": {
                "lights": sum(1 for p in placements if p.component_type == "LIGHT"),
                "switches": sum(1 for p in placements if p.component_type == "SWITCH"),
                "fans": sum(1 for p in placements if p.component_type == "FAN"),
                "sockets": sum(1 for p in placements if p.component_type == "SOCKET"),
            },
            "total_placements": len(placements),
            "room_types": {
                "ROOM": sum(1 for r in geometry.rooms if getattr(r, "room_type", None) == "ROOM"),
                "HALL": sum(1 for r in geometry.rooms if getattr(r, "room_type", None) == "HALL"),
                "OPEN_AREA": sum(1 for r in geometry.rooms if getattr(r, "room_type", None) == "OPEN_AREA"),
                "UNCLASSIFIED": sum(
                    1 for r in geometry.rooms if getattr(r, "room_type", None) not in {"ROOM", "HALL", "OPEN_AREA"}
                ),
            },
        }
        
        return stats

