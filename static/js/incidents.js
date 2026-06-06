// Incidents Page Manager
let allIncidents = [];
let bootstrapEvidenceModal = null;

document.addEventListener('DOMContentLoaded', () => {
    // Initialize Bootstrap Modal
    const modalElement = document.getElementById('evidenceModal');
    bootstrapEvidenceModal = new bootstrap.Modal(modalElement);
    
    // Stop video playback when modal is hidden
    modalElement.addEventListener('hidden.bs.modal', () => {
        const videoElement = document.getElementById('modal-video');
        if (videoElement) {
            videoElement.pause();
            videoElement.src = '';
        }
    });

    // Load incidents
    fetchIncidents();
});

// Fetch all incidents from Flask API
async function fetchIncidents() {
    try {
        const response = await fetch('/api/incidents_history');
        if (!response.ok) return;
        
        allIncidents = await response.json();
        renderIncidents(allIncidents);
    } catch (err) {
        console.error('Error fetching incident log:', err);
        document.getElementById('incidents-container').innerHTML = `
            <div class="text-center w-100 py-5 text-danger">
                <i class="fa-solid fa-circle-exclamation fs-2 mb-2"></i>
                <p>Failed to load incident history logs.</p>
            </div>
        `;
    }
}

// Render list of incidents into container
function renderIncidents(incidents) {
    const container = document.getElementById('incidents-container');
    
    if (incidents.length === 0) {
        container.innerHTML = `
            <div class="text-center w-100 py-5 text-muted">
                <i class="fa-solid fa-folder-open fs-1 d-block mb-3"></i>
                <h5>No incident history records found.</h5>
                <p class="small text-secondary">All traffic checks are clear.</p>
            </div>
        `;
        return;
    }
    
    let html = '';
    
    incidents.forEach(inc => {
        const riskClass = inc.risk_level.toLowerCase();
        const badgeClass = `badge-risk ${riskClass}`;
        const hasMedia = inc.screenshot_path ? true : false;
        
        // Image display source
        const imgSrc = inc.screenshot_path ? `/${inc.screenshot_path}` : 'https://images.unsplash.com/photo-1549317661-bd32c8ce0db2?q=80&w=640&auto=format&fit=crop';
        
        const resLabel = inc.resolved ? 
            `<span class="badge bg-success bg-opacity-25 text-success border border-success border-opacity-50 text-uppercase px-2" style="font-size:10px">Resolved</span>` : 
            `<span class="badge bg-danger bg-opacity-25 text-danger border border-danger border-opacity-50 text-uppercase px-2" style="font-size:10px">Active</span>`;
            
        html += `
            <div class="incident-card" data-id="${inc.id}" data-type="${inc.incident_type}" data-risk="${inc.risk_level}" data-resolved="${inc.resolved}">
                <div class="incident-card-media">
                    <img src="${imgSrc}" class="incident-card-img" alt="Evidence Preview">
                    <div class="incident-card-badge">
                        <span class="${badgeClass}">${inc.risk_level} Risk</span>
                    </div>
                </div>
                
                <div class="incident-card-body">
                    <div class="d-flex justify-content-between align-items-center mb-2">
                        <h5 class="incident-card-title mb-0">${inc.incident_type}</h5>
                        ${resLabel}
                    </div>
                    
                    <div class="incident-card-meta">
                        <span><i class="fa-regular fa-clock me-2"></i> ${inc.timestamp}</span>
                        <span><i class="fa-solid fa-car me-2"></i> Vehicle involved: ${inc.vehicle_id ? '#' + inc.vehicle_id : 'N/A'}</span>
                        <span><i class="fa-solid fa-person-falling me-2"></i> Person involved: ${inc.person_id ? '#' + inc.person_id : 'N/A'}</span>
                    </div>
                    
                    <div class="incident-card-actions">
                        <button class="btn btn-secondary btn-sm" onclick="viewEvidence(${inc.id})">
                            <i class="fa-solid fa-photo-film"></i> Evidence
                        </button>
                        
                        <a href="/api/report/${inc.id}" class="btn btn-primary btn-sm" target="_blank">
                            <i class="fa-solid fa-file-pdf"></i> PDF
                        </a>
                        
                        ${!inc.resolved ? `
                            <button class="btn btn-outline-danger btn-sm" onclick="resolveIncident(${inc.id})">
                                <i class="fa-solid fa-check-double"></i> Resolve
                            </button>
                        ` : ''}
                    </div>
                </div>
            </div>
        `;
    });
    
    container.innerHTML = html;
}

// Client-side filtering logic
function filterIncidents() {
    const searchVal = document.getElementById('search-input').value.toLowerCase();
    const riskVal = document.getElementById('filter-risk').value;
    const statusVal = document.getElementById('filter-status').value;
    
    const cards = document.querySelectorAll('.incident-card');
    
    cards.forEach(card => {
        const id = card.getAttribute('data-id');
        const type = card.getAttribute('data-type').toLowerCase();
        const risk = card.getAttribute('data-risk').toUpperCase();
        const resolved = card.getAttribute('data-resolved') === '1';
        
        let matchesSearch = type.includes(searchVal) || id.includes(searchVal);
        let matchesRisk = riskVal === 'ALL' || risk === riskVal;
        
        let matchesStatus = true;
        if (statusVal === 'ACTIVE') {
            matchesStatus = !resolved;
        } else if (statusVal === 'RESOLVED') {
            matchesStatus = resolved;
        }
        
        if (matchesSearch && matchesRisk && matchesStatus) {
            card.style.display = 'flex';
        } else {
            card.style.display = 'none';
        }
    });
}

// Reset page filter variables
function resetFilters() {
    document.getElementById('search-input').value = '';
    document.getElementById('filter-risk').value = 'ALL';
    document.getElementById('filter-status').value = 'ALL';
    filterIncidents();
}

// Open modal and show evidence details
function viewEvidence(incidentId) {
    const inc = allIncidents.find(x => x.id === incidentId);
    if (!inc) return;
    
    // Set text details
    document.getElementById('modal-desc').textContent = inc.description || `${inc.incident_type} flagged at camera node. Time: ${inc.timestamp}.`;
    
    // Set screenshot image source
    const imgEl = document.getElementById('modal-img');
    const noImgEl = document.getElementById('modal-no-img');
    if (inc.screenshot_path) {
        imgEl.src = `/${inc.screenshot_path}`;
        imgEl.classList.remove('d-none');
        noImgEl.classList.add('d-none');
    } else {
        imgEl.src = '';
        imgEl.classList.add('d-none');
        noImgEl.classList.remove('d-none');
    }
    
    // Set video source
    const videoEl = document.getElementById('modal-video');
    const noVideoEl = document.getElementById('modal-no-video');
    if (inc.video_path) {
        // Strip out the folder to create proper relative URL for static file serving
        let relativeVideoUrl = inc.video_path.replace(/\\/g, '/');
        // If it starts with the static directory prefix, let's format it
        if (relativeVideoUrl.includes('static/')) {
            const index = relativeVideoUrl.indexOf('static/');
            relativeVideoUrl = '/' + relativeVideoUrl.substring(index);
        }
        videoEl.src = relativeVideoUrl;
        videoEl.classList.remove('d-none');
        noVideoEl.classList.add('d-none');
    } else {
        videoEl.src = '';
        videoEl.classList.add('d-none');
        noVideoEl.classList.remove('d-none');
    }
    
    // Reset active tab to screenshot
    document.getElementById('screenshot-tab').click();
    
    // Show modal
    bootstrapEvidenceModal.show();
}

// API call to resolve incident
async function resolveIncident(incidentId) {
    if (!confirm('Mark this incident as resolved? This will clear its alerts.')) return;
    
    try {
        const response = await fetch(`/api/incidents/resolve/${incidentId}`, {
            method: 'POST'
        });
        if (response.ok) {
            fetchIncidents();
        }
    } catch (err) {
        console.error('Error resolving incident:', err);
    }
}

// API call to clear all incident history
async function clearAllHistory() {
    if (!confirm('Are you absolutely sure you want to clear ALL incident history, database records, and captured screenshots/video clips? This cannot be undone.')) return;
    
    try {
        const response = await fetch('/api/incidents/clear', {
            method: 'POST'
        });
        if (response.ok) {
            allIncidents = [];
            renderIncidents([]);
        } else {
            alert('Failed to clear history database.');
        }
    } catch (err) {
        console.error('Error clearing history:', err);
        alert('An error occurred while clearing history.');
    }
}
