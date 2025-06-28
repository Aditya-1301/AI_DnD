from fastapi import FastAPI, HTTPException, Depends, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from contextlib import asynccontextmanager
import os
import logging
from dotenv import load_dotenv
from supabase import create_client, Client
import json
from typing import List, Dict, Optional
import asyncio
from datetime import datetime
import uuid

from routers import auth, sessions, game, messages, ai
from services.websocket_manager import WebSocketManager
from services.ai_service import AIService
from models.schemas import GameAction, DiceRoll, SessionCreate, MessageCreate

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize services
websocket_manager = WebSocketManager()
ai_service = AIService()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting TTRPG Web Application")
    yield
    # Shutdown
    logger.info("Shutting down TTRPG Web Application")

app = FastAPI(
    title="TTRPG Web Application API",
    description="""
    A comprehensive web-based Tabletop RPG platform with AI Game Master powered by Google's Gemini AI.
    
    ## Features
    
    * **AI Game Master**: Dynamic storytelling using Google Gemini AI
    * **Session Management**: Create, manage, and join game sessions
    * **Real-time Communication**: WebSocket-based live gameplay
    * **User Authentication**: Secure user registration and login
    * **Dice Rolling**: Built-in dice system with various dice types
    * **Message History**: Persistent conversation tracking
    
    ## Authentication
    
    Most endpoints require authentication using Bearer tokens. Register or login to get your access token.
    
    ## WebSocket Communication
    
    Real-time gameplay uses WebSocket connections at `/api/v1/ws/session/{session_id}`.
    """,
    version="1.0.0",
    lifespan=lifespan,
    contact={
        "name": "TTRPG Web Support",
        "email": "support@ttrpgweb.com",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers with proper tags and descriptions
app.include_router(
    auth.router, 
    prefix="/api/v1/auth", 
    tags=["Authentication"],
    responses={401: {"description": "Authentication failed"}}
)
app.include_router(
    sessions.router, 
    prefix="/api/v1/sessions", 
    tags=["Session Management"],
    responses={404: {"description": "Session not found"}}
)
app.include_router(
    game.router, 
    prefix="/api/v1/game", 
    tags=["Game Mechanics"],
    responses={400: {"description": "Invalid game action"}}
)
app.include_router(
    messages.router, 
    prefix="/api/v1/messages", 
    tags=["Message Management"],
    responses={403: {"description": "Access denied"}}
)
app.include_router(
    ai.router, 
    prefix="/api/v1/ai", 
    tags=["AI Game Master"],
    responses={500: {"description": "AI service error"}}
)

# Supabase client
supabase_url = os.getenv('SUPABASE_URL')
supabase_key = os.getenv('SUPABASE_KEY')
if not supabase_url or not supabase_key:
    raise ValueError("Please set SUPABASE_URL and SUPABASE_KEY environment variables")

supabase: Client = create_client(supabase_url, supabase_key)

@app.get(
    "/",
    summary="API Root",
    description="Get basic information about the TTRPG Web API",
    response_description="API information and version"
)
async def root():
    """
    Welcome endpoint that provides basic API information.
    
    Returns basic information about the TTRPG Web Application API including
    version, available endpoints, and links to documentation.
    """
    return {
        "message": "TTRPG Web Application API",
        "version": "1.0.0",
        "description": "AI-powered Tabletop RPG platform",
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "endpoints": {
            "authentication": "/api/v1/auth",
            "sessions": "/api/v1/sessions",
            "game": "/api/v1/game",
            "messages": "/api/v1/messages",
            "ai": "/api/v1/ai",
            "websocket": "/api/v1/ws/session/{session_id}"
        }
    }

@app.get(
    "/health",
    summary="Health Check",
    description="Check the health status of the API and its dependencies",
    response_description="Health status information"
)
async def health_check():
    """
    Health check endpoint for monitoring and load balancers.
    
    Verifies that the API is running and can connect to essential services
    like the database and AI service.
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "services": {}
    }
    
    # Check database connection
    try:
        supabase.table('sessions').select('id').limit(1).execute()
        health_status["services"]["database"] = "healthy"
    except Exception as e:
        health_status["services"]["database"] = f"unhealthy: {str(e)}"
        health_status["status"] = "degraded"
    
    # Check AI service
    try:
        ai_service.client  # Just check if client exists
        health_status["services"]["ai"] = "healthy"
    except Exception as e:
        health_status["services"]["ai"] = f"unhealthy: {str(e)}"
        health_status["status"] = "degraded"
    
    return health_status

# WebSocket endpoint for real-time game communication
@app.websocket("/api/v1/ws/session/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time game communication.
    
    Handles real-time messaging between players and the AI Game Master.
    Supports game actions, dice rolls, and typing indicators.
    
    Message Types:
    - game_action: Player actions that require GM response
    - dice_roll: Dice rolling requests
    - typing: Typing indicator updates
    """
    await websocket_manager.connect(websocket, session_id)
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            # Process the message based on type
            if message_data.get("type") == "game_action":
                # Handle game action
                action = GameAction(**message_data["payload"])
                response = await ai_service.process_game_action(action, session_id)
                
                # Broadcast response to all clients in the session
                await websocket_manager.broadcast_to_session(
                    session_id, 
                    {
                        "type": "gm_response",
                        "payload": response,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                )
            
            elif message_data.get("type") == "dice_roll":
                # Handle dice roll
                roll = DiceRoll(**message_data["payload"])
                result = await ai_service.process_dice_roll(roll, session_id)
                
                await websocket_manager.broadcast_to_session(
                    session_id,
                    {
                        "type": "dice_result",
                        "payload": result.dict(),
                        "timestamp": datetime.utcnow().isoformat()
                    }
                )
            
            elif message_data.get("type") == "typing":
                # Handle typing indicators
                await websocket_manager.broadcast_to_session(
                    session_id,
                    {
                        "type": "user_typing",
                        "payload": message_data["payload"],
                        "timestamp": datetime.utcnow().isoformat()
                    },
                    exclude_websocket=websocket
                )
                
    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket, session_id)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        websocket_manager.disconnect(websocket, session_id)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)