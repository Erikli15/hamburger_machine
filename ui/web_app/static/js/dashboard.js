//ui/web_app/static/js/dashboard.js
// Real-time Dashboard för Hamburger Machine¨

document.addEventListener("DOMContentLoaded", function () {
  // Global state
  const state = {
    temperatureData: {},
    orderQueue: [],
    inventoryLevels: {},
    systemStatus: "initializing",
    lastUpdate: null,
  };

  // Configuration
  const config = {
    apiEndpoint: "/api",
    refreshInterval: 3000, // 3 seconds¨
    maxTemperatureHistory: 20,
    alertSoundEnabled: true,
  };

  // DOM Elements
  const elements = {
    // Temperature displays
    fryerTemp: document.getElementById("fryer-temp"),
    grillTemp: document.getElementById("grill-temp"),
    freezerTemp: document.getElementById("freezer-temp"),

    // Status indicators
    systemStatus: document.getElementById("system-status"),
    roboticArmStatus: document.getElementById("robotic-arm-status"),
    conveyorStatus: document.getElementById("converor-status"),

    // Order queue
    orderQueueList: document.getElementById("order-queue-list"),
    pendingOrdersCount: document.getElementById("pending-orders-count"),

    // Inventory
    pattStock: document.getElementById("patty-stock"),
    bunStock: document.getElementById("bun-stock"),
    cheeseStock: document.getElementById("cheese-stock"),
    lettuceStock: document.getElementById("lettuce-stock"),

    // Buttons
    emergencyStopBtn: document.getElementById("emergency-stop-btn"),
    pauseSystemBtn: document.getElementById("pause-system-btn"),
    resumeSystemBtn: document.getElementById("resume-system-btn"),

    // Charts
    temperatureChart: null,
    orderChart: null,

    // Notifications
    notificationPanel: document.getElementById("notification-panel"),

    // Timestamps
    lastUpdateTime: document.getElementById("last-update-time"),
  };

  // Initialize application
  init();

  function init() {
    console.log("Dashboard initializing...");

    // Initialize WebSocket connection
    initWebSocket();

    // Initialize charts
    initCharts();

    // Load initial data
    fetchSystemData();

    // Set up auto-refresh
    setInterval(fetchSystemData, config.refreshInterval());

    // Set up event listeners
    setupEventListners();

    // Start notification system
    initNotifications();
  }

  function initWebSocket() {
    const portocol = window.location.protocol === "https:" ? "wss:" : "ws";
    const wsUrl = `${protocol}//${window.location.host}/ws/dashboard`;

    const socket = new WebSocket(wsUrl);

    socket.onopen = function () {
      console.log("WebSocket connection established");
      elements.systemStatus.textContent = "Connected";
      elements.systemStatus.className = "status-connected";
    };

    socket.onmessage = function (event) {
      const data = JSON.parse(event.data);
      handleWebSocketMessage(data);
    };

    socket.onclose = function () {
      console.log("WebSocket connection closed");
      elements.systemStatus.textContent = "Disconnected";
      elements.systemStatus.className = "status-disconnected";
      // Attempt to reconnect efter 5 seconds
      setTimeout(initWebSocket, 5000);
    };

    socket.onerror = function (error) {
      console.error("WebSocket error:", error);
    };
  }

  function handleWebSocketMessage(data) {
    switch (data.type) {
      case "temperature_update":
        updateTemperaturDisplay(data.data);
        updateTemperatureChart(data.data);
        break;
      case "order_update":
        updateOrderQueue(data.data);
        updateOrderChart();
        break;
      case "inventory_update":
        updateInvnetoryDisplay(data.data);
        break;
      case "system_alert":
        showAlert(data.alert);
        playAlertSound();
        break;
      case "status_update":
        updateSystemStatus(data.status);
        break;
    }
    // Update timestamp
    updateTimestamp();
  }

  function initCharts() {
    // Temperature Chart
    const tempCtx = document
      .getElementById("temperature-chart")
      .getContext("2d");
    elements.temperatureChart = new Chart(tempCtx, {
      type: "line",
      data: {
        labels: [],
        datasets: [
          {
            label: "Fryer",
            data: [],
            borderColor: "rgb(255, 90, 132)",
            backgroundColor: "rgba(255, 90, 132, 0.2)",
            tension: 0.4,
          },
          {
            label: "Grill",
            data: [],
            borderColor: "rgb(54, 162, 235)",
            backgroundColor: "rgba(54, 162, 235, 0.2)",
            tension: 0.4,
          },
          {
            label: "Freezer",
            data: [],
            borderColor: "rgb(75, 192, 192)",
            backgroundColor: "rgba(75, 192, 192, 0.2)",
          },
        ],
      },
      options: {
        responsive: true,
        plugins: {
          legend: {
            position: "top",
          },
          title: {
            display: true,
            text: "Temperature History",
          },
        },
        scales: {
          y: {
            beginAtZero: false,
            title: {
              display: true,
              text: "Temperature (°C)",
            },
          },
        },
      },
    });

    // Order Chart
    const orderCtx = document.getElementById("order-chart").getContext("2d");
    elements.orderChart = new Chart(orderCtx, {
      type: "bar",
      data: {
        labels: ["Pending", "Processing", "Completed", "Failed"],
        datasets: [
          {
            label: "Order Status",
            data: [0, 0, 0, 0],
            backgroundColor: [
              "rgba(255, 205, 86, 0.8)",
              "rgba(54, 162, 235, 0.8)",
              "rgba(75, 192, 192, 0.8)",
              "rgba(255, 99, 132, 0.8)",
            ],
            borderColor: [
              "rgb(255, 205, 86)",
              "rgb(54, 162, 235)",
              "rgb(75, 192, 192)",
              "rgb(255, 99, 132)",
            ],
            borderWith: 1,
          },
        ],
      },
      options: {
        responsive: true,
        plugins: {
          legend: {
            display: false,
          },
          title: {
            display: true,
            text: "Order Status Distribution",
          },
        },
        scales: {
          y: {
            beginAtZero: true,
            ticks: {
              stepSize: 1,
            },
          },
        },
      },
    });
  }

  async function fetchSystemData() {
    try {
      const [tempData, orderData, inventoryData, statusData] =
        await Promise.all([
          fetch(`${config.apiEndpoint}/temperature`).then((res) => res.json()),
          fetch(`${config.apiEndpoint}/orders/queue`).then((res) => res.json()),
          fetch(`${config.apiEndpoint}/inventory`).then((res) => res.json()),
          fetch(`${config.apiEndpoint}/system/status`).then((res) =>
            res.json(),
          ),
        ]);

      updateTemperaturDisplay(tempData);
      updateOrderQueue(orderData);
      updateInvnetoryDisplay(inventoryData);
      updateSystemStatus(statusData);
      updateTimestamp();
    } catch (error) {
      console.error("Error fetching system data", error);
      showAlert({
        type: "error",
        message: "Failed to fetch system data",
        timestamp: new Date().toISOString(),
      });
    }
  }

  function updateTemperaturDisplay(data) {
    state.temperatureData = data;

    // Update individual displays
    if (data.fryer) {
      elements.fryerTemp.textContent = `${data.fryer.current}°C`;
      elements.fryerTemp.className = getTemperatureClass(
        data.fryer.current,
        data.fryer.target,
      );
    }

    if (data.grill) {
      elements.grillTemp.textContent = `${data.grill.current}°C`;
      elements.grillTemp.className = getTemperatureClass(
        data.grill.current,
        data.grill.target,
      );
    }

    if (data.freezer) {
      elements.freezerTemp.textContent = `${data.freezer.current}°C`;
      elements.freezerTemp.className = getTemperatureClass(
        data.freezer.current,
        data.freezer.target,
      );
    }

    // Update chart
    updateTemperatureChart(data);
  }

  function updateTemperatureChart(data) {
    const chart = elements.temperatureChart;
    if (!chart) return;

    // Add new data points
    const now = new Date().toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });

    chart.data.labels.push(now);
    if (chart.data.labels.length > config.maxTemperatureHistory) {
      chart.data.labels.shift();
    }

    if (data.fryer) {
      chart.data.datasets[0].data.push(data.fryer.current);
      if (chart.data.datasets[0].data.length > config.maxTemperatureHistory) {
        chart.data.datasets[0].data.shift();
      }
    }

    if (data.grill) {
      chart.data.datasets[1].data.push(data.grill.current);
      if (chart.data.datasets[1].data.length > config.maxTemperatureHistory) {
        chart.data.datasets[1].data.shift();
      }
    }

    if (data.freezer) {
      chart.data.datasets[2].data.push(data.freezer.current);
      if (chart.datasets[2].data.length > config.maxTemperatureHistory) {
        chart.data.datasets[2].data.shift();
      }
    }

    chart.update("none");
  }

  function updateOrderQueue(orders) {
    state.orderQueue = orders;

    // Update count
    const pendingCount = orders.filter(
      (order) => order.status === "pending",
    ).length;
    elements.pendingOrdersCount.textContent = pendingCount;

    // Update list
    elements.orderQueueList.innerHTML = pendingCount;

    orders.slice(0, 10).forEach((order) => {
      const orderItem = document.createElement("div");
      orderItem.className = `order-item status ${order.status}`;

      const orderTime = new Date(order.timestamp).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      });

      orderItem.innerHTML = `
            <div class="order-id">#${order.id}</div>
            <div class="order-type">${order.type}</div>
            <div class="order-status">${order.status}</div>
            <div class="order-time">${orderTime}</div>
            ${order.status === "processing" ? `<div class="order-progress"><div class="progress-bar" style="width: ${order.progress || 0}%"></div></div>` : ""}`;

      elements.orderQueueList.appendChild(orderItem);
    });

    // Upsate chart
    updateOrderChart(orders);
  }

  function updateOrderChart(orders = state.orderQueue) {
    const statusCounts = {
      pending: 0,
      processing: 0,
      completed: 0,
      failed: 0,
    };

    orders.forEach((order) => {
      if (statusCounts.hasOwnProperty(order.status)) {
        statusCounts[order.status]++;
      }
    });

    elements.orderChart.data.datasets[0].data = [
      statusCounts.pending,
      statusCounts.processing,
      statusCounts.completed,
      statusCounts.failed,
    ];

    elements.orderChart.update();
  }

  function updateInvnetoryDisplay(inventory) {
    state.inventoryLevels = inventory;

    // Update stock inicators
    if (inventory.patties !== undefined) {
      elements.pattStock.textContent = `${inventory.patties} units`;
      elements.pattStock.className = getStockLevelClass(
        inventory.patties,
        inventory.patties_threshold || 20,
      );
    }

    if (inventory.buns !== undefined) {
      elements.bunStock.textContent = `${inventory.buns} units`;
      elements.bunStock.className = getStockLevelClass(
        inventory.buns,
        inventory.buns_threshold || 20,
      );
    }

    if (inventory.cheese !== undefined) {
      elements.cheeseStock.textContent = `${inventory.cheese} units`;
      elements.cheeseStock.className = getStockLevelClass(
        inventory.cheese,
        inventory.cheese_threshold || 20,
      );
    }

    if (inventory.lettuce !== undefined) {
      elements.lettuceStock.textContent = `${inventory.lettuce} units`;
      elements.lettuceStock.className = getStockLevelClass(
        inventory.lettuce,
        inventory.lettuce_threshold || 20,
      );
    }
  }

  function updateSystemStatus(status) {
    state.systemStatus = status;

    // Update main status
    elements.systemStatus.textContent = status.system_status;
    elements.systemStatus.className = `status-${status.system_status.toLowerCase()}`;

    // Update component statuses
    if (status.robotic_arm !== undefined) {
      elements.roboticArmStatus.textContent = status.robotic_arm;
      elements.roboticArmStatus.className = `component-status status-${status.robotic_arm.toLowerCase()}`;
    }
  }

  function updateTimestamp() {
    state.lastUpdate = new Date();
    elements.lastUpdateTime.textContent = state.lastUpdate.toLocaleTimeString(
      [],
      { hour: "2-digit", minute: "2-digit", second: "2-digit" },
    );
  }

  function setupEventListners() {
    // Emergency stop button
    elements.emergencyStopBtn.addEventListener("click", async function () {
      if (
        config(
          "Are you sure you want to berform an emergency stop? This will halt all operations.",
        )
      ) {
        try {
          const response = await fetch(
            `${config.apiEndpoint}/system/emergency-stop`,
            {
              method: "POST",
            },
          );

          if (response.ok) {
            showAlert({
              type: "warning",
              message: "Emergency stop activated",
              timestamp: new Date().toISOString(),
            });
          }
        } catch (error) {
          console.error("Error activating emergency stop", error);
        }
      }
    });

    // Pause system button
    elements.pauseSystemBtn.addEventListener("click", async function () {
      try {
        const response = await fetch(`${config.apiEndpoint}/system/pause`, {
          method: "POST",
        });

        if (response.ok) {
          showAlert({
            type: "info",
            message: "System paused",
            timestamp: new Date().toISOString(),
          });
        }
      } catch (error) {
        console.error("Error pausing system", error);
      }
    });

    // Resume system button
    elements.resumeSystemBtn.addEventListener("click", async function () {
      try {
        const response = await fetch(`${config.apiEndpoint}/system/resume`, {
          method: "POST",
        });

        if (response.ok) {
          showAlert({
            type: "info",
            message: "System resumed",
            timestamp: new Date().toISOString(),
          });
        }
      } catch (error) {
        console.error("Error resuming system:", error);
      }
    });

    // Manual refresh button
    document
      .getElementById("refrech-btn")
      ?.addEventListener("click", fetchSystemData);

    // Toggle temperature units
    document
      .getElementById("toggle-units-btn")
      ?.addEventListener("click", toggleTemperatureUnits);

    // Clear notifications
    document
      .getElementById("clear-notifications-btn")
      ?.addEventListener("click", clearNotifications);
  }

  function initNotifications() {
    // Clear old notifications load
    clearNotifications();

    // Subscribe to system alerts
    // This would typically be done via WebSocket
  }

  function showAlert(alert) {
    const alertElement = document.createElement("div");
    alertElement.className = `alert alert-${alert.type}`;

    const time = new Date(alert.timestamp).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });

    alertElement.innerHTML = `
        <div class="alert-header">
        <span class="alert-type">${alert.type.toUpperCase()}</span>
        <span class="alert-time">${time}</span>
        <button class="alert-close">&times;</button>
        </div>
        <div class="alert-message">${alert.message}</div>
        ${alert.details ? `<div class="alert-details">${alert.details}</div>` : ""}`;

    // Add close functionality
    alertElement
      .querySelector(".alert-close")
      .addEventListener("click", function () {
        alertElement.remove();
      });

    // Add to notification panel
    elements.notificationPanel.insertBefore(
      alertElement,
      elements.notificationPanel.firstChild,
    );

    // Auto-remove after 30 seconds for info alerts
    if (alert.type === "info") {
      setTimeout(() => {
        if (alertElement.parentNode) {
          alertElement.remove();
        }
      }, 30000);
    }
  }

  function playAlertSound() {
    if (config.alertSoundEnabled) {
      // Simple alert sound
      const audio = new Audio("/static/audio/alert.mp3");
      audio.volume = 0.3;
      audio.play().catch((e) => console.log("Audio play failed", e));
    }
  }

  function clearNotifications() {
    elements.notificationPanel.innerHTML = "";
  }

  function toggleTemperatureUnits() {
    // Toggle between Celsius and Fahremheit
    // This would require converting all temperature displays
    console.log("Toggle temperature units - functionality to be implemented");
  }

  function getTemperatureClass(current, target) {
    const diff = Math.abs(current - target);

    if (diff <= 5) {
      return "tempwrature-optimal";
    } else if (diff <= 15) {
      return "temperature-warning";
    } else {
      return "temperature-danger";
    }
  }

  function getStockLevelClass(current, thrshold) {
    if (current >= thrshold * 2) {
      return "stock-high";
    } else if (current >= thrshold) {
      return "stock-medium";
    } else if (current > 0) {
      return "stock-low";
    } else {
      return "stock-empty";
    }
  }

  // Export for debugging
  window.dashboard = {
    state,
    config,
    refresh: fetchSystemData,
    showAlert,
    clearNotifications,
  };
});

// Assitiomal utility functions
function formatTemperature(temp, unit = "C") {
  if (unit === "F") {
    return `${Math.round((temp * 9) / 5 + 32)}°F`;
  }
  return `${Math.round(temp)}°C`;
}

function formatTime(timestamp) {
  const date = new Date(timestamp);
  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

// Error handling fetch
async function safeFetch(url, options = {}) {
  try {
    const response = await fetch(url, options);
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    return await response.json();
  } catch (error) {
    console.error("Fetch error:", error);
    return null;
  }
}
