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
        
        # Place lights
        for room in self.geometry.rooms:
            light_positions = self.rules.place_lights_for_room(room, count=lights_per_room)
            for pos in light_positions:
                placement = Placement(
                    position=pos,
                    component_type="LIGHT",
                    room=room,
                    metadata={
                        "room_layer": room.layer,
                        "floor_level": room.floor_level,
                        "rule": "centroid_or_grid"
                    }
                )
                all_placements.append(placement)
        
        # Place switches
        for door in self.geometry.doors:
            # Find room for door
            room = self.analyzer.find_room_for_point(door.position)
            if not room:
                # Try to find nearest room
                for r in self.geometry.rooms:
                    doors_in_room = self.analyzer.find_doors_for_room(r)
                    if door in doors_in_room:
                        room = r
                        break
            
            if room:
                switch_positions = self.rules.place_switches_for_door(
                    door,
                    room,
                    count=switches_per_door
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
                            "rule": "near_door_on_wall"
                        }
                    )
                    all_placements.append(placement)
        
        # Place fans
        for room in self.geometry.rooms:
            fan_positions = self.rules.place_fans_for_room(room, count=fans_per_room)
            for pos in fan_positions:
                placement = Placement(
                    position=pos,
                    component_type="FAN",
                    room=room,
                    metadata={
                        "room_layer": room.layer,
                        "floor_level": room.floor_level,
                        "rule": "ceiling_center"
                    }
                )
                all_placements.append(placement)
        
        # Place sockets
        if sockets_enabled:
            for room in self.geometry.rooms:
                socket_positions = self.rules.place_sockets_for_room(
                    room,
                    spacing=socket_spacing
                )
                for pos in socket_positions:
                    placement = Placement(
                        position=pos,
                        component_type="SOCKET",
                        room=room,
                        metadata={
                            "room_layer": room.layer,
                            "floor_level": room.floor_level,
                            "height": 300.0,
                            "rule": "along_walls_standard_spacing"
                        }
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
        }
        
        return stats

