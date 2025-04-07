let chart;
let currentIndex = 0;
let drinks = [];
let previousPrices = {};

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
    const tickerContent = Object.entries(prices).map(([name, price]) =>
        `<span id="ticker-${name.replace(/\s+/g, '-')}">${name}: $${price.toFixed(2)} </span>`
    ).join('');

    // Duplicate content for infinite scroll
    ticker.innerHTML = `<div class="ticker-inner">${tickerContent + tickerContent}</div>`;
}

function updateGrid(prices) {
    const grid = document.getElementById("price-grid");
    grid.innerHTML = Object.entries(prices).map(([name, price]) =>
        `<div id="price-${name.replace(/\s+/g, '-')}">${name}: $${price.toFixed(2)}</div>`).join('');
}

async function updateChart(drink) {
    const history = await fetchHistory(drink);
    const labels = history.map(p => p.time);
    const data = history.map(p => p.price);
    const title = document.getElementById("chart-title");
    title.textContent = drink;

    // Force destroy and redraw the chart to reset y-axis scaling
    if (chart) {
        chart.destroy();
        chart = null;
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
                    suggestedMin: Math.min(...data) - 0.25,
                    suggestedMax: Math.max(...data) + 0.25
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

    // Animate price changes in grid + ticker
    Object.entries(prices).forEach(([name, newPrice]) => {
        const oldPrice = previousPrices[name];
        const safeId = name.replace(/\s+/g, '-');

        if (oldPrice !== undefined && oldPrice !== newPrice) {
            // Flash grid cell
            const gridEl = document.getElementById(`price-${safeId}`);
            if (gridEl) {
                gridEl.style.backgroundColor = newPrice > oldPrice ? "green" : "red";
                setTimeout(() => gridEl.style.backgroundColor = "#1e1e1e", 500);
            }

            // Flash ticker text
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
