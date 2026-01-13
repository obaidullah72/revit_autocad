"""
CAD adapter utilities (DXF, POC-level).

To avoid robustness issues with CAD libraries on slightly malformed DXF,
this module uses a very simple **text-level** parser tailored to the POC
convention:

- Rooms: `LWPOLYLINE` entities on layer `ROOM`
- Doors: `INSERT` entities on layer `DOOR`
"""

from pathlib import Path
from typing import Tuple


def detect_rooms_and_doors_from_dxf(path: Path) -> Tuple[int, int]:
    """
    Parse the DXF file line-by-line and count:

    - Rooms: LWPOLYLINE on layer ROOM
    - Doors: INSERT on layer DOOR

    This deliberately avoids depending on ezdxf entity structures, so
    issues like a missing `AcDbPolyline` subclass do not break the POC.
    """

    text = path.read_text(errors="ignore").splitlines()

    room_count = 0
    door_count = 0

    i = 0
    length = len(text)
    current_entity = None
    current_layer = None

    while i < length - 1:
        code = text[i].strip()
        value = text[i + 1].strip()

        if code == "0":
            # new entity
            current_entity = value
            current_layer = None

        elif code == "8":  # layer name
            current_layer = value

            if current_entity == "LWPOLYLINE" and current_layer == "ROOM":
                room_count += 1
            elif current_entity == "INSERT" and current_layer == "DOOR":
                door_count += 1

        i += 2

    return room_count, door_count

