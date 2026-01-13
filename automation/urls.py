from django.urls import path

from . import views

app_name = "automation"

urlpatterns = [
    path("", views.upload_view, name="upload"),
    path("upload/", views.upload_view, name="upload_explicit"),
    path("file/<int:pk>/", views.plan_detail_view, name="plan_detail"),
]


