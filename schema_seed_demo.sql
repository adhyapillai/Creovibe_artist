USE creovibe_db;

-- Category seed
INSERT IGNORE INTO category_table (category_name) VALUES
('Singer'), ('Dancer'), ('Photographer');

-- Subscription plan seed (idempotent by plan name)
INSERT INTO subscription_plan_table
    (Plan_Name, Amount, Duration_Days, max_bookings, has_priority, has_featured, description)
SELECT 'Basic', 299.00, 30, 10, 0, 0, '10 booking slots per month'
WHERE NOT EXISTS (
    SELECT 1 FROM subscription_plan_table WHERE LOWER(Plan_Name) = 'basic'
);

INSERT INTO subscription_plan_table
    (Plan_Name, Amount, Duration_Days, max_bookings, has_priority, has_featured, description)
SELECT 'Premium', 599.00, 30, 30, 1, 0, '30 booking slots + priority support'
WHERE NOT EXISTS (
    SELECT 1 FROM subscription_plan_table WHERE LOWER(Plan_Name) = 'premium'
);

INSERT INTO subscription_plan_table
    (Plan_Name, Amount, Duration_Days, max_bookings, has_priority, has_featured, description)
SELECT 'Pro', 999.00, 30, 999999, 1, 1, 'Unlimited bookings + featured profile'
WHERE NOT EXISTS (
    SELECT 1 FROM subscription_plan_table WHERE LOWER(Plan_Name) = 'pro'
);

-- Demo artist seed
INSERT INTO artist_table
    (First_Name, Last_Name, Username, email, Password, Gender, Dob, Phone_Number,
     State_ID, City_ID, category_id, Portfolio_Path, experience_years, price_per_hour,
     Verification_status, Is_enabled)
SELECT
    'Rohan', 'Sharma', 'rohan@artist.com', 'rohan@artist.com',
    '$2b$12$S4XGJ5Kx8y9wqv0fLJ7x8eJjF5N8xJw7T4f9SxwX0YpW8sD8N4rby',
    'Male', '1995-05-15', '9876543210',
    COALESCE((SELECT State_ID FROM state_table WHERE State_ID = 11 LIMIT 1),
             (SELECT State_ID FROM state_table ORDER BY State_ID LIMIT 1)),
    COALESCE((SELECT City_ID FROM city_table WHERE City_ID = 149 LIMIT 1),
             (SELECT City_ID FROM city_table ORDER BY City_ID LIMIT 1)),
    COALESCE((SELECT category_id FROM category_table WHERE LOWER(category_name) = 'singer' LIMIT 1), 1),
    'portfolio1.pdf', 5, 2000.00, 'approved', 1
WHERE NOT EXISTS (
    SELECT 1 FROM artist_table WHERE LOWER(Username) = 'rohan@artist.com'
);
