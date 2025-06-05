// ─── static/main.js ────────────────────────────────────────────────────────────

// ─── CONFIG/STATE ──────────────────────────────────────────────────────────────
const MAX_HISTORY = 300;           // max points to keep in the chart per drink
let currentIndex = 0;              // which drink to show in the chart each cycle
let drinks = [];                   // list of drink names (keys)
let previousPrices = {};           // { "Bud Light": 4.12, … } from last fetch
let chartInitialized = false;      // track whether Plotly has been initialized
let activeDrink = null;            // which drink is currently displayed

// Utility to get "HH:MM" in Eastern Time (for labeling new points)
function getTimeLabel() {
  const now = new Date();
  return now.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "America/New_York"
  });
}

// ─── FETCH LIVE PRICES ────────────────────────────────────────────────────────
async function fetchPrices() {
  try {
    const res = await fetch("/prices");
    if (!res.ok) throw new Error("Network error");
    return await res.json();
  } catch (err) {
    console.error("Failed to fetch /prices:", err);
    return {}; // return empty to avoid crashes if server is unreachable
  }
}

// ─── FETCH SERVER HISTORY FOR A DRINK ─────────────────────────────────────────
async function fetchHistory(drink) {
  const encodedName = encodeURIComponent(drink);
  try {
    const res = await fetch(`/history/${encodedName}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json(); // returns [ { timestamp, price }, … ]
  } catch (err) {
    console.error(`Failed to fetch /history/${drink}:`, err);
    return [];
  }
}

// ─── INITIALIZE PLOTLY CHART WITH SERVER HISTORY ─────────────────────────────
async function initChart(drink, livePrice) {
  // 1) Fetch the full history array from the server
  const histArray = await fetchHistory(drink);

  // 2) Extract arrays for x (timestamps) and y (prices)
  let times = histArray.map(pt => new Date(pt.timestamp));
  let values = histArray.map(pt => pt.price);

  // 3) If there’s no history yet, seed with the current livePrice
  if (values.length === 0 && livePrice !== undefined) {
    const label = getTimeLabel();
    times = [label];
    values = [livePrice];
  }

  // 4) Build the Plotly trace and layout
  const trace = {
    x: times,
    y: values,
    mode: "lines+markers",
    name: drink,
    line:   { color: "lime", width: 2 },
    marker: { size: 6, color: "lime" }
  };

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

  Plotly.newPlot("chart", [trace], layout, { displayModeBar: false });
  chartInitialized = true;
}

// ─── EXTEND PLOTLY CHART WITH A NEW POINT ────────────────────────────────────
function appendToChart(drink, price) {
  const chartDiv = document.getElementById("chart");
  if (!chartDiv.data || chartDiv.data[0].name !== drink) return;

  const timestamp = getTimeLabel();
  Plotly.extendTraces(
    "chart",
    { x: [[timestamp]], y: [[price]] },
    [0] // extend the first (and only) trace
  );

  // If trace exceeds MAX_HISTORY, adjust the x-axis range to show only the last MAX_HISTORY points
  const currentLength = chartDiv.data[0].x.length;
  if (currentLength > MAX_HISTORY) {
    const startIndex = currentLength - MAX_HISTORY;
    const newRange = [
      chartDiv.data[0].x[startIndex],
      chartDiv.data[0].x[currentLength - 1]
    ];
    Plotly.relayout("chart", { "xaxis.range": newRange });
  }
}

// ─── TICKER ────────────────────────────────────────────────────────────────────
// Rebuilds the <ul id="ticker"> every update. We duplicate the list so CSS keyframes can scroll it continuously.
function updateTicker(prices) {
  const ticker = document.getElementById("ticker");
  if (!ticker) return;

  const baseItems = Object.entries(prices).map(([name, price]) => {
    let direction = "flat";
    if (previousPrices[name] !== undefined) {
      if (price > previousPrices[name]) direction = "up";
      else if (price < previousPrices[name]) direction = "down";
    }
    const arrow = direction === "up" ? "▲" : (direction === "down" ? "▼" : "–");
    const arrowClass = direction === "up" ? "up"
                       : (direction === "down" ? "down" : "flat");

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

// ─── MAIN UPDATE LOOP ──────────────────────────────────────────────────────────
// 1) Fetch /prices → 2) on first run or when drink changes, initPlotly with /history →
// 3) update ticker/grid → 4) append new point for current drink → cycle index
async function updateDashboard() {
  const prices = await fetchPrices();
  drinks = Object.keys(prices);
  if (drinks.length === 0) return;

  const drink = drinks[currentIndex];
  const livePrice = prices[drink];

  // 1) If this is the first run OR the active drink has changed, re-initialize the chart
  if (activeDrink !== drink) {
    activeDrink = drink;
    await initChart(drink, livePrice);
  } else {
    // 2) Otherwise, simply append the latest price to the existing chart
    appendToChart(drink, livePrice);
  }

  // 3) Update ticker and grid unconditionally
  updateTicker(prices);
  updateGrid(prices);

  // 4) Save current prices for next comparison
  previousPrices = { ...prices };

  // 5) Advance index (wrap-around) to rotate to the next drink next cycle
  currentIndex = (currentIndex + 1) % drinks.length;
}

// Run once immediately, then every 10 seconds
updateDashboard();
setInterval(updateDashboard, 10000);

