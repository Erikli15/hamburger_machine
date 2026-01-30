-- ============================================
-- HAMBURGER MACHINE - INVENTORY DATABASE SCHEMA
-- ============================================
-- Skapad: 2024-01-29
-- Verision 1.0.0
-- ============================================

-- Tabbell för ingredienskatagorier
CREATE TABLE IF NOT EXISTS ingredient_categories (
    category_id SERIAL PRIMARY KEY,
    category_name VARCHAR(50) NOT NULL UNIQUE,
    description TEXT,
    storage_requirement VARCHAR(20) CHECK (storage_requirement IN ("frozen", "refrigerated", "room_temp", "dry")),
    min_temperature DECIMAL(5,2),
    max_temperature DECIMAL(5,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabell för ingredienser
CREATE TABLE IF NOT EXISTS ingredients (
    ingredent_id SERIAL PRIMARY KEY,
    ingredent_name VARCHAR(100) NOT NULL UNIQUE,
    category_id INGER REFERENCES ingredient_categories(category_id),
    sku VARCHAR(50) UNIQUE,
    supplier VARCHAR(100),
    unit_of_meadure VARCHAR(20) DEFAULT "grams",
    unit_price DECIMAL(10,2),
    per_level DECIMAL(10,2), -- Optimal lagernivå
    reorder_point DECIMAL(10,2) -- Nivå för beställning
    max_capacity DECIMAL(10,2) -- Max lagringskapacitiet
    current_quantity DECIMAL(10,2) DEFAULT 0,
    shelf_life_days INTEGER,
    location_in_machine VARCHAR(50) -- T.ex. "Dispenser_A1", "Freezer_B2"
    is_active BOOLEAN DEFAULT TRUE,
    last_restocked TIMESTAMP,
    expiration_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabell för recept/ingredienskomponenter
CREATE TABLE IF NOT EXISTS recipe_components (
    recipe_component_id SERIAL PRIMARY KEY,
    recipe_id INTEGER, -- Refererar till recept i recipe_manager
    ingredient_id INTEGER REFERENCES ingredients(ingredent_id),
    quantity_required DECIMAL(10,2) NOT NULL, -- Maängd per portion
    preparation_notes TEXT,
    step_number INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabell för lagerförändringar
CREATE TABLE IF NOT EXISTS inventory_transactions (
    transaction_id SERIAL PRIMARY KEY,
    ingredent_id INTEGER REFERENCES ingredients(ingredent_id),
    transaction_type VARCHAR(20) CHECK (transaction_type IN (
        "restock", "usage", "waste", "adjustment", "transfer"
    )),
    quantity_change DECIMAL(10,2),
    previous_quantity DECIMAL(10,2),
    new_quantity DECIMAL(10,2),
    transaction_reason VARCHAR(100),
    order_id INTEGER, -- Länk till order om användning
    performed_by VARCHAR(50), -- System eller användare
    notes TEXT,
    transaction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP 
);

-- Tabell för automatiska beställningar
CREATE TABLE IF NOT EXISTS auto_orders (
    auto_order_id SERIAL PRIMARY KEY,
    ingredient_id INTEGER REFERENCES ingredients(ingredent_id),
    quantity_to_order DECIMAL(10,2) NOT NULL,
    order_trigger VARCHAR(20) CHECK (order_trigger IN (
        "pending", "ordered", "delivered", "cancelled"
    )),
    expeceted_delivery DATE,
    actual_delivery DATE,
    order_cost DECIMAL(10,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabell för temperaturövervakning
CREATE TABLE IF NOT EXISTS temperature_logs (
    log_id SERIAL PRIMARY KEY,
    sensor_id VARCHAR(50) NOT NULL,
    location VARCHAR(50), -- T.ex. "fritös_1", "freezer_main"
    temperature DECIMAL(5,2) NOT NULL,
    unit VARCHAR(10) DEFAULT "celsius",
    status VARCHAR(20) CHECK (status IN ("normal", "warning", "critical")),
    threshold_min DECIMAL(5,2),
    threshold_max DECIMAL(5,2),
    logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabell för kvalitetskontroll
CREATE TABLE IF NOT EXISTS quality_checks (
    check_id SERIAL PRIMARY KEY,
    ingredent_id INTEGER REFERENCES ingredients(ingredent_id),
    check_type VARCHAR(30)CHECK (check_type IN (
        "exiration", "temperature", "visual", "weight", "sensor"
    )),
    check_result VARCHAR(20) CHECK (check_result IN (
        "pass", "fail", "warning"
    )),
    measured_value DECIMAL(10,2),
    expexted_value DECIMAL(10,2),
    tolerance_percentage DECIMAL(5,2),
    performed_by VARCHAR(50) DEFAULT "system",
    notes TEXT,
    check_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabell för waste/spill
CREATE TABLE IF NOT EXISTS waste_logs (
    waste_id SERIAL PRIMARY KEY,
    ingredent_id INTEGER REFERENCES ingredients(ingredent_id),
    waste_type VARCHAR(20) CHECK (waste_type IN (
        "expired", "overcooked", "undercooked", "spillage", "other"
    )),
    quanity DECIMAL(10,2) NOT NULL,
    cost DECIMAL(10,2),
    reason TEXT,
    logged_by VARCHAR(50),
    waste_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabell för predikiv inventering
CREATE TABLE IF EXISTS inventory_predictions (
    predictioon_id SERIAL PRIMARY KEY,
    ingredent_id INTEGER REFERENCES ingredients(ingredent_id),
    predictioon_date DATE NOT NULL,
    predictioon_usage DECIMAL(10,2),
    confidence_level DECIMAL(5,2), --0-100%
    prediciton_model VARCHAR(50),
    actual_usage DECIMAL(10,2),
    accuracy DECIMAL(5,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- INDEX FÖR PERFORMANCE
-- ============================================

--Index föe snabba ingredienssökningar
CREATE INDEX idx_ingredients_name ON ingredients(ingredent_name);
CREATE INDEX idx_ingredients_category ON ingredients(category_id);
CREATE INDEX idx_ingredients_location ON ingredients(location_in_machine);
CREATE INDEX idx_ingredients_exporation ON ingredients(expiration_date) WHERE expiration_date IS NOT NULL;

-- Index för transaktioner
CREATE INDEX idx_trasactions_ingredient ON inventory_transactions(ingredent_id);
CREATE INDEX idx_trasactions_date ON inventory_transactions(transaction_date);
CREATE INDEX idx_trasactions_status ON inventory_transactions(transaction_type):

-- Index för temperaturloggar
CREATE INDEX idx_temperature_sensor ON temperature_logs(sensor_id);
CREATE INDEX idx_temperature_date ON temperature_logs(logged_at);
CREATE INDEX idx_temperature_status ON temperature_logs(status);

-- Index för kvalitetskontroller
CREATE INDEX idx_quality_ingredient ON quanity_checks(ingredent_id);
CREATE INDEX idx_quality_date ON quanity_checks(check_date);
CREATE INDEX idx_quality_result ON quality_checks(check_result);

-- ============================================
-- TRIGGERS FÖR DATAINTEGRITET
-- ============================================


-- Trigger för att uppdatera updated_at vid ändringar
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
NEW.updated_at = CURRENT_TIMESTAMP;
RETURN NEW;
END;
$$ language "plpsql";

CREATE TRIGGER update_ingredients_updated_at
BEFORE UPDATE ON ingredients
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_auto_orders_updated_at
BEFORE UPDATE ON auto_orders
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Trigger för att logga kvantitetsändrimgar aitomatiskt
CREATE OR REPLACE FUNCTION log_inventory_change()
RETURNS TRIGGER AS $$ 
BEGIN
IF OLD.current_quantity != NEW.current_quantity THEN
INSERT INTO inventory_transactions (
    ingredent_id,
    transaction_id,
    quantity_change,
    previous_quantity,
    new_quantity,
    performed_by,
    transaction_reason
) VALUES (
    NEW.ingredent_id,
    "adjustment",
    NEW.current_quantity - OLD.current_quantity,
    OLD.current_quantity,
    NEW.current_quantity,
    "system",
    "automatic_adjustment"
);
END IF;
RETURN NEW;
END;
$$ language "plsgsql";

CREATE TRIGGER trigger_log_inventory_change
AFTER UPDATE OF current_quantity ON ingredients
FOR EACH ROW EXECUTE FUNCTION log_inventory_change();

-- ============================================
-- VYER FÖR RAPPORTER
-- ============================================

-- Vy för lagerstatus med varningar
CREATE OR REPLACE VIEW inventory_status_view AS
SELECT
i.ingredent_id,
i.ingredent_name,
i.category_id,
ic.category_name,
i.current_quantity,
i.par_level,
i.reorder_point,
i.max_capacity,
i.unit_of_meadure,
ROUND((i.current_quantity / i.par_level * 100), 2) AS stock_percentage,
CASE
WHEN i.current_quantity <= i.reorder_point THEN "REORDER"
WHEN i.current_quantity <= (i.par_level * 0.5) THEN "LOW"
WHEN i.current_quantity >= i.max_capacity THEN "OVERSTOCK"
ELSE "OK"
END AS stock_status,
i.expiration_date,
CASE
WHEN i.expiration_date <= CURRENT_DATE THEN "EXPIRED"
WHEN i.expiration_date <= CURRENT_DATE + INTERVAL "3 days" THEN "SOON_EXÅIRING"
ELSE "VALID"
END AS exiration_status,
i.location_in_machine,
i.last_restocked
FROM ingredients i 
LEFT JOIN ingredient_categories ic ON i.category_id = ic.category_id
WHERE i.is_active = TRUE;

-- Vy för dagens användning
CREATE OR REPLACE VIEW daily_usage_view AS
SELECT
it.ingredient_id,
i.ingredent_name,
DATE(it.transaction_date) AS usage_date,
SUM(CASE WHEN it.transaction_type = "usage" THEN it.quantity_change ELSE 0 END) AS total_used,
SUM(CASE WHEN it.transaction_type = "waste" THEN it quantity_change ELSE 0 END) AS total_wasted,
COUNT(DISTINCT it.order_id) AS order_count
FROM inventory_transactions it
JOIN ingredients i ON it.ingredent_id = i.ingredent_id
WHERE DATE(it.transaction_date) = CURRENT_DATE
GROUP BY it.ingredent_id, i.ingredent_name, DATE(it.transaction_date);

-- Vy för leverantörsprestanda
CREATE OR REPLACE VIEW supplier_performance_viwe AS
SELECT
i.supplier,
COUNT(DISTINCT i.ingredent_id) AS ingredents_count,
AVG(i.unit_price) AS avg_price,
MIN(ao.expexted_delivery - ao.created_at) AS min_lead_time,
MAX(ao.expeceted_delivery - ao.expeceted_delivery) AS avg_delivery_deviation
FROM ingredients i
LEFT JOIN auto_orders ao ON ingredent_id = ao.ingredent_id
WHERE i.supplier IS NOT NULL
GROUP by i.supplier;

-- ============================================
-- BASDATA (DEFAULT CATEGORIES)
-- ============================================

INSERT INTO ingredient_categories (category_name, storage_requirement, min_temperature, max_temperature, description) VALUES
("Bread & Buns", "room_temp", 18.0, 22.0, "Bröd burgerbröd, toast"),
("Meat & Patties", "frozen", -18.0, -15.0, "Kött, burgare, kyckling"),
("Cheese", "refrigerated", 2.0, 6.0, "Ost, cheddar, mozzarella"),
("Vegetables", "refrigerated", 2.0, 6.0, "Sallad, tomater, lök"),
("Sauces & Condiments", "refrigerated", 3.0, 7.0, "Ketchup, majonäs, dressing"),
("Frozen Vegetables", "frozen", -18.0, 15.0, "Pommes frites, lökar"),
("Packaging", "dry", 15.0, 25.0, "Förpackningar, servetter"),
("Toppings", "room_temp", 18.0, 22.0, "Bacon, pickles, svamp")
ON COFLICT (category_name) DO NOTHING;

-- ============================================
FUNKTIONER FÖR INVENTORY MANAGEMENT
-- ============================================

--  Funktion fär att registrera ingrediensanvändning
CREATE OR REPLACE FUNCTION use_ingredient(
    p_ingredient_id INTEGER,
    p_quantity DECIMAL,
    p_order_id INTEGER DEFAULT NULL,
    p_notes TEXT DEFAULT NULL
) RETURNS BOOLEAN AS $$
DECLARE
v_current_quantity DECIMAL;
BEGIN
-- Hämta nuvarande kvantitet
SELECT current_quantity INTO v_current_quantity
FROM ingredients
WHERE ingredent_id = p_ingredient_id;

-- Kontrollera tillgänglighet
IF v_current_quantity < p_quantity THEN
RAISE EXEPTION "Insufficient stock. Available: %, Requested: %",
v.v_current_quantity, p_quantity;
RETURN FALSE;
END IF;

-- Uppdatera loger
UPDATE ingredients
SET current_quantity = current_quantity - p_quantity
WHERE ingredent_id = p_ingredient_id;

-- Logga transaktion
INSERT INTO inventory_transactions (
    ingredent_id,
    transaction_type,
    quantity_change,
    previous_quantity,
    new_quantity,
    order_id,
    transaction_reason,
    performed_by,
    notes
) VALUES (
    p_ingredient_id,
    "usage",
    -p_quantity,
    v_current_quantity,
    v_current_quantity - p_quantity,
    p_order_id,
    "order_fulfillment",
    "system",
    p_notes
);

RETURN TRUE;
END;
$$ LANGUAGE plsgsql

-- Funktion för att kontollera och flagga lågt lager
CREATE OR REPLACE FUNCTION check_reorder_status()
RETURNS TABLE(
    ingredent_id INTEGER,
    ingredent_name VARCHAR,
    current_quantity DECIMAL,
    reorder_point DECIMAL,
    status VARCHAR,
    days_until_empty INTEGER
) AS $$ 
BEGIN
RETURN QUERY
SELECT
i.ingredent_id,
i.ingredent_name,
i.current_quantity,
i.reorder_point,
CASE
WHEN i.current_quantity <= i.reorder_point * 0.3 THEN "CRITICAL"
WHEN i.v_current_quantity <= i.reorder_point THEN "LOW"
ELSE "OK"
END AS status,
CASE
WHEN di.avg_daily_usage > 0
THEN CEIL(i.current_quantity / di.avg_daily_usage)
ELSE NULL
END AS days_until_empty
FROM ingredients i
LEFT JOIN (
    SELECT
    ingredent_id,
    AVG(ABS(quantity_change)) AS avg_daily_usage
    FROM inventory_transactions
    WHERE transaction_type IN ("usage", "waste")
    AND transaction_date >= CURRENT_DATE - INTEGER "30 days"
    GROUP BY ingredent_id 
) di ON i.ingredent_id = di.ingredent_id
WHERE i.is_active = TRUE
AND i.current_quantity <= i.reorder_point * 1.2; -- Visa även nära reorder
END;
$$ LANGUAGE plpsql;

-- Funktion för att generera automatiska beställningar
CREATE OR REPLACE FUNCTION generate_auto_orders()
RETURNS INTEGER AS $$
DECLARE
v_order_count INTEGER := 0;
v_igredient RECORD;
BEGIN
FOR v_igredient IN
SELECT * FROM check_reorder_status()
WHERE status IN ("CRITICAL", "LOW")
LOOP
INSERT INTO auto_orders (
    ingredent_id,
    quantity_to_order,
    order_trigger,
    status,
    expeceted_delivery
) VALUES (
    v_igredient.v_igredient,
    v_igredient.reorder_point * 2 - v_igredient.current_quantity, -- Beställ up till 2x reorder
    "low_stock",
    "pending",
    CURRENT_DATE + INTERVAL "2 days" -- Anta 2 dagars leveranstid
);
v_order_count := v_order_count + 1;
END LOOP;

RETURN v_order_count;
END
$$ LANGUAGE plsgsql

-- ============================================
-- ADMINISTATIVA FUNKTIONER
-- ============================================

 -- Grant behörigjeter för applikationen
 -- (Kör seperat med administrativa rättigheter)

 /*
 GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO hamburger_app;
 GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO hamburger_app;
 GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO hamburger_app;
 */

 -- ============================================
-- KOMMENTERA
-- ============================================

COMMET ON TABLE ingredients IS "Huvudtabell för all ingredienser i hamburgarmaskinen";
COMMET ON TABLE inventory_transactions IS "Spårar alla lagerförändringar för audit trail";
COMMET ON TABLE temperature_logs IS "Loggar temperaturdata från alla sensorer";
COMMET ON TABLE quality_checks IS "Kvalitetskontroller för ingredienser";
COMMET ON TABLE waste_logs IS "Spill- och svinnlogg för kostnadskontroll";


COMMET ON TABLE ingredients.per_level IS "Optimal lagernivå för jamn produktion";
COMMET ON TABLE ingredients.reorder_point IS "Nivå vid vilken automatisk beställning triggers";
COMMET ON TABLE ingredients.location_in_machine IS "Fysisk placering i maskinen (dospenser, frysfack, etc.)";

-- ============================================
-- DATABASE VERSIONING METADATA
-- ============================================

CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_id SERIAL PRIMARY KEY,
    version VARCHAR(20) NOT NULL,
    description TEXT,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    applied_by VARCHAR(50) DEFAULT CURRENT_USER
);

INSERT INTO schema_migrations (version, description) VALUES
("1.0.0", "Initial inventory schema for Hamburger Machine")
ON CONFLICT DO NOTHING



