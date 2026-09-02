from django.urls import path    
from . import views

urlpatterns = [
    path("medicinas/", views.medicinas, name="medicinas"),
]