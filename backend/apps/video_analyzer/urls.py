from django.urls import path

from . import views

urlpatterns = [
    path("uploads/", views.uploads),
    path("uploads/<int:upload_id>/", views.upload_detail),
    path("uploads/<int:upload_id>/analyze/", views.analyze),
    path("uploads/<int:upload_id>/first-frame/", views.first_frame),
    path("uploads/<int:upload_id>/result/", views.result),
]
