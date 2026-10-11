from django.urls import path

from .views import edge_page

urlpatterns = [
    path("", edge_page),
    path("<path:path>", edge_page),
]
