from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from models.schemas import UserCreate, UserLogin, User, APIResponse, ErrorResponse
import os
from supabase import create_client, Client
import logging

logger = logging.getLogger(__name__)
router = APIRouter()
security = HTTPBearer()

# Supabase client
supabase_url = os.getenv('SUPABASE_URL')
supabase_key = os.getenv('SUPABASE_KEY')
supabase: Client = create_client(supabase_url, supabase_key)

@router.post(
    "/register",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register New User",
    description="Register a new user account with email and password",
    responses={
        201: {"description": "User registered successfully"},
        400: {"description": "Registration failed - invalid data or user already exists"},
        422: {"description": "Validation error"}
    }
)
async def register(user_data: UserCreate):
    """
    Register a new user account.
    
    Creates a new user with the provided email and password. Username is optional.
    The user will need to verify their email before they can log in (if email
    confirmation is enabled).
    
    - **email**: Valid email address (will be converted to lowercase)
    - **password**: Password (minimum 6 characters)
    - **username**: Optional display name
    """
    try:
        # Use Supabase Auth to create user
        response = supabase.auth.sign_up({
            "email": user_data.email,
            "password": user_data.password,
            "options": {
                "data": {
                    "username": user_data.username
                }
            }
        })
        
        if response.user:
            return APIResponse(
                success=True,
                message="User registered successfully",
                data={
                    "user_id": response.user.id,
                    "email": response.user.email,
                    "username": user_data.username,
                    "email_confirmed": response.user.email_confirmed_at is not None
                }
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Registration failed"
            )
            
    except Exception as e:
        logger.error(f"Registration error: {e}")
        if "already registered" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.post(
    "/login",
    response_model=APIResponse,
    summary="User Login",
    description="Authenticate user and return access token",
    responses={
        200: {"description": "Login successful"},
        401: {"description": "Invalid credentials"},
        422: {"description": "Validation error"}
    }
)
async def login(user_data: UserLogin):
    """
    Authenticate user and return access tokens.
    
    Validates the user's credentials and returns access and refresh tokens
    that can be used for authenticated requests.
    
    - **email**: User's email address
    - **password**: User's password
    
    Returns access token, refresh token, and user information.
    """
    try:
        response = supabase.auth.sign_in_with_password({
            "email": user_data.email,
            "password": user_data.password
        })
        
        if response.user and response.session:
            return APIResponse(
                success=True,
                message="Login successful",
                data={
                    "access_token": response.session.access_token,
                    "refresh_token": response.session.refresh_token,
                    "token_type": "bearer",
                    "expires_in": response.session.expires_in,
                    "user": {
                        "id": response.user.id,
                        "email": response.user.email,
                        "username": response.user.user_metadata.get("username"),
                        "email_confirmed": response.user.email_confirmed_at is not None,
                        "last_sign_in": response.user.last_sign_in_at
                    }
                }
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )
            
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

@router.post(
    "/logout",
    response_model=APIResponse,
    summary="User Logout",
    description="Logout user and invalidate tokens",
    responses={
        200: {"description": "Logout successful"},
        401: {"description": "Invalid or expired token"}
    }
)
async def logout(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Logout user and invalidate their session.
    
    Invalidates the current session and access token. The user will need
    to log in again to access protected endpoints.
    
    Requires valid Bearer token in Authorization header.
    """
    try:
        # Set the session for the current user
        supabase.auth.set_session(credentials.credentials, None)
        supabase.auth.sign_out()
        
        return APIResponse(
            success=True,
            message="Logout successful"
        )
    except Exception as e:
        logger.error(f"Logout error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Logout failed"
        )

@router.get(
    "/me",
    response_model=APIResponse,
    summary="Get Current User",
    description="Get current authenticated user information",
    responses={
        200: {"description": "User information retrieved"},
        401: {"description": "Invalid or expired token"}
    }
)
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Get current authenticated user information.
    
    Returns detailed information about the currently authenticated user
    including profile data and account status.
    
    Requires valid Bearer token in Authorization header.
    """
    try:
        # Verify the token and get user info
        response = supabase.auth.get_user(credentials.credentials)
        
        if response.user:
            return APIResponse(
                success=True,
                message="User retrieved successfully",
                data={
                    "id": response.user.id,
                    "email": response.user.email,
                    "username": response.user.user_metadata.get("username"),
                    "email_confirmed": response.user.email_confirmed_at is not None,
                    "created_at": response.user.created_at,
                    "last_sign_in": response.user.last_sign_in_at,
                    "role": response.user.user_metadata.get("role", "player")
                }
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
            
    except Exception as e:
        logger.error(f"Get user error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

@router.post(
    "/refresh",
    response_model=APIResponse,
    summary="Refresh Access Token",
    description="Refresh access token using refresh token",
    responses={
        200: {"description": "Token refreshed successfully"},
        401: {"description": "Invalid refresh token"}
    }
)
async def refresh_token(refresh_token: str):
    """
    Refresh access token using refresh token.
    
    When an access token expires, use this endpoint with a valid refresh
    token to get a new access token without requiring the user to log in again.
    
    - **refresh_token**: Valid refresh token from login response
    """
    try:
        response = supabase.auth.refresh_session(refresh_token)
        
        if response.session:
            return APIResponse(
                success=True,
                message="Token refreshed successfully",
                data={
                    "access_token": response.session.access_token,
                    "refresh_token": response.session.refresh_token,
                    "token_type": "bearer",
                    "expires_in": response.session.expires_in
                }
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )
            
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )

@router.post(
    "/change-password",
    response_model=APIResponse,
    summary="Change Password",
    description="Change user password",
    responses={
        200: {"description": "Password changed successfully"},
        400: {"description": "Invalid current password"},
        401: {"description": "Authentication required"}
    }
)
async def change_password(
    current_password: str,
    new_password: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Change user password.
    
    Allows authenticated users to change their password by providing
    their current password and a new password.
    
    - **current_password**: User's current password
    - **new_password**: New password (minimum 6 characters)
    """
    try:
        # Verify current user
        user_response = supabase.auth.get_user(credentials.credentials)
        if not user_response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
        
        # Update password
        response = supabase.auth.update_user({
            "password": new_password
        })
        
        if response.user:
            return APIResponse(
                success=True,
                message="Password changed successfully"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to change password"
            )
            
    except Exception as e:
        logger.error(f"Change password error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to change password"
        )

async def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """
    Dependency to get current user ID from token.
    
    This is a dependency function used by other endpoints to extract
    the user ID from the authentication token.
    """
    try:
        response = supabase.auth.get_user(credentials.credentials)
        if response.user:
            return response.user.id
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
    except Exception as e:
        logger.error(f"Token validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

async def get_current_user_full(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """
    Dependency to get full current user information from token.
    
    Returns complete user information for endpoints that need more
    than just the user ID.
    """
    try:
        response = supabase.auth.get_user(credentials.credentials)
        if response.user:
            return {
                "id": response.user.id,
                "email": response.user.email,
                "username": response.user.user_metadata.get("username"),
                "role": response.user.user_metadata.get("role", "player")
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
    except Exception as e:
        logger.error(f"Token validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )