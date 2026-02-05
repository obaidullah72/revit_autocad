import os
import subprocess
from pathlib import Path
import math
import shutil

from django.core.files import File

from ..models import ProcessedOutput, UploadedPlan
from .cad_adapters import detect_rooms_and_doors_from_dxf
from .electrical_placer import ElectricalPlacer


def convert_dwg_to_dxf(dwg_path: Path, dxf_path: Path) -> None:
    """
    DWG -> DXF conversion via external converter.

    Requires the DWG_CONVERTER_CMD env var, where the command is a template
    that accepts two placeholders: {input} and {output}.

    Example (using a wrapper script around ODAFileConverter):

        DWG_CONVERTER_CMD="dwg2dxf {input} {output}"

    The wrapper script is responsible for calling ODAFileConverter with the
    correct arguments.
    """
    cmd_template = os.getenv("DWG_CONVERTER_CMD")
    if not cmd_template:
        raise RuntimeError(
            "DWG_CONVERTER_CMD is not configured.\n"
            "Set DWG_CONVERTER_CMD to a DWG->DXF converter command, for example:\n"
            '  DWG_CONVERTER_CMD="dwg2dxf {input} {output}"\n'
            "where 'dwg2dxf' is a small wrapper around ODAFileConverter."
        )

    cmd = cmd_template.format(input=str(dwg_path), output=str(dxf_path))
    completed = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(
            f"DWG conversion failed: {completed.stderr or completed.stdout}"
        )


def _generate_output_with_blocks(
    input_path: Path,
    output_path: Path,
    lights_per_room: int = 1,
    switches_per_door: int = 1,
    fans_per_room: int = 0,
) -> None:
    """
    Read the source DXF, detect rooms/doors and append INSERT entities for:

    - LIGHT_BLOCK at each room centroid
    - SWITCH_BLOCK 200mm to the "right" of each door (based on rotation)
    """

    lines = input_path.read_text(errors="ignore").splitlines()

    # Ensure FAN_BLOCK exists in the BLOCKS section so inserts are visible.
    def ensure_fan_block(block_lines: list[str]) -> list[str]:
        blocks_start = None
        blocks_end = None
        for idx in range(len(block_lines) - 3):
            if (
                block_lines[idx].strip() == "0"
                and block_lines[idx + 1].strip() == "SECTION"
                and block_lines[idx + 2].strip() == "2"
                and block_lines[idx + 3].strip() == "BLOCKS"
            ):
                blocks_start = idx + 4
            if (
                blocks_start is not None
                and block_lines[idx].strip() == "0"
                and block_lines[idx + 1].strip() == "ENDSEC"
            ):
                blocks_end = idx
                break

        if blocks_start is None or blocks_end is None:
            return block_lines

        # Check if FAN_BLOCK is already defined.
        i = blocks_start
        while i < blocks_end - 3:
            if (
                block_lines[i].strip() == "0"
                and block_lines[i + 1].strip() == "BLOCK"
                and block_lines[i + 2].strip() == "2"
                and block_lines[i + 3].strip().upper() == "FAN_BLOCK"
            ):
                return block_lines
            i += 1

        fan_def = [
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
            "300",
            "0",
            "ENDBLK",
        ]

        return block_lines[:blocks_end] + fan_def + block_lines[blocks_end:]

    lines = ensure_fan_block(lines)

    # Locate ENTITIES section and its ENDSEC to know where to inject.
    entities_start = None
    entities_end = None
    for i in range(len(lines) - 3):
        if (
            lines[i].strip() == "0"
            and lines[i + 1].strip() == "SECTION"
            and lines[i + 2].strip() == "2"
            and lines[i + 3].strip() == "ENTITIES"
        ):
            entities_start = i + 4
        if (
            entities_start is not None
            and lines[i].strip() == "0"
            and lines[i + 1].strip() == "ENDSEC"
        ):
            entities_end = i
            break

    # Fallback: if ENTITIES not found, just copy as-is.
    if entities_start is None or entities_end is None:
        shutil.copyfile(input_path, output_path)
        return

    # Each room stores its vertices so we can place multiple lights later.
    room_vertices: list[list[tuple[float, float]]] = []
    door_data: list[tuple[float, float, float]] = []  # x, y, rotation_deg

    current_entity = None
    current_layer = None
    pending_x: float | None = None
    current_vertices: list[tuple[float, float]] = []
    door_x: float | None = None
    door_y: float | None = None
    door_rot: float = 0.0

    i = entities_start
    while i < entities_end - 1:
        code = lines[i].strip()
        value = lines[i + 1].strip()

        if code == "0":
            # finalize previous entity
            if current_entity == "LWPOLYLINE" and current_layer == "ROOM":
                if current_vertices:
                    room_vertices.append(list(current_vertices))
            elif current_entity == "INSERT" and current_layer == "DOOR":
                if door_x is not None and door_y is not None:
                    door_data.append((door_x, door_y, door_rot))

            # start new entity
            current_entity = value
            current_layer = None
            pending_x = None
            current_vertices = []
            door_x = None
            door_y = None
            door_rot = 0.0

        elif code == "8":  # layer name
            current_layer = value

        # Collect vertices for ROOM polylines
        if current_entity == "LWPOLYLINE":
            if code == "10":
                try:
                    pending_x = float(value)
                except ValueError:
                    pending_x = None
            elif code == "20" and pending_x is not None:
                try:
                    y = float(value)
                    current_vertices.append((pending_x, y))
                except ValueError:
                    pass
                pending_x = None

        # Collect insert point and rotation for DOOR inserts
        if current_entity == "INSERT":
            if code == "10":
                try:
                    door_x = float(value)
                except ValueError:
                    door_x = None
            elif code == "20":
                try:
                    door_y = float(value)
                except ValueError:
                    door_y = None
            elif code == "50":
                try:
                    door_rot = float(value)
                except ValueError:
                    door_rot = 0.0

        i += 2

    # Finalize last entity
    if current_entity == "LWPOLYLINE" and current_layer == "ROOM" and current_vertices:
        room_vertices.append(list(current_vertices))
    elif current_entity == "INSERT" and current_layer == "DOOR":
        if door_x is not None and door_y is not None:
            door_data.append((door_x, door_y, door_rot))

    # Build new INSERT entities for lights, fans and switches.
    new_entities: list[str] = []

    def add_insert(block_name: str, x: float, y: float, rotation_deg: float) -> None:
        new_entities.extend(
            [
                "0",
                "INSERT",
                "8",
                "0",  # layer 0 for now
                "2",
                block_name,
                "10",
                f"{x}",
                "20",
                f"{y}",
                "50",
                f"{rotation_deg}",
            ]
        )

    # Place lights and fans. Fans are always at (or near) centroid; lights are
    # arranged around the fan so they don't overlap visually.
    for verts in room_vertices:
        xs = [v[0] for v in verts]
        ys = [v[1] for v in verts]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        width = max_x - min_x
        height = max_y - min_y

        cx = (min_x + max_x) / 2.0
        cy = (min_y + max_y) / 2.0

        # Lights: place around the centroid so the fan can sit in the middle.
        light_positions: list[tuple[float, float]] = []
        if lights_per_room <= 4:
            dx = width * 0.25 or 500.0
            dy = height * 0.25 or 500.0
            candidates = [
                (cx - dx, cy + dy),
                (cx + dx, cy + dy),
                (cx - dx, cy - dy),
                (cx + dx, cy - dy),
            ]
            light_positions = candidates[: max(1, lights_per_room)]
        else:
            # For many lights, fall back to a simple interior grid.
            cols = 3
            rows = max(2, (lights_per_room + cols - 1) // cols)
            step_x = width / (cols + 1)
            step_y = height / (rows + 1)
            placed = 0
            for r in range(rows):
                for c in range(cols):
                    if placed >= lights_per_room:
                        break
                    x = min_x + (c + 1) * step_x
                    y = min_y + (r + 1) * step_y
                    light_positions.append((x, y))
                    placed += 1

        for lx, ly in light_positions:
            add_insert("LIGHT_BLOCK", lx, ly, 0.0)

        # Fans: by default place at room centroid; if more requested, stack slightly vertically.
        if fans_per_room > 0:
            for n in range(fans_per_room):
                fy = cy + n * (height * 0.05 or 150.0)
                add_insert("FAN_BLOCK", cx, fy, 0.0)

    # Place switches: along the wall line, starting just to the "right" of the door,
    # spaced by 200mm. We approximate wall direction as rotation + 90 degrees.
    # Start a bit away from the door opening, then step further along the wall.
    start_offset_mm = -750.0  # first switch ~0.5m from door insertion
    step_offset_mm = 300.0   # spacing between switches
    for x, y, rot_deg in door_data:
        theta = math.radians(rot_deg)
        wall_dir = theta + math.pi / 2.0
        dx_unit = math.cos(wall_dir)
        dy_unit = math.sin(wall_dir)
        for n in range(max(1, switches_per_door)):
            offset = start_offset_mm + n * step_offset_mm
            sx = x + dx_unit * offset
            sy = y + dy_unit * offset
            add_insert("SWITCH_BLOCK", sx, sy, rot_deg)

    # Assemble final DXF: insert new entities just before ENDSEC of ENTITIES.
    updated_lines = (
        lines[:entities_end] + new_entities + lines[entities_end:]
    )

    # Ensure a simple FAN_BLOCK definition exists so viewers can render fans.
    final_lines = _ensure_fan_block_definition(updated_lines)

    output_path.write_text("\n".join(final_lines) + "\n", errors="ignore")


def _ensure_fan_block_definition(lines: list[str]) -> list[str]:
    """
    If the DXF already defines FAN_BLOCK in the BLOCKS section, return lines
    unchanged. Otherwise, append a minimal FAN_BLOCK definition so that
    inserted FAN_BLOCK instances are visible in viewers.
    """

    # Locate BLOCKS section.
    blocks_start = None
    blocks_end = None
    for i in range(len(lines) - 3):
        if (
            lines[i].strip() == "0"
            and lines[i + 1].strip() == "SECTION"
            and lines[i + 2].strip() == "2"
            and lines[i + 3].strip() == "BLOCKS"
        ):
            blocks_start = i + 4
        if (
            blocks_start is not None
            and lines[i].strip() == "0"
            and lines[i + 1].strip() == "ENDSEC"
        ):
            blocks_end = i
            break

    if blocks_start is None or blocks_end is None:
        return lines

    # Check if FAN_BLOCK already exists.
    i = blocks_start
    while i < blocks_end - 1:
        code = lines[i].strip()
        value = lines[i + 1].strip()
        if code == "2" and value.upper() == "FAN_BLOCK":
            return lines
        i += 2

    # Minimal FAN_BLOCK definition: simple circle symbol on layer 0.
    fan_block_def = [
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
        "300",
        "0",
        "ENDBLK",
    ]

    return lines[:blocks_end] + fan_block_def + lines[blocks_end:]


def process_plan(
    plan: UploadedPlan,
    processed: ProcessedOutput,
    lights_per_room: int = 1,
    switches_per_door: int = 1,
    fans_per_room: int = 0,
    sockets_enabled: bool = True,
    socket_spacing: float | None = None,
    use_legacy_mode: bool = False,
) -> ProcessedOutput:
    """
    Apply deterministic, rule-based electrical component placement to CAD plans.

    Uses comprehensive geometry parsing, spatial analysis, and validation
    to place switches, lights, fans, and sockets according to engineering standards.

    Args:
        plan: Uploaded CAD plan
        processed: ProcessedOutput model instance
        lights_per_room: Number of lights per room
        switches_per_door: Number of switches per door
        fans_per_room: Number of fans per room
        sockets_enabled: Whether to place sockets/outlets
        socket_spacing: Spacing between sockets in mm (None for default 3000mm)
        use_legacy_mode: Use old simple placement logic (for backward compatibility)

    Returns:
        Updated ProcessedOutput instance
    """

    processed.status = ProcessedOutput.STATUS_RUNNING
    processed.log = "Starting processing...\n"
    processed.save(update_fields=["status", "log"])

    try:
        input_path = Path(plan.original_file.path)

        # If DWG, always convert to DXF first via external converter.
        if input_path.suffix.lower() == ".dwg":
            try:
                converted = input_path.with_suffix(".dxf")
                convert_dwg_to_dxf(input_path, converted)
                input_path = converted
            except Exception as dwg_exc:
                processed.status = ProcessedOutput.STATUS_FAILED
                processed.log = (
                    "Processing failed: DWG file could not be processed.\n"
                    f"{dwg_exc}\n"
                    "Hint: Install a DWG->DXF converter (e.g. ODAFileConverter),\n"
                    "create a small wrapper script (e.g. 'dwg2dxf'), and set the\n"
                    "DWG_CONVERTER_CMD environment variable, for example:\n"
                    '  DWG_CONVERTER_CMD="dwg2dxf {input} {output}"\n'
                    "Alternatively, upload DXF directly."
                )
                processed.save()
                return processed

        # Use legacy mode for backward compatibility
        if use_legacy_mode:
            return _process_legacy(
                plan, processed, input_path,
                lights_per_room, switches_per_door, fans_per_room
            )

        # Use new comprehensive placement system
        try:
            placer = ElectricalPlacer(input_path)
            
            # Generate output path
            outputs_dir = input_path.parent.parent / "outputs"
            outputs_dir.mkdir(parents=True, exist_ok=True)
            output_path = outputs_dir / f"plan_{plan.pk}_after.dxf"
            
            # Process with new system
            stats = placer.process(
                output_path=output_path,
                lights_per_room=lights_per_room,
                switches_per_door=switches_per_door,
                fans_per_room=fans_per_room,
                sockets_enabled=sockets_enabled,
                socket_spacing=socket_spacing
            )
            
            # Persist processed DXF via Django's storage backend
            with output_path.open("rb") as fh:
                processed.output_file.save(output_path.name, File(fh), save=False)
            
            # Build detailed log
            log_lines = [
                "Processing completed successfully.",
                "",
                "=== Geometry Detection ===",
                f"Rooms detected: {stats['rooms_detected']}",
                f"Walls detected: {stats['walls_detected']}",
                f"Doors detected: {stats['doors_detected']}",
                f"Windows detected: {stats['windows_detected']}",
                f"Floor levels: {stats['floor_levels']}",
                f"3D geometry: {'Yes' if stats['is_3d'] else 'No'}",
                "",
                "=== Placement Rules Applied ===",
                f"Lights per room: {lights_per_room}",
                f"Switches per door: {switches_per_door}",
                f"Fans per room: {fans_per_room}",
                f"Sockets enabled: {'Yes' if sockets_enabled else 'No'}",
                "",
                "=== Placement Results ===",
                f"Lights placed: {stats['placements']['lights']}",
                f"Switches placed: {stats['placements']['switches']}",
                f"Fans placed: {stats['placements']['fans']}",
                f"Sockets placed: {stats['placements']['sockets']}",
                f"Total placements: {stats['total_placements']}",
                "",
                "=== Placement Standards ===",
                "Switches: ~1400mm height, near doors, avoid swing zones",
                "Lights: Room centroid or grid, on ceiling plane (3D)",
                "Fans: Ceiling center, exclude bathrooms/small spaces",
                "Sockets: Along walls, 3000mm spacing, avoid doors/windows",
            ]
            
            processed.status = ProcessedOutput.STATUS_DONE
            processed.log = "\n".join(log_lines)
            processed.save()
            
        except Exception as new_exc:  # noqa: BLE001
            # Fallback to legacy mode if new system fails
            processed.log += f"\n\nNew system error: {new_exc}\nFalling back to legacy mode...\n"
            processed.save()
            return _process_legacy(
                plan, processed, input_path,
                lights_per_room, switches_per_door, fans_per_room
            )
            
    except Exception as exc:  # noqa: BLE001
        processed.status = ProcessedOutput.STATUS_FAILED
        processed.log = f"Processing failed: {exc}"
        processed.save()

    return processed


def _process_legacy(
    plan: UploadedPlan,
    processed: ProcessedOutput,
    input_path: Path,
    lights_per_room: int,
    switches_per_door: int,
    fans_per_room: int,
) -> ProcessedOutput:
    """Legacy processing mode for backward compatibility."""
    try:
        room_count, door_count = detect_rooms_and_doors_from_dxf(input_path)
        geometry_warning: str | None = None
    except Exception as geo_exc:  # noqa: BLE001
        room_count, door_count = 0, 0
        geometry_warning = f"Geometry detection warning (non-fatal): {geo_exc}"

    log_lines = [
    "Processing completed successfully (legacy mode).",
        f"Rooms detected (layer ROOM): {room_count}",
        f"Doors detected (layer DOOR): {door_count}",
    ]
    if geometry_warning:
        log_lines.append("")
        log_lines.append(geometry_warning)

    log_lines.extend(
        [
            "",
        "Legacy POC logic:",
            f"- {max(1, lights_per_room)} LIGHT_BLOCK per room "
            "(centroid or 2x2 grid for multiple).",
            f"- {max(0, fans_per_room)} FAN_BLOCK per room at/near centroid.",
            f"- {max(1, switches_per_door)} SWITCH_BLOCK per door, offset along wall.",
        ]
    )

    # Generate an "after" DXF with LIGHT_BLOCK, FAN_BLOCK and SWITCH_BLOCK inserts.
    outputs_dir = input_path.parent.parent / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    output_path = outputs_dir / f"plan_{plan.pk}_after.dxf"
    _generate_output_with_blocks(
        input_path,
        output_path,
        lights_per_room=lights_per_room,
        switches_per_door=switches_per_door,
        fans_per_room=fans_per_room,
    )

    # Persist processed DXF via Django's storage backend.
    with output_path.open("rb") as fh:
        processed.output_file.save(output_path.name, File(fh), save=False)

    processed.status = ProcessedOutput.STATUS_DONE
    processed.log = "\n".join(log_lines)
    processed.save()

    return processed


