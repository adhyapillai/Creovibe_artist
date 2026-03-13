USE creovibe_db;

SELECT Artist_ID, Username, email
FROM artist_table
WHERE email LIKE '%@email.com';

UPDATE artist_table
SET email = REPLACE(email, '@email.com', '@gmail.com')
WHERE email LIKE '%@email.com';

UPDATE artist_table
SET Username = REPLACE(Username, '@email.com', '@gmail.com')
WHERE Username LIKE '%@email.com';

SELECT Artist_ID, First_Name, Last_Name, Username, email
FROM artist_table
ORDER BY Artist_ID;
