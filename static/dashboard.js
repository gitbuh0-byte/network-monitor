const summaryEls = {
  monitoredConnections: document.querySelector("#monitoredConnections"),
  avgUptime: document.querySelector("#avgUptime"),
  avgLatency: document.querySelector("#avgLatency"),
  avgPacketLoss: document.querySelector("#avgPacketLoss"),
  openIncidents: document.querySelector("#openIncidents"),
  activeTickets: document.querySelector("#activeTickets"),
};

const connectionsTable = document.querySelector("#connectionsTable");
const incidentList = document.querySelector("#incidentList");
const lastUpdated = document.querySelector("#lastUpdated");

let qualityChart;
let bandwidthChart;

async function getJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Request failed: ${url}`);
  }
  return response.json();
}

function formatNumber(value, suffix = "") {
  if (value === null || value === undefined) return "--";
  return `${value}${suffix}`;
}

function updateSummary(summary) {
  summaryEls.monitoredConnections.textContent = formatNumber(summary.monitored_connections);
  summaryEls.avgUptime.textContent = formatNumber(summary.avg_uptime, "%");
  summaryEls.avgLatency.textContent = formatNumber(summary.avg_latency, " ms");
  summaryEls.avgPacketLoss.textContent = formatNumber(summary.avg_packet_loss, "%");
  summaryEls.openIncidents.textContent = formatNumber(summary.open_incidents);
  summaryEls.activeTickets.textContent = formatNumber(summary.active_tickets);
}

function updateConnections(rows) {
  connectionsTable.innerHTML = rows.map((row) => `
    <tr>
      <td>${row.customer_name}</td>
      <td>${row.region}</td>
      <td>${row.service_tier}</td>
      <td>${row.uptime_percent ?? "--"}%</td>
      <td>${row.latency_ms ?? "--"} ms</td>
      <td>${row.packet_loss_percent ?? "--"}%</td>
      <td>${row.utilization_percent ?? "--"}%</td>
      <td><span class="health ${row.health}">${row.health}</span></td>
    </tr>
  `).join("");
}

function updateIncidents(rows) {
  if (!rows.length) {
    incidentList.innerHTML = '<div class="incident"><strong>No active incidents</strong><p>All monitored services are inside operational thresholds.</p><small>NOC clear</small></div>';
    return;
  }

  incidentList.innerHTML = rows.map((row) => `
    <article class="incident ${row.severity}">
      <strong>${row.priority || "P3"} ${row.category} - ${row.customer_name}</strong>
      <p>${row.message}</p>
      <small>${row.region} / ${row.assigned_team || "Monitoring"} / ETA ${row.response_eta_minutes || "--"} min</small>
    </article>
  `).join("");
}

function makeQualityChart(trends) {
  const ctx = document.querySelector("#qualityChart");
  qualityChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: trends.map((row) => row.recorded_at.slice(11, 19)),
      datasets: [
        {
          label: "Latency ms",
          data: trends.map((row) => row.latency_ms),
          borderColor: "#0f8f88",
          backgroundColor: "rgba(15, 143, 136, 0.12)",
          tension: 0.35,
          yAxisID: "latency",
        },
        {
          label: "Packet loss %",
          data: trends.map((row) => row.packet_loss_percent),
          borderColor: "#c8831c",
          backgroundColor: "rgba(200, 131, 28, 0.12)",
          tension: 0.35,
          yAxisID: "loss",
        },
      ],
    },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { labels: { usePointStyle: true } } },
      scales: {
        latency: { type: "linear", position: "left", beginAtZero: true },
        loss: { type: "linear", position: "right", beginAtZero: true, grid: { drawOnChartArea: false } },
      },
    },
  });
}

function makeBandwidthChart(trends) {
  const ctx = document.querySelector("#bandwidthChart");
  bandwidthChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: trends.map((row) => row.recorded_at.slice(11, 19)),
      datasets: [
        {
          label: "Utilization %",
          data: trends.map((row) => row.bandwidth_utilization),
          backgroundColor: "#183349",
          borderRadius: 4,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true, suggestedMax: 100 } },
    },
  });
}

function updateCharts(trends) {
  const labels = trends.map((row) => row.recorded_at.slice(11, 19));
  if (!qualityChart || !bandwidthChart) {
    makeQualityChart(trends);
    makeBandwidthChart(trends);
    return;
  }

  qualityChart.data.labels = labels;
  qualityChart.data.datasets[0].data = trends.map((row) => row.latency_ms);
  qualityChart.data.datasets[1].data = trends.map((row) => row.packet_loss_percent);
  qualityChart.update();

  bandwidthChart.data.labels = labels;
  bandwidthChart.data.datasets[0].data = trends.map((row) => row.bandwidth_utilization);
  bandwidthChart.update();
}

async function refreshDashboard() {
  const [summary, connections, incidents, trends] = await Promise.all([
    getJson("/api/summary"),
    getJson("/api/connections"),
    getJson("/api/incidents"),
    getJson("/api/trends"),
  ]);

  updateSummary(summary);
  updateConnections(connections);
  updateIncidents(incidents);
  updateCharts(trends);
  lastUpdated.textContent = new Date().toLocaleTimeString();
}

refreshDashboard().catch(console.error);
setInterval(() => refreshDashboard().catch(console.error), 5000);
