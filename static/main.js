// ─── static/main.js ────────────────────────────────────────────────────────────

// ─── CONFIG/STATE ──────────────────────────────────────────────────────────────
const MAX_HISTORY = 300;           // max points to keep in the chart per drink
let currentIndex = 0;              // which drink to show in the chart each cycle
let drinks = [];                   // list of drink names (keys)
let previousPrices = {};           // { "Bud Light": 4.12, … } from last fetch
let priceDirections = {};          // persistent up/down arrow state per drink
let chartInitialized = false;      // true once Plotly.newPlot has been called
let activeDrink = null;            // which drink is currently displayed

// ─── MARKET HOURS ──────────────────────────────────────────────────────────────
// New hours: open at 16:00 ET (4 PM) and close at 00:00 ET (midnight).
// In other words, if ET‐hour is >= 16 (4 PM) and < 24:00, the “market” is open.
function isMarketOpenET() {
  // Get current time in ET:
  const nowET = new Date(new Date().toLocaleString("en-US", { timeZone: "America/New_York" }));
  const h = nowET.getHours(); // 0–23
  return h >= 16;             // 16–23 → open; 0–15 → closed
}

// Utility: get "HH:MM" in Eastern Time (for labeling new points)
function getTimeLabel() {
  return new Date().toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "America/New_York"
  });
}

// Build arrays for upward (green) and downward (red) line segments
function buildSegmentTraces(times, values) {
  const upX = [], upY = [];
  const downX = [], downY = [];
  for (let i = 1; i < values.length; i++) {
    if (values[i] >= values[i - 1]) {
      upX.push(times[i - 1], times[i], null);
      upY.push(values[i - 1], values[i], null);
    } else {
      downX.push(times[i - 1], times[i], null);
      downY.push(values[i - 1], values[i], null);
    }
  }
  return { upX, upY, downX, downY };
}

// ─── FETCH LIVE PRICES ────────────────────────────────────────────────────────
async function fetchPrices() {
  try {
    const res = await fetch("/prices");
    if (!res.ok) throw new Error("Network error");
    return await res.json();
  } catch (err) {
    console.error("Failed to fetch /prices:", err);
    return {};
  }
}

// ─── FETCH SERVER HISTORY FOR A DRINK ─────────────────────────────────────────
async function fetchHistory(drink) {
  const encodedName = encodeURIComponent(drink);
  try {
    const res = await fetch(`/history/${encodedName}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json(); // [ { timestamp, price }, … ]
  } catch (err) {
    console.error(`Failed to fetch /history/${drink}:`, err);
    return [];
  }
}

// ─── FETCH PURCHASE HISTORY (last 40, newest first) ─────────────────────────
async function fetchPurchases() {
  try {
    const res = await fetch("/purchases");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json(); // [ { timestamp, drink, quantity, price }, … ]
  } catch (err) {
    console.error("Failed to fetch /purchases:", err);
    return [];
  }
}

// ─── INITIALIZE (OR RE‐INITIALIZE) PLOTLY CHART ─────────────────────────────────
async function initChart(drink, livePrice) {
  // 1) Fetch full history for that drink
  const histArray = await fetchHistory(drink);

  // 2) Build arrays of Date objects (x) and price (y)
  let times  = histArray.map(pt => new Date(pt.timestamp));
  let values = histArray.map(pt => pt.price);

  // 3) If no history yet, seed with the current livePrice
  if (values.length === 0 && livePrice !== undefined) {
    const nowLabel = new Date();
    times  = [nowLabel];
    values = [livePrice];
  }

  // 4) Build traces for line segments and markers
  //    • Markers: color per point (green ↑, red ↓, white →)
  //    • Line segments: green if rising, red if falling
  const markerColors = values.map((v, i) => {
    if (i === 0) return "lime";
    if (v > values[i - 1]) return "lime";
    if (v < values[i - 1]) return "red";
    return "#ffffff";
  });

  const { upX, upY, downX, downY } = buildSegmentTraces(times, values);

  const upTrace = { x: upX, y: upY, mode: "lines", line: { color: "lime", width: 2 }, showlegend: false };
  const downTrace = { x: downX, y: downY, mode: "lines", line: { color: "red", width: 2 }, showlegend: false };
  const markerTrace = { x: times, y: values, mode: "markers", marker: { size: 6, color: markerColors }, showlegend: false, name: drink };

  // 5) Layout: no built-in title (we write our own), hide x-axis labels, white on dark
  const layout = {
    title: { text: "" },
    xaxis: { visible: false },
    yaxis: {
      autorange: true,
      title: { text: "Price (USD)", font: { color: "#ffffff" } },
      tickfont: { color: "#ffffff" },
      gridcolor: "#444"
    },
    margin: { l: 40, r: 20, t: 10, b: 20 },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor:  "rgba(0,0,0,0)"
  };

  // 6) staticPlot:true → disables all zoom/hover/toolbar
  const config = { staticPlot: true };

  Plotly.newPlot("chart", [upTrace, downTrace, markerTrace], layout, config);
  chartInitialized = true;
  activeDrink = drink;

  // 7) Manually write the chart title in our own div:
  document.getElementById("chart-title").innerText = drink;
}

// ─── APPEND A SINGLE NEW PRICE POINT ───────────────────────────────────────────
function appendToChart(drink, price) {
  const chartDiv = document.getElementById("chart");
  if (!chartDiv.data || chartDiv.data.length < 3 || chartDiv.data[2].name !== drink) return;

  const nowLabel = new Date();
  const prevVals  = chartDiv.data[2].y;
  const prevMarks = chartDiv.data[2].marker.color;
  const prevTimes = chartDiv.data[2].x;

  // Determine new marker color
  const lastVal = prevVals[prevVals.length - 1];
  let newColor;
  if (price > lastVal) newColor = "lime";
  else if (price < lastVal) newColor = "red";
  else newColor = "#ffffff";

  // 1) Extend marker.color array by one newColor
  const newMarkerColors = [ ...prevMarks, newColor ];
  Plotly.restyle("chart", { "marker.color": [ newMarkerColors ] }, [2]);

  // 2) Extend the appropriate line segment trace and marker trace
  const prevTime = prevTimes[prevTimes.length - 1];
  const segData = { x: [[prevTime, nowLabel, null]], y: [[lastVal, price, null]] };
  if (price >= lastVal) {
    Plotly.extendTraces("chart", segData, [0]);
  } else {
    Plotly.extendTraces("chart", segData, [1]);
  }
  Plotly.extendTraces("chart", { x: [[nowLabel]], y: [[price]] }, [2]);

  // 3) If too many points, “window” the x-axis to last MAX_HISTORY
  const currentLength = chartDiv.data[2].x.length;
  if (currentLength > MAX_HISTORY) {
    const startIdx = currentLength - MAX_HISTORY;
    const x0 = chartDiv.data[2].x[startIdx];
    const x1 = chartDiv.data[2].x[currentLength - 1];
    Plotly.relayout("chart", { "xaxis.range": [x0, x1] });
  }
}

// ─── UPDATE THE TOP TICKER (permanent ▲/▼/– arrows) ─────────────────────────────
function updateTicker(prices) {
  const ticker = document.getElementById("ticker");
  if (!ticker) return;

  // Track direction persistently so arrows stay consistent across refreshes
  Object.entries(prices).forEach(([name, price]) => {
    if (previousPrices[name] !== undefined) {
      if (price > previousPrices[name]) priceDirections[name] = "up";
      else if (price < previousPrices[name]) priceDirections[name] = "down";
      else if (!priceDirections[name]) priceDirections[name] = "flat";
    } else if (!priceDirections[name]) {
      priceDirections[name] = "flat";
    }
  });

  const baseItems = Object.entries(prices).map(([name, price]) => {
    const direction = priceDirections[name] || "flat";
    const arrow = direction === "up"   ? "▲"
                : direction === "down" ? "▼"
                : "–";
    const arrowClass = direction === "up" ? "up"
                     : direction === "down" ? "down"
                     : "flat";

    return `
      <li class="ticker-item">
        <span class="drink-name">${name}</span>
        <span class="drink-price">${price.toFixed(2)}</span>
        <span class="arrow ${arrowClass}">${arrow}</span>
      </li>`;
  }).join("");

  // Duplicate so CSS can scroll seamlessly
  ticker.innerHTML = baseItems + baseItems;
}

// ─── UPDATE THE BOTTOM PRICE GRID (with consistent flashes) ────────────────────
function updateGrid(prices) {
  const grid = document.getElementById("price-grid");
  if (!grid) return;

  // Track direction persistently like the ticker
  Object.entries(prices).forEach(([name, price]) => {
    if (previousPrices[name] !== undefined) {
      if (price > previousPrices[name]) priceDirections[name] = "up";
      else if (price < previousPrices[name]) priceDirections[name] = "down";
      else if (!priceDirections[name]) priceDirections[name] = "flat";
    } else if (!priceDirections[name]) {
      priceDirections[name] = "flat";
    }
  });

  const content = Object.entries(prices).map(([name, price]) => {
    let flashClass = "";
    if (previousPrices[name] !== undefined && price !== previousPrices[name]) {
      flashClass = price > previousPrices[name] ? "up-flash" : "down-flash";
    }
    const dir = priceDirections[name] || "flat";
    const priceClass = dir === "up" ? "up" : dir === "down" ? "down" : "flat";

    return `
      <div class="grid-item ${flashClass}">
        <span class="grid-name">${name}</span>
        <span class="grid-price ${priceClass}">${price.toFixed(2)}</span>
      </div>`;
  }).join("");

  grid.innerHTML = content;

  // Remove the flash class after 800ms so the next update can flash again
  setTimeout(() => {
    document.querySelectorAll(".up-flash, .down-flash").forEach(el => {
      el.classList.remove("up-flash", "down-flash");
    });
  }, 800);
}

// ─── UPDATE PURCHASE HISTORY PANEL ────────────────────────────────────────────
async function renderPurchaseHistory() {
  const purchases = await fetchPurchases(); // newest first
  const col1 = document.getElementById("col-1");
  const col2 = document.getElementById("col-2");
  col1.innerHTML = "";
  col2.innerHTML = "";

  const filtered = activeDrink
    ? purchases.filter(p => p.drink === activeDrink)
    : purchases;

  if (filtered.length === 0) {
    // If there are no purchases at all, show a placeholder
    col1.innerHTML = `<div class="no-purchase-msg">No purchases yet</div>`;
    return;
  }

  // Otherwise, show up to 40 entries, split 20/20 into two columns
  filtered.forEach((p, idx) => {
    const ts = new Date(p.timestamp).toLocaleString("en-US", {
      hour12: false,
      timeZone: "America/New_York"
    });
    const line = `
      <div class="history-item">
        <span class="hist-time">${ts}</span>
        <span class="hist-drink">${p.drink}</span>
        <span class="hist-qty">x${p.quantity}</span>
        <span class="hist-price">$${p.price.toFixed(2)}</span>
      </div>`;
    if (idx < 20) {
      col1.insertAdjacentHTML("beforeend", line);
    } else {
      col2.insertAdjacentHTML("beforeend", line);
    }
  });
}

// ─── MAIN UPDATE LOOP ──────────────────────────────────────────────────────────
async function updateDashboard() {
  // 1) Always fetch the latest prices & build the `drinks` array
  const prices = await fetchPrices();
  drinks = Object.keys(prices);
  if (drinks.length === 0) return; // no data → abort

  // 2) On first run (chartInitialized === false), always initialize chart
  if (!chartInitialized) {
    activeDrink = drinks[0];
    await initChart(activeDrink, prices[activeDrink]);
  }

  // 3) Check if market is open (4 PM–midnight ET)
  const nowOpen = isMarketOpenET();
  const chartTitleEl = document.getElementById("chart-title");

  if (!nowOpen) {
    // ─── MARKET CLOSED ───────────────────────────────────────────────────────
    // Show "Market Closed" header and clear the chart so the next open starts fresh.
    chartTitleEl.innerText = "Market Closed";
    if (chartInitialized) {
      Plotly.purge("chart");
      chartInitialized = false;
      activeDrink = null;
    }
    // Still update ticker & grid so they “freeze” on last known prices
    updateTicker(prices);
    updateGrid(prices);
    // Update purchase history (will show "No purchases yet" if none exist)
    await renderPurchaseHistory();
    return;
  }

  // ─── MARKET IS OPEN ─────────────────────────────────────────────────────────────
  // 4) If open, pick the next drink (rotate) and either re-init or append
  const drink    = drinks[currentIndex];
  const livePrice= prices[drink];

  if (drink !== activeDrink) {
    // If the drink has changed, re-initialize the chart for the new drink
    activeDrink = drink;
    chartInitialized = false;
    await initChart(drink, livePrice);
  } else {
    // Same drink as last cycle, so append a new point
    appendToChart(drink, livePrice);
  }

  // 5) Update ticker (top) and price grid (bottom)
  updateTicker(prices);
  updateGrid(prices);

  // 6) Update purchase history panel
  await renderPurchaseHistory();

  // 7) Save currentPrices for next-cycle arrow & flash comparisons
  previousPrices = { ...prices };

  // 8) Advance index (wrap around) to rotate to the next drink next cycle
  currentIndex = (currentIndex + 1) % drinks.length;
}

// ─── INITIAL KICKOFF ────────────────────────────────────────────────────────────
// Run once immediately, then every 10 seconds
updateDashboard();
setInterval(updateDashboard, 10000);


