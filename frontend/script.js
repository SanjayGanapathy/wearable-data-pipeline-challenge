const backendBaseUrl = 'http://localhost:8001'; // FastAPI backend URL

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
    const imputeData = document.getElementById('imputeData').checked; // Read checkbox state
    const messageElement = document.getElementById('message');

    messageElement.textContent = 'Loading data...';

    if (!startDate || !endDate || !userId || !metric) {
        messageElement.textContent = 'Please fill in all fields.';
        return;
    }

    // Calculate offset for current page
    const offset = (currentPage - 1) * currentLimit;

    // Conditionally build URL based on imputeData checkbox
    const endpoint = imputeData ? '/data/imputed' : '/data';
    const url = `${backendBaseUrl}${endpoint}?start_date=${startDate}&end_date=${endDate}&user_id=${userId}&metric=${metric}&limit=${currentLimit}&offset=${offset}`;

    try {
        const response = await fetch(url);
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(`Backend Error: ${response.status} - ${errorData.detail || response.statusText}`);
        }
        const responseJson = await response.json(); // Backend now returns {data: [], total_count: N} or [] for imputed

        // Handle different response structures for /data vs /data/imputed
        const data = Array.isArray(responseJson) ? responseJson : responseJson.data;
        totalRecords = Array.isArray(responseJson) ? responseJson.length : responseJson.total_count;

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
        const imputedFlags = data.map(item => item.is_imputed || false); // Get imputed flag (default to false)

        renderChart(labels, values, metric, imputedFlags); // Pass imputedFlags

    } catch (error) {
        console.error('Error fetching data:', error);
        messageElement.textContent = `Failed to load data: ${error.message || error}`;
    }
}

// Pass imputedFlags to renderChart
function renderChart(labels, values, metric, imputedFlags) {
    const ctx = document.getElementById('myChart').getContext('2d');

    if (myChart) {
        myChart.destroy(); // Destroy existing chart instance if it exists
    }

    // Prepare point styles based on imputedFlag
    const pointBackgroundColors = values.map((val, index) => 
        imputedFlags[index] ? 'red' : 'rgb(75, 192, 192)' // Red for imputed, default for original
    );
    const pointBorderColors = pointBackgroundColors; // Same for border
    const pointBorderWidths = values.map((val, index) => 
        imputedFlags[index] ? 2 : 1 // Thicker border for imputed
    );
    const pointRadii = values.map((val, index) => 
        imputedFlags[index] ? 4 : 3 // Larger radius for imputed
    );


    myChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels, 
            datasets: [{
                label: `${metric} for ${document.getElementById('userId').value}`,
                data: values,
                borderColor: 'rgb(75, 192, 192)',
                tension: 0.1,
                fill: false,
                pointBackgroundColor: pointBackgroundColors, // Apply conditional styles
                pointBorderColor: pointBorderColors,
                pointBorderWidth: pointBorderWidths,
                pointRadius: pointRadii,
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
                            // Add imputed status to tooltip
                            const index = context.dataIndex;
                            if (imputedFlags[index]) {
                                label += ' (Imputed)';
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