-- MySQL dump 10.13  Distrib 8.0.43, for Win64 (x86_64)
--
-- Host: localhost    Database: creovibe_db
-- ------------------------------------------------------
-- Server version	8.0.43

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `artist_table`
--

DROP TABLE IF EXISTS `artist_table`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `artist_table` (
  `artist_id` int NOT NULL AUTO_INCREMENT,
  `first_name` varchar(50) NOT NULL,
  `last_name` varchar(50) NOT NULL,
  `username` varchar(100) NOT NULL,
  `password` varchar(255) NOT NULL,
  `gender` enum('Male','Female','Other') NOT NULL,
  `dob` date NOT NULL,
  `phone_no` char(10) NOT NULL,
  `pincode` char(6) NOT NULL,
  `state_id` smallint NOT NULL,
  `city_id` smallint NOT NULL,
  `category` varchar(50) NOT NULL,
  `portfolio_path` text NOT NULL,
  `approval_status` enum('Pending','Approved','Rejected') DEFAULT 'Pending',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`artist_id`),
  UNIQUE KEY `username` (`username`),
  KEY `state_id` (`state_id`),
  KEY `city_id` (`city_id`),
  CONSTRAINT `artist_table_ibfk_1` FOREIGN KEY (`state_id`) REFERENCES `state_table` (`state_id`),
  CONSTRAINT `artist_table_ibfk_2` FOREIGN KEY (`city_id`) REFERENCES `city_table` (`city_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `artist_table`
--

LOCK TABLES `artist_table` WRITE;
/*!40000 ALTER TABLE `artist_table` DISABLE KEYS */;
/*!40000 ALTER TABLE `artist_table` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `booking_table`
--

DROP TABLE IF EXISTS `booking_table`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `booking_table` (
  `booking_id` int NOT NULL AUTO_INCREMENT,
  `artist_id` int NOT NULL,
  `client_name` varchar(100) NOT NULL,
  `booking_date` date NOT NULL,
  `slot_time` varchar(50) NOT NULL,
  `status` enum('Upcoming','Completed','Cancelled','Reschedule Requested') DEFAULT 'Upcoming',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`booking_id`),
  KEY `artist_id` (`artist_id`),
  CONSTRAINT `booking_table_ibfk_1` FOREIGN KEY (`artist_id`) REFERENCES `artist_table` (`artist_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `booking_table`
--

LOCK TABLES `booking_table` WRITE;
/*!40000 ALTER TABLE `booking_table` DISABLE KEYS */;
/*!40000 ALTER TABLE `booking_table` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `city_table`
--

DROP TABLE IF EXISTS `city_table`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `city_table` (
  `city_id` smallint NOT NULL AUTO_INCREMENT,
  `city_name` varchar(100) NOT NULL,
  `state_id` smallint NOT NULL,
  PRIMARY KEY (`city_id`),
  KEY `state_id` (`state_id`),
  CONSTRAINT `city_table_ibfk_1` FOREIGN KEY (`state_id`) REFERENCES `state_table` (`state_id`)
) ENGINE=InnoDB AUTO_INCREMENT=381 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `city_table`
--

LOCK TABLES `city_table` WRITE;
/*!40000 ALTER TABLE `city_table` DISABLE KEYS */;
INSERT INTO `city_table` VALUES (127,'Abohar',20),(128,'Adilabad',24),(129,'Agartala',25),(130,'Agra',26),(131,'Ahmadnagar',14),(132,'Ahmedabad',7),(133,'Aizawl',17),(134,'Ajmer',21),(135,'Akola',14),(136,'Alappuzha',12),(137,'Aligarh',26),(138,'Allahabad',26),(139,'Alwar',21),(140,'Ambala',8),(141,'Amaravati',14),(142,'Amritsar',20),(143,'Asansol',28),(144,'Aurangabad',14),(145,'Aurangabad',4),(146,'Bareilly',26),(147,'Belgaum',11),(148,'Bellary',11),(149,'Bengaluru',11),(150,'Bhagalpur',4),(151,'Bharatpur',21),(152,'Bhatpara',28),(153,'Bhavnagar',7),(154,'Bhilai',5),(155,'Bhilwara',21),(156,'Bhiwandi',14),(157,'Bhiwani',8),(158,'Bhopal',13),(159,'Bhubaneshwar',19),(160,'Bhuj',7),(161,'Bhusaval',14),(162,'Bidar',11),(163,'Bijapur',11),(164,'Bikaner',21),(165,'Bilaspur',5),(166,'Brahmapur',19),(167,'Budaun',26),(168,'Bulandshahr',26),(169,'Calicut',12),(170,'Chandigarh',30),(171,'Chennai',23),(172,'Chirala',1),(173,'Coimbatore',23),(174,'Cuddalore',23),(175,'Cuttack',19),(176,'Davangere',11),(177,'Dehradun',27),(178,'Delhi',32),(179,'Dhanbad',10),(180,'Dibrugarh',3),(181,'Dispur',3),(182,'Faridabad',8),(183,'Gangtok',22),(184,'Gaya',4),(185,'Gandhinagar',7),(186,'Ghaziabad',26),(187,'Guntur',1),(188,'Gurugram',8),(189,'Guwahati',3),(190,'Gwalior',13),(191,'Hyderabad',24),(192,'Imphal',15),(193,'Indore',13),(194,'Itanagar',2),(195,'Jaipur',21),(196,'Jammu',33),(197,'Jamshedpur',10),(198,'Jhansi',26),(199,'Jodhpur',21),(200,'Kochi',12),(201,'Kohima',18),(202,'Kolkata',28),(203,'Kota',21),(204,'Lucknow',26),(205,'Ludhiana',20),(206,'Madurai',23),(207,'Mangalore',11),(208,'Meerut',26),(209,'Mumbai',14),(210,'Mysore',11),(211,'Nagpur',14),(212,'Nashik',14),(213,'New Delhi',32),(214,'Panaji',6),(215,'Patna',4),(216,'Pune',14),(217,'Raipur',5),(218,'Rajkot',7),(219,'Ranchi',10),(220,'Shillong',16),(221,'Shimla',9),(222,'Srinagar',33),(223,'Surat',7),(224,'Thiruvananthapuram',12),(225,'Tirupati',1),(226,'Udaipur',21),(227,'Vadodara',7),(228,'Varanasi',26),(229,'Vishakhapatnam',1),(230,'Warangal',24),(254,'Abohar',20),(255,'Adilabad',24),(256,'Agartala',25),(257,'Agra',26),(258,'Ahmadnagar',14),(259,'Ahmedabad',7),(260,'Aizawl',17),(261,'Ajmer',21),(262,'Akola',14),(263,'Alappuzha',12),(264,'Aligarh',26),(265,'Allahabad',26),(266,'Alwar',21),(267,'Ambala',8),(268,'Amaravati',14),(269,'Amritsar',20),(270,'Asansol',28),(271,'Aurangabad',14),(272,'Aurangabad',4),(273,'Bareilly',26),(274,'Belgaum',11),(275,'Bellary',11),(276,'Bengaluru',11),(277,'Bhagalpur',4),(278,'Bharatpur',21),(279,'Bhatpara',28),(280,'Bhavnagar',7),(281,'Bhilai',5),(282,'Bhilwara',21),(283,'Bhiwandi',14),(284,'Bhiwani',8),(285,'Bhopal',13),(286,'Bhubaneshwar',19),(287,'Bhuj',7),(288,'Bhusaval',14),(289,'Bidar',11),(290,'Bijapur',11),(291,'Bikaner',21),(292,'Bilaspur',5),(293,'Brahmapur',19),(294,'Budaun',26),(295,'Bulandshahr',26),(296,'Calicut',12),(297,'Chandigarh',30),(298,'Chennai',23),(299,'Chirala',1),(300,'Coimbatore',23),(301,'Cuddalore',23),(302,'Cuttack',19),(303,'Davangere',11),(304,'Dehradun',27),(305,'Delhi',32),(306,'Dhanbad',10),(307,'Dibrugarh',3),(308,'Dispur',3),(309,'Faridabad',8),(310,'Gangtok',22),(311,'Gaya',4),(312,'Gandhinagar',7),(313,'Ghaziabad',26),(314,'Guntur',1),(315,'Gurugram',8),(316,'Guwahati',3),(317,'Gwalior',13),(318,'Hyderabad',24),(319,'Imphal',15),(320,'Indore',13),(321,'Itanagar',2),(322,'Jaipur',21),(323,'Jammu',33),(324,'Jamshedpur',10),(325,'Jhansi',26),(326,'Jodhpur',21),(327,'Kochi',12),(328,'Kohima',18),(329,'Kolkata',28),(330,'Kota',21),(331,'Lucknow',26),(332,'Ludhiana',20),(333,'Madurai',23),(334,'Mangalore',11),(335,'Meerut',26),(336,'Mumbai',14),(337,'Mysore',11),(338,'Nagpur',14),(339,'Nashik',14),(340,'New Delhi',32),(341,'Panaji',6),(342,'Patna',4),(343,'Pune',14),(344,'Raipur',5),(345,'Rajkot',7),(346,'Ranchi',10),(347,'Shillong',16),(348,'Shimla',9),(349,'Srinagar',33),(350,'Surat',7),(351,'Thiruvananthapuram',12),(352,'Tirupati',1),(353,'Udaipur',21),(354,'Vadodara',7),(355,'Varanasi',26),(356,'Vishakhapatnam',1),(357,'Warangal',24);
/*!40000 ALTER TABLE `city_table` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `earnings_table`
--

DROP TABLE IF EXISTS `earnings_table`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `earnings_table` (
  `earning_id` int NOT NULL AUTO_INCREMENT,
  `artist_id` int NOT NULL,
  `booking_id` int NOT NULL,
  `amount` decimal(10,2) NOT NULL,
  `payment_date` date NOT NULL,
  PRIMARY KEY (`earning_id`),
  KEY `artist_id` (`artist_id`),
  KEY `booking_id` (`booking_id`),
  CONSTRAINT `earnings_table_ibfk_1` FOREIGN KEY (`artist_id`) REFERENCES `artist_table` (`artist_id`),
  CONSTRAINT `earnings_table_ibfk_2` FOREIGN KEY (`booking_id`) REFERENCES `booking_table` (`booking_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `earnings_table`
--

LOCK TABLES `earnings_table` WRITE;
/*!40000 ALTER TABLE `earnings_table` DISABLE KEYS */;
/*!40000 ALTER TABLE `earnings_table` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `feedback_table`
--

DROP TABLE IF EXISTS `feedback_table`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `feedback_table` (
  `feedback_id` int NOT NULL AUTO_INCREMENT,
  `artist_id` int NOT NULL,
  `client_name` varchar(100) DEFAULT NULL,
  `rating` tinyint DEFAULT NULL,
  `comment` text,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`feedback_id`),
  KEY `artist_id` (`artist_id`),
  CONSTRAINT `feedback_table_ibfk_1` FOREIGN KEY (`artist_id`) REFERENCES `artist_table` (`artist_id`),
  CONSTRAINT `feedback_table_chk_1` CHECK ((`rating` between 1 and 5))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `feedback_table`
--

LOCK TABLES `feedback_table` WRITE;
/*!40000 ALTER TABLE `feedback_table` DISABLE KEYS */;
/*!40000 ALTER TABLE `feedback_table` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `notification_table`
--

DROP TABLE IF EXISTS `notification_table`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `notification_table` (
  `notification_id` int NOT NULL AUTO_INCREMENT,
  `artist_id` int NOT NULL,
  `message` varchar(255) NOT NULL,
  `is_read` tinyint(1) DEFAULT '0',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`notification_id`),
  KEY `artist_id` (`artist_id`),
  CONSTRAINT `notification_table_ibfk_1` FOREIGN KEY (`artist_id`) REFERENCES `artist_table` (`artist_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `notification_table`
--

LOCK TABLES `notification_table` WRITE;
/*!40000 ALTER TABLE `notification_table` DISABLE KEYS */;
/*!40000 ALTER TABLE `notification_table` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `state_table`
--

DROP TABLE IF EXISTS `state_table`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `state_table` (
  `state_id` smallint NOT NULL AUTO_INCREMENT,
  `state_name` varchar(100) NOT NULL,
  PRIMARY KEY (`state_id`),
  UNIQUE KEY `state_name` (`state_name`)
) ENGINE=InnoDB AUTO_INCREMENT=73 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `state_table`
--

LOCK TABLES `state_table` WRITE;
/*!40000 ALTER TABLE `state_table` DISABLE KEYS */;
INSERT INTO `state_table` VALUES (29,'Andaman and Nicobar Islands'),(1,'Andhra Pradesh'),(2,'Arunachal Pradesh'),(3,'Assam'),(4,'Bihar'),(30,'Chandigarh'),(5,'Chhattisgarh'),(31,'Dadra and Nagar Haveli and Daman and Diu'),(32,'Delhi'),(6,'Goa'),(7,'Gujarat'),(8,'Haryana'),(9,'Himachal Pradesh'),(33,'Jammu and Kashmir'),(10,'Jharkhand'),(11,'Karnataka'),(12,'Kerala'),(34,'Ladakh'),(35,'Lakshadweep'),(13,'Madhya Pradesh'),(14,'Maharashtra'),(15,'Manipur'),(16,'Meghalaya'),(17,'Mizoram'),(18,'Nagaland'),(19,'Odisha'),(36,'Puducherry'),(20,'Punjab'),(21,'Rajasthan'),(22,'Sikkim'),(23,'Tamil Nadu'),(24,'Telangana'),(25,'Tripura'),(26,'Uttar Pradesh'),(27,'Uttarakhand'),(28,'West Bengal');
/*!40000 ALTER TABLE `state_table` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `subscription_table`
--

DROP TABLE IF EXISTS `subscription_table`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `subscription_table` (
  `subscription_id` int NOT NULL AUTO_INCREMENT,
  `artist_id` int NOT NULL,
  `plan_name` varchar(50) NOT NULL,
  `amount` decimal(10,2) NOT NULL,
  `start_date` date NOT NULL,
  `end_date` date NOT NULL,
  `status` enum('Active','Expired') DEFAULT 'Active',
  PRIMARY KEY (`subscription_id`),
  KEY `artist_id` (`artist_id`),
  CONSTRAINT `subscription_table_ibfk_1` FOREIGN KEY (`artist_id`) REFERENCES `artist_table` (`artist_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `subscription_table`
--

LOCK TABLES `subscription_table` WRITE;
/*!40000 ALTER TABLE `subscription_table` DISABLE KEYS */;
/*!40000 ALTER TABLE `subscription_table` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-01-11 11:17:30
