"""
DXF preview generation utilities.

For the POC we use ezdxf's drawing addon with a matplotlib backend
to render simple PNG previews of DXF files.
"""

from pathlib import Path
import logging

from matplotlib.figure import Figure
import ezdxf
from ezdxf import recover
from ezdxf.addons.drawing import matplotlib as ezdxf_mpl  # type: ignore[import]
from ezdxf.lldxf.const import DXFStructureError


logger = logging.getLogger(__name__)


def generate_preview(dxf_path: Path, png_path: Path) -> None:
    """
    Render a DXF file to a PNG image and overlay markers for auto elements.

    - LIGHT_BLOCK inserts: green circles with label
    - SWITCH_BLOCK inserts: orange squares with label

    Any errors are swallowed in production so that preview generation never
    breaks the POC, but in development we log full details so issues are visible.
    """

    fig = None
    try:
        try:
            doc = ezdxf.readfile(str(dxf_path))
        except DXFStructureError:
            try:
                doc, _ = recover.readfile(str(dxf_path), errors="ignore")
            except DXFStructureError:
                # As a last resort, generate a simple placeholder PNG so that the
                # UI still has something to show for this plan, even though the
                # DXF structure is not parseable by ezdxf.
                logger.warning(
                    "Generating placeholder preview for %s due to unrecoverable DXFStructureError",
                    dxf_path,
                )
                fig = Figure(figsize=(8.0, 5.0))
                ax = fig.add_subplot(111)
                ax.text(
                    0.5,
                    0.5,
                    "Preview not available\n(Invalid DXF structure)",
                    ha="center",
                    va="center",
                    fontsize=11,
                    weight="bold",
                )
                ax.axis("off")
                png_path.parent.mkdir(parents=True, exist_ok=True)
                fig.savefig(
                    str(png_path),
                    dpi=180,
                    bbox_inches="tight",
                    facecolor="#ffffff",
                )
                return

        msp = doc.modelspace()
        fig = ezdxf_mpl.plot_dxf(
            msp,
            size_inches=(8.0, 5.0),
            adjust_figure=True,
        )

        # Collect auto-added inserts to overlay with color and labels.
        lights = []
        switches = []
        fans = []
        all_points = []
        for insert in msp.query("INSERT"):
            name = insert.dxf.name.upper() if insert.dxf.name else ""
            pt = insert.dxf.insert
            all_points.append(pt)
            if name == "LIGHT_BLOCK":
                lights.append(pt)  # (x, y, z)
            elif name == "SWITCH_BLOCK":
                switches.append(pt)
            elif name == "FAN_BLOCK":
                fans.append(pt)

        ax = fig.axes[0] if fig.axes else None
        if ax:

            def _plot(points, color, marker, label):
                if not points:
                    return
                xs = [p.x for p in points]
                ys = [p.y for p in points]
                ax.scatter(
                    xs,
                    ys,
                    s=72,
                    color=color,
                    marker=marker,
                    zorder=15,
                    linewidths=1.2,
                    edgecolors="#0f172a",
                )
                for x, y in zip(xs, ys):
                    ax.text(
                        x + 120,
                        y + 120,
                        label,
                        color=color,
                        fontsize=9,
                        weight="bold",
                        zorder=16,
                        bbox=dict(
                            facecolor="#ffffff",
                            edgecolor=color,
                            boxstyle="round,pad=0.22",
                            linewidth=0.8,
                        ),
                    )

            _plot(lights, "#10b981", "o", "Light")
            _plot(switches, "#f97316", "s", "Switch")
            _plot(fans, "#3b82f6", "^", "Fan")

            # Pad extents so overlay is comfortably visible.
            if all_points:
                xs = [p.x for p in all_points]
                ys = [p.y for p in all_points]
                min_x, max_x = min(xs), max(xs)
                min_y, max_y = min(ys), max(ys)
                pad = max((max_x - min_x), (max_y - min_y)) * 0.1 + 200
                ax.set_xlim(min_x - pad, max_x + pad)
                ax.set_ylim(min_y - pad, max_y + pad)

            ax.set_aspect("equal", adjustable="datalim")
            ax.axis("off")

        png_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(png_path), dpi=240, bbox_inches="tight", facecolor="#ffffff")
    except Exception as exc:  # pragma: no cover - debug logging
        # Log the error so we can see why previews are missing.
        logger.exception("Failed to generate preview for %s -> %s", dxf_path, png_path)
    finally:
        if fig is not None:
            ezdxf_mpl.close(fig)


