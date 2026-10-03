from django.urls import path
from .views import RouteFuelAPIView, MapView

urlpatterns = [
    path('api/route-fuel/', RouteFuelAPIView.as_view(), name='api-route-fuel'),
    path('api/route/', RouteFuelAPIView.as_view(), name='api-route'),
    path('', MapView.as_view(), name='map-view'),
]
