#!/user/bin/env python3
"""
Admin Panel för Hamburger Maskinen
Lokal gränssnitt för övervakning och kontroll av maskinen
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import queue
import json
from datetime import datetime
from pathlib import Path

# Simulerad imports för din verkliga struktur
# from core.controller import MachineController
# from core.stete_manager import SystemState
# from utils.logger import get_logger
# from hardware.temperature.sensor_manager import TemperatureManager

class AdminPanel:
    def __init__(self, root):
        """Initiera adminstatörspanel"""
        self.root = root
        self.root.title("Hamburger Maskin - Admin Panel")
        self.root.genometry("1200x800")
        self.root.configure(bg="#f0f0f0")

        # Sätt ikon (om tillgänglig)
        try:
            self.root.iconbitmap("ui/web_app/static/images/icon.ico")
        except:
            pass

        # Ställ in protocal för att hantera stängning
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Statusvaribler
        self.is_connected = False
        self.machine_status = "Offline"
        self.current_temperatures = {}
        self.pending_orders = []
        self.inventory_levels = {}

        # Kö för händelser från maskinen
        self.event_queue = queue.Queue()

        # Skapa huvudlayout
        self.setup_ui()

        # Starta händelsehanterare
        self.check_events()

        # Simulerad anslutning till maskinen
        self.connect_to_machine()

    def setup_ui(self):
        """Skapa användargränssnittet"""
        # Huvudram
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Konfigurera grid
        self.root.columnconfigure(0, weight=1)
        self.root.rowiconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(1, weight=1)

        # Statusbar
        self.create_status_bar(main_frame)

        # Huvudområde med notebook (flikar)
        self.create_notebook(main_frame)

        # Kontrollpanel till höger
        self.create_control_panel(main_frame)

    def create_status_bar(self, parent):
        """Skapa statuserad"""
        status_frame = ttk.Frame(parent)
        status_frame.grid(row=0, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))

        # Statusindikator
        self.status_indicator = tk.Canvas(status_frame, width=20, height=20, bg="red")
        self.status_inicator.grid(row=0, column=0, padx=(0, 10))

        # Statuslabel
        self.status_label = ttk.Label(
            status_frame,
            text="Status: Offline",
            font=("Arial", 12, "bold")
        )
        self.status_label.grid(row=0, column=0,padx=(0, 20))

        # Tid och datum
        self.time_label = ttk.Label(
            status_frame,
            text=self.get_current_time,
            font=("Arial", 10)
        )
        self.time_label.grid(row=0, column=2)

        # Uppdatera tiden varje sekund
        self.update_time()

    def create_notebook(self, parant):
        """Skapa flikar för olika funktioner"""
        self.notebook = ttk.Notebook(parant)
        self.notebook.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 10))

        # Flik 1: Översikt
        self.tab_owerview = ttk.Frame(self.notebook)
        self.create_overview_tab(self.tab_owerview)
        self.notebook.add(self.tab_owerview, text="Översikt")

        # Flik 2: Temperaturkontroll
        self.tab_temperature = ttk.Frame(self.notebook)
        self.create_overview_tab(self.tab_owerview)
        self.notebook.add(self.tab_temperature, text="Temperatur")

        # Flik 3: Orderhantering
        self.tab_orders = ttk.Frame(self.notebook)
        self.create_orders_tab(self.tab_orders)
        self.notebook.add(self.tab_orders, text="Order")

        # Flik 4: Inventering
        self.tab_inventory = ttk.Frame(self.notebook)
        self.create_inventory_tab(self.tab_inventory)
        self.notebook.add(self.tab_inventory, text="Inventering")

        # Flik 5: Loggar
        self.tab_logs = ttk.Frame(self.notebook)
        self.create_logs_tab(self.tab_settings)
        self.notebook.add(self.tab_logs, text="Loggar")

        # Flik 6: Inställningar
        self.tab_settings = ttk.Frame(self.notebook)
        self.create_settings_tab(self.tab_settings)
        self.notebook.add(self.tab_settings, text="Inställningar")

    def create_overview_tab(self, parent):
        """Skapa översiktsfilk"""
        # Vänster kolumn - Systemstatus
        status_frame = ttk.Labelfram(parent, text="Systemstatus", padding="10")
        status_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)

        # Statusinikatorer
        inicators = [
            ("Maskin", "Stopped", "red"),
            ("Fritös", "75°C", "orange"),
            ("Grill", "200°C", "green"),
            ("Frys", "-18°C", "blue"),
            ("Robotarm", "Klar", "green"),
            ("Transportband", "Pauset", "orange")
        ]

        for i, (label, value, color) in enumerate(inicators):
            lbl = ttk.Label(status_frame, text=f"{label}", font=("Arial", 10, "bold"))
            lbl.grid(row=i, column=0, sticky=tk.W, pady=2)

            val = tk.Label(
                status_frame,
                text=value,
                font=("Arial", 10),
                fg=color,
                bg="#f0f0f0"
            )
            val.grid(row=i, column=1, sticky=tk.W, padx=(10, 0), pady=2)
            setattr(self, f"status_{label.lower().replace(" ", " ")}", val)

            # Höger kolumn - Snabbstatistik
            stats_frame = ttk.LabelFrame(parent, text="Statistik idag", padding="10")
            stats_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)

            stats = [
                ("Tillverkade hamburgare:", "0"),
                ("Genomsnittlig tid:", "0:00"),
                ("Misslyckade order:", "0"),
                ("Aktiva order", "0")
            ]

            for i, (label, value) in enumerate(stats):
                ttk.Label(stats_frame, text=label).grid(row=i, column=0, sticky=tk.W, pady=2)
                lbl = ttk.Label(stats_frame, text=value, font=("Arial", 10, "bold"))
                lbl.grid(row=i, column=1, sticky=tk.W, padx=(10, 0), pady=2)
                setattr(self, f"stat_{label.split(":")[0].lower().replace(" ", "_")}", lbl)

            # Nödstopp knopp
            emergency_frame = ttk.Frame(parent)
            emergency_frame.grid(row=1, column=0, columnspan=2, pady=20)

            self.emergency_btn = tk.Button(
                emergency_frame,
                text="NÖDSTOPP",
                command=self.emergency_stop,
                bg="red",
                fg="white",
                font=("Arial", 16, "bold"),
                padx=30,
                pady=10
            )
            self.emergency_btn.pack()

        def create_temperature_tab(self, parant):
            """Skapa temperaturkontroll flik"""
            # Temperaturövervakning
            temp_frame = ttk.LabelFrame(parant, text="Temperaturövervakning", padding="15")
            temp_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

            # Temperaturzoner
            zones = [
                ("Fritös 1:", "75°C", 50, 200, 75),
                ("Fritös 2", "75°C", 50 , 200, 75),
                ("Grill 1", "200°C", 150, 300, 200),
                ("Grill 2", "200°C", 150, 300, 200),
                ("Frysfack", "-18°C", -25, -10, -18)
            ]

            for i, (name, current, min_temp, max_temp, target) in enumerate(zones):
                # Namn och värde
                frame = ttk.Frame(temp_frame)
                frame.pack(fill=tk.X, pady=5)

                ttk.Label(frame, text=name, width=15).pack(side=tk.LEFT)

                value_label = ttk.Label(frame, text=current, font=("Arial", 10, "bold"), width=10)
                value_label.pack(side=tk.LEFT, padx=(0, 20))
                setattr(self, f"temp_{name.lower().replace(" ", "_" ).replace(":", "")}", value_label)

                # Skala för manuell inställning
                scale = tk.Scale(
                    frame,
                    from_=min_temp,
                    to=max_temp,
                    orient=tk.HORIZONTAL,
                    length=200,
                    command=lambda v, n=name: self.update_temperature(n,v)
                )
                scale.set(target)
                scale.pack(side=tk.LEFT)

                # Target label
                ttk.Label(frame, text=f"Mål: {target}°C", width=10).pack(side=tk.LEFT, padx=10)

                # Temperaturgrafik (simulerad)
                graph_frame = ttk.LabelFrame(parent, text="Temperaturhistorik", padding="10")
                graph_frame.pack(fill=tk.BOTH, expand=True)

                # Rita simulerad graf
                self.draw_temperature_graph()

            def create_orders_tab(self, parent):
                """Skpa orderhanteringsflik"""
                # Orderlista
                list_frame = ttk.LabelFrame(parent, text="Aktiva Order", padding="10")
                list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

                # Trädy för order
                columns = ("ID", "Tid", "Typ", "Status", "Åtegärd")
                self.order_tree = ttk.Treeview(list_frame, columns=columns, show="headings",height=10)

                for col in columns:
                    self.order_tree.heading(col, text=col)
                    self.order_tree.column(col, width=100)

                self.order_tree.pack(fill=tk.BOTH, expand=True)

                # Scrollbar
                scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.order_tree.yview)
                scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
                self.order_tree.configure(yscrollcommand=scrollbar.set)

                # Kontrollknappar för order
                btn_frame = ttk.Frame(parant)
                btn_frame.pack(fill=tk.X, padx=10, pady=5)

                ttk.Button(btn_frame, text="Uppdatera", command=self.refresh_orders).pack(side=tk.LEFT, padx=5)
                ttk.Button(btn_frame, text="Pausa alla", command=self.pause_all_orders).pack(side=tk.LEFT, padx=5)
                ttk.Button(btn_frame, text="Återuppta alla", command=self.resume_all_orders).pack(side=tk.LEFT, padx=5)
                ttk.Button(btn_frame, text="Rensa slutförda", command=self.clear_completed_orders).pack(side=tk.LEFT, padx=5)

                # Manuell orderinmatning
                manual_frame = ttk.LabelFrame(parant, text="Manuell Order", padding=10)
                manual_frame.pack(fill=tk.X, padx=10, pady=10)

                ttk.Label(manual_frame, text="Typ:").grid(row=0, column=0, padx=5, pady=5)
                self.order_type = ttk.Combobox(manual_frame, values=["Cheesburger", "Hamburger", "Dubbel", "Vegetarisk"])
                self.order_type.grid(row=0, column=1, padx=5, pady=5)

                ttk.Label(manual_frame, text="Antal:").grid(row=0, column=2, padx=5, pady=5)
                self.order_quantity = ttk.Spinbox(manual_frame, from_=1, to=10, width=5)
                self.order_quantity.grid(row=0, column=3, padx=5, pady=5)

                ttk.Button(manual_frame, text="Lägg till", command=self.add_manual_order).grid(row=0, column=4, padx=10, pady=5)

    def creat_inventory_tab(self, parent):
        """Skapa inventeringsflik"""
        # Inventeringslista
        inv_frame = ttk.LabelFrame(parent, text="Inventeringsnivåer", padding="10")
        inv_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Skapa trädvy
        columns = ("Ingrediens", "Nuvarande", "Minimum", "Maximum", "Status")
        self.inv_tree = ttk.Treeview(inv_frame, columns=columns, show="headings", height=15)

        for col in columns:
            self.inv_tree.heading(col, text=col)
            self.inv_tree.column(col, width=120)

        self.inv_tree.pack(fill=tk.BOTH, expand=True)

        # Fyll med exempeldata
        self.populate_inventory()

        # Kontrollknappar
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Button(btn_frame, text="Uppdatera", command=self.refresh_inventory).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Lägg till", command=self.add_inventory).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Återställ varningar", command=self.reset_inventory_alerts).pack(side=tk.X, padx=5)

        # Nivåindikatorer
        level_frame = ttk.LabelFrame(parent, text="Snabböversikt", padding="10")
        level_frame.pack(fill=tk.X, padx=10, pady=10)

        # Skapa progress bars för viktiga ingredienser
        importan_items = ["Nötkött", "Ost", "Bröd", "Sallad", "Tomat"]
        for i, item in enumerate(importan_items):
            ttk.Label(level_frame, text=item).grid(row=i, column=0, sticky=tk.W, padx=5, pady=2)
            pb = ttk.Progressbar(level_frame, length=200, mode="determinate")
            pb.grid(row=i, column=1, padx=5, pady=2)
            pb["value"] = 75 # Exempelvärde
            setattr(self, f"pb_{item.lower()}", pb)

    def create_logs_tab(self, parent):
        """Skapa loggvisningsflik"""
        # Loggatextruta
        log_frame = ttk.LabelFrame(parent, text="Systemloggar", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            wrap=tk.WORD,
            width=80,
            height=20,
            font=("Consolas", 9)
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Ladda exempelloggar
        self.load_logs()


        # Loggkontroller
        control_frame = ttk.Frame(parent)
        control_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Button(control_frame, text="Uppdatera", command=self.refresh_logs).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Rensa", command=self.clear_logs).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Spara som...", command=self.save_logs).pack(side=tk.LEFT, padx=5)

        # Loggnivåfilter
        ttk.Label(control_frame, text="Filter:").pack(side=tk.LEFT, padx=(20, 5))
        self.log_level = ttk.Combobox(
            control_frame,
            values=["Alla", "INFO", "WARNING", "ERROR", "CRITICAL"],
            width=10,
            state="readonly"
        )
        self.log_level.set("Alla")
        self.log_level.pack(side=tk.LEFT, padx=5)
        self.log_level.bind("<<ComboboxSelected>>", self.filter_logs)

    def create_settings_tab(self, parent):
        """Skapa inställningsflik"""
        # Systeminställningar
        settings_frame = ttk.LabelFrame(parent, text="Systeminställningar", padding="15")
        settings_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        settings = [
            ("Automatisk start:", tk.BooleanVar(value=True)),
            ("Larmsystem:", tk.BooleanVar(value=True)),
            ("Auto-beställning:", tk.BooleanVar(value=False)),
            ("Underhållsläge:", tk.BooleanVar(value=False)),
            ("Demonstrationsläge", tk.BooleanVar(value=False))
        ]

        for i, (label, var) in enumerate(settings):
            cb = ttk.Checkbutton(settings_frame, text=label, variable=var)
            cb.grid(row=i, column=0, sticky=tk.W, pady=5)
            setattr(self, f"setting_{label.lower().replace(" ", "_").replace(":",""), var}")

        # Temperaturinställningar
        temp_frame = ttk.LabelFrame(parent, text="Temperaturinställningar", padding="15")
        temp_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        temp_settings = [
            ("Standard grilltemp:", 200, "°C"),
            ("Standard fritöstemp:", 175, "°C"),
            ("Frystemp:", -18, "°C"),
            ("Övertemp varning:", 10, "°C över")
        ]

        for i, (label, default, unit) in enumerate(temp_settings):
            ttk.Label(temp_frame, text=label).grid(row=i, column=0, sticky=tk.W, pady=5)

            spinbox = ttk.Spinbox(
                temp_frame,
                from_=50 if "Frys" in label else 0,
                to=300,
                width=10
            )
            spinbox.set(default)
            spinbox.grid(row=i, column=1, padx=10, pady=5)

            ttk.Label(temp_frame, text=unit).grid(row=i, column=2, sticky=tk.W, pady=5)
            setattr(self, f"temp_setting_{label.lower().split()[0]}", spinbox)

        # Spara/Återställ knappar
        btn_fram = ttk.Frame(parent)
        btn_fram.pack(fill=tk.X, padx=10, pady=20)

        ttk.Button(btn_fram, text="Spara inställningar", command=self.save_settings).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_fram, text="Återställ standard", command=self.reset_settings).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_fram, text="Ladda från fil", command=self.load_settings).pack(side=tk.LEFT, padx=5)

    def create_control_panel(self, parent):
        """Skapa högerkontrollpanel"""
        control_farm = ttk.LabelFrame(parent, text="Snabbkontroller", padding="10")
        control_farm.grid(row=1, column=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 10))

        # Styrknappar
        buttons = [
            ("Starta Maskin", self.start_machine, "green"),
            ("Stoppa Maskin", self.stop_machine, "Red"),
            ("Pausa", self.pause_machine, "orange"),
            ("Testkör", self.test_run, "blue"),
            ("Rengör", self.clean_machine, "lightblue"),
            ("Kalibrera", self.calibrate_sensors, "purple")
        ]

        for i, (text, command, color) in enumerate(buttons):
            btn = tk.Button(
                control_farm,
                text=text,
                command=command,
                bg=color,
                fg="white" if color != "lightblue" else "black",
                font=("Arial", 10, "bold"),
                width=15,
                height=2
            )
            btn.pack(pady=5, fill=tk.X)

        # Snabbstatus
        status_fram = ttk.LabelFrame(parent, text="Aktivitet", padding="10")
        status_fram.grid(row=2, column=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 10), pady=(10, 0))

        self.activity_text = scrolledtext.ScrolledText(
            status_fram,
            wrap=tk.WORD,
            width=30,
            hight=10,
            font=("Consolas", 8)
        )
        self.activity_text.pack(fill=tk.BOTH, expand=True)

        # Skriv startmeddelande
        self.log_activity("Admin panel startad")
        self.log_activity("Väntar på anslutning...")

    # ===== HUVUDFUNKTIONER =====

    def connect_to_machine(self):
        """Anslut till maskinens kontrollsystem"""
        self.log_activity("Ansluter till maskin...")

        # Simulerad anslutning (ersätt med riktig logik)
        threading.Timer(2.0, self.on_connected).start()

    def on_connected(self):
        """När anslutning är upprättad"""
        self.is_connected = True
        self.machine_status = "Online"

        # Uppdatera UI
        self.status_indicator.configure(bg="green")
        self.status_label.configure(text="Status: Online")

        # Logga 
        self.log_activity("Ansluten till maskin")
        self.log_activity("System: Klar")

        # Uppdatera status
        self.update_machine_status()

    def update_machine_status(self):
        """Uppdatera maskinstatus (simulerad)"""
        if not self.is_connected:
            return
        
        # Simulerad datauppdatering
        self.status_fritös.configure(text=f"{75 + (id("fritös") % 10)}°C")
        self.status_grill.configure(text=f"{200 + (id("grill") % 20)}°C")

        # Schemalägg nästa uppdatering
        self.root.after(5000, self.update_machine_status)

    def emergency_stop(self):
        """Nödstopp för maskinen"""
        if messagebox.askyesno("NÖDSTOPP", "Är du säker på att du vill aktivera nödstopp?\nAlla processer kommer att avbrytas omedelbart."):
            self.log_activity("NÖDSTOPP AKTIVERAT", "ERROR")
            self.machine_status = "NÖDSTOPP"
            self.status_indicator.configure(bg="röd", flash=True)

            # Uppdatera alla statuslabels
            self.status_label.configure(text="Status: NÖDSTOPP - ÅTERSTÄLL MANUELLT")
            self.status_maskin.configure(text="NÖDSTOPP", fg="red")

            # Disable alla kontroller
            for child in self.root.winfo_children():
                if isinstance(child, tk.Button) and child["text"] != "NÖDSTOPP":
                    child.configure(state="disabled")

    def start_machine(self):
        """Starta maskinen"""
        self.log_activity("Startar maskin...")
        self.machine_status = "Kör"
        self.status_maskin.configure(text="Kör", fg="green")
        messagebox.showinfo("Startad", "Maskinen har startats")

    def stop_machine(self):
        """Pausa maskinen"""
        self.log_activity("Pausar maskin...")
        self.machine_status = "Paused"
        self.status_maskin.configure(text="Paused", fg="orange")

    def test_run(self):
        """Kör testsekvens"""
        self.log_activity("Startar testkörning...")

        # Simulaterad testsekvens
        steps = [
            "Testar sensorer...",
            "Testar robortarm...",
            "Testar temperaturkontroller...",
            "Testar dispensers...",
            "Testkörning slutförd"
        ]

        for step in steps:
            self.log_activity(step)
            self.root.update()
            self.root.after(1000)

    def clean_machine(self):
        """Starta rengöringssekvens"""
        if messagebox.askyesno("Rengöring", "Starta automatisk rengöring?\nMaskinen kommer att stängas av under av under processen"):
            self.log_activity("Startar rengöring...")
            self.machine_status = " Rengör"
            self.status_maskin.configure(text="Rengör", fg="blue")

    def calibrate_sensors(self):
        """Kalibrera alla sensorer"""
        self.log_activity("Kalibrerar sensorer...")
        messagebox.showinfo("Kalibrering", "Kalibrering påbörjad. Detta kan ta några minuter.")

    def update_temperature(self, zone, value):
        """Uppdatera temperatör för zon"""
        label_name = f"temp_{zone.lower().replace(" ", "_").replace(":", "")}"
        if hasattr(self, label_name):
            getattr(self, label_name).configure(text=f"Uppdatera {zone} till {value}°C")
            self.log_activity(f"Uppdaterar {zone} till {value}°C")

    def add_manual_order(self):
        """Lägg till manuell order"""
        order_type = self.order_type.get()
        quantity = self.order_quantity.get()

        if order_type and quantity:
            order_id = f"MAN{datetime.now().strftime("%H%M%S")}"
            self.order_tree.insert(
                "", "end",
                values=(order_id, datetime.now().strftime("%H:%M"), order_type, quantity, "Väntar")
            )
            self.log_activity(f"Manuell order tillagd: {quantity}x {order_type}")
            messagebox.showinfo("Order tillagd", f"Order {order_id} har lagts till i kö")
        else:
            messagebox.showwarning("Ogiltig order", "Vänligen fyll i både typ och antal")

    def refresh_orders(self):
        """Uppdatera orderlista"""
        self.log_activity("Uppdaterar orderlista...")
        # I riktig implementation: hämta från databas/API

    def populate_inventory(self):
        """Fyll inventeringslista med data"""
        inventory_data = [
            ("Nötkött", "85%", "20%", "100%", "OK"),
            ("Ost", "45%", "30%", "100%", "LOG"),
            ("Bröd", "90%", "25%", "100%", "OK"),
            ("Sallad", "30%", "40%", "100%", "MYCKET LÅG"),
            ("Tomat", "60%", "35%", "100%", "OK"),
            ("Lök", "75%", "30%", "100%", "OK"),
            ("Bacon", "50%", "25%", "100%", "LÅG"),
            ("Såser", "80%", "20%", "100%", "OK"),
            ("Pommes", "95%", "15%", "100%", "OK"),
            ("Drickor", "65%", "10%", "100%", "OK")
        ]

        for item in inventory_data:
            self.inv_tree.insert("", "end", values=item)

    def refresh_inventory(self):
        """Uppdatera inventeringslista"""
        self.log_activity("Uppdaterar inventering...")

    def add_invnetory(self):
        """Lägg till inventeringspost"""
        messagebox.showinfo("Lägg till", "Öppna inventeringsfacket och lägg till ingredienser manuellt.")

    def reset_inventory_alerts(self):
        """Äterställ inventeringsvarningar"""
        self.log_activity("Återställer inventeringsvarningar...")

    def load_logs(self):
        """Ladda loggar från fil"""
        # Simulerade loggar
        sample_logs = [
            "2024-01-15 08:30:15 INFO: System startad",
            "2024-01-15 08:31:22 INFO: Temperatursensor initialiserade",
            "2024-01-15 08:32:45 WARNING: Fritös 1 temperatur avvikelse +5°C",
            "2024-01-15 08:35:10 INFO: Order #00123 mottagen",
            "2024-01-15 08:36:30 INFO: Order #00123 tillverkad",
            "2024-01-15 09:15:00 ERROR: Dispenser 3 stoppad - kontaktad underhåll",
            "2024-01-15 10:20:15 INFO: Underhållsarbete slutfört"
        ]

        for log in sample_logs:
            self.log_text.insert(tk.END, log + "\n")

    def refresh_logs(self):
        """Uppdatera loggvisning"""
        self.log_activity("Uppdaterar loggar...")

    def clear_logs(self):
        """Rensa loggvisning"""
        self.log_text.delete(1.0, tk.END)
        self.log_activity("Loggar rensade")

    def save_logs(self):
        """Spara loggar till fil"""
        # I riktig implementation: spara till fil
        messagebox.showinfo("Spara", "Loggar sparad till logs/system_admin.log")

    def filter_logs(self, event=None):
        """Filtrera loggar baserat på nivå"""
        level = self.log_level.get()
        self.log_activity(f"Filtrerar loggar: {level}")

    def save_settings(self):
        """Spara systeminställningar"""
        self.log_activity("Inställningar sparade")
        messagebox.showinfo("Sparad", "Inställningar har sparats")

    def reser_settings(self):
        """Återställ till standardinställningar"""
        if messagebox.askyesno("Återställ", "Återställa alla inställningar till standard?"):
            self.lot_activity("Inställningar återställada")

    def load_settings(self):
        """Ladda inställningar från fil"""
        self.log_activity("Inställningar laddade från fil")

    def draw_temperature_graph(self):
        """Rita similerad temperaturgraf"""
        canvas = self.temp_canvas
        canvas.delete("all")

        width = canvas.winfo_width() or 400
        height = canvas.winfo_height() or 150

        # Rita axlar
        canvas.create_line(30, 20, 30, height-30, fill="black", width=2)
        canvas.create_line(30, height-30, width-30, height-30, fill="black", width=2)

        # Rita simulerad temperaturkurva
        points = []
        for i in range(0, width-60, 10):
            x = 30 + i
            y = height - 30 - (50 + 30 * (i / 100 % 1))
            points.append((x, y))

        if len(points) > 1:
            canvas.create_line(points, fill="red", width=2, smooth=True)

    def log_activity(self, message, level="INFO"):
        """Logga aktivitet till aktivitetsfönstret"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {level}: {message}\n"

        self.log_activity_text.insert(tk.END, log_entry)
        self.activity_text.see(tk.END)

        # Färgkodning baserat på nivå
        if level == "ERROR":
            self.activity_text.tag_add("error", "end-2l", "end-1l")
            self.activity_text.tag_config("error", foreground="red")
        elif level == "WARNING":
            self.activity_text.tag_add("warning", "end-2l", "end-1l")
            self.activity_text.tag_config("warning", foreground="orange")

    def update_time(self):
        """Uppdatera tiden i statusbaren"""
        self.time_label.configure(text=self.get_current_time())
        self.root.after(1000, self.update_time)

    def get_current_time(self):
        """Hämta aktuell tid och datum"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def check_events(self):
        """Kolla efter händelser från maskinen"""
        try:
            while True:
                event = self.event_queue.get_nowait()
                self.handle_event(event)
        except queue.Empty:
            pass

        # Schemalägg nästa kontroll
        self.root.after(100, self.check_events)

    def handle_event(self, event):
        """Hantera inkommande händelse"""
        # I riktig implementation: hantera olika händelsetyper
        self.log_activity(f"Händelse: {event}")

    def on_closing(self):
        """Hantera fönsterstängning"""
        if messagebox.askokcancel("Avsluta", "Vill du verkligen avsluta administratörspanelen?"):
            self.log_activity("Admin panel stängs")
            self.root.destroy()

def main():
    """Huvudfunktion för att starta admin panel"""
    root = tk.Tk()

    # Styling
    style = ttk.Style()
    style.theme_use("clam")

    app = AdminPanel(root)

    # Centrera fönster
    root.update_idletasks()
    width = root.winfo_width()
    height = root.winfo_height()
    x = (root.winfo_screenmmwidth() // 2) - (width // 2)
    y = (root.winfo_screenmmheight() // 2) - (height // 2)
    root.geometry(f"{width}x{height}+{x}+{y}")

    root.mainloop()

if __name__ == "__main__":
    main() 
 







