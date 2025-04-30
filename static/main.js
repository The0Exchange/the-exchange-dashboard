let chart;
let currentIndex = 0;
let drinks = [];
let previousPrices = {};
let tickerInitialized = false;

const DRINKS = [
    "Bud Light", "Budweiser", "Busch Light", "Coors Light", "Corona Light",
    "Guinness", "Heineken", "Michelob Ultra", "Miller Light", "Modelo"
];

const MAX_HISTORY = 300;

function getTimeLabel() {
    const now = new Date();
    return now.toLocaleTimeString("en-US", { hour: '2-digit', minute: '2-digit' });
}

function getDateKey() {
    const now = new Date();
    return now.toLocaleDateString("en-US", { timeZone: "America/New_York" });
}

function checkAndClearHistoryIfNeeded() {
    const now = new Date();
    const hourET = now.toLocaleString("en-US", { timeZone: "America/New_York", hour: '2-digit', hour12: false });
    const cleared = localStorage.getItem("history_cleared");

    if (hourET === "16" && cleared !== getDateKey()) {
        for (let drink of DRINKS) {
            localStorage.removeItem(`history_${drink}`);
        }
        localStorage.setItem("history_cleared", getDateKey());
        console.log("Price history reset for new day.");
    }
}

async function fetchPrices() {
    const res = await fetch("/prices");
    return await res.json();
}

function updateTicker(prices) {
    const ticker = document.getElementById("ticker");

    if (!tickerInitialized) {
        const tickerContent = Object.entries(prices).map(([name, price]) =>
            `<span id="ticker-${name.replace(/\s+/g, '-')}">${name}: $${price.toFixed(2)} </span>`
        ).join('');
        ticker.innerHTML = `<div class="ticker-inner">${tickerContent + tickerContent}</div>`;
        tickerInitialized = true;
    } else {
        Object.entries(prices).forEach(([name, price]) => {
            const tickerEl = document.getElementById(`ticker-${name.replace(/\s+/g, '-')}`);
            if (tickerEl) {
                tickerEl.textContent = `${name}: $${price.toFixed(2)} `;
            }
        });
    }
}

function updateGrid(prices) {
    const grid = document.getElementById("price-grid");
    grid.innerHTML = Object.entries(prices).map(([name, price]) =>
        `<div id="price-${name.replace(/\s+/g, '-')}">${name}: $${price.toFixed(2)}</div>`).join('');
}

function updateChart(drink) {
    const localKey = `history_${drink}`;
    let history = JSON.parse(localStorage.getItem(localKey) || "[]");

    const now = new Date();
    const timeStr = now.toLocaleTimeString("en-US", { hour: '2-digit', minute: '2-digit' });
    const currentPrice = previousPrices[drink];

    history.push({ time: timeStr, price: currentPrice });
    if (history.length > MAX_HISTORY) history.shift();
    localStorage.setItem(localKey, JSON.stringify(history));

    const labels = history.map(p => p.time);
    const data = history.map(p => parseFloat(p.price));

    const title = document.getElementById("chart-title");
    title.textContent = drink;

    if (chart) {
        chart.destroy();
        chart = null;
    }

    let dailyHigh = Math.max(...data);
    let dailyLow = Math.min(...data);
    if (!isFinite(dailyHigh) || !isFinite(dailyLow) || dailyHigh === dailyLow) {
        const fallback = data[0] || 5.0;
        dailyLow = fallback - 1;
        dailyHigh = fallback + 1;
    }

    const ctx = document.getElementById("priceChart").getContext("2d");
    chart = new Chart(ctx, {
        type: "line",
        data: {
            labels: labels,
            datasets: [{
                label: "Price",
                data: data,
                borderColor: "lime",
                backgroundColor: "transparent"
            }]
        },
        options: {
            responsive: true,
            scales: {
                x: { display: false },
                y: {
                    ticks: { color: "white" },
                    grid: { color: "#444" },
                    suggestedMin: dailyLow,
                    suggestedMax: dailyHigh
                }
            },
            plugins: {
                legend: { display: false }
            }
        }
    });
}

async function updateDashboard() {
    checkAndClearHistoryIfNeeded();
    const prices = await fetchPrices();
    drinks = Object.keys(prices);

    updateTicker(prices);
    updateGrid(prices);

    Object.entries(prices).forEach(([name, newPrice]) => {
        const oldPrice = previousPrices[name];
        const safeId = name.replace(/\s+/g, '-');

        if (oldPrice !== undefined && oldPrice !== newPrice) {
            const gridEl = document.getElementById(`price-${safeId}`);
            if (gridEl) {
                gridEl.style.backgroundColor = newPrice > oldPrice ? "green" : "red";
                setTimeout(() => gridEl.style.backgroundColor = "#1e1e1e", 500);
            }

            const tickerEl = document.getElementById(`ticker-${safeId}`);
            if (tickerEl) {
                tickerEl.style.color = newPrice > oldPrice ? "lime" : "red";
                setTimeout(() => tickerEl.style.color = "white", 500);
            }
        }
    });

    previousPrices = { ...prices };

    if (drinks.length > 0) {
        await updateChart(drinks[currentIndex]);
        currentIndex = (currentIndex + 1) % drinks.length;
    }
}

setInterval(updateDashboard, 10000);
updateDashboard();
