from django.urls import include, path

urlpatterns = [
    path("api/", include("sitemend.api.urls")),
    path("origin/", include("shop.urls")),
    path("edge/", include("sitemend.edge.urls")),
]
