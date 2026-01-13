"""
Validation system for electrical component placements.

Prevents overlaps, maintains minimum clearances, and ensures
all placements are within room boundaries.
"""

from typing import NamedTuple, Optional
from dataclasses import dataclass

from .geometry_parser import Point3D, Room


@dataclass
class Placement:
    """Represents an electrical component placement."""
    position: Point3D
    component_type: str  # "SWITCH", "LIGHT", "FAN", "SOCKET"
    room: Optional[Room] = None
    rotation: float = 0.0
    metadata: dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class ValidationResult(NamedTuple):
    """Result of validation check."""
    is_valid: bool
    message: str


class PlacementValidator:
    """Validates electrical component placements."""

    # Minimum clearances (in mm)
    MIN_CLEARANCE_SWITCH_SWITCH = 200.0
    MIN_CLEARANCE_LIGHT_LIGHT = 1000.0
    MIN_CLEARANCE_FAN_FAN = 1500.0
    MIN_CLEARANCE_SOCKET_SOCKET = 500.0
    MIN_CLEARANCE_CROSS_TYPE = 300.0  # Between different component types

    def __init__(self):
        self.placements: list[Placement] = []

    def add_placement(self, placement: Placement) -> ValidationResult:
        """Add a placement and validate it."""
        # Check boundary
        if placement.room:
            if not placement.room.contains_point_2d(placement.position):
                return ValidationResult(
                    False,
                    f"{placement.component_type} placement outside room boundary"
                )
        
        # Check overlaps with existing placements
        for existing in self.placements:
            result = self._check_clearance(placement, existing)
            if not result.is_valid:
                return result
        
        # Add if valid
        self.placements.append(placement)
        return ValidationResult(True, "Placement valid")

    def validate_all(self, placements: list[Placement]) -> list[ValidationResult]:
        """Validate a list of placements."""
        results = []
        self.placements = []
        
        for placement in placements:
            result = self.add_placement(placement)
            results.append(result)
        
        return results

    def _check_clearance(
        self,
        placement1: Placement,
        placement2: Placement
    ) -> ValidationResult:
        """Check clearance between two placements."""
        distance = placement1.position.distance_to(placement2.position)
        
        # Get required clearance
        required_clearance = self._get_required_clearance(
            placement1.component_type,
            placement2.component_type
        )
        
        if distance < required_clearance:
            return ValidationResult(
                False,
                f"Insufficient clearance between {placement1.component_type} "
                f"and {placement2.component_type}: {distance:.1f}mm < {required_clearance:.1f}mm"
            )
        
        return ValidationResult(True, "Clearance adequate")

    def _get_required_clearance(
        self,
        type1: str,
        type2: str
    ) -> float:
        """Get required clearance between two component types."""
        # Same type clearances
        if type1 == type2:
            if type1 == "SWITCH":
                return self.MIN_CLEARANCE_SWITCH_SWITCH
            elif type1 == "LIGHT":
                return self.MIN_CLEARANCE_LIGHT_LIGHT
            elif type1 == "FAN":
                return self.MIN_CLEARANCE_FAN_FAN
            elif type1 == "SOCKET":
                return self.MIN_CLEARANCE_SOCKET_SOCKET
        
        # Cross-type clearance
        return self.MIN_CLEARANCE_CROSS_TYPE

    def check_room_boundary(self, placement: Placement) -> ValidationResult:
        """Check if placement is within room boundary."""
        if not placement.room:
            return ValidationResult(True, "No room constraint")
        
        if placement.room.contains_point_2d(placement.position):
            return ValidationResult(True, "Within room boundary")
        
        return ValidationResult(False, "Placement outside room boundary")

    def check_floor_level(self, placement: Placement, floor_level: float) -> ValidationResult:
        """Check if placement respects floor level constraints."""
        # For 2D placements, Z should be at or above floor level
        if placement.position.z < floor_level:
            return ValidationResult(
                False,
                f"Placement below floor level: {placement.position.z} < {floor_level}"
            )
        
        return ValidationResult(True, "Floor level constraint satisfied")

    def get_valid_placements(self) -> list[Placement]:
        """Get all valid placements."""
        return [p for p in self.placements]

