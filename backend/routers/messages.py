from fastapi import APIRouter, HTTPException, Depends, Query, status
from models.schemas import (
    MessageCreate, Message, APIResponse, MessageListResponse, 
    ErrorResponse
)
from routers.auth import get_current_user_id
import os
from supabase import create_client, Client
import logging
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter()

# Supabase client
supabase_url = os.getenv('SUPABASE_URL')
supabase_key = os.getenv('SUPABASE_KEY')
supabase: Client = create_client(supabase_url, supabase_key)

@router.get(
    "/{session_id}",
    response_model=MessageListResponse,
    summary="Get Session Messages",
    description="Get paginated messages for a session",
    responses={
        200: {"description": "Messages retrieved successfully"},
        404: {"description": "Session not found"},
        403: {"description": "Access denied"},
        401: {"description": "Authentication required"}
    }
)
async def get_session_messages(
    session_id: str,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=100, description="Messages per page"),
    role_filter: Optional[str] = Query(None, description="Filter by message role"),
    search: Optional[str] = Query(None, description="Search in message content"),
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Get paginated messages for a session.
    
    Returns conversation history with support for filtering and searching.
    Messages are ordered chronologically.
    
    - **session_id**: The ID of the session
    - **page**: Page number (starts from 1)
    - **per_page**: Number of messages per page (1-100)
    - **role_filter**: Filter by message role (user, model, system)
    - **search**: Search term for message content
    """
    try:
        # Verify user has access to the session
        session_response = supabase.table('sessions').select('creator_id').eq('id', session_id).execute()
        
        if not session_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        # TODO: Implement proper participant checking
        # For now, allow access if user is creator or assume they're a participant
        
        offset = (page - 1) * per_page
        
        # Build query
        query = supabase.table('messages').select('*').eq('session_id', session_id)
        
        # Apply role filter
        if role_filter:
            query = query.eq('role', role_filter)
        
        # Apply search filter
        if search:
            query = query.ilike('content', f'%{search}%')
        
        # Execute query with pagination
        response = query.order('created_at').range(offset, offset + per_page - 1).execute()
        
        # Get total count for pagination
        count_query = supabase.table('messages').select('id', count='exact').eq('session_id', session_id)
        if role_filter:
            count_query = count_query.eq('role', role_filter)
        if search:
            count_query = count_query.ilike('content', f'%{search}%')
        
        count_response = count_query.execute()
        total = count_response.count
        
        return MessageListResponse(
            messages=response.data,
            total=total,
            page=page,
            per_page=per_page
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get messages error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to retrieve messages: {str(e)}"
        )

@router.post(
    "/{session_id}",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Message",
    description="Create a new message in a session",
    responses={
        201: {"description": "Message created successfully"},
        400: {"description": "Invalid message data"},
        404: {"description": "Session not found"},
        403: {"description": "Access denied"},
        401: {"description": "Authentication required"}
    }
)
async def create_message(
    session_id: str,
    message_data: MessageCreate,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Create a new message in a session.
    
    Adds a message to the session conversation. The message will be
    visible to all session participants.
    
    - **session_id**: The ID of the session
    - **content**: The message content
    - **role**: The message role (user, model, system)
    """
    try:
        # Verify user has access to the session
        session_response = supabase.table('sessions').select('creator_id, status').eq('id', session_id).execute()
        
        if not session_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        session = session_response.data[0]
        
        # Check if session allows new messages
        if session['status'] == 'completed':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot add messages to completed session"
            )
        
        # TODO: Implement proper participant checking
        
        response = supabase.table('messages').insert({
            'session_id': session_id,
            'user_id': current_user_id,
            'content': message_data.content,
            'role': message_data.role
        }).execute()
        
        if response.data:
            return APIResponse(
                success=True,
                message="Message created successfully",
                data=response.data[0]
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create message"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create message error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create message: {str(e)}"
        )

@router.get(
    "/{session_id}/{message_id}",
    response_model=APIResponse,
    summary="Get Specific Message",
    description="Get details of a specific message",
    responses={
        200: {"description": "Message retrieved successfully"},
        404: {"description": "Message or session not found"},
        403: {"description": "Access denied"},
        401: {"description": "Authentication required"}
    }
)
async def get_message(
    session_id: str,
    message_id: str,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Get details of a specific message.
    
    Returns complete information about a single message including
    metadata and timestamps.
    
    - **session_id**: The ID of the session
    - **message_id**: The ID of the message
    """
    try:
        # Verify user has access to the session
        session_response = supabase.table('sessions').select('creator_id').eq('id', session_id).execute()
        
        if not session_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        # TODO: Implement proper participant checking
        
        # Get the specific message
        message_response = supabase.table('messages').select('*').eq('id', message_id).eq('session_id', session_id).execute()
        
        if not message_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Message not found"
            )
        
        return APIResponse(
            success=True,
            message="Message retrieved successfully",
            data=message_response.data[0]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get message error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to retrieve message: {str(e)}"
        )

@router.delete(
    "/{session_id}/{message_id}",
    response_model=APIResponse,
    summary="Delete Message",
    description="Delete a specific message",
    responses={
        200: {"description": "Message deleted successfully"},
        404: {"description": "Message or session not found"},
        403: {"description": "Access denied - can only delete own messages"},
        401: {"description": "Authentication required"}
    }
)
async def delete_message(
    session_id: str,
    message_id: str,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Delete a specific message.
    
    Users can only delete their own messages. Session creators can
    delete any message in their sessions.
    
    - **session_id**: The ID of the session
    - **message_id**: The ID of the message to delete
    """
    try:
        # Verify user has access to the session
        session_response = supabase.table('sessions').select('creator_id').eq('id', session_id).execute()
        
        if not session_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        session = session_response.data[0]
        
        # Get the message to check ownership
        message_response = supabase.table('messages').select('user_id').eq('id', message_id).eq('session_id', session_id).execute()
        
        if not message_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Message not found"
            )
        
        message = message_response.data[0]
        
        # Check if user can delete this message
        if message['user_id'] != current_user_id and session['creator_id'] != current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Can only delete your own messages or messages in your sessions"
            )
        
        # Delete the message
        supabase.table('messages').delete().eq('id', message_id).execute()
        
        return APIResponse(
            success=True,
            message="Message deleted successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete message error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to delete message: {str(e)}"
        )

@router.delete(
    "/{session_id}/clear",
    response_model=APIResponse,
    summary="Clear Session Messages",
    description="Clear all messages from a session",
    responses={
        200: {"description": "Messages cleared successfully"},
        404: {"description": "Session not found"},
        403: {"description": "Access denied - only session creator can clear messages"},
        401: {"description": "Authentication required"}
    }
)
async def clear_session_messages(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Clear all messages from a session.
    
    Permanently deletes all conversation history for the session.
    Only the session creator can perform this action.
    
    - **session_id**: The ID of the session to clear
    """
    try:
        # Verify user owns the session
        session_response = supabase.table('sessions').select('creator_id').eq('id', session_id).execute()
        
        if not session_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        session = session_response.data[0]
        
        if session['creator_id'] != current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the session creator can clear messages"
            )
        
        # Delete all messages for the session
        result = supabase.table('messages').delete().eq('session_id', session_id).execute()
        
        return APIResponse(
            success=True,
            message="Messages cleared successfully",
            data={"session_id": session_id, "cleared_count": len(result.data) if result.data else 0}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Clear messages error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to clear messages: {str(e)}"
        )

@router.get(
    "/{session_id}/export",
    response_model=APIResponse,
    summary="Export Session Messages",
    description="Export all session messages in various formats",
    responses={
        200: {"description": "Messages exported successfully"},
        404: {"description": "Session not found"},
        403: {"description": "Access denied"},
        401: {"description": "Authentication required"}
    }
)
async def export_session_messages(
    session_id: str,
    format: str = Query("json", description="Export format (json, txt, csv)"),
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Export all session messages in various formats.
    
    Allows users to download their conversation history in different
    formats for backup or sharing purposes.
    
    - **session_id**: The ID of the session to export
    - **format**: Export format (json, txt, csv)
    """
    try:
        # Verify user has access to the session
        session_response = supabase.table('sessions').select('creator_id, title').eq('id', session_id).execute()
        
        if not session_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        # TODO: Implement proper participant checking
        
        # Get all messages
        messages_response = supabase.table('messages').select('*').eq('session_id', session_id).order('created_at').execute()
        
        messages = messages_response.data
        session_title = session_response.data[0]['title']
        
        if format.lower() == "txt":
            # Plain text format
            export_content = f"Session: {session_title}\n"
            export_content += f"Exported on: {datetime.utcnow().isoformat()}\n"
            export_content += "=" * 50 + "\n\n"
            
            for msg in messages:
                role_label = {
                    'user': 'Player',
                    'model': 'Game Master',
                    'system': 'System'
                }.get(msg['role'], msg['role'].title())
                
                export_content += f"[{msg['created_at']}] {role_label}:\n"
                export_content += f"{msg['content']}\n\n"
        
        elif format.lower() == "csv":
            # CSV format
            import csv
            import io
            
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['timestamp', 'role', 'content', 'user_id'])
            
            for msg in messages:
                writer.writerow([
                    msg['created_at'],
                    msg['role'],
                    msg['content'],
                    msg.get('user_id', '')
                ])
            
            export_content = output.getvalue()
        
        else:  # JSON format (default)
            import json
            export_data = {
                "session_id": session_id,
                "session_title": session_title,
                "exported_at": datetime.utcnow().isoformat(),
                "message_count": len(messages),
                "messages": messages
            }
            export_content = json.dumps(export_data, indent=2)
        
        return APIResponse(
            success=True,
            message="Messages exported successfully",
            data={
                "session_id": session_id,
                "format": format,
                "content": export_content,
                "message_count": len(messages)
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Export messages error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to export messages: {str(e)}"
        )