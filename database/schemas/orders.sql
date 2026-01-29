-- Ordersystem för automatisk hamburgertillverkning
-- Databasschema för orderhantering, tracking och historik

-- =================== TABELLER ====================

-- Tabell för kundorders
CREAT TABLE orders (
    order_id VARCHAR(36) PRIMARY KEY DEFAULT (UUID()), -- Unikt order-ID
    customer_id VARCHAR(36), -- Kund-ID (om tillgängligt)
    order_type ENUM("walk-in", "kiosk", "mobile") NOT NULL DEFAULT "walk-in" -- Ordertyp
    order_status ENUM(
        "received" --Order mottagen
        "processing", -- Bearbetas
        "cooking", -- Tillagas
        "assembling", -- Monteras
        "packaging", -- Packeteras
        "raedy", -- Klart för utlämning
        "delivered", -- Utlämmnad
        "cancelled", -- Avbruten
        "failed", -- Misslyckade 
    ) NOT NULL DEFAULT "received",

    -- Orderingformation
    burger_type ENUM(
        "classic", -- Klassisk hamburgare
        "cheese", -- Cheeseburgare
        "double", -- Dubbelburgare
        "bacon", -- Baconburgare
        "veggie", -- Vegetarisk
        "custom" -- Specialbeställning
    ) NOT NULL,

    -- Ingredienser (JSON för flexibilitet)
    ingredients JSON NOT NULL,
    -- {
    -- "patty_count: 1",
    -- "cheese": true,
    -- "bacon": false,
    -- "lettuce": true,
    -- "tomato": true,
    -- "onion": true,
    -- "pickles": true,
    -- "ketchup": true,
    -- "mustard": false,
    -- "mayonnaise": truem
    -- "special_instructions": "extra ketchup"
    --}

    -- Tillbehör
    sider_order ENUM("fries", "onion_rings", "salad", "none") DEFAULT "fries",
    drink ENUM("cola", "fanta", "water", "beer", "none") DEFAULT "cola",

    -- Prisinformation
    subroral DECIMAL(10, 2) NOT NULL, --Delbelopp
    tax DECIMAL(10, 2) NOT NULL, -- Moms
    total_amount DECIMAL(10, 2) NOT NULL -- Totalt belopp

    -- Betalning
    payment_method ENUM("card", "cash", "mobile") NOT NULL,
    payment_status ENUM("pemding", "completed", "failed", "refunded") NOT NULL DEFAULT "pending",
    payment_transaction_id VARCHAR(100), -- Transaktions-ID fråm betalningssystem

    -- Tillganingstider
    estimated_prep_time INT, -- Uppskattad tillagningstid (sekunder)
    actual_prep_time INT, -- Faktisk tillagningstid (sekunder)

    -- Maskininformation
    grill_slot_id VARCHAR(20), -- Grillplats som användas
    fritös_batch_id VARCHAR(20), -- Fritsbatch för pommes
    assembly_station_id VARCHAR(20), -- Monteringsstation

    -- Tidsstämplar
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- Order skapad
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP, -- Senast uppdaterad
    started_cooking_at TIMESTAMP, -- Tillagnings startad
    finiched_cooking_at TIMESTAMP, -- Tillagning avslutad
    assembled_at TIMESTAMP, --Monterad
    delivered_at TIMESTAMP, -- Utlämnad

    -- Index för prestanda
    INDEX idx_order_status (order_status),
    INDEX idx_created_at (created_at),
    INDEX idx_customer_id (customer_id),
    INDEX idx_payment_status (payment_status)
);

-- Tabell för orderhistorik/logging
CREATE TABLE order_history (
    history_id BIGINT AUTO_INCUREMENT PRIMARY KEY,
    order_id VARCHAR(36) NOT NULL,
    event_type ENUM(
        "order_created",
        "payment_processed",
        "cooking_started",
        "ingredient_dispensed",
        "grill_started",
        "grill_completed",
        "assembly_started",
        "assembly_completed",
        "paclaging_started",
        "order_ready",
        "order_delivered",
        "status_changed",
        "error_occurred",
        "maintenance_needed"
    ) NOT NULL,
    event_description TEXT,
    previous_status VARCHAR(50),
    new_status VARCHAR(50),
    machine_component VARCHAR(50), -- Vilken maskindel
    temperature DECIMAL(5, 2), -- Temperatur vid event
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Fremdschlussel
    FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE CASCADE,

    INDEX idx_order_id (order_id)
    INDEX idx_event_type (event_type)
    INDEX id_timestamp (timestamp)
);

-- Tabell för orderkö
CREATE TABLE order_queue (
    queue_id INT AUTO_INCUREMENT PRIMARY KEY,
    order_id VARCHAR(36) NOT NULL,
    queue_position INT NOT NULL, -- Position i kön
    priority_level ENUM("normal", "high", "urgent") DEFAULT "normal",
    estimated_wait_time INT, -- Uppskattad väntetid (sekunder)
    actual_wait_time INT, -- Faktisk väntetid (sekunder)
    added_to_queue_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    removed_form_queue_at TIMESTAMP,

    -- Fremdschlussel
    FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE CASCADE,

    INDEX idx_queue_position (queue_position),
    INDEX idx_priority (priority_level),
    UNIQUE INDEX idx_order_in_queue (order_id, removed_form_queue_at)
);

-- Tabbell för ,askintillstånd per order
CREATE TABLE machine_state_log (
    log_id BIGINT AUTO_INCUREMENT PRIMARY KEY,
    order_id VARCHAR(36) NOT NULL,
    log_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Temperature
    grill_temperature DECIMAL(5,2), -- Grilltemperatur
    fryer_temperature DECIMAL(5,2), -- Fritöstemperatur
    freezer_temperature DECIMAL(5,2), -- Frysfacktemperatur

    -- Aktuatorpositioner
    robortic_arm_position JSON, -- Robotarmens position
    connveyor_speed DECIMAL(5,2), -- Transportbandshastighet

    -- Sensordata
    patty_sensor_state BOOLEAN, -- Köttbittsansor
    bun_sensor_state BOOLEAN, -- Brödsensor
    cheese_sensor_state BOOLEAN, -- Ostsensor
    safety_semsor_state BOOLEAN, -- Säkerhetssensor

    -- Systemstatus
    system_voltage DECIMAL(5,2), -- Systemspänning
    cpu_temperature DECIMAL(5,2) -- CPU-temperatur
    memory_usage_precent DECIMAL(5,2), -- Minneanvändning

    -- Fremschlussel
    FOREIGN KEY (order_id) REFERENCES order(order_id) ON DELETE CASCADE,

    INDEX idx_order_timestamp (order_id, log_timestamp)
);

-- Tabell för kvalitetskontroll
CREATE TABLE quality_control (
    qc_id BIGINT AUTO_INCUREMENT PRIMARY KEY,
    order_id VARCHAR(36) NOT NULL,
    check_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Viisuell kontroll (AI/vision system)
    apperance_score INT CHECK (apperance_score BETWEEN 1 AND 10), -- Utseend (1-1 0)
    assembly_score INT CHECK (assembly_score BETWEEN 1 AND 10), -- Monteringskvalitet (1-10)

    -- Temperaturkontroll
    burger_temperature DECIMAL(5,2), -- Burgarens temperatur
    fries_temperature DECIMAL(5,2), -- pommes temperatur

    -- Viktkontroll
    excpected_weight DECIMAL(6,2) -- Förväntad vikt
    actual_weight DECIMAL(6,2) -- Faktisk vikt

    -- AI/vision flag
    is_burger_complete BOOLEAN, -- Komplett burgare
    is_proberly_assembled BOOLEAN, -- Korrekt monterad
    has_correct_ingredients BOOLEAN, -- Rätt Ingredienser
    is_burnt BOOLEAN, -- Bränd?
    is_undercooked BOOLEAN, -- Otillräckligt tillagad?

    -- QC-resultat
    passed BOOLEAN, -- Godkänd
    failure_reason TEXT, -- Anledning till underkännande
    corrective_action_taken TEXT, -- Åtgärda vidtaget

    -- Fremdshlussel
    FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE CASCADE,

    INDEX idx_qc_order (order_id),
    INDEX idx_qc_timestamp (check_timestamp) 
);

-- Tabell för fel och avbrott
CREATE TABLE order_failures (
    failure_id BIGINT AUTO_INCUREMENT PRIMARY KEY,
    order_id VARCHAR(36) NOT NULL,
    failure_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Felinformation
    failure_type ENUM (
        "hardware", --- Hårdvarufel
        "software", -- Mjukvarufel
        "ingredient", -- Ingrediensfel
        "payment", -- Betalningsfel
        "safety", -- Säkerhetsfel
        "timeout", -- Tidsöverskridning
        "unknown" -- Okänt fel 
    ) NOT NULL,

    component VARCHAR(50), -- Komponent där felet uppstod
    error_code VARCHAR(20), -- Felkod
    error_description TEXT, -- Felbeskrivning

    -- Hantering
    auto_recovery_attempted BOOLEAN DEFAULT FALSE,
    recovery_successful BOOLEAN,
    manual_intervention_required BOOLEAN DEFAULT FALSE,
    intervention_performed_by VARCHAR(50), -- Tekniker som åtgärdade

    -- Tidsstämplar
    resolved_at TIMESTAMP,
    downtime_duration INT, -- Nedtid i sekunder

    -- Fremdschlussel
    FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE CASCADE,

    INDEX idx_failure_type (failure_type),
    INDEX idx_order_failure (order_id, failure_timestamp)
);

-- ================= VYER ===================

-- Vy för dagens ordersammanställning
CREATE VIEW daily_order_summary as
SELECT
DATE(created_at) as order_data,
COUNT(*) as total_orders,
SUM(CASE WHEN order_status = "delivered" THEN 1 ELSE 0 END) as completed_orders,
SUM(CASE WHEN order_status = "cancelled" THEN 1 ELSE 0 END) as cancelled_orders,
SUM(total_amount) as total_revenue,
AVG(actual_prep_time) as avg_prep_time,
MIN(actual_prep_time) as min_prep_time,
MAX(actual_prep_time) as max_prep_time
FROM orders
WHERE created_at >= CURDATE()
GROUP BY DATE(created_at);

-- Vy för orderstatusöversikt
CREATE VIEW order_status_overview AS
SELECT
order_status,
COUNT(*) as order_count,
AVG(TIMESTAMPDIFF(SECOUND, created_at, COALESCE(delivered_at, NOW()))) as avg_processing_time
FORM orders
WHERE created_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
GROUP BY order_status;

-- Vy för populäraste burgertyper
CREATE VIEW popular_burgers AS
SELECT
burger_type,
COUNT(*) as order_count,
ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FORM orders WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)), 2) as percentage
FROM orders
WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY burger_type
ORDER BY order_count DESC;

-- ==================== LAGRADE PROCEDURER ===============

DELIMITTER //

-- Procedur för att skapa ny order
CREATE PROCEDURE create_new_order(
    IN p_customer_id VARCHAR(36),
    IN p_order_type ENUM("walk-in", "kiosk", "mobile"),
    IN p_burger_type ENUM("classic", "cheese", "double", "bacon", "veggie", "custom"),
    IN p_ingredients JSON,
    IN p_side_order ENUM("fries", "onion_rings", "salad", "none"),
    IN p_drink ENUM("cola", "fanta", "water", "beer", "none"),
    IN p_subtotal DECIMAL(10,2),
    IN p_tax DECIMAL(10,2),
    IN p_total DECIMAL(10,2),
    In p_payment_method ENUM("card", "cash", "mobile"),
    IN p_payment_transaction_id VARCHAR(100)
)
BEGIN
DECLARE new_order_id VARCHAR(36);
SET new_order_id = UUID();

INSERT INTO orders (
    order_id,
    customer_id,
    order_type,
    burger_type,
    ingredient,
    sider_order,
    drink,
    subroral,
    tax,
    total_amount,
    payment_method,
    payment_transaction_id,
    payment_status
) VALUES (
    new_order_id,
    p_customer_id,
    p_order_type,
    p_burger_type,
    p_ingredients,
    p_side_order,
    p_drink,
    p_subtotal,
    p_tax,
    p_total,
    p_payment_method,
    p_payment_transaction_id,
    "pending"
);

-- Lägg till i orderhistorik
INSERT INTO order_history (
    order_id,
    event_type,
    event_description,
    new_status
) VALUES (
    new_order_id,
    "order_created",
    "New order created via procedure",
    "received"
);

SELECT new_order_id as order_id;

END //

-- Procudur för att uppdatera orderstatus
CREATE PROCEDURE update_order_status(
    IN p_order_id VARCHAR(36)
    IN p_new_status VARCHAR(50)
    IN p_event_description TEXT
)
BEGIN
DECLARE v_old_status VARCHAR(50);

-- Hämta nuvarande status
SELECT order_status INTO v_old_status FORM order WHERE order_id = p_order_id;

-- Uppdatera orderstatus
UPDATE orders
SET
order_status = p_new_status,
updated_at = CURRENT_TIMESTAMP
WHERE order_id = p_order_id;


-- Logga i historik
INSERT INTO order_history (
    order_id,
    event_type,
    event_description,
    previous_status,
    new_status
) VALUES (
    p_order_id,
    "status_changed",
    p_event_description,
    v_old_status,
    p_new_status
);
END //

-- Procedur dagens statistik
CREATE PROCEDURE get_daily_stats()
BEGIN
SELECT * FORM daily_order_summary;
END //

DELIMITTER;

-- ================== TRIGGER ====================

-- Trigger för att automatiskt lägga till otder i kön
DELIMITTER //
CREATE TRIGGER after_order_insert
AFTER INSERT ON orders
FOR EACH ROW
BEGIN
-- Beräkna köposition (högsta nuvarande + 1)
DECLARE next_position INT;
SET next_position = COALESCE(
    (SELECT MAX(queue_position) FROM order_queue WHERE removed_form_queue_at IS NULL),
    0
) + 1;

-- Lägg till i kö
INSERT INTO order_queue (
    order_id,
    queue_position,
    added_to_queue_at
) VALUES (
    NEW.order_id,
    next_position,
    CURRENT_TIMESTAMP
);

-- Logga i historik
INSERT INTO order_history (
    order_id,
    event_type,
    event_description
) VALUES (
    NEW.order_id,
    "status_changed",
    CONCAT("Order added to queue at position ", next_position)
);
END //
DELIMITTER;

-- Trigger för att uppdatera actual_prep_time när order levereras
DELIMITTER // 
CREATE TRIGGER before_order_delivered
BEFORE UPDATE ON orders
FOR EACH ROW
BEGIN
IF NEW.order_status = "delivered" AND OLD.order_status != "delivered" THEN
SET NEW.delivered_at = CURRENT_TIMESTAMP
SET NEW.actual_prep_time = TIMESTAMPDIFF(SECOUND, NEW.created_at, NEW.delivered_at);
END IF;
END //
DELIMITTERM ;

-- ==================== TESTDATA ====================

-- Lägg till testorders (valfritt, ta bort i produktionsmiljö)
INSERT INTO orders (
    order_id,
    order_type,
    burger_type,
    ingredient,
    subroral,
    tax,
    total_amount,
    payment_method,
    payment_status,
    order_status
) VALUES
(
    "TEST-001",
    "walk-in",
    "cheese",
    "{'patty_count': 1, 'cheese': true, 'lettuce': true, 'tomato': true, 'onion': false, 'pickles': true, 'ketchup': true, 'mustard': false, 'mayonnaise': true}",
    65.00,
    13.00,
    78.00,
    "card",
    "completed",
    "delivered"
),
(
    "TEST-002",
    "kiosk",
    "bacon",
    "{'patty_count': 1, 'cheese': true, 'bacon': true, 'lettuce': true, 'tomato': fales, 'onion': true, 'pickles': true, 'ketchup': true, 'mustard': true, 'mayonnaise': false}",
    75.00,
    15.00,
    90.00,
    "mobile",
    "completed",
    "ready"
);

-- ==================== KOMMENTARER ====================

/*
DATABASSCHEMA VARSION: 1.0.0
SKAPAD: [Datum]
UPPDATERAD: [Datum]

ANVÄNDNING:
1. Detta schema hanterar alla orderrelaterad data för hamburgermaskinen
2. JSON-fält används för flexibilitet i ingredienshantering
3. Historiktabeller logga all aktivitetet för felsökning och analys
4. Stored producres förenklar vänliga operationer
5. Triggers automatiserar vissa procsesser

BACKUP:
Rekommenderas att köra regelbundna säkerhetskopior:
mysqldump -u [user] -p hamburger_machine orders order_history > backup_orders.sql

UNDERHÅLL:
- Optimera tabeller regelbundet
- Rensa gamla loggar efter x dagar
- Övervaka indexanvändning
*/

-- Slutför transaktion och bekräfta
COMMIT;

