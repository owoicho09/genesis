from django.urls import path
from . import views
from rest_framework_simplejwt.views import TokenRefreshView
from django.views.generic import TemplateView


app_name = 'agent'

urlpatterns = [
    path('user/token/', views.MyTokenObtainPairView.as_view()),
    path('user/token/refresh/', TokenRefreshView.as_view()),
    path('user/register/', views.RegisterView.as_view()),
    path("email-open/<str:email>", views.email_open_view, name="email_open"),
    path("genesis-agent/", views.run_genesis_agent),

    path("chat/", TemplateView.as_view(template_name="chatbot/index.html")),  # if using templates

]