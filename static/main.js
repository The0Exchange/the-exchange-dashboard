// ─── CONFIG/STATE ─────────────────────────────────────────────────────────────
const MAX_HISTORY = 300;           // max points stored in localStorage per drink
let currentIndex = 0;              // which drink to show in chart this cycle
let drinks = [];                   // list of drink names (keys)
let previousPrices = {};           // { "Bud Light": 4.12, … } from last fetch

// Utility to get "HH:MM" in Eastern Time (for labeling)
function getTimeLabel() {
  const now = new Date();
  return now.toLocaleTimeString("en-US", { hour: '2-digit', minute: '2-digit' });
}

// Fetch live prices from our Flask /prices endpoint
async function fetchPrices() {
  try {
    const res = await fetch("/prices");
    if (!res.ok) throw new Error("Network error");
    return await res.json();
  } catch (err) {
    console.error("Failed to fetch /prices:", err);
    return {}; // return empty to avoid crashes
  }
}

// ─── TICKER ────────────────────────────────────────────────────────────────────
// Rebuilds the <ul id="ticker"> every update. We duplicate the list to allow CSS
// keyframes to scroll it continuously.
function updateTicker(prices) {
  const ticker = document.getElementById("ticker");
  if (!ticker) return;

  // Build one iteration of <li> items
  const baseItems = Object.entries(prices).map(([name, price]) => {
    // Determine arrow direction/color based on previousPrices
    let direction = "flat";
    if (previousPrices[name] !== undefined) {
      if (price > previousPrices[name]) direction = "up";
      else if (price < previousPrices[name]) direction = "down";
    }
    let arrow = direction === "up" ? "▲" : direction === "down" ? "▼" : "–";
    let arrowClass = direction === "up" ? "up" : direction === "down" ? "down" : "flat";

    return `
      <li class="ticker-item">
        <span class="drink-name">${name}</span>
        <span class="drink-price">${price.toFixed(2)}</span>
        <span class="arrow ${arrowClass}">${arrow}</span>
      </li>`;
  }).join("");

  // Duplicate so the CSS animation can scroll seamlessly
  ticker.innerHTML = baseItems + baseItems;
}

// ─── PRICE GRID ────────────────────────────────────────────────────────────────
// Rebuilds the bottom grid each update. Highlights background green/red if price changed.
function updateGrid(prices) {
  const grid = document.getElementById("price-grid");
  if (!grid) return;

  const content = Object.entries(prices).map(([name, price]) => {
    let bgColor = "#1e1e1e"; // default dark background
    if (previousPrices[name] !== undefined && price !== previousPrices[name]) {
      bgColor = price > previousPrices[name] ? "green" : "red";
    }
    return `
      <div class="grid-item" style="background-color: ${bgColor}">
        <span class="grid-name">${name}</span>
        <span class="grid-price">${price.toFixed(2)}</span>
      </div>`;
  }).join("");

  grid.innerHTML = content;
}

// ─── CHART ─────────────────────────────────────────────────────────────────────
// Updates Plotly chart for one drink. Maintains history in localStorage.
function updateChart(drink, currentPrice) {
  const timeLabel = getTimeLabel();
  const key = `history_${drink}`;
  let history = JSON.parse(localStorage.getItem(key) || "[]");

  // Append new point
  history.push({ time: timeLabel, price: currentPrice });
  if (history.length > MAX_HISTORY) history.shift();
  localStorage.setItem(key, JSON.stringify(history));

  // Extract arrays for Plotly
  const times = history.map((pt) => pt.time);
  const vals  = history.map((pt) => pt.price);

  // Update chart title above the plot
  const titleEl = document.getElementById("chart-title");
  if (titleEl) titleEl.textContent = drink;

  // Build a single trace
  const trace = {
    x: times,
    y: vals,
    mode: "lines+markers",
    name: drink,
    line:   { color: "lime", width: 2 },
    marker: { size: 6, color: "lime" }
  };

  // Layout: hide x-axis labels, auto‐range y‐axis, dark background
  const layout = {
    title: {
      text: drink,
      font: { size: 24, family: "Orbitron, sans-serif", color: "#ffffff" }
    },
    xaxis: { visible: false },
    yaxis: {
      autorange: true,
      title: { text: "Price (USD)", font: { color: "#ffffff" } },
      tickfont: { color: "#ffffff" },
      gridcolor: "#444"
    },
    margin: { l: 40, r: 20, t: 50, b: 20 },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor:  "rgba(0,0,0,0)"
  };

  // If the chart hasn’t been created yet (or we switch to a new drink), call newPlot
  // Otherwise, we can use Plotly.react() to efficiently update the existing plot
  const chartDiv = document.getElementById("chart");
  if (!chartDiv.data || chartDiv.data[0].name !== drink) {
    Plotly.newPlot("chart", [trace], layout, { displayModeBar: false });
  } else {
    Plotly.react("chart", [trace], layout, { displayModeBar: false });
  }
}

// ─── MAIN UPDATE LOOP ──────────────────────────────────────────────────────────
// Fetches prices → updates ticker/grid → rotates chart every 10 seconds.
async function updateDashboard() {
  const prices = await fetchPrices();
  drinks = Object.keys(prices);

  // 1) Ticker + Grid
  updateTicker(prices);
  updateGrid(prices);

  // 2) Chart rotation
  if (drinks.length > 0) {
    const drink = drinks[currentIndex];
    const livePrice = prices[drink];

    // Populate chart for this drink
    updateChart(drink, livePrice);

    // Move to next drink (wrap around)
    currentIndex = (currentIndex + 1) % drinks.length;
  }

  // 3) Save for next tick (so up/down detection works next time)
  previousPrices = { ...prices };
}

// Run once immediately, then every 10 seconds
updateDashboard();
setInterval(updateDashboard, 10_000);

