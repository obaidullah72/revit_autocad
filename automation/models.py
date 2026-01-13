from django.db import models


class UploadedPlan(models.Model):
    """
    Stores an uploaded CAD file (DXF/DWG converted to DXF for POC).
    """

    name = models.CharField(max_length=255, blank=True)
    original_file = models.FileField(upload_to="uploads/")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name or f"Plan {self.pk}"


class ProcessedOutput(models.Model):
    """
    Stores the processing result and generated output file.
    """

    STATUS_PENDING = "PENDING"
    STATUS_RUNNING = "RUNNING"
    STATUS_DONE = "DONE"
    STATUS_FAILED = "FAILED"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_RUNNING, "Running"),
        (STATUS_DONE, "Done"),
        (STATUS_FAILED, "Failed"),
    ]

    plan = models.OneToOneField(
        UploadedPlan,
        on_delete=models.CASCADE,
        related_name="processed_output",
    )
    output_file = models.FileField(upload_to="outputs/", blank=True, null=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    log = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Output for {self.plan}"

