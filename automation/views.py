from pathlib import Path

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .models import ProcessedOutput, UploadedPlan
from .services.processor import process_plan


def upload_view(request: HttpRequest) -> HttpResponse:
    """
    Handles drawing upload and kicks off processing.
    """

    if request.method == "POST":
        uploaded_file = request.FILES.get("file")
        name = request.POST.get("name") or (uploaded_file.name if uploaded_file else "")

        # Optional tuning of rule parameters from UI.
        def _as_int(value: str | None, default: int, allow_zero: bool = False) -> int:
            try:
                if value is None:
                    return default
                v = int(value)
                if v < 0:
                    return default
                if v == 0 and not allow_zero:
                    return default
                return v
            except (TypeError, ValueError):
                return default

        lights_per_room = _as_int(request.POST.get("lights_per_room"), 1)
        switches_per_door = _as_int(request.POST.get("switches_per_door"), 1)
        fans_per_room = _as_int(request.POST.get("fans_per_room"), 0, allow_zero=True)
        
        # New parameters for comprehensive placement
        sockets_enabled = request.POST.get("sockets_enabled") == "on"
        socket_spacing_str = request.POST.get("socket_spacing")
        socket_spacing = None
        if socket_spacing_str:
            try:
                socket_spacing = float(socket_spacing_str)
                if socket_spacing < 500:  # Minimum 500mm
                    socket_spacing = None
            except (TypeError, ValueError):
                socket_spacing = None
        
        use_legacy_mode = request.POST.get("use_legacy_mode") == "on"

        if not uploaded_file:
            return render(
                request,
                "automation/upload.html",
                {"error": "Please choose a DXF or DWG file to upload."},
            )

        plan = UploadedPlan.objects.create(name=name, original_file=uploaded_file)
        processed = ProcessedOutput.objects.create(plan=plan)

        # For POC we run synchronously; later this can be moved to a background worker.
        process_plan(
            plan,
            processed,
            lights_per_room=lights_per_room,
            switches_per_door=switches_per_door,
            fans_per_room=fans_per_room,
            sockets_enabled=sockets_enabled,
            socket_spacing=socket_spacing,
            use_legacy_mode=use_legacy_mode,
        )

        return redirect(reverse("automation:plan_detail", args=[plan.pk]))

    # Show recent plans on the upload screen as a simple history.
    recent_plans = (
        UploadedPlan.objects.order_by("-created_at")
        .select_related("processed_output")[:5]
    )

    return render(
        request,
        "automation/upload.html",
        {
            "recent_plans": recent_plans,
            "default_lights_per_room": 1,
            "default_switches_per_door": 1,
            "default_fans_per_room": 0,
        },
    )


def plan_detail_view(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Shows status, logs and link to download the processed file.
    """

    plan = get_object_or_404(UploadedPlan, pk=pk)
    processed = getattr(plan, "processed_output", None)

    processed_summary = None

    # Very lightweight parsing of log to surface counts in UI.
    if processed and processed.log:
        rooms = doors = None
        for line in processed.log.splitlines():
            line = line.strip()
            if line.startswith("Rooms detected"):
                parts = line.split(":")
                if len(parts) == 2:
                    try:
                        rooms = int(parts[1].strip())
                    except ValueError:
                        rooms = None
            elif line.startswith("Doors detected"):
                parts = line.split(":")
                if len(parts) == 2:
                    try:
                        doors = int(parts[1].strip())
                    except ValueError:
                        doors = None
        if rooms is not None or doors is not None:
            processed_summary = type(
                "ProcessedSummary",
                (),
                {"rooms": rooms or 0, "doors": doors or 0},
            )()

    context = {
        "plan": plan,
        "processed": processed,
        "processed_summary": processed_summary,
    }
    return render(request, "automation/detail.html", context)

