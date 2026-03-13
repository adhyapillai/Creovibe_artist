USE creovibe_db;

SELECT Artist_ID, Username, email
FROM artist_table
WHERE email LIKE '%@artist.com';

UPDATE artist_table
SET email = REPLACE(email, '@artist.com', '@email.com')
WHERE email LIKE '%@artist.com';

UPDATE artist_table
SET Username = REPLACE(Username, '@artist.com', '@email.com')
WHERE Username LIKE '%@artist.com';

SELECT Artist_ID, First_Name, Last_Name, Username, email
FROM artist_table
ORDER BY Artist_ID;
