from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User,Profile

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('email', 'username', 'full_name', 'is_staff', 'is_active')
    list_filter = ('is_staff', 'is_active')
    search_fields = ('email', 'username', 'full_name')
    ordering = ('email',)
    
@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'bio', 'phone_number', 'address')
    search_fields = ('user__email', 'user__username', 'user__full_name')
    list_filter = ('created_at', 'updated_at')
    ordering = ('user__email',)
    
    
    