USE creovibe_db;

SHOW TABLES;
DESCRIBE artist_table;
DESCRIBE calendar_table;
DESCRIBE booking_table;

SELECT
    TABLE_NAME,
    COLUMN_NAME,
    CONSTRAINT_NAME,
    REFERENCED_TABLE_NAME,
    REFERENCED_COLUMN_NAME
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
WHERE REFERENCED_TABLE_SCHEMA = 'creovibe_db'
  AND REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY TABLE_NAME, COLUMN_NAME;

SELECT category_id, category_name FROM category_table ORDER BY category_id;
SELECT Plan_ID, Plan_Name, Amount, Duration_Days, max_bookings, has_priority, has_featured
FROM subscription_plan_table
ORDER BY Plan_ID;
SELECT Artist_ID, Username, email, category_id, Verification_status, Is_enabled
FROM artist_table
WHERE LOWER(Username) = 'rohan@artist.com';
