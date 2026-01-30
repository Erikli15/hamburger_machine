-- Logs.sql
-- Loggschema för Haburgerautomatem
-- Skapad: [Datum]
-- Uppdaterad: [Datum]

-- =============================================
-- TABELL: system_logs
-- Loggar för systemhändelser och normal drift
-- =============================================
CRIATE TABLE IF NOT EXISTS system_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    log_level VARCHAR(10) NOT NULL CHECK(log_level IN ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")),
    component VARCHAR(50) NOT NULL,
    message TEXT NOT NULL,
    details TEXT,
    session_id VARCHAR(36),
    user_id VARCHAR(50),

    -- Index för snabbare sökningar
    INDEX idx_log_level (log_level),
    INDEX idx_component (component),
    INDEX idx_timestamp (timestamp),
    INDEX idx_session (session_id)
);

-- =============================================
-- TABELL: error_logs
-- Detaljerade fellogger
-- =============================================
CRIATE TABLE IF NOT EXISTS error_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    error_code VARCHAR(20) NOT NULL,
    error_type VARCHAR(50) NOT NULL,
    component VARCHAR(50) NOT NULL,
    message TEXT NOT NULL,
    stack_trace TEXT, 
    user_action TEXT,
    system_state TEXT,
    resolved BOOLEAN DEFAULT 0,
    resolved_at DATETIME,
    resolved_by VARCHAR(50),

    -- Index
    INDEX idx_error_code (error_code),
    INDEX idx_error_type (error_type),
    INDEX idx_resolved (resolved),
    INDEX idx_timestamp_error (timestamp)
);

-- =============================================
-- TABELL: order_audit_log
-- Loggar för orderrelaterade händelser
-- =============================================
CRIATE TABLE IF NOT EXISTS order_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP.
    order_id VARCHAR(20) NOT NULL,
    event_type VARCHAR(30) NOT NULL CHECK(event_type IN (
        "ORDER_CREATED",
        "ORDER_STARTED",
        "ORDER_COMPLETED",
        "ORDER_CANCELLED",
        "ORDER_FAILED",
        "PAYMENT_RECETIVED",
        "PAYMENT_FAILED",
        "INGREDIENT_DISPENSED",
        "COOKING_STARTED"
        "COOKING_COMPLETED",
        "ASSEMBLY_STARTED",
        "ASSEMBLY_COMPLETED"
    )),
    event_details TEXT,
    user_id VARCHAR(50),
    machine_id VARCHAR(20),
    duration_seconds INTEGER,

    -- Index
    INDEX idx_order_id (order_id),
    INDEX idx_event_type (event_type),
    INDEX idx_timestamp_order (timestamp)
);

-- =============================================
-- TABELL hardware_logs
-- Loggar för maskinvaruhändelser
-- =============================================
CRIATE TABLE IF NOT EXISTS hardware_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    device_type VARCHAR(30) NOT NULL CHECK (device_type IN (
        "FRITOS",
        "GRILL",
        "FREEZER",
        "ROBOTIC_ARM",
        "CONVEYOR",
        "DISPENSER",
        "TEMPERATURE_SENSOR",
        "INVENTORY_SENSOR",
        "SAFETY_SENSOR",
        "CARD_READER"
    )),
    device_id VARCHAR(20) NOT NULL,
    event_type VARCHAR(30) NOT NULL,
    value_reading FLOAT,
    unit VARCHAR(10),
    status VARCHAR(20) NOT NULL,
    alert_level VARCHAR(10) CHECK(alert_level IN ("NORMAL", "WARNING", "CRITICAL")), 

    -- Index
    INDEX idx_device_type (device_type),
    INDEX idx_device_id (device_id),
    INDEX idx_status (status),
    INDEX idx_timestamp_hardware (timestamp)
 );

 -- =============================================
-- TABELL: maintenance_logs
-- Underhållsloggar
-- =============================================
CREATE TABLE IF NOT EXISTS maintenance_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    maintenance_type VARCHAR(30) NOT NULL CHECK(maintenance_type IN (
        "ROUTINE",
        "CURRECTIVE",
        "PREVENTIVE",
        "CALIBRATION",
        "CLEANING",
        "REPLACEMENT"
    )),
    component VARCHAR(50) NOT NULL,
    technician_id VARCHAR(50),
    description TEXT NOT NULL,
    duration_minutes INTEGER,
    parts_replaced TEXT,
    notes TEXT,
    next_maintenance_date DATE,

    -- Index
    INDEX idx_maintenance_type (maintenance_type),
    INDEX idx_component_maint (component),
    INDEX idx_next_maintenance (next_maintenance_date)
);

-- =============================================
-- TABELL: temperature_log
-- Temperatureloggar för övervakning
-- =============================================
CREATE TABLE IF NOT EXISTS temperature_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sensor_id VARCHAR(20) NOT NULL,
    temperature_celsius FLOAT NOT NULL,
    setpoint_celsius FLOAT,
    status VARCHAR(20) CHECK(status IN ("NORMAL", "TOO_HIGH", "TOO_LOW", "ERROR")),
    heater_status BOOLEAN,
    cooler_status BOOLEAN,

    -- Index
    INDEX idx_sensor_id (sensor_id),
    INDEX idx_timestamp_temp (timestamp),
    INDEX idx_status_temp (status)
);

-- =============================================
-- TABELL: inventory_logs
-- Loggar för inventeringsändringar
-- =============================================
CREATE TABLE IF NOT EXISTS inventory_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ingredient_id VARCHAR(20) NOT NULL,
    ingredient_name VARCHAR(50) NOT NULL,
    change_amount INTEGER NOT NULL,
    new_quantity INTEGER NOT NULL,
    reason VARCHAR(30) NOT NULL CHECK( reason IN (
        "ORDER_USAGE",
        "RESTOCK",
        "WASTE",
        "ADJUSTMENT",
        "EXPIRATION",
        "INITIAL_SETUP"
    )),
    order_id VARCHAR(20),
    user_id VARCHAR(50),

    -- Index
    INDEX idx_ingredient_id (ingredient_id),
    INDEX idx_reason (reason),
    INDEX idx_timestamp_inv (timestamp)
);

-- =============================================
-- TABELL: safety_logs
-- Säkerhetsrelaterade logger
-- =============================================
CREATE TABLE IF NOT EXISTS safety_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    safety_event VARCHAR(30) NOT NULL CHECK(safety_event IN (
        "EMERGENCY_STOP",
        "DOOR_OPENEND",
        "OVERHEAT",
        "MOTOR_STALL",
        "SAFETY_BARRIER",
        "FIRE_DETECTED",
        "POWER_FAILURE",
        "MANUAL_OVERRIDE"
    )),
    device_id VARCHAR(20),
    serverity VARCHAR(10) CHECK(serverity IN ("LOW", "MEDIUM", "HIGH", "CRITICAL")),
    auto_resolved BOOLEAN,
    resolved_at DATETIME,
    resolved_by VARCHAR(50),
    action_taken TEXT,

    -- Index
    INDEX idx_safety_event (safety_event),
    INDEX idx_severity (serverity),
    INDEX idx_timestamp_safety (timestamp)
);

-- =============================================
-- TABELL: user_action_logs
-- Loggar för användaråtergärder
-- =============================================
CREATE TABLE IF NOT EXISTS user_action_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id VARCHAR(50) NOT NULL,
    action_type VARCHAR(30) NOT NULL CHECK(action_type IN (
        "LOGIN",
        "LOGOUT",
        "SETTINGS_CHANGE",
        "MANUAL_OVERRIDE",
        "MAINTENANCE_ACTION",
        "INVENTORY_UPDATE",
        "RECIPE_CHANGE",
        "SYSTEM_SHUTDOWN",
        "SYSTEM_STARTUP"
    )),
    action_details TEXT,
    ip_address VARCHAR(45),
    user_agent TEXT,

    -- Index
    INDEX idx_user_id (user_id),
    INDEX idx_action_type (action_type),
    Index idx_timestamp_user (timestamp)
);

-- =============================================
-- TABELL: performance_logs
-- Prestandaloggar
-- =============================================
CREATE TABLE IF NOT EXISTS performance_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metric_name VARCHAR(30) NOT NULL CHECK(metric_name IN (
        "ORDER_PROCESSING_TIME",
        "COOKING_TIME",
        "ASSEMBLY_TIME",
        "PAYMENT_PROCESSING_TIME",
        "SYSTEM_UPTIME",
        "CPU_USAGE",
        "MEMORY:USAGE",
        "DISK_USAGE",
        "NETWORK_LATENCY"
    )),
     metric_value FLOAT NOT NULL,
     unit VARCHAR(10),
     component VARCHAR(50),

     -- Index
     INDEX idx_metric_name (metric_name),
     INDEX idx_timestamp_perf (timestamp)
);

-- =============================================
-- Vy: vw_recent_errors
-- Vy för senaste felen
-- =============================================
CREATE VIEW IF NOT EXISTS vw_recent_errors AS
SELECT
timestamp,
error_code,
error_type,
component,
message,
resolved
FROM error_logs
WHERE timestamp >= datetime("now", "-24 hours")
ORDER BY timestamp DESC;

-- =============================================
-- VY: vm_daily_summary
-- Vy för daglig sammanfattning
-- =============================================
CREATE VIEW IF NOT EXISTS vm_daily_summary AS
SELECT
date(timestamp) as log_date,
COUNT(*) as total_logs,
SUM(CASE WHEN log_level = "ERROR" THEN 1 ELSE 0 END) as error_count,
SUM(CASE WHEN log_level = "WARNING" THEN 1 ELSE 0 END) as warning_count,
MIN(timestamp) as first_log,
MAX(timestamp) as last_log
FROM system_logs
GROUP BY date(timestamp);

-- =============================================
-- TRIGGER: tag_error_notification
-- Trigger för att flagga nya fel
-- =============================================
CREATE TRIGGER if NOT EXISTS tag_error_notification
AFTER INSERT ON error_logs
WHEN NEW.resolved = 0
BEGIN
INSERT INTO system_logs (
    log_level,
    component,
    message,
    details
) VALUES (
    "ERROR",
    "ERROR_HANDLER",
    "New error logged: " || NEW.error_code,
    NEW.message
);
END;

-- =============================================
-- TRIGGER: trg_inventory_low
-- Trigger för låg inventeringsvarning
-- =============================================
CREATE TRIGGER IF NOT EXISTS trg_inventory_low
AFTER INSERT ON inventory_logs
WHEN NEW.new_quantity < 10
BEGIN
INSERT INTO system_logs (
    log_level,
    component,
    message,
    details
) VALUES (
    "WAENING",
    "INVENTORY",
    "Low inventory: " || NEW.ingredient_name,
    "Current quantity: " || NEW.new_quantity
);
END;

-- =============================================
-- PRODUCEDUR: sp_cleanup_old_logs
-- Rensar gamöa loggar (körs måndasvis)
-- =============================================
CREATE INDEX IF NOT EXISTS idx_system_logs_comprehensive
BEGIN
-- System logs: behåll 90 dagar
DELETE FROM system_logs
WHERE timestamp < datetime("now", "-" || rentation_days || "days");

-- Temperature logs: behåll 30 dagar
DELETE FROM temperature_log
WHERE timestamp < datetime("now", "-30 days");

-- Performennce logs:behåll 7 dagar
DELETE FROM performance_logs
WHERE timestamp < datetime("now", "-7 days");
END;

-- =============================================
-- INDEX för ytterligare prestandoptimering
-- =============================================

-- Sammansatta index för vanliga queries
CREATE INDEX IF NOT EXISTS idx_system_logs_comprehensive
ON system_logs(timestamp, log_level, component);

CRIATE INDEX if NOT EXISTS idx_order_audit_comprehensive 
ON order_audit_log(order_id, event_type, timestamp);

CREATE INDEX IF NOT EXISTS idx_hardware_logs_comprehensive
ON hardware_logs(device_id, timestamp, status):

-- =============================================
-- KOMMENTARER
-- =============================================

/* 
NOTERA:
1. Alla tabeller använder INTERGER PRIMARY KEY AUTOINCREMENT för enkelhet
2. TIMESTAMP används konsekvent för tidsstämpling
3. CHECK constraints används för databalidering
4. Idndex optimera vanliga sökningar
5. Vyerna förenklar rapportering
6. Triggers automatiserar vissa loggningshändelser

REKOMENDARIONER:
- Köra sp_cleanup_old_logs månadsvis via cron-jobb
- Använda vyer för dashboards och rapporter
- Backup av databasen dagligen
- Monitorera storleken på loggtabellerna
*/

-- =============================================
-- INITIELL DATA (om nödvändigt)
-- =============================================
INSERT OR IGNORE INTO system_logs (
    log_level,
    component,
    message
) VALUES (
    "INFO",
    "DATABASE",
    "Log databas schema initilized successfully"
);

