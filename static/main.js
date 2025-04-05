let chart;
let currentIndex = 0;
let drinks = [];

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
    ticker.innerHTML = Object.entries(prices).map(([name, price]) =>
        `<span style='margin:0 20px;'>${name}: $${price.toFixed(2)}</span>`).join('');
}

function updateGrid(prices) {
    const grid = document.getElementById("price-grid");
    grid.innerHTML = Object.entries(prices).map(([name, price]) =>
        `<div>${name}: $${price.toFixed(2)}</div>`).join('');
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
                    y: { ticks: { color: "white" }, grid: { color: "#444" } }
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
    await updateChart(drinks[currentIndex]);
    currentIndex = (currentIndex + 1) % drinks.length;
}

setInterval(updateDashboard, 10000);
updateDashboard();
