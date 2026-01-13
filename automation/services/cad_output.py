"""
CAD output generator for electrical component placements.

Generates updated DWG/DXF files with proper block placements,
coordinates, rotations, layers, and metadata.
"""

from pathlib import Path
from typing import Optional
import math

from .geometry_parser import Point3D
from .placement_validator import Placement


class CADOutputGenerator:
    """Generates CAD output files with electrical component placements."""

    def __init__(self, input_path: Path):
        self.input_path = input_path
        self.lines: list[str] = []
        self.placements: list[Placement] = []

    def add_placement(self, placement: Placement) -> None:
        """Add a placement to be written."""
        self.placements.append(placement)

    def generate_output(self, output_path: Path) -> None:
        """Generate output DXF file with placements."""
        # Read input file
        self.lines = self.input_path.read_text(errors="ignore").splitlines()
        
        # Ensure block definitions exist
        self._ensure_block_definitions()
        
        # Insert placement blocks into ENTITIES section
        self._insert_placements()
        
        # Write output
        output_path.write_text("\n".join(self.lines) + "\n", errors="ignore")

    def _ensure_block_definitions(self) -> None:
        """Ensure all required block definitions exist."""
        required_blocks = {
            "SWITCH_BLOCK": self._get_switch_block_definition(),
            "LIGHT_BLOCK": self._get_light_block_definition(),
            "FAN_BLOCK": self._get_fan_block_definition(),
            "SOCKET_BLOCK": self._get_socket_block_definition(),
        }
        
        # Find BLOCKS section
        blocks_start, blocks_end = self._find_section("BLOCKS")
        if blocks_start is None or blocks_end is None:
            return
        
        # Check which blocks are missing
        existing_blocks = set()
        i = blocks_start
        while i < blocks_end - 1:
            code = self.lines[i].strip()
            value = self.lines[i + 1].strip()
            if code == "2":  # Block name
                existing_blocks.add(value.upper())
            i += 2
        
        # Insert missing blocks
        for block_name, block_def in required_blocks.items():
            if block_name not in existing_blocks:
                # Insert before ENDSEC
                self.lines = (
                    self.lines[:blocks_end] +
                    block_def +
                    self.lines[blocks_end:]
                )
                blocks_end += len(block_def)

    def _insert_placements(self) -> None:
        """Insert placement blocks into ENTITIES section."""
        # Find ENTITIES section
        entities_start, entities_end = self._find_section("ENTITIES")
        if entities_start is None or entities_end is None:
            return
        
        # Generate INSERT entities for each placement
        new_entities: list[str] = []
        
        for placement in self.placements:
            block_name = self._get_block_name(placement.component_type)
            if not block_name:
                continue
            
            # Create INSERT entity
            insert_entity = [
                "0",
                "INSERT",
                "8",  # Layer
                self._get_layer_name(placement.component_type),
                "2",  # Block name
                block_name,
                "10",  # X
                f"{placement.position.x:.6f}",
                "20",  # Y
                f"{placement.position.y:.6f}",
                "30",  # Z
                f"{placement.position.z:.6f}",
                "50",  # Rotation
                f"{placement.rotation:.6f}",
            ]
            
            # Add metadata as extended data if available
            if placement.metadata:
                insert_entity.extend([
                    "100",
                    "AcDbEntity",
                    "100",
                    "AcDbBlockReference",
                ])
            
            new_entities.extend(insert_entity)
        
        # Insert new entities before ENDSEC
        self.lines = (
            self.lines[:entities_end] +
            new_entities +
            self.lines[entities_end:]
        )

    def _find_section(self, section_name: str) -> tuple[Optional[int], Optional[int]]:
        """Find start and end indices of a DXF section."""
        start_idx = None
        end_idx = None
        
        for i in range(len(self.lines) - 3):
            if (
                self.lines[i].strip() == "0" and
                self.lines[i + 1].strip() == "SECTION" and
                self.lines[i + 2].strip() == "2" and
                self.lines[i + 3].strip() == section_name
            ):
                start_idx = i + 4
            elif (
                start_idx is not None and
                self.lines[i].strip() == "0" and
                self.lines[i + 1].strip() == "ENDSEC"
            ):
                end_idx = i
                break
        
        return (start_idx, end_idx)

    def _get_block_name(self, component_type: str) -> str:
        """Get block name for component type."""
        mapping = {
            "SWITCH": "SWITCH_BLOCK",
            "LIGHT": "LIGHT_BLOCK",
            "FAN": "FAN_BLOCK",
            "SOCKET": "SOCKET_BLOCK",
        }
        return mapping.get(component_type, "")

    def _get_layer_name(self, component_type: str) -> str:
        """Get layer name for component type."""
        mapping = {
            "SWITCH": "ELECTRICAL_SWITCHES",
            "LIGHT": "ELECTRICAL_LIGHTS",
            "FAN": "ELECTRICAL_FANS",
            "SOCKET": "ELECTRICAL_SOCKETS",
        }
        return mapping.get(component_type, "ELECTRICAL")

    def _get_switch_block_definition(self) -> list[str]:
        """Get block definition for switch."""
        return [
            "0",
            "BLOCK",
            "2",
            "SWITCH_BLOCK",
            "70",
            "0",
            "10",
            "0",
            "20",
            "0",
            "30",
            "0",
            "3",
            "SWITCH_BLOCK",
            "1",
            "",
            "0",
            "CIRCLE",
            "8",
            "0",
            "10",
            "0",
            "20",
            "0",
            "40",
            "50",  # Radius 50mm
            "0",
            "LINE",
            "8",
            "0",
            "10",
            "-30",
            "20",
            "0",
            "11",
            "30",
            "21",
            "0",
            "0",
            "ENDBLK",
        ]

    def _get_light_block_definition(self) -> list[str]:
        """Get block definition for light."""
        return [
            "0",
            "BLOCK",
            "2",
            "LIGHT_BLOCK",
            "70",
            "0",
            "10",
            "0",
            "20",
            "0",
            "30",
            "0",
            "3",
            "LIGHT_BLOCK",
            "1",
            "",
            "0",
            "CIRCLE",
            "8",
            "0",
            "10",
            "0",
            "20",
            "0",
            "40",
            "100",  # Radius 100mm
            "0",
            "CIRCLE",
            "8",
            "0",
            "10",
            "0",
            "20",
            "0",
            "40",
            "150",  # Outer circle
            "0",
            "ENDBLK",
        ]

    def _get_fan_block_definition(self) -> list[str]:
        """Get block definition for fan."""
        return [
            "0",
            "BLOCK",
            "2",
            "FAN_BLOCK",
            "70",
            "0",
            "10",
            "0",
            "20",
            "0",
            "30",
            "0",
            "3",
            "FAN_BLOCK",
            "1",
            "",
            "0",
            "CIRCLE",
            "8",
            "0",
            "10",
            "0",
            "20",
            "0",
            "40",
            "300",  # Radius 300mm
            "0",
            "LINE",
            "8",
            "0",
            "10",
            "-300",
            "20",
            "0",
            "11",
            "300",
            "21",
            "0",
            "0",
            "LINE",
            "8",
            "0",
            "10",
            "0",
            "20",
            "-300",
            "11",
            "0",
            "21",
            "300",
            "0",
            "ENDBLK",
        ]

    def _get_socket_block_definition(self) -> list[str]:
        """Get block definition for socket."""
        return [
            "0",
            "BLOCK",
            "2",
            "SOCKET_BLOCK",
            "70",
            "0",
            "10",
            "0",
            "20",
            "0",
            "30",
            "0",
            "3",
            "SOCKET_BLOCK",
            "1",
            "",
            "0",
            "RECTANGLE",
            "8",
            "0",
            "10",
            "-25",
            "20",
            "-15",
            "11",
            "25",
            "21",
            "15",
            "0",
            "CIRCLE",
            "8",
            "0",
            "10",
            "-15",
            "20",
            "0",
            "40",
            "8",
            "0",
            "CIRCLE",
            "8",
            "0",
            "10",
            "15",
            "20",
            "0",
            "40",
            "8",
            "0",
            "ENDBLK",
        ]

