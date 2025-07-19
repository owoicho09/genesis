from rest_framework import serializers
from django.contrib.auth import get_user_model
from userauth.models import Profile
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth.password_validation import validate_password
from .models import *


User = get_user_model()

class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ['bio', 'profile_picture', 'phone_number', 'address', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


class UserSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer(read_only=True)
    password = serializers.CharField(write_only=True, required=False)
    
    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'full_name', 'password', 'profile', 'is_active', 'date_joined']
        read_only_fields = ['id', 'date_joined']
        extra_kwargs = {
            'password': {'write_only': True}
        }


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        # Get the default token
        token = super().get_token(user)

        # Add user details to the token
        token['full_name'] = user.full_name
        token['email'] = user.email
        token['username'] = user.username



        return token

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})

    class Meta:
        model = User
        fields = ['email', 'username', 'full_name', 'password', 'password2']
        extra_kwargs = {
            'email': {'required': True},
            'username': {'required': True},
            'full_name': {'required': True}
        }

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        
        if User.objects.filter(email=attrs['email']).exists():
            raise serializers.ValidationError({"email": "Email already exists."})
        
        return attrs

    def create(self, validated_data):
        validated_data.pop('password2')
        user = User.objects.create_user(**validated_data)
        return user 



class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = '__all__'


class CampaignSerializer(serializers.ModelSerializer):
    class Meta:
        model = Campaign
        fields = '__all__'


class AudienceSegmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = AudienceSegment
        fields = '__all__'


class AdCreativeSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdsCreatives
        fields = '__all__'


class OptimizationLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = OptimizationLog
        fields = '__all__'


class PromptLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = PromptLog
        fields = '__all__'



class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = '__all__'


