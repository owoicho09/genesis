from django.db import models
from django.contrib.auth.models import AbstractUser
from cloudinary.models import CloudinaryField


class User(AbstractUser):
    username = models.CharField(unique=True, max_length=100)
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=100)
    otp = models.CharField(null=True, blank=True, max_length=100)
    refresh_token = models.CharField(null=True, blank=True, max_length=5000)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'full_name']

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        email_username, full_name = self.email.split("@")
        if self.full_name == "" or self.full_name == None:
            self.full_name = email_username
        if self.username == "" or self.username== None:
            self.username = email_username
        super(User, self).save(*args, **kwargs)


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    full_name = models.CharField(max_length=100,null=True,blank=True)
    bio = models.TextField(max_length=500, blank=True)
    profile_picture = CloudinaryField('profile_picture', null=True, blank=True)
    phone_number = models.CharField(max_length=15, blank=True)
    address = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.email}'s Profile"

    def save(self, *args, **kwargs):
        # Set full_name to the user's username if it's empty or None
        if not self.full_name:  # This checks for both empty and None
            self.full_name = self.user.username

        super(Profile, self).save(*args, **kwargs)

 