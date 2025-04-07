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
    ticker.innerHTML = `<span>` +
        Object.entries(prices).map(([name, price]) =>
            `${name}: $${price.toFixed(2)} `).join('') +
        `</span>`;
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

    if (chart) {
        chart.data.labels = labels;
        chart.data.datasets[0].data = data;
        chart.options.scales.y.suggestedMin = Math.min(...data) - 0.25;
        chart.options.scales.y.suggestedMax = Math.max(...data) + 0.25;
        chart.update();
    } else {
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
}

async function updateDashboard() {
    const prices = await fetchPrices();
    drinks = Object.keys(prices);
    updateTicker(prices);
    updateGrid(prices);

    // Animate price changes
    Object.entries(prices).forEach(([name, newPrice]) => {
        const oldPrice = previousPrices[name];
        if (oldPrice !== undefined && oldPrice !== newPrice) {
            const el = document.getElementById(`price-${name.replace(/\s+/g, '-')}`);
            if (el) {
                el.style.backgroundColor = newPrice > oldPrice ? "green" : "red";
                setTimeout(() => {
                    el.style.backgroundColor = "#1e1e1e";
                }, 500);
            }
        }
    });
    previousPrices = { ...prices };

    // Chart
    await updateChart(drinks[currentIndex]);
    currentIndex = (currentIndex + 1) % drinks.length;
}

// Run
setInterval(updateDashboard, 10000);
updateDashboard();
