// ─── static/main.js ────────────────────────────────────────────────────────────

// ─── CONFIG/STATE ──────────────────────────────────────────────────────────────
const MAX_HISTORY = 300;           // max points to keep in the chart per drink
let currentIndex = 0;              // which drink to show in the chart each cycle
let drinks = [];                   // list of drink names (keys)
let previousPrices = {};           // { "Bud Light": 4.12, … } from last fetch
let chartInitialized = false;      // track whether Plotly has been initialized
let activeDrink = null;            // the drink currently displayed
let lastPointTime = null;          // timestamp of the last plotted point
const MARKET_OPEN_HOUR = 9;        // 9:30 AM ET → hour 9 (we’ll check minutes)
const MARKET_OPEN_MIN  = 30;
const MARKET_CLOSE_HOUR= 16;       // 4:00 PM ET → hour 16
const MARKET_CLOSE_MIN = 0;

// Utility: get a Date object for today at a specific HH:MM in ET
function getETDate(hour, minute) {
  const now = new Date();
  // Build a string like "2025-06-05T09:30:00-04:00" (ET is UTC−4 in summer/dst)
  const year  = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day   = String(now.getDate()).padStart(2, "0");
  const hh    = String(hour).padStart(2, "0");
  const mm    = String(minute).padStart(2, "0");
  // We assume ET is −04:00 (DST). If you need auto adjust, you can compute offset.
  const isoString = `${year}-${month}-${day}T${hh}:${mm}:00-04:00`;
  return new Date(isoString);
}

// Utility: returns true if current ET time is between 9:30 and 16:00
function isMarketOpenET() {
  const now = new Date().toLocaleString("en-US", { timeZone: "America/New_York" });
  const etNow = new Date(now);
  const openTime  = getETDate(MARKET_OPEN_HOUR, MARKET_OPEN_MIN);
  const closeTime = getETDate(MARKET_CLOSE_HOUR, MARKET_CLOSE_MIN);
  return etNow >= openTime && etNow < closeTime;
}

// Utility: get "HH:MM" in Eastern Time (for x‐axis labeling)
function getTimeLabel() {
  return new Date().toLocaleTimeString("en-US", {
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
    return {}; // will interpret as market closed/offline
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

// ─── FETCH PURCHASE HISTORY (last 40, newest first) ─────────────────────────
async function fetchPurchases() {
  try {
    const res = await fetch("/purchases");
    if (!res.ok) throw new Error("HTTP " + res.status);
    return await res.json(); // [ { timestamp, drink, quantity, price }, … ]
  } catch (err) {
    console.error("Failed to fetch /purchases:", err);
    return [];
  }
}

// ─── INITIALIZE (OR RE‐INITIALIZE) PLOTLY CHART ─────────────────────────────────
async function initChart(drink, livePrice) {
  // 1) Fetch the full history array from the server
  const histArray = await fetchHistory(drink);

  // 2) Extract arrays for x (Date) and y (price)
  let times  = histArray.map(pt => new Date(pt.timestamp));
  let values = histArray.map(pt => pt.price);

  // 3) If there’s no history yet, seed with the current livePrice
  if (values.length === 0 && livePrice !== undefined) {
    const nowLabel = new Date(); 
    times  = [nowLabel];
    values = [livePrice];
  }

  // 4) Build the initial trace, with a dummy color arrays (we’ll recolor segments on‐the‐fly)
  const trace = {
    x: times,
    y: values,
    mode: "lines+markers",
    name: drink,
    line:   { color: "lime", width: 2 },
    marker: { size: 6, color: values.map((v,i) => {
      // First point is always green by default
      if (i === 0) return "lime";
      // If price rose from previous, green; if dropped, red; if flat, white
      return (values[i] > values[i-1]) ? "lime"
           : (values[i] < values[i-1]) ? "red"
           : "#ffffff";
    }) }
  };

  // 5) Layout: disable the Plotly default title, hide x‐axis labels, white-on-dark
  const layout = {
    title: { text: "" },  // we’ll show drink name in #chart-title instead
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

  // 6) Give Plotly the “staticPlot:true” config to disable all interactivity (no zoom, no hover)
  const config = { staticPlot: true };

  Plotly.newPlot("chart", [trace], layout, config);
  chartInitialized = true;
  lastPointTime = times[times.length - 1];
  
  // 7) Set the chart title up top manually
  document.getElementById("chart-title").innerText = `${drink}`;
}

// ─── APPEND A SINGLE NEW PRICE POINT ───────────────────────────────────────────
// We will add both a new marker (colored by direction) and extend the line segment
function appendToChart(drink, price) {
  const chartDiv = document.getElementById("chart");
  if (!chartDiv.data || chartDiv.data[0].name !== drink) return;

  const nowLabel = new Date();
  const prevValues = chartDiv.data[0].y;
  const prevTimes  = chartDiv.data[0].x;

  // Determine new marker‐color based on last value
  const lastVal = prevValues[prevValues.length - 1];
  let newColor;
  if (price > lastVal) newColor = "lime";
  else if (price < lastVal) newColor = "red";
  else newColor = "#ffffff";

  // 1) Extend marker colors array
  Plotly.restyle("chart", {
    "marker.color": [ [...prevValues.map((_, i) => chartDiv.data[0].marker.color[i]), newColor ] ]
  }, [0]);

  // 2) Extend the line itself (it will adopt the last point’s color by default for the segment)
  Plotly.extendTraces("chart", {
    x: [[nowLabel]],
    y: [[price]]
  }, [0]);

  // 3) If trace exceeds MAX_HISTORY, shift the window
  const currentLength = chartDiv.data[0].x.length;
  if (currentLength > MAX_HISTORY) {
    const startIndex = currentLength - MAX_HISTORY;
    const x0 = chartDiv.data[0].x[startIndex];
    const x1 = chartDiv.data[0].x[currentLength - 1];
    Plotly.relayout("chart", { "xaxis.range": [x0, x1] });
  }

  lastPointTime = nowLabel;
}

// ─── UPDATE THE TOP TICKER (rotating beers with arrows) ────────────────────────
function updateTicker(prices) {
  const ticker = document.getElementById("ticker");
  if (!ticker) return;

  // Build each <li> with name, price, and a permanent up/down/flat arrow
  const baseItems = Object.entries(prices).map(([name, price]) => {
    let direction = "flat";
    if (previousPrices[name] !== undefined) {
      if (price > previousPrices[name]) direction = "up";
      else if (price < previousPrices[name]) direction = "down";
    }
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

  // Duplicate once so the CSS keyframes can scroll it seamlessly
  ticker.innerHTML = baseItems + baseItems;
}

// ─── UPDATE THE BOTTOM PRICE GRID (with flash) ────────────────────────────────
function updateGrid(prices) {
  const grid = document.getElementById("price-grid");
  if (!grid) return;

  const content = Object.entries(prices).map(([name, price]) => {
    // By default, dark background
    let bgColor = "#1e1e1e";
    // If price changed vs previousPrices → color flash
    let priceClass = "flat";
    if (previousPrices[name] !== undefined && price !== previousPrices[name]) {
      if (price > previousPrices[name]) {
        bgColor = "#1a5c1a";     // darker green for flash
        priceClass = "up-flash";
      } else {
        bgColor = "#5c1a1a";     // darker red for flash
        priceClass = "down-flash";
      }
    }
    return `
      <div class="grid-item ${priceClass}" style="background-color: ${bgColor}">
        <span class="grid-name">${name}</span>
        <span class="grid-price">${price.toFixed(2)}</span>
      </div>`;
  }).join("");

  grid.innerHTML = content;

  // Remove the flash class after 800ms so each update only lasts briefly
  setTimeout(() => {
    document.querySelectorAll(".up-flash, .down-flash").forEach(el => {
      el.classList.remove("up-flash", "down-flash");
      el.style.backgroundColor = "#1e1e1e";
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

  // We want up to 40 entries, split 20/20 between two columns.
  purchases.forEach((p, idx) => {
    const ts   = new Date(p.timestamp).toLocaleString("en-US", { hour12: false, timeZone: "America/New_York" });
    const line = `<div class="history-item">
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
// 1) Check market hours → if closed: stop rotating & show “Market Closed”  
// 2) If open: regular steps: fetch /prices → rotate chart → update ticker & grid → update purchases
async function updateDashboard() {
  const nowOpen = isMarketOpenET();
  const chartTitleEl = document.getElementById("chart-title");

  // If market is closed, we still want to show yesterday’s chart (no new points),
  // but we replace “<drink>” with “Market Closed” and do NOT rotate the chart.
  if (!nowOpen) {
    chartTitleEl.innerText = "Market Closed";
    // Still render the ticker & grid one last time to freeze on the last-known prices:
    const prices = await fetchPrices();
    if (Object.keys(prices).length > 0) {
      updateTicker(prices);
      updateGrid(prices);
    }
    // Also update purchase history (static until market opens next day)
    await renderPurchaseHistory();
    return;
  }

  // ─── MARKET IS OPEN ─────────────────────────────────────────────────────────────
  // 1) Fetch live prices, rotate chart if needed
  const prices = await fetchPrices();
  drinks = Object.keys(prices);
  if (drinks.length === 0) return; // no data → bail

  const drink    = drinks[currentIndex];
  const livePrice= prices[drink];

  // 1a) If new drink (first run OR index changed), re‐initialize the chart
  if (activeDrink !== drink) {
    activeDrink = drink;
    chartInitialized = false;
    await initChart(drink, livePrice);
  } else {
    // 1b) If same drink as last cycle, append new point if it’s a new timestamp
    if (chartInitialized) {
      appendToChart(drink, livePrice);
    }
  }

  // 2) Update ticker (top) and price grid (bottom)
  updateTicker(prices);
  updateGrid(prices);

  // 3) Update purchase history panel
  await renderPurchaseHistory();

  // 4) Save current prices for direction comparisons on next cycle
  previousPrices = { ...prices };

  // 5) Advance index to rotate to the next drink next cycle
  currentIndex = (currentIndex + 1) % drinks.length;
}

// ─── INITIAL KICKOFF ────────────────────────────────────────────────────────────
// Run once immediately, then every 10s
updateDashboard();
setInterval(updateDashboard, 10000);

