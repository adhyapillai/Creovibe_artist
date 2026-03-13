USE creovibe_db;
UPDATE artist_table
SET email = Username
WHERE email IS NULL AND Username IS NOT NULL;
SELECT Artist_ID, Username, email
FROM artist_table
WHERE LOWER(Username) = 'rohan@artist.com';
