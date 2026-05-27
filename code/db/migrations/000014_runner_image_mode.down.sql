ALTER TABLE runners DROP CONSTRAINT IF EXISTS runners_source_check;
ALTER TABLE runners DROP COLUMN IF EXISTS image;
-- script_content ramane nullable; revenirea la NOT NULL ar putea esua daca
-- exista randuri cu script_content NULL (runner-e in mod image).
