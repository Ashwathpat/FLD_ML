// File Upload Handling
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('image-upload');
const fileNameDisplay = document.getElementById('file-name');
let selectedFile = null;

// Drag and drop events
dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('dragover');
});

dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('dragover');
});

dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    if (e.dataTransfer.files.length) {
        handleFileSelection(e.dataTransfer.files[0]);
    }
});

fileInput.addEventListener('change', (e) => {
    if (e.target.files.length) {
        handleFileSelection(e.target.files[0]);
    }
});

function handleFileSelection(file) {
    if (!file.type.startsWith('image/')) {
        alert('Please upload a valid image file (JPG/PNG).');
        return;
    }
    selectedFile = file;
    // We replace the dropzone text with the file name + a checkmark
    fileNameDisplay.innerHTML = `<span style="color: var(--neon-blue); font-weight: bold;">✓ ${file.name}</span>`;
    
    // Create a data loader object URL to preview image if we wanted, but not needed yet.
}

// Chart Instances
let donutChart = null;
let barChart = null;

// Form Submission
const predictForm = document.getElementById('predict-form');
const submitBtn = document.getElementById('submit-btn');
const loadingSpinner = document.getElementById('loading-spinner');
const resultsPlaceholder = document.querySelector('.results-placeholder');
const resultsContent = document.getElementById('results-content');
const resultLabel = document.getElementById('result-label');
const disclaimerText = document.getElementById('disclaimer-text');
const servedByText = document.getElementById('served-by-text');

predictForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    if (!selectedFile) {
        alert("Please upload a tongue image first.");
        return;
    }

    // Prepare UI for loading
    submitBtn.classList.add('hidden');
    loadingSpinner.classList.remove('hidden');
    
    // Prepare FormData
    const formData = new FormData(predictForm);
    // Ensure file is appended (it should be automatically, but we enforce it just in case)
    formData.set('file', selectedFile);

    try {
        const response = await fetch('/predict', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error(`Server returned ${response.status}`);
        }

        const data = await response.json();
        const servedBy = response.headers.get('X-Served-By') || 'Local';
        
        displayResults(data, servedBy);

    } catch (error) {
        console.error(error);
        alert("Inference failed: " + error.message);
    } finally {
        submitBtn.classList.remove('hidden');
        loadingSpinner.classList.add('hidden');
    }
});

function displayResults(data, servedBy) {
    // Reveal results panel
    resultsPlaceholder.classList.add('hidden');
    resultsContent.classList.remove('hidden');

    // 1. Primary Badge
    resultLabel.textContent = data.label.replace('_', ' ');
    resultLabel.className = 'result-badge'; // reset
    if (data.label === "FLD") {
        resultLabel.classList.add('fld');
    } else {
        resultLabel.classList.add('no-fld');
    }

    // 2. Footer details
    disclaimerText.textContent = data.disclaimer;
    servedByText.textContent = `Diagnostic Computed by: ${servedBy.toUpperCase()} Cloud Node (ID: ${data.id.substring(0,8)})`;

    // 3. Render Charts
    renderDonutChart(data.probabilities);
    renderBarChart(data.top_features);
}

function renderDonutChart(probsDict) {
    const ctx = document.getElementById('donut-chart').getContext('2d');
    
    const labels = Object.keys(probsDict);
    const data = Object.values(probsDict).map(v => (v * 100).toFixed(1));

    if (donutChart) donutChart.destroy();

    // Theming logic for colors
    const colors = labels.map(label => label === 'FLD' ? 'rgba(255, 65, 108, 0.8)' : 'rgba(16, 185, 129, 0.8)');
    const borders = labels.map(label => label === 'FLD' ? '#ff416c' : '#10b981');

    donutChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: data,
                backgroundColor: colors,
                borderColor: borders,
                borderWidth: 2,
                hoverOffset: 10
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '75%',
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { color: '#a0aec0', padding: 20, font: { family: 'Inter', size: 13 } }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return ` ${context.label}: ${context.raw}%`;
                        }
                    }
                }
            }
        }
    });
}

function renderBarChart(topFeaturesArray) {
    const ctx = document.getElementById('bar-chart').getContext('2d');
    
    const labels = topFeaturesArray.map(f => f.feature.replace('phys_', '').replace('texture_', '').replace('color_', ''));
    const data = topFeaturesArray.map(f => f.importance_score);

    if (barChart) barChart.destroy();

    // Create gradient
    const gradient = ctx.createLinearGradient(0, 0, 0, 250);
    gradient.addColorStop(0, 'rgba(0, 242, 254, 0.8)');
    gradient.addColorStop(1, 'rgba(79, 172, 254, 0.2)');

    barChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'SHAP Importance',
                data: data,
                backgroundColor: gradient,
                borderRadius: 6,
                borderWidth: 1,
                borderColor: '#00f2fe'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#a0aec0' }
                },
                x: {
                    grid: { display: false },
                    ticks: { 
                        color: '#a0aec0',
                        maxRotation: 45,
                        minRotation: 45,
                        font: { size: 11 }
                    }
                }
            },
            plugins: {
                legend: { display: false }
            }
        }
    });
}
