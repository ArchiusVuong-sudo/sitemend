from django.urls import path

from .views import origin_page

urlpatterns = [
    path("", origin_page),
    path("<path:path>", origin_page),
]
