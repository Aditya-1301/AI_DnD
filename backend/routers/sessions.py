from fastapi import APIRouter, HTTPException, Depends, Query, status
from fastapi.security import HTTPAuthorizationCredentials
from models.schemas import (
    SessionCreate, SessionUpdate, Session, APIResponse, 
    SessionListResponse, ErrorResponse
)
from routers.auth import get_current_user_id, get_current_user_full
import os
from supabase import create_client, Client
import logging
from typing import Optional
import uuid

logger = logging.getLogger(__name__)
router = APIRouter()

# Supabase client
supabase_url = os.getenv('SUPABASE_URL')
supabase_key = os.getenv('SUPABASE_KEY')
supabase: Client = create_client(supabase_url, supabase_key)

@router.post(
    "/",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create New Session",
    description="Create a new game session",
    responses={
        201: {"description": "Session created successfully"},
        400: {"description": "Invalid session data"},
        401: {"description": "Authentication required"}
    }
)
async def create_session(
    session_data: SessionCreate,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Create a new game session.
    
    Creates a new TTRPG session with the specified parameters. The creating
    user becomes the session owner and can manage the session.
    
    - **title**: Optional session title (auto-generated if not provided)
    - **description**: Optional session description
    - **max_players**: Maximum number of players (1-10, default: 4)
    
    Returns the created session data and initial AI message.
    """
    try:
        session_uuid = str(uuid.uuid4())
        
        # Generate title if not provided
        title = session_data.title or f"Game Session {session_uuid[:8]}"
        
        response = supabase.table('sessions').insert({
            'session_uuid': session_uuid,
            'title': title,
            'description': session_data.description,
            'max_players': session_data.max_players,
            'creator_id': current_user_id,
            'status': 'active'
        }).execute()
        
        if response.data:
            session = response.data[0]
            
            # Initialize the session with AI
            from services.ai_service import AIService
            ai_service = AIService()
            initial_message = await ai_service.initialize_session(session['id'])
            
            return APIResponse(
                success=True,
                message="Session created successfully",
                data={
                    "session": session,
                    "initial_message": initial_message
                }
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create session"
            )
            
    except Exception as e:
        logger.error(f"Create session error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create session: {str(e)}"
        )

@router.get(
    "/",
    response_model=SessionListResponse,
    summary="List Sessions",
    description="Get a paginated list of user's sessions",
    responses={
        200: {"description": "Sessions retrieved successfully"},
        401: {"description": "Authentication required"}
    }
)
async def list_sessions(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(10, ge=1, le=100, description="Items per page"),
    status_filter: Optional[str] = Query(None, description="Filter by session status"),
    search: Optional[str] = Query(None, description="Search in title and description"),
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Get a paginated list of the user's game sessions.
    
    Returns sessions where the user is the creator or a participant.
    Supports filtering and searching.
    
    - **page**: Page number (starts from 1)
    - **per_page**: Number of sessions per page (1-100)
    - **status_filter**: Filter by session status (active, paused, completed)
    - **search**: Search term for title and description
    """
    try:
        offset = (page - 1) * per_page
        
        # Build query
        query = supabase.table('sessions').select('*')
        
        # Filter by creator (TODO: add participant filtering)
        query = query.eq('creator_id', current_user_id)
        
        # Apply status filter
        if status_filter:
            query = query.eq('status', status_filter)
        
        # Apply search filter
        if search:
            query = query.or_(f'title.ilike.%{search}%,description.ilike.%{search}%')
        
        # Apply pagination and ordering
        response = query.order('created_at', desc=True).range(offset, offset + per_page - 1).execute()
        
        # Get total count for pagination
        count_query = supabase.table('sessions').select('id', count='exact').eq('creator_id', current_user_id)
        if status_filter:
            count_query = count_query.eq('status', status_filter)
        if search:
            count_query = count_query.or_(f'title.ilike.%{search}%,description.ilike.%{search}%')
        
        count_response = count_query.execute()
        total = count_response.count
        
        return SessionListResponse(
            sessions=response.data,
            total=total,
            page=page,
            per_page=per_page
        )
        
    except Exception as e:
        logger.error(f"List sessions error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to retrieve sessions: {str(e)}"
        )

@router.get(
    "/{session_id}",
    response_model=APIResponse,
    summary="Get Session Details",
    description="Get detailed information about a specific session",
    responses={
        200: {"description": "Session retrieved successfully"},
        404: {"description": "Session not found"},
        403: {"description": "Access denied"},
        401: {"description": "Authentication required"}
    }
)
async def get_session(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Get detailed information about a specific session.
    
    Returns complete session information including metadata,
    participant count, and recent activity.
    
    - **session_id**: The unique identifier of the session
    """
    try:
        response = supabase.table('sessions').select('*').eq('id', session_id).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        session = response.data[0]
        
        # Check if user has access to this session
        if session['creator_id'] != current_user_id:
            # TODO: Check if user is a participant
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        # Get additional session statistics
        messages_response = supabase.table('messages').select('id', count='exact').eq('session_id', session_id).execute()
        message_count = messages_response.count
        
        # Get last activity
        last_message_response = supabase.table('messages').select('created_at').eq('session_id', session_id).order('created_at', desc=True).limit(1).execute()
        last_activity = last_message_response.data[0]['created_at'] if last_message_response.data else session['created_at']
        
        session_data = {
            **session,
            "message_count": message_count,
            "last_activity": last_activity,
            "participant_count": 1  # TODO: Implement participant counting
        }
        
        return APIResponse(
            success=True,
            message="Session retrieved successfully",
            data=session_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get session error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to retrieve session: {str(e)}"
        )

@router.put(
    "/{session_id}",
    response_model=APIResponse,
    summary="Update Session",
    description="Update session information",
    responses={
        200: {"description": "Session updated successfully"},
        404: {"description": "Session not found"},
        403: {"description": "Access denied - only session owner can update"},
        401: {"description": "Authentication required"}
    }
)
async def update_session(
    session_id: str,
    session_data: SessionUpdate,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Update session information.
    
    Only the session creator can update session details.
    
    - **session_id**: The unique identifier of the session
    - **title**: Updated session title
    - **description**: Updated session description  
    - **status**: Updated session status (active, paused, completed)
    """
    try:
        # Check if user owns the session
        session_response = supabase.table('sessions').select('creator_id').eq('id', session_id).execute()
        
        if not session_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        if session_response.data[0]['creator_id'] != current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the session creator can update the session"
            )
        
        # Update the session
        update_data = {k: v for k, v in session_data.dict().items() if v is not None}
        update_data['updated_at'] = 'now()'
        
        response = supabase.table('sessions').update(update_data).eq('id', session_id).execute()
        
        return APIResponse(
            success=True,
            message="Session updated successfully",
            data=response.data[0] if response.data else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update session error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to update session: {str(e)}"
        )

@router.delete(
    "/{session_id}",
    response_model=APIResponse,
    summary="Delete Session",
    description="Delete a session and all associated data",
    responses={
        200: {"description": "Session deleted successfully"},
        404: {"description": "Session not found"},
        403: {"description": "Access denied - only session owner can delete"},
        401: {"description": "Authentication required"}
    }
)
async def delete_session(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Delete a session and all associated data.
    
    This permanently deletes the session and all its messages.
    Only the session creator can delete a session.
    
    - **session_id**: The unique identifier of the session to delete
    """
    try:
        # Check if user owns the session
        session_response = supabase.table('sessions').select('creator_id').eq('id', session_id).execute()
        
        if not session_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        if session_response.data[0]['creator_id'] != current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the session creator can delete the session"
            )
        
        # Delete associated messages first
        supabase.table('messages').delete().eq('session_id', session_id).execute()
        
        # Delete the session
        supabase.table('sessions').delete().eq('id', session_id).execute()
        
        return APIResponse(
            success=True,
            message="Session deleted successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete session error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to delete session: {str(e)}"
        )

@router.post(
    "/{session_id}/join",
    response_model=APIResponse,
    summary="Join Session",
    description="Join a session as a player",
    responses={
        200: {"description": "Joined session successfully"},
        404: {"description": "Session not found"},
        400: {"description": "Cannot join session (full, inactive, etc.)"},
        401: {"description": "Authentication required"}
    }
)
async def join_session(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Join a session as a player.
    
    Allows users to join active sessions that have available slots.
    
    - **session_id**: The unique identifier of the session to join
    """
    try:
        # Get session info
        session_response = supabase.table('sessions').select('*').eq('id', session_id).execute()
        
        if not session_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        session = session_response.data[0]
        
        # Check if session is active
        if session['status'] != 'active':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot join inactive session"
            )
        
        # TODO: Implement session participants table and check max_players
        # TODO: Check if user is already in the session
        # For now, just return success
        
        return APIResponse(
            success=True,
            message="Joined session successfully",
            data=session
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Join session error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to join session: {str(e)}"
        )

@router.post(
    "/{session_id}/leave",
    response_model=APIResponse,
    summary="Leave Session",
    description="Leave a session as a player",
    responses={
        200: {"description": "Left session successfully"},
        404: {"description": "Session not found"},
        400: {"description": "Cannot leave session (not a participant, etc.)"},
        401: {"description": "Authentication required"}
    }
)
async def leave_session(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Leave a session as a player.
    
    Removes the user from the session participant list.
    Session creators cannot leave their own sessions.
    
    - **session_id**: The unique identifier of the session to leave
    """
    try:
        # Get session info
        session_response = supabase.table('sessions').select('creator_id').eq('id', session_id).execute()
        
        if not session_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        session = session_response.data[0]
        
        # Check if user is the creator
        if session['creator_id'] == current_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Session creators cannot leave their own sessions"
            )
        
        # TODO: Implement session participants table and remove user
        # For now, just return success
        
        return APIResponse(
            success=True,
            message="Left session successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Leave session error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to leave session: {str(e)}"
        )

@router.get(
    "/{session_id}/participants",
    response_model=APIResponse,
    summary="Get Session Participants",
    description="Get list of session participants",
    responses={
        200: {"description": "Participants retrieved successfully"},
        404: {"description": "Session not found"},
        403: {"description": "Access denied"},
        401: {"description": "Authentication required"}
    }
)
async def get_session_participants(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Get list of session participants.
    
    Returns information about all users participating in the session.
    
    - **session_id**: The unique identifier of the session
    """
    try:
        # Check if user has access to the session
        session_response = supabase.table('sessions').select('creator_id').eq('id', session_id).execute()
        
        if not session_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        # TODO: Implement proper access control
        # TODO: Implement participants table and return participant list
        
        # For now, return just the creator
        participants = [
            {
                "user_id": session_response.data[0]['creator_id'],
                "role": "creator",
                "joined_at": session_response.data[0].get('created_at'),
                "is_online": False  # TODO: Implement online status
            }
        ]
        
        return APIResponse(
            success=True,
            message="Participants retrieved successfully",
            data={
                "session_id": session_id,
                "participants": participants,
                "total_participants": len(participants)
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get participants error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to get participants: {str(e)}"
        )