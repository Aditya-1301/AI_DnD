from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from enum import Enum

class UserRole(str, Enum):
    """User role enumeration"""
    PLAYER = "player"
    GM = "gm"
    ADMIN = "admin"

class SessionStatus(str, Enum):
    """Session status enumeration"""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"

class MessageRole(str, Enum):
    """Message role enumeration"""
    USER = "user"
    MODEL = "model"
    SYSTEM = "system"

class DiceType(str, Enum):
    """Supported dice types"""
    D4 = "d4"
    D6 = "d6"
    D8 = "d8"
    D10 = "d10"
    D12 = "d12"
    D20 = "d20"
    D100 = "d100"

# User schemas
class UserCreate(BaseModel):
    """Schema for user registration"""
    email: str = Field(..., description="User's email address", example="player@example.com")
    password: str = Field(..., min_length=6, description="User's password (minimum 6 characters)")
    username: Optional[str] = Field(None, description="Optional username", example="DragonSlayer")

    @validator('email')
    def validate_email(cls, v):
        if '@' not in v:
            raise ValueError('Invalid email format')
        return v.lower()

class UserLogin(BaseModel):
    """Schema for user login"""
    email: str = Field(..., description="User's email address")
    password: str = Field(..., description="User's password")

class User(BaseModel):
    """User information schema"""
    id: str
    email: str
    username: Optional[str] = None
    role: UserRole = UserRole.PLAYER
    created_at: datetime

    class Config:
        from_attributes = True

# Session schemas
class SessionCreate(BaseModel):
    """Schema for creating a new game session"""
    title: Optional[str] = Field(None, description="Session title", example="The Dragon's Lair")
    description: Optional[str] = Field(None, description="Session description", example="A thrilling adventure in ancient dungeons")
    max_players: int = Field(default=4, ge=1, le=10, description="Maximum number of players allowed")

class SessionUpdate(BaseModel):
    """Schema for updating an existing session"""
    title: Optional[str] = Field(None, description="Updated session title")
    description: Optional[str] = Field(None, description="Updated session description")
    status: Optional[SessionStatus] = Field(None, description="Updated session status")

class Session(BaseModel):
    """Complete session information schema"""
    id: str
    session_uuid: str
    title: Optional[str] = None
    description: Optional[str] = None
    status: SessionStatus = SessionStatus.ACTIVE
    max_players: int = 4
    created_at: datetime
    updated_at: datetime
    creator_id: str

    class Config:
        from_attributes = True

# Message schemas
class MessageCreate(BaseModel):
    """Schema for creating a new message"""
    content: str = Field(..., description="Message content", example="I want to search for traps")
    role: MessageRole = Field(default=MessageRole.USER, description="Message role")

class Message(BaseModel):
    """Complete message information schema"""
    id: str
    session_id: str
    user_id: Optional[str] = None
    content: str
    role: MessageRole
    created_at: datetime

    class Config:
        from_attributes = True

# Game action schemas
class GameAction(BaseModel):
    """Schema for game actions submitted by players"""
    action: str = Field(..., description="The action the player wants to take", example="Attack the goblin with my sword")
    description: Optional[str] = Field(None, description="Additional description of the action")
    parameters: Optional[Dict[str, Any]] = Field(None, description="Additional parameters for the action")

    @validator('action')
    def validate_action(cls, v):
        if len(v.strip()) == 0:
            raise ValueError('Action cannot be empty')
        return v.strip()

class DiceRoll(BaseModel):
    """Schema for dice rolling requests"""
    dice_type: DiceType = Field(default=DiceType.D20, description="Type of dice to roll")
    count: int = Field(default=1, ge=1, le=10, description="Number of dice to roll")
    modifier: int = Field(default=0, ge=-20, le=20, description="Modifier to add to the roll")
    skill_name: Optional[str] = Field(None, description="Name of the skill being checked", example="Stealth")

class DiceResult(BaseModel):
    """Schema for dice roll results"""
    rolls: List[int] = Field(..., description="Individual dice roll results")
    total: int = Field(..., description="Sum of all dice rolls")
    modifier: int = Field(..., description="Modifier applied to the roll")
    final_result: int = Field(..., description="Total + modifier")
    skill_name: Optional[str] = Field(None, description="Skill name if this was a skill check")
    success: Optional[bool] = Field(None, description="Whether the roll was successful (if applicable)")

# AI interaction schemas
class AIPrompt(BaseModel):
    """Schema for direct AI prompts"""
    prompt: str = Field(..., description="The prompt to send to the AI", example="Describe a mysterious forest")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="AI creativity level (0.0-2.0)")
    max_tokens: Optional[int] = Field(None, ge=1, le=4000, description="Maximum tokens in response")

class AIResponse(BaseModel):
    """Schema for AI responses"""
    response: str = Field(..., description="The AI's response")
    tokens_used: Optional[int] = Field(None, description="Number of tokens used")
    model: str = Field(..., description="AI model used")
    timestamp: datetime = Field(..., description="Response timestamp")

# WebSocket message schemas
class WebSocketMessage(BaseModel):
    """Schema for WebSocket messages"""
    type: str = Field(..., description="Message type", example="game_action")
    payload: Dict[str, Any] = Field(..., description="Message payload")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    user_id: Optional[str] = Field(None, description="User ID of sender")

# Response schemas
class APIResponse(BaseModel):
    """Standard API response schema"""
    success: bool = Field(..., description="Whether the operation was successful")
    message: str = Field(..., description="Human-readable message")
    data: Optional[Any] = Field(None, description="Response data")

class ErrorResponse(BaseModel):
    """Error response schema"""
    success: bool = Field(default=False, description="Always false for errors")
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")

class SessionListResponse(BaseModel):
    """Schema for session list responses"""
    sessions: List[Session] = Field(..., description="List of sessions")
    total: int = Field(..., description="Total number of sessions")
    page: int = Field(..., description="Current page number")
    per_page: int = Field(..., description="Items per page")

class MessageListResponse(BaseModel):
    """Schema for message list responses"""
    messages: List[Message] = Field(..., description="List of messages")
    total: int = Field(..., description="Total number of messages")
    page: int = Field(..., description="Current page number")
    per_page: int = Field(..., description="Items per page")

# Game state schemas
class GameState(BaseModel):
    """Schema for game state information"""
    session_id: str = Field(..., description="Session identifier")
    current_scene: Optional[str] = Field(None, description="Current scene description")
    active_players: List[str] = Field(default_factory=list, description="List of active player IDs")
    game_variables: Dict[str, Any] = Field(default_factory=dict, description="Game state variables")
    last_action: Optional[str] = Field(None, description="Last action taken")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

# Statistics schemas
class SessionStats(BaseModel):
    """Schema for session statistics"""
    session_id: str
    total_messages: int = Field(..., description="Total messages in session")
    total_actions: int = Field(..., description="Total game actions")
    total_dice_rolls: int = Field(..., description="Total dice rolls")
    session_duration: Optional[int] = Field(None, description="Session duration in minutes")
    created_at: datetime
    last_activity: datetime

class UserStats(BaseModel):
    """Schema for user statistics"""
    user_id: str
    total_sessions: int = Field(..., description="Total sessions created")
    total_messages: int = Field(..., description="Total messages sent")
    total_playtime: int = Field(..., description="Total playtime in minutes")
    favorite_dice: Optional[str] = Field(None, description="Most used dice type")
    joined_at: datetime