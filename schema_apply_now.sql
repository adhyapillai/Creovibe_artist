USE creovibe_db;

SET FOREIGN_KEY_CHECKS = 0;

CREATE TABLE IF NOT EXISTS category_table (
    category_id TINYINT NOT NULL AUTO_INCREMENT,
    category_name VARCHAR(50) NOT NULL UNIQUE,
    PRIMARY KEY (category_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO category_table (category_name) VALUES ('Singer'), ('Dancer'), ('Photographer');

ALTER TABLE artist_table
    ADD COLUMN category_id TINYINT NULL;

UPDATE artist_table a
JOIN category_table c ON LOWER(c.category_name) = LOWER(a.Category)
SET a.category_id = c.category_id
WHERE a.category_id IS NULL;

ALTER TABLE artist_table
    ADD INDEX idx_artist_category_id (category_id);

ALTER TABLE artist_table
    ADD CONSTRAINT fk_artist_category
    FOREIGN KEY (category_id) REFERENCES category_table(category_id);

CREATE TABLE IF NOT EXISTS artist_bank_details (
    bank_id INT NOT NULL AUTO_INCREMENT,
    artist_id TINYINT NOT NULL,
    bank_name VARCHAR(120) NULL,
    account_holder_name VARCHAR(120) NULL,
    account_number VARCHAR(40) NULL,
    ifsc_code VARCHAR(20) NULL,
    upi_id VARCHAR(120) NULL,
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (bank_id),
    UNIQUE KEY uq_artist_bank_artist (artist_id),
    CONSTRAINT fk_artist_bank_artist FOREIGN KEY (artist_id) REFERENCES artist_table(Artist_ID) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

ALTER TABLE calendar_table
    MODIFY COLUMN Slot_Type ENUM('Communication','Performance') NOT NULL,
    MODIFY COLUMN Status ENUM('Available','Blocked') DEFAULT 'Available',
    MODIFY COLUMN price DECIMAL(10,2) NULL DEFAULT 0.00;

ALTER TABLE booking_table
    MODIFY COLUMN Booking_Status ENUM('pending','confirmed','completed','cancelled','reschedule') DEFAULT 'pending',
    ADD COLUMN reschedule_status ENUM('none','requested','approved','rejected') DEFAULT 'none',
    ADD COLUMN reschedule_reason VARCHAR(255) NULL,
    ADD COLUMN reschedule_requested_at TIMESTAMP NULL,
    ADD COLUMN rescheduled_to_slot_id TINYINT NULL,
    ADD COLUMN cancellation_reason VARCHAR(255) NULL,
    ADD COLUMN cancelled_by ENUM('artist','client','system') NULL,
    ADD COLUMN cancelled_at TIMESTAMP NULL,
    ADD KEY idx_booking_rescheduled_slot (rescheduled_to_slot_id),
    ADD CONSTRAINT fk_booking_rescheduled_slot FOREIGN KEY (rescheduled_to_slot_id) REFERENCES calendar_table(Slot_ID);

ALTER TABLE subscription_plan_table
    ADD COLUMN max_bookings INT NOT NULL DEFAULT 10,
    ADD COLUMN has_priority TINYINT(1) NOT NULL DEFAULT 0,
    ADD COLUMN has_featured TINYINT(1) NOT NULL DEFAULT 0,
    ADD COLUMN description VARCHAR(255) NULL;

ALTER TABLE subscription_table
    ADD COLUMN plan_id INT NULL;

UPDATE subscription_table s
JOIN subscription_plan_table p ON LOWER(p.Plan_Name) = LOWER(s.Plan_Type)
SET s.plan_id = p.Plan_ID
WHERE s.plan_id IS NULL;

ALTER TABLE subscription_table
    ADD KEY idx_subscription_plan (plan_id),
    ADD CONSTRAINT fk_subscription_plan FOREIGN KEY (plan_id) REFERENCES subscription_plan_table(Plan_ID);

ALTER TABLE payment_table
    MODIFY COLUMN Booking_ID TINYINT NULL,
    ADD COLUMN Subscription_ID TINYINT NULL,
    ADD COLUMN Artist_ID TINYINT NULL,
    ADD COLUMN Payment_Method VARCHAR(50) NULL,
    ADD COLUMN Order_ID VARCHAR(100) NULL,
    ADD COLUMN Refund_Status ENUM('none','requested','processed','failed') DEFAULT 'none',
    ADD COLUMN Refunded_At TIMESTAMP NULL,
    ADD KEY idx_payment_subscription (Subscription_ID),
    ADD KEY idx_payment_artist (Artist_ID),
    ADD CONSTRAINT fk_payment_subscription FOREIGN KEY (Subscription_ID) REFERENCES subscription_table(Subscription_ID) ON DELETE SET NULL,
    ADD CONSTRAINT fk_payment_artist FOREIGN KEY (Artist_ID) REFERENCES artist_table(Artist_ID) ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS favorite_table (
    favorite_id INT NOT NULL AUTO_INCREMENT,
    client_id TINYINT NOT NULL,
    artist_id TINYINT NOT NULL,
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (favorite_id),
    UNIQUE KEY uq_favorite_client_artist (client_id, artist_id),
    KEY idx_favorite_artist (artist_id),
    CONSTRAINT fk_favorite_client FOREIGN KEY (client_id) REFERENCES client_table(Client_ID) ON DELETE CASCADE,
    CONSTRAINT fk_favorite_artist FOREIGN KEY (artist_id) REFERENCES artist_table(Artist_ID) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS notification_table (
    notification_id BIGINT NOT NULL AUTO_INCREMENT,
    recipient_type ENUM('artist','client') NOT NULL,
    recipient_id BIGINT NOT NULL,
    message VARCHAR(255) NOT NULL,
    is_read TINYINT(1) NOT NULL DEFAULT 0,
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (notification_id),
    KEY idx_notification_recipient (recipient_type, recipient_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SET FOREIGN_KEY_CHECKS = 1;

DROP TRIGGER IF EXISTS trg_artist_age_check_ins;
DELIMITER $$
CREATE TRIGGER trg_artist_age_check_ins
BEFORE INSERT ON artist_table
FOR EACH ROW
BEGIN
    IF TIMESTAMPDIFF(YEAR, NEW.Dob, CURDATE()) < 18 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Artist must be at least 18 years old';
    END IF;
END$$
DELIMITER ;

DROP TRIGGER IF EXISTS trg_artist_age_check_upd;
DELIMITER $$
CREATE TRIGGER trg_artist_age_check_upd
BEFORE UPDATE ON artist_table
FOR EACH ROW
BEGIN
    IF TIMESTAMPDIFF(YEAR, NEW.Dob, CURDATE()) < 18 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Artist must be at least 18 years old';
    END IF;
END$$
DELIMITER ;

DROP TRIGGER IF EXISTS trg_calendar_price_validate_ins;
DELIMITER $$
CREATE TRIGGER trg_calendar_price_validate_ins
BEFORE INSERT ON calendar_table
FOR EACH ROW
BEGIN
    IF NEW.price IS NOT NULL AND NEW.price < 100 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Calendar slot price must be at least 100';
    END IF;
    IF NEW.Slot_Type = 'Communication' AND NEW.price > 500 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Communication slot price cannot exceed 500';
    END IF;
    IF NEW.Start_Time >= NEW.End_Time THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Start time must be before end time';
    END IF;
END$$
DELIMITER ;

DROP TRIGGER IF EXISTS trg_calendar_price_validate_upd;
DELIMITER $$
CREATE TRIGGER trg_calendar_price_validate_upd
BEFORE UPDATE ON calendar_table
FOR EACH ROW
BEGIN
    IF NEW.price IS NOT NULL AND NEW.price < 100 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Calendar slot price must be at least 100';
    END IF;
    IF NEW.Slot_Type = 'Communication' AND NEW.price > 500 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Communication slot price cannot exceed 500';
    END IF;
    IF NEW.Start_Time >= NEW.End_Time THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Start time must be before end time';
    END IF;
END$$
DELIMITER ;
