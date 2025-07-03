const backendBaseUrl = 'http://localhost:8000'; // Your FastAPI backend URL

let myChart; // Variable to hold the Chart.js instance

async function fetchDataAndRenderChart() {
    const startDate = document.getElementById('startDate').value;
    const endDate = document.getElementById('endDate').value;
    const userId = document.getElementById('userId').value;
    const metric = document.getElementById('metric').value;
    const messageElement = document.getElementById('message');

    messageElement.textContent = 'Loading data...';

    if (!startDate || !endDate || !userId || !metric) {
        messageElement.textContent = 'Please fill in all fields.';
        return;
    }

    const url = `${backendBaseUrl}/data?start_date=${startDate}&end_date=${endDate}&user_id=${userId}&metric=${metric}`;

    try {
        const response = await fetch(url);
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(`Backend Error: ${response.status} - ${errorData.detail || response.statusText}`);
        }
        const data = await response.json();

        if (data.length === 0) {
            messageElement.textContent = `No data found for ${metric} for participant ${userId} from ${startDate} to ${endDate}.`;
            if (myChart) {
                myChart.destroy(); // Destroy old chart if no data
            }
            return;
        }

        messageElement.textContent = ''; // Clear message on success

        // Prepare data for Chart.js
        // Simplification: Labels will just be the raw timestamp strings for now
        const labels = data.map(item => item.timestamp); // Use raw timestamp string
        const values = data.map(item => item.value_numeric); 

        renderChart(labels, values, metric);

    } catch (error) {
        console.error('Error fetching data:', error);
        messageElement.textContent = `Failed to load data: ${error.message || error}`;
    }
}

function renderChart(labels, values, metric) {
    const ctx = document.getElementById('myChart').getContext('2d');

    if (myChart) {
        myChart.destroy(); // Destroy existing chart instance if it exists
    }

    myChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels, // Now these are raw timestamp strings
            datasets: [{
                label: `${metric} for ${document.getElementById('userId').value}`,
                data: values,
                borderColor: 'rgb(75, 192, 192)',
                tension: 0.1,
                fill: false
            }]
        },
        options: {
            responsive: true,
            scales: {
                x: {
                    // Changed type from 'time' to 'category' or 'linear' for simplicity
                    type: 'category', // Use 'category' for discrete string labels
                    title: {
                        display: true,
                        text: 'Datetime (Raw String)' // Update title
                    }
                },
                y: {
                    beginAtZero: false,
                    title: {
                        display: true,
                        text: metric.replace(/_/g, ' ') 
                    }
                }
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        title: function(context) {
                            return context[0].label; // Use the raw label
                        },
                        label: function(context) {
                            let label = context.dataset.label || '';
                            if (label) {
                                label += ': ';
                            }
                            if (context.parsed.y !== null) {
                                label += context.parsed.y.toFixed(2);
                            }
                            return label;
                        }
                    }
                }
            }
        }
    });
}

document.addEventListener('DOMContentLoaded', () => {
    // You might want to pre-populate or just load on button click
    // fetchDataAndRenderChart();
});