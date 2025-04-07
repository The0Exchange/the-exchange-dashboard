let chart;
let currentIndex = 0;
let drinks = [];
let previousPrices = {};
let tickerInitialized = false;

async function fetchPrices() {
    const res = await fetch("/prices");
    return await res.json();
}

async function fetchHistory(drink) {
    const res = await fetch("/history/" + encodeURIComponent(drink));
    return await res.json();
}

function updateTicker(prices) {
    const ticker = document.getElementById("ticker");

    // Only create ticker once
    if (!tickerInitialized) {
        const tickerContent = Object.entries(prices).map(([name, price]) =>
            `<span id="ticker-${name.replace(/\s+/g, '-')}">${name}: $${price.toFixed(2)} </span>`
        ).join('');
        ticker.innerHTML = `<div class="ticker-inner">${tickerContent + tickerContent}</div>`;
        tickerInitialized = true;
    } else {
        // Just update values in place
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

async function updateChart(drink) {
    const history = await fetchHistory(drink);
    const labels = history.map(p => p.time);
    const data = history.map(p => parseFloat(p.price));  // Ensure numeric

    console.log("Chart Data for", drink, data);  // Debug logging

    const title = document.getElementById("chart-title");
    title.textContent = drink;

    if (chart) {
        chart.destroy();
        chart = null;
    }

    let dailyHigh = Math.max(...data);
    let dailyLow = Math.min(...data);

    // Fallback if data is invalid or flat
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
    const prices = await fetchPrices();
    drinks = Object.keys(prices);

    updateTicker(prices);
    updateGrid(prices);

    // Animate updates
    Object.entries(prices).forEach(([name, newPrice]) => {
        const oldPrice = previousPrices[name];
        const safeId = name.replace(/\s+/g, '-');

        if (oldPrice !== undefined && oldPrice !== newPrice) {
            // Flash grid
            const gridEl = document.getElementById(`price-${safeId}`);
            if (gridEl) {
                gridEl.style.backgroundColor = newPrice > oldPrice ? "green" : "red";
                setTimeout(() => gridEl.style.backgroundColor = "#1e1e1e", 500);
            }

            // Flash ticker
            const tickerEl = document.getElementById(`ticker-${safeId}`);
            if (tickerEl) {
                tickerEl.style.color = newPrice > oldPrice ? "lime" : "red";
                setTimeout(() => tickerEl.style.color = "white", 500);
            }
        }
    });

    previousPrices = { ...prices };

    await updateChart(drinks[currentIndex]);
    currentIndex = (currentIndex + 1) % drinks.length;
}

setInterval(updateDashboard, 10000);
updateDashboard();
