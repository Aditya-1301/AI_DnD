-- TTRPG Web Application Database Migration
-- Run this in your Supabase SQL Editor

-- 1. User Profiles Table (extends Supabase Auth)
CREATE TABLE IF NOT EXISTS user_profiles (
  id UUID REFERENCES auth.users(id) PRIMARY KEY,
  username TEXT UNIQUE,
  display_name TEXT,
  avatar_url TEXT,
  role TEXT DEFAULT 'player' CHECK (role IN ('player', 'gm', 'admin')),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Sessions Table
CREATE TABLE IF NOT EXISTS sessions (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  session_uuid UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL,
  title TEXT,
  description TEXT,
  status TEXT DEFAULT 'active' CHECK (status IN ('active', 'paused', 'completed')),
  max_players INTEGER DEFAULT 4 CHECK (max_players >= 1 AND max_players <= 10),
  creator_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Messages Table
CREATE TABLE IF NOT EXISTS messages (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  session_id UUID REFERENCES sessions(id) ON DELETE CASCADE,
  user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  content TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('user', 'model', 'system')),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. Session Participants Table
CREATE TABLE IF NOT EXISTS session_participants (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  session_id UUID REFERENCES sessions(id) ON DELETE CASCADE,
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  role TEXT DEFAULT 'player' CHECK (role IN ('player', 'gm')),
  joined_at TIMESTAMPTZ DEFAULT NOW(),
  last_active TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(session_id, user_id)
);

-- 5. Game States Table
CREATE TABLE IF NOT EXISTS game_states (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  session_id UUID REFERENCES sessions(id) ON DELETE CASCADE UNIQUE,
  current_scene TEXT,
  game_variables JSONB DEFAULT '{}',
  last_action TEXT,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 6. Dice Rolls Table
CREATE TABLE IF NOT EXISTS dice_rolls (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  session_id UUID REFERENCES sessions(id) ON DELETE CASCADE,
  user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  dice_type TEXT NOT NULL,
  count INTEGER NOT NULL DEFAULT 1,
  modifier INTEGER DEFAULT 0,
  rolls INTEGER[] NOT NULL,
  total INTEGER NOT NULL,
  final_result INTEGER NOT NULL,
  skill_name TEXT,
  success BOOLEAN,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable Row Level Security
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE session_participants ENABLE ROW LEVEL SECURITY;
ALTER TABLE game_states ENABLE ROW LEVEL SECURITY;
ALTER TABLE dice_rolls ENABLE ROW LEVEL SECURITY;

-- RLS Policies for user_profiles
CREATE POLICY "Users can view all profiles" ON user_profiles
  FOR SELECT USING (true);

CREATE POLICY "Users can insert own profile" ON user_profiles
  FOR INSERT WITH CHECK (auth.uid() = id);

CREATE POLICY "Users can update own profile" ON user_profiles
  FOR UPDATE USING (auth.uid() = id);

-- RLS Policies for sessions
CREATE POLICY "Users can view accessible sessions" ON sessions
  FOR SELECT USING (
    creator_id = auth.uid() OR 
    id IN (SELECT session_id FROM session_participants WHERE user_id = auth.uid())
  );

CREATE POLICY "Users can create sessions" ON sessions
  FOR INSERT WITH CHECK (creator_id = auth.uid());

CREATE POLICY "Creators can update their sessions" ON sessions
  FOR UPDATE USING (creator_id = auth.uid());

CREATE POLICY "Creators can delete their sessions" ON sessions
  FOR DELETE USING (creator_id = auth.uid());

-- RLS Policies for messages
CREATE POLICY "Users can view session messages" ON messages
  FOR SELECT USING (
    session_id IN (
      SELECT id FROM sessions WHERE creator_id = auth.uid()
      UNION
      SELECT session_id FROM session_participants WHERE user_id = auth.uid()
    )
  );

CREATE POLICY "Users can create messages in accessible sessions" ON messages
  FOR INSERT WITH CHECK (
    session_id IN (
      SELECT id FROM sessions WHERE creator_id = auth.uid()
      UNION
      SELECT session_id FROM session_participants WHERE user_id = auth.uid()
    )
  );

CREATE POLICY "Users can delete own messages or session creators can delete any" ON messages
  FOR DELETE USING (
    user_id = auth.uid() OR
    session_id IN (SELECT id FROM sessions WHERE creator_id = auth.uid())
  );

-- RLS Policies for session_participants
CREATE POLICY "Users can view participants of accessible sessions" ON session_participants
  FOR SELECT USING (
    session_id IN (
      SELECT id FROM sessions WHERE creator_id = auth.uid()
      UNION
      SELECT session_id FROM session_participants WHERE user_id = auth.uid()
    )
  );

CREATE POLICY "Users can join sessions" ON session_participants
  FOR INSERT WITH CHECK (user_id = auth.uid());

CREATE POLICY "Users can leave sessions or creators can remove participants" ON session_participants
  FOR DELETE USING (
    user_id = auth.uid() OR
    session_id IN (SELECT id FROM sessions WHERE creator_id = auth.uid())
  );

-- RLS Policies for game_states
CREATE POLICY "Users can view game states of accessible sessions" ON game_states
  FOR SELECT USING (
    session_id IN (
      SELECT id FROM sessions WHERE creator_id = auth.uid()
      UNION
      SELECT session_id FROM session_participants WHERE user_id = auth.uid()
    )
  );

CREATE POLICY "Session creators can manage game states" ON game_states
  FOR ALL USING (
    session_id IN (SELECT id FROM sessions WHERE creator_id = auth.uid())
  );

-- RLS Policies for dice_rolls
CREATE POLICY "Users can view dice rolls from accessible sessions" ON dice_rolls
  FOR SELECT USING (
    session_id IN (
      SELECT id FROM sessions WHERE creator_id = auth.uid()
      UNION
      SELECT session_id FROM session_participants WHERE user_id = auth.uid()
    )
  );

CREATE POLICY "Users can create dice rolls in accessible sessions" ON dice_rolls
  FOR INSERT WITH CHECK (
    session_id IN (
      SELECT id FROM sessions WHERE creator_id = auth.uid()
      UNION
      SELECT session_id FROM session_participants WHERE user_id = auth.uid()
    )
  );

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_sessions_creator_id ON sessions(creator_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);
CREATE INDEX IF NOT EXISTS idx_session_participants_session_id ON session_participants(session_id);
CREATE INDEX IF NOT EXISTS idx_session_participants_user_id ON session_participants(user_id);
CREATE INDEX IF NOT EXISTS idx_dice_rolls_session_id ON dice_rolls(session_id);
CREATE INDEX IF NOT EXISTS idx_dice_rolls_created_at ON dice_rolls(created_at);

-- Create a function to automatically create user profile on signup
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.user_profiles (id, username, display_name)
  VALUES (
    NEW.id,
    NEW.raw_user_meta_data->>'username',
    COALESCE(NEW.raw_user_meta_data->>'username', split_part(NEW.email, '@', 1))
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Create trigger to automatically create profile on user signup
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- Create a function to update updated_at timestamp
CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Add triggers for updated_at columns
CREATE TRIGGER update_user_profiles_updated_at
  BEFORE UPDATE ON user_profiles
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

CREATE TRIGGER update_sessions_updated_at
  BEFORE UPDATE ON sessions
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

CREATE TRIGGER update_game_states_updated_at
  BEFORE UPDATE ON game_states
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();