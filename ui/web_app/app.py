#!/user/bin/env python3
"""
Hamburger Machine Web Interface
Flask-baserat webbgränssnitt för övervakning och kontroll av hamburgerautomaten.
"""

import os
import json
import time
from datetime import datetime
from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from flask_socketio import SocketIO, emit
from functools import wraps
import logging
from typing import Dict, Any, Optional

# Importera systemkomponenter
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), "../.."))

from ...utils.logger import setup_logger
from ...utils.config_loader import load_config
from ...core.controller import MachineController
from ...core.state_manager import SystemState
from ...order_management.order_processor import OrderPeocessor
from ...hardware.temperature.sensor_manager import TemperatureManager


# Konfiguration
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "../../config.yaml")
config = load_config(CONFIG_PATH)

# Setup logger
logger = setup_logger("web_ui", config.get("logging", {}))

# Flask-app
app = Flask(__name__)
app.config["SECRET_KEY"] = config.get("web_ui, {}").get("secret_key", "hamburger-machine-secret-key")
app.config["SESSION_TYPE"] = "filesystem"

# SocketIO för realtidsuppdateringar
socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")

# Systeminstanser
system_state = None
machine_controller = None
order_processor = None
temperature_manager = None

# Autentisering
USERS = {
    "admin": {"password": "admin123", "role": "admin"},
    "operator": {"password": "operator123", "role": "operator"},
    "viewer": {"password": "viewer123", "role": "viewer"}
}

def login_required(f):
    """Decorator för att kräva inloggning."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

def role_required(required_role):
    """Decorator för att kräva specifik roll."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if "username" not in session:
                return redirect(url_for("login"))
            
            user_role = session.get("role")
            if user_role != "admin" and user_role != required_role:
                return jsonify({"error": "Insufficient permissins"}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def initialize_system():
    """Initiera systemkompenenter."""
    global system_state, machine_controller, order_processor, temperature_manager

    try:
        # Initiera systemtillstånd
        system_state = SystemState(config)

        # Initiera kontroller
        machine_controller = MachineController(config, system_state)

        # Initiera temperaturehanterare
        temperature_manager = TemperatureManager(config)

        logger.info("System components initialized successfully")

        # Starta systemövervakningstråd
        temp_thread = threading.Thread(target=temperature_monitoring_loop, daemon=True)
        temp_thread.start()

    except Exception as e:
        logger.error(f"Failed to initialize system: {e}")
        raise

def system_monitoring_loop():
    """Tråd för systemövervakning och SocketIO-uppdatering"""
    while True:
        try:
            if system_state and machine_controller:
                # Samla systemstatus
                system_status = {
                    "system_state": system_state.get_current_state(),
                    "machine_status": machine_controller.get_status(),
                    "timestamp": datetime.now().isoformat(),
                    "order_in_queue": order_processor.queue_manager.get_queue_length() if order_processor else 0,
                    "current_operation": system_state.get_current_operation()
                }     

                # skicka till alla alutna klienter
                socketio.emit("sytem_update", system_status)

            # Uppdatera var 2:e sekund
            time.sleep(2)

        except Exception as e:
            logger.error(f"Error i monitoring loop: {e}")
            time.sleep(5)

def temperature_monitoring_loop():
    """Tråd för temperaturövervakning."""
    while True:
        try:
            if temperature_manager:
                # Hämta temperaturer från alla zoner
                temperatures = {
                    "fryer": temperature_manager.get_fryer_temperature(),
                    "grill": temperature_manager.get_grill_temperature(),
                    "freezer": temperature_manager.get_freezer_temperature(),
                    "ambient": temperature_manager.get_ambient_temperature()
                }

                # Skicka temperaturuppdatering
                socketio.emit("temperature_update", temperatures)

            # Uppdatera var 5:e sekund
            time.sleep(5)
        except Exception as e:
            logger.error(f"Error i temperature loop: {e}")
            time.sleep(10)

# Routes
@app.route("/")
@login_required
def login():
    """Inloggbungssida."""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if username in USERS and USERS[username]["password"] == password:
            session["username"] = username
            session["role"] = USERS[username]["role"]
            logger.info(f"User {username} logged in")
            return redirect(url_for("index"))
        
        return render_template("login.html", error="Invalid credentials")
    
    return render_template("login.html")

@app.route("/logout")
def logout():
    """Utloggning."""
    username = session.get("username")
    session.clear()
    logger.info(f"User {username} logged out")
    return redirect(url_for("login"))

@app.route("/temperature")
@login_required
def temperature_page():
    """Temperaturöversiktssida."""
    current_temps = {}
    if temperature_manager:
        current_temps = {
            "fryer": temperature_manager.get_fryer_temperature(),
            "grill": temperature_manager.get_grill_temperature(),
            "freezer": temperature_manager.get_freezer_temperature(),
            "ambient": temperature_manager.get_ambient_temperature()
        }
    
    return render_template("temperature.html",
                           temperatures=current_temps,
                           username=session.get("username"),
                           role=session.get("role"))

@app.route("/orders")
@login_required
def orders_page():
    """Orderhanteringssida."""
    orders = []
    if order_processor:
        orders = order_processor.get_recent_orders(limit=50)

    return render_template("orders.html",
                           orders=orders,
                           username=session.get("username"),
                           role=session.get("role"))

@app.route("/inventory")
@login_required
def inventory_page():
    """Inventeringsstatus sida."""
    inventory = {}
    if order_processor and hasattr(order_processor, "inventory_tracker"):
        inventory = order_processor.inventory_tracker.get_inventory_status()

    return render_template("inventory.html",
                           inventory=inventory,
                           username=session.get("username"),
                           role=session.get("role"))

@app.route("/system")
@login_required
@role_required("admin")
def system_page():
    """Systemstatus och konfiguration (endast admin)."""
    if system_state:
        state = system_state.get_current_state()
        config_summary = {
            "machine_id": config.get("machine_id", "unknown"),
            "version": config.get("version", "1.0.0"),
            "operating_hourse": system_state.get_operating_hourse(),
            "total_orders": system_state.get_total_orders_processed()
        }
        return render_template("system.html",
                               state=state,
                               config=config_summary,
                               username=session.get("username"),
                               role=session.get("role"))
    return render_template("error.html", message="System not initialized")

# API Routes
@app.route("/api/system/status")
@login_required
def get_system_status():
    """API: Hämta systemstatus."""
    if system_state and machine_controller:
        return jsonify({
            "system_state": system_state.get_current_state(),
            "machine_status": machine_controller.get_status(),
            "orders_in_queue": order_processor.queue_manager.get_queue_length() if order_processor else 0,
            "timestamp": datetime.now().isoformat()
        })
    return jsonify({"error": "System not initialized"}), 500

@app.route("/app/temperatures")
@login_required
def get_temperatures():
    """API: Hämta aktuella temperaturer."""
    if temperature_manager:
        return jsonify({
            "fryer": temperature_manager.get_fryer_temperature(),
            "grill": temperature_manager.get_grill_temperature(),
            "freezer": temperature_manager.get_freezer_temperature(),
            "ambient": temperature_manager.get_ambient_temperature()
        })
    
    return jsonify({"error": "Temperature manager not initialized"}), 500

@app.route("/api/orders", methods=["GET", "POST"])
@login_required
@role_required("operator")
def handle_orders():
    """API: Hantera ordrar."""
    if request.method == "POST":
        try:
            order_data = request.json
            if not order_data:
                return jsonify({"error": "No order data provided"}), 400
            
            # Validera orderdata
            required_fields = ["burger_type", "quantity"]
            for field in required_fields:
                if field not in order_data:
                    return jsonify({"error": f"Missing required field: {field}"}), 400
                
            # Lägg till order
            order_id = order_processor.add_order(order_data)

            logger.info(f"New order added: {order_id}")
            return jsonify({
                "success": True,
                "order_id": order_id,
                "message": f"Order {order_id} added to queue"
            })
        except Exception as e:
            logger.error(f"Error adding order: {e}")
            return jsonify({"error": str(e)}), 500
        
    else: # GET
        try:
            limit = request.args.get("limit", 20, type=int)
            status = request.args.get("status", None)

            orders = order_processor.get_recent_orders(limit=limit, status=status)
            return jsonify({"orders": orders})
        
        except Exception as e:
            logger.error(f"Error fetching orders: {e}")
            return jsonify({"error": str(e)}), 500
        
@app.route("/api/orders/<order_id>", methods=["GET", "DELETE"])
@login_required
@role_required("operator")
def handle_single_order(order_id):
    """API: Hämta enskild order."""
    if request.method == "GET":
        try:
            order = order_processor.get_order(order_id)
            if order:
                return jsonify(order)
            return jsonify({"error": "Order not found"}), 404
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        
    elif request.method == "DELETE":
        try:
            success = order_processor.cancel_order(order_id)
            if success:
                return jsonify({"success": True, "message": f"Order {order_id} canceled"})
            return jsonify({"error": "Order not found or cannot be cancelled"}), 404
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        
@app.route("/api/inventory")
@load_config
def get_inventory():
    """API: Hämta inventeringsstatus."""
    try:
        if order_processor and hasattr(order_processor, "invnetory_tracker"):
            inventory = order_processor.inventory_tracker.get_inventory_status()
            return jsonify(inventory)
        return jsonify({"error": "Invnetory tracker not available"}), 500
    except Exception as e:
        logger.error(f"Error fetching inventory: {e}")
        return jsonify({"error": str(e)}), 500
    

@app.route("/api/system/control", method=["POST"])
@login_required
@role_required("admin")
def system_control():
    """API: Sytemkontroll (start/stopp)"""
    try:
        command = request.json.get("command")

        if not command:
            return jsonify({"error": "No command provided"}), 400

        if command == "start":
            success = machine_controller.start_system()
            message = "System startad" if success else "Failed to stop system"

        elif command == "stop":
            success = machine_controller.stop_system()
            message = "System stopped" if success else "Failed to stop system"

        elif command == "emergency_stop":
            success = machine_controller.emergency_stop()
            message = "Emergency stop activated" if success else "Failed emergency stop"

        elif command == "reset":
            success = machine_controller.reset_system()
            message = "System reset" if success else "Failed reset system"

        else:
            return jsonify({"error": f"Unknown command: {command}"}), 400

        logger.info(f"System control command executed: {command} - {message}")
        return jsonify({"success": success, "message": message})

    except Exception as e:
        logger.error(f"Error in system control: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/temperature/control", method=["POST"])
@login_required
@role_required("operator")
def temperature_control():
    """API: Temperaturkontroll."""
    try:
        zone = request.json.get("temperature")
        temperature = request.json.get("temperature")

        if not zone or temperature is None:
            return jsonify({"error": "Zone and temperatured"}), 400

        # Validera temperatur
        try:
            temperature = float(temperature)
        except ValueError:
            return jsonify({"error": "INvalid temperature value"}), 400

        # Sätt temperatur baserat på zon
        success = False
        if zone == "fryer" and hasattr(temperature_manager, "set_fryer_temperature"):
            success = temperature_manager.set_fryer_temperature(temperature)
        elif zone == "grill" and hasattr(temperature_manager, "set_grill_temperature"):
            success = temperature_manager.set_grill_temperature(temperature)
        elif zone == "freezer" and hasattr(temperature_manager, "set_freezer_temperature"):
            success = temperature_manager.set_freezer_temperature(temperature)
        else:
            return jsonify({"error": f"Unknown zone: {zone}"}), 400
        
        if success:
            logger.info(f"Temperature set: {zone} = {temperature}°C")
            return jsonify({"success": True, "message": f"{zone} temperature set to {temperature}°C"})
        else:
            return jsonify({"error": f"Failed to set temperature for {zone}"}), 500

    except Exception as e:
        logger.error(f"Error in temperature control: {e}")
        return jsonify({"error": str(e)}), 500
    
# Error handlers
@app.errorhandler(404)
def not_found(error):
    """Hantera 404-fel."""
    return render_template("error.html",
                           message="Page not found",
                           username=session.get("username"),
                           role=session.get("role")), 404

@app.errorhandler(500)
def internal_error(error):
    """Hantera 500-fel."""
    logger.error(f"Internal server error: {error}")
    return render_template("error.html",
                           message="Internal sever error",
                           username=session.get("username"),
                           role=session.get("role")), 500

# SocketIO event
@socketio.on("connect")
def handle_connect():
    """Hantera klientanslutning."""
    logger.info(f"Client connected: {request.sid}")
    emit("connected", {"message": "Connected to Hamburger Machine WebSocket"})

@socketio.on("disconnect")
def handle_disconnect():
    """Hantera klient frånkoppling."""
    logger.info(f"Client disconnected: {request.sid}")

@socketio.on("request_status")
def handle_status_request():
    """Hantera statusförfrågningan från klient."""
    if system_state:
        emit("status_response", {
            "system_state": system_state.get_current_state(),
            "timestamp": datetime.now().isoformat()
        })

# Main
if __name__ == "__main__":
    try:
        # Initiera systemet
        initialize_system()

        # Hämta webbinställningar
        web_config = config.get("web_ui", {})
        host = web_config.get("host", "0.0.0.0")
        port = web_config.get("port", 5000)
        debug = web_config.get("debug", False)

        logger.info(f"Starting web interface on {host}:{port}")
        logger.info(f"Debug mode: {debug}")

        # Starta Flask-app med SocketIO
        socketio.run(app, host=host, port=port, debug=debug, allow_unsafe_werkzeug=True)

    except Exception as e:
        logger.error(f"Failed to start web interface: {e}")
        sys.exit(1)
