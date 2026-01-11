from rest_framework import status, generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from .serializers import (
    RegisterSerializer, LoginSerializer, UserSerializer,
    ChangePasswordSerializer, UpdateProfileSerializer
)
from integrations.supabase_client import get_supabase_client, get_supabase_admin_client

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    """User registration endpoint using Supabase Auth."""
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        email = serializer.validated_data['email']
        password = serializer.validated_data['password']
        username = serializer.validated_data['username']
        full_name = serializer.validated_data.get('full_name', '')
        
        try:
            # Use admin client to create user (auto-confirms email)
            supabase_admin = get_supabase_admin_client()
            
            # Create user with admin API (bypasses email confirmation)
            auth_response = supabase_admin.auth.admin.create_user({
                'email': email,
                'password': password,
                'email_confirm': True,  # Auto-confirm email
                'user_metadata': {
                    'username': username,
                    'full_name': full_name
                }
            })
            
            if auth_response.user is None:
                return Response({
                    'error': 'Failed to create user in Supabase Auth'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            supabase_user_id = auth_response.user.id
            
            # Check if user already exists in public.users
            try:
                user = User.objects.get(id=supabase_user_id)
                user.email = email
                user.username = username
                user.full_name = full_name
                user.is_active = True
                user.save()
            except User.DoesNotExist:
                # Create user in public.users table
                user = User.objects.create(
                    id=supabase_user_id,
                    email=email,
                    username=username,
                    full_name=full_name,
                    is_active=True
                )
                user.set_unusable_password()
                user.save()
            
            # Now sign in to get tokens
            supabase = get_supabase_client()
            login_response = supabase.auth.sign_in_with_password({
                'email': email,
                'password': password
            })
            
            session = login_response.session
            
            return Response({
                'message': 'User registered successfully',
                'user': UserSerializer(user).data,
                'access_token': session.access_token if session else None,
                'refresh_token': session.refresh_token if session else None
            }, status=status.HTTP_201_CREATED)
            
        except IntegrityError as e:
            # Handle duplicate username or email in public.users
            error_msg = str(e)
            if 'username' in error_msg:
                return Response({
                    'error': 'Username already exists'
                }, status=status.HTTP_400_BAD_REQUEST)
            elif 'email' in error_msg:
                return Response({
                    'error': 'Email already exists'
                }, status=status.HTTP_400_BAD_REQUEST)
            return Response({
                'error': f'Registration failed: {error_msg}'
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            error_msg = str(e)
            # Check for Supabase specific errors
            if 'User already registered' in error_msg:
                return Response({
                    'error': 'Email already registered. Please login instead.'
                }, status=status.HTTP_400_BAD_REQUEST)
            return Response({
                'error': f'Registration failed: {error_msg}'
            }, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    """User login endpoint using Supabase Auth."""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        email = serializer.validated_data['email']
        password = serializer.validated_data['password']
        
        try:
            # Authenticate with Supabase Auth
            supabase = get_supabase_client()
            auth_response = supabase.auth.sign_in_with_password({
                'email': email,
                'password': password
            })
            
            if auth_response.user is None:
                return Response({
                    'error': 'Invalid email or password'
                }, status=status.HTTP_401_UNAUTHORIZED)
            
            supabase_user_id = auth_response.user.id
            
            # Get or create user in public.users table
            try:
                user = User.objects.get(id=supabase_user_id)
            except User.DoesNotExist:
                # User exists in auth.users but not in public.users, create it
                user = User.objects.create(
                    id=supabase_user_id,
                    email=email,
                    username=auth_response.user.user_metadata.get('username', email.split('@')[0]),
                    full_name=auth_response.user.user_metadata.get('full_name', ''),
                    is_active=True
                )
                user.set_unusable_password()
                user.save()
            
            # Update last login
            from django.utils import timezone
            user.last_login = timezone.now()
            user.save(update_fields=['last_login'])
            
            # Get tokens from Supabase Auth response
            session = auth_response.session
            
            return Response({
                'message': 'Login successful',
                'user': UserSerializer(user).data,
                'access_token': session.access_token,
                'refresh_token': session.refresh_token
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            error_msg = str(e)
            if 'Invalid login credentials' in error_msg:
                return Response({
                    'error': 'Invalid email or password'
                }, status=status.HTTP_401_UNAUTHORIZED)
            return Response({
                'error': f'Login failed: {error_msg}'
            }, status=status.HTTP_400_BAD_REQUEST)


class RefreshTokenView(APIView):
    """Refresh access token using Supabase refresh token."""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        refresh_token = request.data.get('refresh_token')
        
        if not refresh_token:
            return Response({
                'error': 'Refresh token is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Refresh session with Supabase
            supabase = get_supabase_client()
            auth_response = supabase.auth.refresh_session(refresh_token)
            
            if auth_response.session is None:
                return Response({
                    'error': 'Invalid refresh token'
                }, status=status.HTTP_401_UNAUTHORIZED)
            
            session = auth_response.session
            
            return Response({
                'access_token': session.access_token,
                'refresh_token': session.refresh_token
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'error': f'Token refresh failed: {str(e)}'
            }, status=status.HTTP_401_UNAUTHORIZED)


class LogoutView(APIView):
    """User logout endpoint using Supabase Auth."""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        try:
            # Sign out from Supabase
            supabase = get_supabase_client()
            supabase.auth.sign_out()
            
            return Response({
                'message': 'Logout successful'
            }, status=status.HTTP_200_OK)
        except Exception:
            # Even if Supabase logout fails, return success
            # Client should delete tokens anyway
            return Response({
                'message': 'Logout successful'
            }, status=status.HTTP_200_OK)


class MeView(APIView):
    """Get current user information."""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)


class UpdateProfileView(generics.UpdateAPIView):
    """Update user profile."""
    serializer_class = UpdateProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        return self.request.user


class ChangePasswordView(APIView):
    """Change user password using Supabase Auth."""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        new_password = serializer.validated_data['new_password']
        
        try:
            # Update password in Supabase Auth
            supabase = get_supabase_client()
            supabase.auth.update_user({
                'password': new_password
            })
            
            return Response({
                'message': 'Password changed successfully'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'error': f'Password change failed: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)
