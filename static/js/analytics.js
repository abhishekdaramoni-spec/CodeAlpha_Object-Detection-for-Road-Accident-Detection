// Analytics Page Chart.js Renderer

document.addEventListener('DOMContentLoaded', () => {
    fetchAnalyticsData();
});

async function fetchAnalyticsData() {
    try {
        const response = await fetch('/api/analytics_stats');
        if (!response.ok) return;
        
        const data = await response.json();
        
        renderHourlyTraffic(data.hourly_traffic);
        renderVehicleClasses(data.vehicle_distribution);
        renderRiskDist(data.risk_distribution);
        renderIncidentTrend(data.incidents_by_date);
    } catch (err) {
        console.error('Error rendering analytics charts:', err);
    }
}

// Chart Options Helper for Dark Mode
const chartBaseOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
        legend: {
            labels: {
                color: '#94A3B8', // text-muted
                font: { family: 'Inter', size: 12 }
            }
        }
    },
    scales: {
        x: {
            grid: { color: 'rgba(255, 255, 255, 0.05)' },
            ticks: { color: '#94A3B8', font: { family: 'Inter' } }
        },
        y: {
            grid: { color: 'rgba(255, 255, 255, 0.05)' },
            ticks: { color: '#94A3B8', font: { family: 'Inter' } }
        }
    }
};

// 1. Hourly Traffic Area Chart
function renderHourlyTraffic(hourlyData) {
    const ctx = document.getElementById('trafficHourChart').getContext('2d');
    
    // Create gradient
    const gradient = ctx.createLinearGradient(0, 0, 0, 300);
    gradient.addColorStop(0, 'rgba(6, 182, 212, 0.4)');
    gradient.addColorStop(1, 'rgba(6, 182, 212, 0.0)');
    
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: hourlyData.map(d => d.label),
            datasets: [{
                label: 'Vehicles Detected',
                data: hourlyData.map(d => d.count),
                borderColor: '#06B6D4',
                borderWidth: 2,
                backgroundColor: gradient,
                fill: true,
                tension: 0.4
            }]
        },
        options: chartBaseOptions
    });
}

// 2. Vehicle Classes Distribution Doughnut
function renderVehicleClasses(classData) {
    const ctx = document.getElementById('vehicleClassChart').getContext('2d');
    const classes = Object.keys(classData);
    const counts = Object.values(classData);
    
    // Fallback if empty
    const labels = classes.length > 0 ? classes : ['Car', 'Motorcycle', 'Truck', 'Bus', 'Bicycle'];
    const dataValues = counts.length > 0 ? counts : [0, 0, 0, 0, 0];
    
    new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels.map(l => l.toUpperCase()),
            datasets: [{
                data: dataValues,
                backgroundColor: [
                    '#06B6D4', // cyan
                    '#8B5CF6', // violet/purple
                    '#EC4899', // pink
                    '#3B82F6', // blue
                    '#10B981'  // emerald green
                ],
                borderWidth: 1,
                borderColor: '#0F172A' // match sidebar dark bg
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right',
                    labels: {
                        color: '#94A3B8',
                        font: { family: 'Inter', size: 11 }
                    }
                }
            }
        }
    });
}

// 3. Risk Level Severity Split Bar Chart
function renderRiskDist(riskData) {
    const ctx = document.getElementById('riskSplitChart').getContext('2d');
    
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['LOW RISK', 'MODERATE RISK', 'HIGH RISK'],
            datasets: [{
                label: 'Logged Events',
                data: [
                    riskData['Low'] || 0,
                    riskData['Moderate'] || 0,
                    riskData['High'] || 0
                ],
                backgroundColor: [
                    'rgba(16, 185, 129, 0.65)', // soft green
                    'rgba(245, 158, 11, 0.65)',  // soft orange
                    'rgba(239, 68, 68, 0.65)'   // soft red
                ],
                borderColor: [
                    '#10B981',
                    '#F59E0B',
                    '#EF4444'
                ],
                borderWidth: 1.5,
                borderRadius: 4
            }]
        },
        options: chartBaseOptions
    });
}

// 4. Incident Over Time Trend Line
function renderIncidentTrend(trendData) {
    const ctx = document.getElementById('incidentTrendChart').getContext('2d');
    
    const labels = trendData.labels.length > 0 ? trendData.labels : ['No Data'];
    const counts = trendData.counts.length > 0 ? trendData.counts : [0];
    
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Accidents Flagged',
                data: counts,
                borderColor: '#EF4444',
                borderWidth: 2.5,
                backgroundColor: 'rgba(239, 68, 68, 0.1)',
                fill: true,
                tension: 0.3
            }]
        },
        options: chartBaseOptions
    });
}
