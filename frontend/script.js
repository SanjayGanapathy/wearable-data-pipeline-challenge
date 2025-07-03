const backendBaseUrl = 'http://localhost:8001'; // Your FastAPI backend URL

let myChart; // Variable to hold the Chart.js instance

// Pagination state variables
let currentPage = 1;
let currentLimit = 50; // Default page size
let totalRecords = 0; // Total records from backend

// Function to update page info display
function updatePageInfo() {
    const pageInfoElement = document.getElementById('pageInfo');
    const totalPages = Math.ceil(totalRecords / currentLimit);
    pageInfoElement.textContent = `Page ${currentPage} of ${totalPages || 1}`;
}

// Event listeners for pagination buttons (defined in index.html)
window.prevPage = function() {
    if (currentPage > 1) {
        currentPage--;
        fetchDataAndRenderChart();
    }
};

window.nextPage = function() {
    const totalPages = Math.ceil(totalRecords / currentLimit);
    if (currentPage < totalPages) {
        currentPage++;
        fetchDataAndRenderChart();
    }
};

// Event listener for page size dropdown
document.addEventListener('DOMContentLoaded', () => {
    const pageSizeSelect = document.getElementById('pageSize');
    pageSizeSelect.addEventListener('change', (event) => {
        currentLimit = parseInt(event.target.value);
        currentPage = 1; // Reset to first page when page size changes
        fetchDataAndRenderChart();
    });
    updatePageInfo(); // Initialize page info on load
});


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

    // Calculate offset for current page
    const offset = (currentPage - 1) * currentLimit;

    // Construct URL with limit and offset
    const url = `${backendBaseUrl}/data?start_date=${startDate}&end_date=${endDate}&user_id=${userId}&metric=${metric}&limit=${currentLimit}&offset=${offset}`;

    try {
        const response = await fetch(url);
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(`Backend Error: ${response.status} - ${errorData.detail || response.statusText}`);
        }
        const responseJson = await response.json(); // Backend now returns {data: [], total_count: N}
        const data = responseJson.data;
        totalRecords = responseJson.total_count; // Update total records

        updatePageInfo(); // Update page info after fetching

        if (data.length === 0) {
            messageElement.textContent = `No data found for ${metric} for participant ${userId} from ${startDate} to ${endDate} on this page.`;
            if (myChart) {
                myChart.destroy();
            }
            return;
        }

        messageElement.textContent = ''; // Clear message on success

        // Prepare data for Chart.js
        const labels = data.map(item => item.timestamp);
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
            labels: labels, 
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
                    type: 'category', 
                    title: {
                        display: true,
                        text: 'Datetime (Raw String)' 
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
                            return context[0].label; 
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

// Initial load when the page loads
document.addEventListener('DOMContentLoaded', () => {
    // Automatically fetch data on page load with default settings
    fetchDataAndRenderChart(); 
});