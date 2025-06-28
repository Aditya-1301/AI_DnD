from fastapi import APIRouter, HTTPException, Depends, status
from models.schemas import (
    GameAction, DiceRoll, DiceResult, APIResponse, 
    GameState, ErrorResponse
)
from routers.auth import get_current_user_id
from services.ai_service import AIService
import logging
from datetime import datetime
import os
from supabase import create_client, Client

logger = logging.getLogger(__name__)
router = APIRouter()

# Initialize AI service
ai_service = AIService()

# Supabase client
supabase_url = os.getenv('SUPABASE_URL')
supabase_key = os.getenv('SUPABASE_KEY')
supabase: Client = create_client(supabase_url, supabase_key)

@router.post(
    "/action/{session_id}",
    response_model=APIResponse,
    summary="Submit Game Action",
    description="Submit a player action to the AI Game Master",
    responses={
        200: {"description": "Action processed successfully"},
        400: {"description": "Invalid action or processing error"},
        404: {"description": "Session not found"},
        403: {"description": "Access denied"},
        401: {"description": "Authentication required"}
    }
)
async def submit_game_action(
    session_id: str,
    action: GameAction,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Submit a game action to the AI Game Master.
    
    The AI will process the action within the context of the current
    game session and generate an appropriate narrative response.
    
    - **session_id**: The ID of the game session
    - **action**: The action the player wants to take
    - **description**: Optional additional description
    - **parameters**: Optional action parameters
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
        
        # Check if session is active
        if session['status'] != 'active':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot perform actions in inactive session"
            )
        
        # TODO: Implement proper participant checking
        # For now, allow creator and assume others are participants
        
        response = await ai_service.process_game_action(action, session_id)
        
        return APIResponse(
            success=True,
            message="Action processed successfully",
            data=response
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Game action error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to process action: {str(e)}"
        )

@router.post(
    "/roll/{session_id}",
    response_model=DiceResult,
    summary="Roll Dice",
    description="Roll dice for skill checks or random events",
    responses={
        200: {"description": "Dice rolled successfully"},
        400: {"description": "Invalid dice roll parameters"},
        404: {"description": "Session not found"},
        403: {"description": "Access denied"},
        401: {"description": "Authentication required"}
    }
)
async def roll_dice(
    session_id: str,
    roll: DiceRoll,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Roll dice for skill checks or random events.
    
    Performs dice rolls and optionally interprets the results
    within the game context.
    
    - **session_id**: The ID of the game session
    - **dice_type**: Type of dice to roll (d4, d6, d8, d10, d12, d20, d100)
    - **count**: Number of dice to roll (1-10)
    - **modifier**: Modifier to add to the result (-20 to +20)
    - **skill_name**: Optional skill name for context
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
        
        # Check if session is active
        if session['status'] != 'active':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot roll dice in inactive session"
            )
        
        # TODO: Implement proper participant checking
        
        result = await ai_service.process_dice_roll(roll, session_id)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Dice roll error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to roll dice: {str(e)}"
        )

@router.post(
    "/initialize/{session_id}",
    response_model=APIResponse,
    summary="Initialize Game Session",
    description="Initialize a game session with the AI Game Master",
    responses={
        200: {"description": "Session initialized successfully"},
        404: {"description": "Session not found"},
        403: {"description": "Access denied - only session creator can initialize"},
        401: {"description": "Authentication required"}
    }
)
async def initialize_game_session(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Initialize a game session with the AI Game Master.
    
    Sets up the AI with the proper game master persona and
    creates the initial welcome message. Only the session
    creator can initialize the session.
    
    - **session_id**: The ID of the session to initialize
    """
    try:
        # Verify user owns the session
        session_response = supabase.table('sessions').select('creator_id, status').eq('id', session_id).execute()
        
        if not session_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        session = session_response.data[0]
        
        if session['creator_id'] != current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the session creator can initialize the session"
            )
        
        initial_message = await ai_service.initialize_session(session_id)
        
        return APIResponse(
            success=True,
            message="Session initialized successfully",
            data={
                "session_id": session_id,
                "initial_message": initial_message,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Session initialization error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to initialize session: {str(e)}"
        )

@router.get(
    "/state/{session_id}",
    response_model=GameState,
    summary="Get Game State",
    description="Get the current game state for a session",
    responses={
        200: {"description": "Game state retrieved successfully"},
        404: {"description": "Session not found"},
        403: {"description": "Access denied"},
        401: {"description": "Authentication required"}
    }
)
async def get_game_state(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Get the current game state for a session.
    
    Returns information about the current scene, active players,
    and game variables.
    
    - **session_id**: The ID of the session
    """
    try:
        # Verify user has access to the session
        session_response = supabase.table('sessions').select('creator_id, status').eq('id', session_id).execute()
        
        if not session_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        # TODO: Implement proper access control
        
        # Get recent messages to determine current scene
        messages_response = supabase.table('messages').select('content, role').eq('session_id', session_id).order('created_at', desc=True).limit(5).execute()
        
        current_scene = None
        last_action = None
        
        for msg in messages_response.data:
            if msg['role'] == 'model' and not current_scene:
                current_scene = msg['content'][:200] + "..." if len(msg['content']) > 200 else msg['content']
            elif msg['role'] == 'user' and not last_action:
                last_action = msg['content']
        
        # TODO: Implement proper participant tracking
        active_players = [current_user_id]
        
        game_state = GameState(
            session_id=session_id,
            current_scene=current_scene,
            active_players=active_players,
            game_variables={},  # TODO: Implement game variables storage
            last_action=last_action,
            timestamp=datetime.utcnow()
        )
        
        return game_state
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get game state error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to get game state: {str(e)}"
        )

@router.post(
    "/pause/{session_id}",
    response_model=APIResponse,
    summary="Pause Game Session",
    description="Pause an active game session",
    responses={
        200: {"description": "Session paused successfully"},
        404: {"description": "Session not found"},
        403: {"description": "Access denied - only session creator can pause"},
        400: {"description": "Session is not active"},
        401: {"description": "Authentication required"}
    }
)
async def pause_game_session(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Pause an active game session.
    
    Changes the session status to 'paused', preventing new actions
    until the session is resumed. Only the session creator can pause.
    
    - **session_id**: The ID of the session to pause
    """
    try:
        # Verify user owns the session
        session_response = supabase.table('sessions').select('creator_id, status').eq('id', session_id).execute()
        
        if not session_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        session = session_response.data[0]
        
        if session['creator_id'] != current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the session creator can pause the session"
            )
        
        if session['status'] != 'active':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Session is not active"
            )
        
        # Update session status
        supabase.table('sessions').update({'status': 'paused'}).eq('id', session_id).execute()
        
        return APIResponse(
            success=True,
            message="Session paused successfully",
            data={"session_id": session_id, "status": "paused"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pause session error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to pause session: {str(e)}"
        )

@router.post(
    "/resume/{session_id}",
    response_model=APIResponse,
    summary="Resume Game Session",
    description="Resume a paused game session",
    responses={
        200: {"description": "Session resumed successfully"},
        404: {"description": "Session not found"},
        403: {"description": "Access denied - only session creator can resume"},
        400: {"description": "Session is not paused"},
        401: {"description": "Authentication required"}
    }
)
async def resume_game_session(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Resume a paused game session.
    
    Changes the session status back to 'active', allowing new actions.
    Only the session creator can resume.
    
    - **session_id**: The ID of the session to resume
    """
    try:
        # Verify user owns the session
        session_response = supabase.table('sessions').select('creator_id, status').eq('id', session_id).execute()
        
        if not session_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        session = session_response.data[0]
        
        if session['creator_id'] != current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the session creator can resume the session"
            )
        
        if session['status'] != 'paused':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Session is not paused"
            )
        
        # Update session status
        supabase.table('sessions').update({'status': 'active'}).eq('id', session_id).execute()
        
        return APIResponse(
            success=True,
            message="Session resumed successfully",
            data={"session_id": session_id, "status": "active"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Resume session error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to resume session: {str(e)}"
        )

@router.post(
    "/complete/{session_id}",
    response_model=APIResponse,
    summary="Complete Game Session",
    description="Mark a game session as completed",
    responses={
        200: {"description": "Session completed successfully"},
        404: {"description": "Session not found"},
        403: {"description": "Access denied - only session creator can complete"},
        401: {"description": "Authentication required"}
    }
)
async def complete_game_session(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Mark a game session as completed.
    
    Changes the session status to 'completed', indicating the adventure
    has ended. Only the session creator can complete a session.
    
    - **session_id**: The ID of the session to complete
    """
    try:
        # Verify user owns the session
        session_response = supabase.table('sessions').select('creator_id, status').eq('id', session_id).execute()
        
        if not session_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        session = session_response.data[0]
        
        if session['creator_id'] != current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the session creator can complete the session"
            )
        
        # Update session status
        supabase.table('sessions').update({'status': 'completed'}).eq('id', session_id).execute()
        
        # Add a completion message
        await ai_service._save_message(
            session_id, 
            "system", 
            "The adventure has been completed. Thank you for playing!"
        )
        
        return APIResponse(
            success=True,
            message="Session completed successfully",
            data={"session_id": session_id, "status": "completed"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Complete session error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to complete session: {str(e)}"
        )