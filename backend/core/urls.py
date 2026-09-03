from django.urls import path
from . import views
from .progress_stream import generate_report_stream

urlpatterns = [
    path("generate-report/", views.generate_report, name="generate-report"),
    path("generate-report/stream/", generate_report_stream, name="generate-report-stream"),
    path("approvals/submit/", views.submit_approval, name="submit-approval"),
    path("approvals/review/", views.review_approval, name="review-approval"),
    path("approvals/list/", views.list_approvals, name="list-approvals"),
    path("jira/events/", views.get_jira_events, name="jira-events"),
    path("health/", views.health_check, name="health-check"),
]
