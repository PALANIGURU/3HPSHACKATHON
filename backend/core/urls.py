from django.urls import path
from . import views
from .progress_stream import generate_report_stream

urlpatterns = [
    path("generate-report/", views.generate_report, name="generate-report"),
    path("generate-report/stream/", generate_report_stream, name="generate-report-stream"),
    path("health/", views.health_check, name="health-check"),
]
