from django.urls import path

from . import views

urlpatterns = [
    path("health", views.health),
    path("site", views.site_view),
    path("site/reset", views.reset_view),
    path("policies/<str:category>", views.policy_view),
    path("scan", views.scan_view),
    path("generate", views.generate_view),
    path("deploy", views.deploy_view),
    path("verify", views.verify_view),
    path("runs", views.runs_view),
    path("runs/<int:pk>", views.run_view),
    path("baselines", views.baselines_view),
    path("issues", views.issues_view),
    path("pages", views.pages_view),
    path("fixes", views.fixes_view),
    path("fixes/bulk-approve", views.bulk_approve_view),
    path("fixes/<int:pk>", views.fix_view),
    path("fixes/<int:pk>/check", views.fix_check_view),
    path("fixes/<int:pk>/revert", views.revert_view),
    path("fixes/<int:pk>/<str:action>", views.fix_action_view),
    path("releases", views.releases_view),
    path("releases/<int:number>/rollback", views.rollback_view),
    path("compare", views.compare_view),
]
