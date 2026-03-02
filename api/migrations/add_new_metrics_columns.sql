-- Add 7 new biomechanics metric columns to shots table
-- Run this in Supabase SQL editor

ALTER TABLE shots ADD COLUMN IF NOT EXISTS hip_angle_load REAL DEFAULT 0.0;
ALTER TABLE shots ADD COLUMN IF NOT EXISTS elbow_height_load REAL DEFAULT 0.0;
ALTER TABLE shots ADD COLUMN IF NOT EXISTS heel_height_release REAL DEFAULT 0.0;
ALTER TABLE shots ADD COLUMN IF NOT EXISTS trunk_lean_release REAL DEFAULT 0.0;
ALTER TABLE shots ADD COLUMN IF NOT EXISTS stance_width REAL DEFAULT 0.0;
ALTER TABLE shots ADD COLUMN IF NOT EXISTS shoulder_level_diff REAL DEFAULT 0.0;
ALTER TABLE shots ADD COLUMN IF NOT EXISTS elbow_lateral_offset REAL DEFAULT 0.0;
