import os
import logging
from typing import Dict, List, Optional, AsyncGenerator
from google import genai
from google.genai import types
from models.schemas import GameAction, DiceRoll, DiceResult, SessionStats
import random
from datetime import datetime
import asyncio

logger = logging.getLogger(__name__)

class AIService:
    def __init__(self):
        self.client = None
        self.setup_client()
        
    def setup_client(self):
        """Initialize the Gemini AI client"""
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            logger.error("GEMINI_API_KEY not found in environment variables")
            raise ValueError("GEMINI_API_KEY is required")
        
        self.client = genai.Client(api_key=api_key)
        logger.info("Gemini AI client initialized successfully")

    async def generate_direct_response(
        self, 
        prompt: str, 
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> Dict:
        """Generate a direct AI response without game context"""
        try:
            config = types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_tokens
            )
            
            response = self.client.models.generate_content(
                model="gemini-2.5-flash-preview-05-20",
                contents=[types.Content(parts=[types.Part(text=prompt)], role="user")],
                config=config
            )
            
            return {
                "text": response.text,
                "model": "gemini-2.5-flash-preview-05-20",
                "tokens_used": len(response.text.split()) if response.text else 0
            }
            
        except Exception as e:
            logger.error(f"Error generating direct response: {e}")
            raise

    async def stream_response(
        self, 
        prompt: str, 
        temperature: float = 0.7
    ) -> AsyncGenerator[str, None]:
        """Stream AI response in chunks"""
        try:
            # Note: Gemini doesn't support streaming in the current SDK
            # This is a simulation - in production you'd use the streaming API
            response = await self.generate_direct_response(prompt, temperature)
            text = response["text"]
            
            # Simulate streaming by yielding chunks
            chunk_size = 50
            for i in range(0, len(text), chunk_size):
                chunk = text[i:i + chunk_size]
                yield chunk
                await asyncio.sleep(0.1)  # Simulate network delay
                
        except Exception as e:
            logger.error(f"Error streaming response: {e}")
            yield f"Error: {str(e)}"

    async def process_game_action(self, action: GameAction, session_id: str) -> Dict:
        """Process a game action and generate AI response"""
        try:
            # Get conversation history from database
            conversation_history = await self._get_conversation_history(session_id)
            
            # Add the user's action to the conversation
            user_content = f"Player action: {action.action}"
            if action.description:
                user_content += f"\nDescription: {action.description}"
            if action.parameters:
                user_content += f"\nParameters: {action.parameters}"
            
            conversation_history.append(
                types.Content(parts=[types.Part(text=user_content)], role="user")
            )
            
            # Generate AI response
            response = self.client.models.generate_content(
                model="gemini-2.5-flash-preview-05-20",
                contents=conversation_history,
                config=types.GenerateContentConfig(temperature=0.7)
            )
            
            # Save both user action and AI response to database
            await self._save_message(session_id, "user", user_content)
            await self._save_message(session_id, "model", response.text)
            
            return {
                "response": response.text,
                "action_processed": action.action,
                "timestamp": datetime.utcnow().isoformat(),
                "session_id": session_id
            }
            
        except Exception as e:
            logger.error(f"Error processing game action: {e}")
            return {
                "response": "I apologize, but I'm having trouble processing your action right now. Please try again.",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
                "session_id": session_id
            }

    async def process_dice_roll(self, roll: DiceRoll, session_id: str) -> DiceResult:
        """Process a dice roll and return results"""
        try:
            # Parse dice type to get the number of sides
            dice_sides = int(roll.dice_type.value.replace('d', ''))
            
            # Roll the dice
            rolls = [random.randint(1, dice_sides) for _ in range(roll.count)]
            total = sum(rolls)
            final_result = total + roll.modifier
            
            # Determine success based on common D&D rules (optional)
            success = None
            if roll.skill_name and dice_sides == 20:
                # Simple success check: 10+ is success
                success = final_result >= 10
            
            result = DiceResult(
                rolls=rolls,
                total=total,
                modifier=roll.modifier,
                final_result=final_result,
                skill_name=roll.skill_name,
                success=success
            )
            
            # Create a message for the dice roll
            roll_message = f"Rolled {roll.count}{roll.dice_type.value}"
            if roll.modifier != 0:
                roll_message += f" + {roll.modifier}" if roll.modifier > 0 else f" - {abs(roll.modifier)}"
            if roll.skill_name:
                roll_message += f" for {roll.skill_name}"
            roll_message += f": {rolls} = {final_result}"
            if success is not None:
                roll_message += f" ({'Success' if success else 'Failure'})"
            
            # Save the dice roll to the conversation
            await self._save_message(session_id, "system", roll_message)
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing dice roll: {e}")
            return DiceResult(
                rolls=[1],
                total=1,
                modifier=0,
                final_result=1,
                skill_name=roll.skill_name
            )

    async def initialize_session(self, session_id: str) -> str:
        """Initialize a new game session with GM persona"""
        gm_persona = """
        You are an advanced AI Game Master (GM) for an immersive Dungeons & Dragons-style Tabletop Role-Playing Game. Your primary goal is to facilitate an engaging, dynamic, and narrative-rich experience for the player(s).

        1. GM Persona & Core Principles:
            - Role: You are the omniscient GM. You describe the world, its inhabitants, and the consequences of player actions. You interpret rules, adjudicate outcomes, and drive the evolving narrative.
            - Tone & Style: Your narrative is vivid, descriptive, and immersive, akin to a well-written fantasy novel. Employ rich sensory details, strong verbs, and evocative language. Maintain a consistent tone and atmosphere appropriate to the scenario.
            - Player Agency: Player choices are paramount. Always adapt the story meaningfully to their actions, even if unexpected. Avoid railroading.
            - Fairness: Adjudicate rules impartially.
            - Conciseness & Flow: Deliver narrative turns in single, comprehensive messages.

        2. Game Setup & Initialization:
            - Ask the player if they have a specific scenario in mind or if you should create one.
            - Ask if they want to define their character or if you should create one for them.
            - Do not generate a story, characters, or rules until the player has answered these questions.

        Please greet the player and ask these two initial questions.
        """
        
        try:
            # Generate initial GM response
            response = self.client.models.generate_content(
                model="gemini-2.5-flash-preview-05-20",
                contents=[types.Content(parts=[types.Part(text=gm_persona)], role="user")],
                config=types.GenerateContentConfig(temperature=0.7)
            )
            
            # Save the initialization to the database
            await self._save_message(session_id, "system", gm_persona)
            await self._save_message(session_id, "model", response.text)
            
            return response.text
            
        except Exception as e:
            logger.error(f"Error initializing session: {e}")
            return "Welcome to the AI TTRPG! I'm your Game Master. Let's start by setting up your adventure. Do you have a specific scenario in mind, or would you like me to create one for you?"

    async def get_session_context(self, session_id: str) -> Dict:
        """Get the current session context and conversation history"""
        try:
            conversation_history = await self._get_conversation_history(session_id)
            
            return {
                "session_id": session_id,
                "message_count": len(conversation_history),
                "conversation_history": [
                    {
                        "role": msg.role,
                        "content": msg.parts[0].text if msg.parts else "",
                        "timestamp": datetime.utcnow().isoformat()  # In real implementation, get from DB
                    }
                    for msg in conversation_history
                ],
                "context_length": sum(len(msg.parts[0].text) for msg in conversation_history if msg.parts),
                "last_updated": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting session context: {e}")
            raise

    async def reset_session_context(self, session_id: str) -> bool:
        """Reset the session context by clearing conversation history"""
        try:
            from supabase import create_client
            supabase = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))
            
            # Delete all messages for the session
            supabase.table('messages').delete().eq('session_id', session_id).execute()
            
            logger.info(f"Session context reset for session {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error resetting session context: {e}")
            return False

    async def get_available_models(self) -> List[Dict]:
        """Get information about available AI models"""
        return [
            {
                "name": "gemini-2.5-flash-preview-05-20",
                "description": "Fast and efficient model for interactive gameplay",
                "max_tokens": 8192,
                "capabilities": ["text_generation", "conversation", "creative_writing"],
                "recommended_for": ["game_master", "interactive_storytelling"],
                "cost_tier": "standard"
            },
            {
                "name": "gemini-pro",
                "description": "Advanced model for complex narratives",
                "max_tokens": 32768,
                "capabilities": ["text_generation", "conversation", "complex_reasoning"],
                "recommended_for": ["complex_campaigns", "detailed_worldbuilding"],
                "cost_tier": "premium"
            }
        ]

    async def get_session_stats(self, session_id: str) -> SessionStats:
        """Get AI usage statistics for a session"""
        try:
            from supabase import create_client
            supabase = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))
            
            # Get session info
            session_response = supabase.table('sessions').select('created_at').eq('id', session_id).execute()
            if not session_response.data:
                raise ValueError("Session not found")
            
            session_data = session_response.data[0]
            
            # Get message statistics
            messages_response = supabase.table('messages').select('role, created_at').eq('session_id', session_id).execute()
            messages = messages_response.data
            
            total_messages = len(messages)
            total_actions = len([m for m in messages if m['role'] == 'user'])
            total_dice_rolls = len([m for m in messages if m['role'] == 'system' and 'Rolled' in m.get('content', '')])
            
            # Calculate session duration
            if messages:
                first_message = min(messages, key=lambda x: x['created_at'])
                last_message = max(messages, key=lambda x: x['created_at'])
                duration = (datetime.fromisoformat(last_message['created_at'].replace('Z', '+00:00')) - 
                           datetime.fromisoformat(first_message['created_at'].replace('Z', '+00:00'))).total_seconds() / 60
            else:
                duration = 0
            
            return SessionStats(
                session_id=session_id,
                total_messages=total_messages,
                total_actions=total_actions,
                total_dice_rolls=total_dice_rolls,
                session_duration=int(duration),
                created_at=datetime.fromisoformat(session_data['created_at'].replace('Z', '+00:00')),
                last_activity=datetime.fromisoformat(last_message['created_at'].replace('Z', '+00:00')) if messages else datetime.utcnow()
            )
            
        except Exception as e:
            logger.error(f"Error getting session stats: {e}")
            raise

    async def _get_conversation_history(self, session_id: str) -> List[types.Content]:
        """Retrieve conversation history from database"""
        try:
            from supabase import create_client
            supabase = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))
            
            response = supabase.table('messages').select('role, content').eq('session_id', session_id).order('created_at').execute()
            
            conversation_history = []
            for msg in response.data:
                conversation_history.append(
                    types.Content(parts=[types.Part(text=msg['content'])], role=msg['role'])
                )
            
            return conversation_history
            
        except Exception as e:
            logger.error(f"Error retrieving conversation history: {e}")
            return []

    async def _save_message(self, session_id: str, role: str, content: str):
        """Save a message to the database"""
        try:
            from supabase import create_client
            supabase = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))
            
            supabase.table('messages').insert({
                'session_id': session_id,
                'role': role,
                'content': content
            }).execute()
            
        except Exception as e:
            logger.error(f"Error saving message: {e}")