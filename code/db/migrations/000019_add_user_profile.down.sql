ALTER TABLE users
    DROP COLUMN IF EXISTS avatar_mime,
    DROP COLUMN IF EXISTS avatar_data,
    DROP COLUMN IF EXISTS bio,
    DROP COLUMN IF EXISTS affiliation,
    DROP COLUMN IF EXISTS full_name;
