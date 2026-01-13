from django.contrib import admin

from .models import ProcessedOutput, UploadedPlan


@admin.register(UploadedPlan)
class UploadedPlanAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "original_file", "created_at")
    search_fields = ("name",)
    ordering = ("-created_at",)


@admin.register(ProcessedOutput)
class ProcessedOutputAdmin(admin.ModelAdmin):
    list_display = ("id", "plan", "status", "created_at", "updated_at")
    list_filter = ("status",)
    ordering = ("-created_at",)

