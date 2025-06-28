from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.responses import StreamingResponse
from models.schemas import (
    AIPrompt, AIResponse, APIResponse, ErrorResponse,
    GameAction, DiceRoll, SessionStats
)
from routers.auth import get_current_user_id
from services.ai_service import AIService
import logging
from typing import AsyncGenerator
import json
from datetime import datetime

logger = logging.getLogger(__name__)
router = APIRouter()

# Initialize AI service
ai_service = AIService()

@router.post(
    "/prompt",
    response_model=AIResponse,
    summary="Send Direct AI Prompt",
    description="Send a direct prompt to the AI without game context",
    responses={
        200: {"description": "AI response generated successfully"},
        400: {"description": "Invalid prompt or AI service error"},
        401: {"description": "Authentication required"},
        500: {"description": "Internal AI service error"}
    }
)
async def send_ai_prompt(
    prompt_data: AIPrompt,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Send a direct prompt to the AI service.
    
    This endpoint allows sending custom prompts to the AI without the context
    of a game session. Useful for testing AI responses or getting general
    creative content.
    
    - **prompt**: The text prompt to send to the AI
    - **temperature**: Controls randomness (0.0 = deterministic, 2.0 = very creative)
    - **max_tokens**: Maximum length of the response
    """
    try:
        response = await ai_service.generate_direct_response(
            prompt_data.prompt,
            temperature=prompt_data.temperature,
            max_tokens=prompt_data.max_tokens
        )
        
        return AIResponse(
            response=response["text"],
            tokens_used=response.get("tokens_used"),
            model=response.get("model", "gemini-2.5-flash-preview-05-20"),
            timestamp=datetime.utcnow()
        )
        
    except Exception as e:
        logger.error(f"AI prompt error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI service error: {str(e)}"
        )

@router.post(
    "/stream-prompt",
    summary="Stream AI Response",
    description="Send a prompt and receive a streaming response",
    responses={
        200: {"description": "Streaming AI response"},
        400: {"description": "Invalid prompt"},
        401: {"description": "Authentication required"}
    }
)
async def stream_ai_prompt(
    prompt_data: AIPrompt,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Send a prompt and receive the AI response as a stream.
    
    This endpoint provides real-time streaming of AI responses, allowing
    for better user experience with long responses.
    """
    async def generate_stream() -> AsyncGenerator[str, None]:
        try:
            async for chunk in ai_service.stream_response(
                prompt_data.prompt,
                temperature=prompt_data.temperature
            ):
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            yield "data: [DONE]\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/plain",
        headers={"Cache-Control": "no-cache"}
    )

@router.post(
    "/initialize-session/{session_id}",
    response_model=APIResponse,
    summary="Initialize AI for Session",
    description="Initialize the AI Game Master for a specific session",
    responses={
        200: {"description": "Session initialized successfully"},
        404: {"description": "Session not found"},
        401: {"description": "Authentication required"},
        403: {"description": "Access denied"}
    }
)
async def initialize_ai_session(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Initialize the AI Game Master for a game session.
    
    This sets up the AI with the proper game master persona and
    creates the initial welcome message for the session.
    
    - **session_id**: The ID of the session to initialize
    """
    try:
        # TODO: Verify user has access to the session
        
        initial_message = await ai_service.initialize_session(session_id)
        
        return APIResponse(
            success=True,
            message="AI Game Master initialized successfully",
            data={
                "session_id": session_id,
                "initial_message": initial_message,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        
    except Exception as e:
        logger.error(f"AI session initialization error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize AI session: {str(e)}"
        )

@router.post(
    "/process-action/{session_id}",
    response_model=APIResponse,
    summary="Process Game Action",
    description="Process a player action through the AI Game Master",
    responses={
        200: {"description": "Action processed successfully"},
        400: {"description": "Invalid action"},
        404: {"description": "Session not found"},
        401: {"description": "Authentication required"}
    }
)
async def process_game_action(
    session_id: str,
    action: GameAction,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Process a player's game action through the AI Game Master.
    
    The AI will interpret the action within the context of the current
    game session and generate an appropriate response.
    
    - **session_id**: The ID of the game session
    - **action**: The player's action description
    - **description**: Optional additional details
    - **parameters**: Optional action parameters
    """
    try:
        # TODO: Verify user has access to the session
        
        response = await ai_service.process_game_action(action, session_id)
        
        return APIResponse(
            success=True,
            message="Game action processed successfully",
            data=response
        )
        
    except Exception as e:
        logger.error(f"Game action processing error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to process game action: {str(e)}"
        )

@router.post(
    "/roll-dice/{session_id}",
    response_model=APIResponse,
    summary="Process Dice Roll",
    description="Process a dice roll and get AI interpretation",
    responses={
        200: {"description": "Dice roll processed successfully"},
        400: {"description": "Invalid dice roll"},
        404: {"description": "Session not found"},
        401: {"description": "Authentication required"}
    }
)
async def process_dice_roll(
    session_id: str,
    roll: DiceRoll,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Process a dice roll within the context of a game session.
    
    The AI can interpret the results and provide narrative context
    for the roll outcome.
    
    - **session_id**: The ID of the game session
    - **dice_type**: Type of dice (d4, d6, d8, d10, d12, d20, d100)
    - **count**: Number of dice to roll
    - **modifier**: Modifier to add to the result
    - **skill_name**: Optional skill name for context
    """
    try:
        # TODO: Verify user has access to the session
        
        result = await ai_service.process_dice_roll(roll, session_id)
        
        return APIResponse(
            success=True,
            message="Dice roll processed successfully",
            data=result.dict()
        )
        
    except Exception as e:
        logger.error(f"Dice roll processing error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to process dice roll: {str(e)}"
        )

@router.get(
    "/session-context/{session_id}",
    response_model=APIResponse,
    summary="Get Session Context",
    description="Get the current AI context for a session",
    responses={
        200: {"description": "Context retrieved successfully"},
        404: {"description": "Session not found"},
        401: {"description": "Authentication required"},
        403: {"description": "Access denied"}
    }
)
async def get_session_context(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Get the current AI context and conversation history for a session.
    
    This includes the conversation history, current game state,
    and AI memory context.
    
    - **session_id**: The ID of the session
    """
    try:
        # TODO: Verify user has access to the session
        
        context = await ai_service.get_session_context(session_id)
        
        return APIResponse(
            success=True,
            message="Session context retrieved successfully",
            data=context
        )
        
    except Exception as e:
        logger.error(f"Get session context error: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Failed to get session context: {str(e)}"
        )

@router.delete(
    "/reset-session/{session_id}",
    response_model=APIResponse,
    summary="Reset Session Context",
    description="Reset the AI context for a session",
    responses={
        200: {"description": "Session reset successfully"},
        404: {"description": "Session not found"},
        401: {"description": "Authentication required"},
        403: {"description": "Access denied"}
    }
)
async def reset_session_context(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Reset the AI context and conversation history for a session.
    
    This will clear all conversation history and reset the AI
    to its initial state for the session.
    
    - **session_id**: The ID of the session to reset
    """
    try:
        # TODO: Verify user owns the session
        
        await ai_service.reset_session_context(session_id)
        
        return APIResponse(
            success=True,
            message="Session context reset successfully",
            data={"session_id": session_id, "timestamp": datetime.utcnow().isoformat()}
        )
        
    except Exception as e:
        logger.error(f"Reset session context error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset session context: {str(e)}"
        )

@router.get(
    "/models",
    response_model=APIResponse,
    summary="Get Available AI Models",
    description="Get list of available AI models and their capabilities",
    responses={
        200: {"description": "Models retrieved successfully"},
        401: {"description": "Authentication required"}
    }
)
async def get_available_models(
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Get information about available AI models.
    
    Returns a list of available AI models with their capabilities,
    token limits, and recommended use cases.
    """
    try:
        models = await ai_service.get_available_models()
        
        return APIResponse(
            success=True,
            message="Available models retrieved successfully",
            data=models
        )
        
    except Exception as e:
        logger.error(f"Get models error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get available models: {str(e)}"
        )

@router.get(
    "/stats/{session_id}",
    response_model=SessionStats,
    summary="Get Session AI Statistics",
    description="Get AI usage statistics for a session",
    responses={
        200: {"description": "Statistics retrieved successfully"},
        404: {"description": "Session not found"},
        401: {"description": "Authentication required"},
        403: {"description": "Access denied"}
    }
)
async def get_session_ai_stats(
    session_id: str,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Get AI usage statistics for a specific session.
    
    Includes information about AI interactions, token usage,
    and response times for the session.
    
    - **session_id**: The ID of the session
    """
    try:
        # TODO: Verify user has access to the session
        
        stats = await ai_service.get_session_stats(session_id)
        
        return stats
        
    except Exception as e:
        logger.error(f"Get session stats error: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Failed to get session statistics: {str(e)}"
        )