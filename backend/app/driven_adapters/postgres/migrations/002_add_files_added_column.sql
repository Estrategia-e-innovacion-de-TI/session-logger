ALTER TABLE copilot_events
ADD COLUMN IF NOT EXISTS files_added JSONB NOT NULL DEFAULT '[]'::jsonb;
