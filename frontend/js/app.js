/**
 * ISSR Funding Intelligence - Frontend Application Logic
 */

document.addEventListener('DOMContentLoaded', () => {
    // ── State ──
    const state = {
        currentView: 'opportunities', // opportunities, semantic-search, tags
        searchQuery: '',
        statusFilter: 'open',
        agencyFilter: '',
        currentPage: 1,
        pageSize: 21, // Multiple of 3 for nice grids
    };

    // ── DOM Elements ──
    const elements = {
        navItems: document.querySelectorAll('.nav-item'),
        viewSections: document.querySelectorAll('.view-section'),
        themeToggle: document.getElementById('theme-toggle'),
        foaGrid: document.getElementById('foa-grid'),
        resultsCount: document.getElementById('results-count'),
        searchInput: document.getElementById('keyword-search'),
        searchBtn: document.querySelector('.search-btn'),
        statusFilter: document.getElementById('status-filter'),
        agencyFilter: document.getElementById('agency-filter'),
        semanticInput: document.getElementById('profile-input'),
        semanticBtn: document.getElementById('semantic-search-btn'),
        semanticGrid: document.getElementById('semantic-results-grid'),
        thresholdInput: document.getElementById('match-threshold'),
        thresholdVal: document.getElementById('threshold-val'),
        modalOverlay: document.getElementById('foa-modal'),
        modalClose: document.querySelector('.modal-close'),
        modalBody: document.getElementById('modal-body'),
        exportCsvBtn: document.getElementById('export-csv'),
    };

    // ── Initialization ──
    initTheme();
    setupEventListeners();
    loadOpportunities();

    // ── Event Listeners ──
    function setupEventListeners() {
        // Navigation
        elements.navItems.forEach(item => {
            item.addEventListener('click', (e) => {
                e.preventDefault();
                const view = item.getAttribute('data-view');
                switchView(view);
            });
        });

        // Theme Toggle
        elements.themeToggle.addEventListener('click', () => {
            const html = document.documentElement;
            const isDark = html.getAttribute('data-theme') === 'dark';
            html.setAttribute('data-theme', isDark ? 'light' : 'dark');
            elements.themeToggle.innerHTML = isDark ? '<i class="fa-solid fa-sun"></i>' : '<i class="fa-solid fa-moon"></i>';
        });

        // Keyword Search & Filters
        elements.searchBtn.addEventListener('click', handleSearch);
        elements.searchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') handleSearch();
        });
        elements.statusFilter.addEventListener('change', (e) => {
            state.statusFilter = e.target.value;
            state.currentPage = 1;
            if (state.currentView === 'opportunities') loadOpportunities();
        });
        elements.agencyFilter.addEventListener('change', (e) => {
            state.agencyFilter = e.target.value;
            state.currentPage = 1;
            if (state.currentView === 'opportunities') loadOpportunities();
        });

        // Semantic Search
        elements.thresholdInput.addEventListener('input', (e) => {
            elements.thresholdVal.textContent = parseFloat(e.target.value).toFixed(2);
        });
        elements.semanticBtn.addEventListener('click', handleSemanticSearch);

        // Modal
        elements.modalClose.addEventListener('click', closeModal);
        elements.modalOverlay.addEventListener('click', (e) => {
            if (e.target === elements.modalOverlay) closeModal();
        });

        // Export
        elements.exportCsvBtn.addEventListener('click', () => {
            const url = ApiClient.getExportCsvUrl(state.statusFilter, state.agencyFilter);
            window.location.href = url;
        });
    }

    function initTheme() {
        // Check OS preference
        if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
            document.documentElement.setAttribute('data-theme', 'dark');
        }
    }

    function switchView(viewName) {
        state.currentView = viewName;
        
        // Update Nav UI
        elements.navItems.forEach(item => {
            item.classList.toggle('active', item.getAttribute('data-view') === viewName);
        });

        // Update Sections UI
        elements.viewSections.forEach(section => {
            section.classList.toggle('active', section.id === `${viewName}-view`);
        });

        // Lazy load views
        if (viewName === 'tags' && document.getElementById('tags-dashboard').innerHTML.trim() === '') {
            loadTags();
        }
    }

    // ── Data Loading & Rendering ──

    async function loadOpportunities() {
        renderLoading(elements.foaGrid);
        
        try {
            let data;
            if (state.searchQuery.trim()) {
                data = await ApiClient.searchKeyword(
                    state.searchQuery, state.currentPage, state.pageSize, 
                    state.statusFilter, state.agencyFilter
                );
            } else {
                data = await ApiClient.getOpportunities(
                    state.currentPage, state.pageSize, 
                    state.statusFilter, state.agencyFilter
                );
            }
            
            elements.resultsCount.textContent = `${data.total.toLocaleString()} opportunities`;
            renderFoaGrid(elements.foaGrid, data.items);
            
        } catch (error) {
            console.error(error);
            elements.foaGrid.innerHTML = `<div class="empty-state"><p>Error loading opportunities. Is the API server running?</p></div>`;
        }
    }

    function handleSearch() {
        state.searchQuery = elements.searchInput.value;
        state.currentPage = 1;
        
        if (state.currentView !== 'opportunities') {
            switchView('opportunities');
        }
        
        loadOpportunities();
    }

    async function handleSemanticSearch() {
        const text = elements.semanticInput.value.trim();
        if (!text) return;

        const threshold = parseFloat(elements.thresholdInput.value);
        
        renderLoading(elements.semanticGrid);
        
        try {
            const data = await ApiClient.searchSemantic(text, 15, threshold, state.statusFilter);
            
            if (data.items && data.items.length > 0) {
                renderFoaGrid(elements.semanticGrid, data.items, true);
            } else {
                elements.semanticGrid.innerHTML = `
                    <div class="empty-state">
                        <i class="fa-solid fa-ghost"></i>
                        <p>No matching grants found above the threshold. Try lowering the threshold or providing a more detailed profile.</p>
                        <p class="subtitle">${data.message || ''}</p>
                    </div>
                `;
            }
        } catch (error) {
            console.error(error);
            elements.semanticGrid.innerHTML = `<div class="empty-state"><p>Semantic search failed. Did you run the 'tag-all' command to build the FAISS index?</p></div>`;
        }
    }

    async function loadTags() {
        const container = document.getElementById('tags-dashboard');
        renderLoading(container);
        
        try {
            const data = await ApiClient.getTagCategories();
            
            if (!data.categories || data.categories.length === 0) {
                container.innerHTML = `<div class="empty-state"><p>No tags found. Run the tagging pipeline first.</p></div>`;
                return;
            }

            let html = '<div class="modal-meta-grid" style="margin-top:2rem;">';
            data.categories.forEach(cat => {
                html += `
                    <div class="meta-box">
                        <span class="meta-label">${formatCategory(cat.category)}</span>
                        <span class="meta-value">${cat.concept_count} Concepts</span>
                        <span style="font-size:0.8rem; color:var(--text-muted)">Applied ${cat.total_uses} times</span>
                    </div>
                `;
            });
            html += '</div>';
            container.innerHTML = html;
            
        } catch (error) {
            container.innerHTML = `<div class="empty-state"><p>Error loading tags.</p></div>`;
        }
    }

    // ── Component Rendering ──

    function renderLoading(container) {
        container.innerHTML = `
            <div class="loading-state">
                <div class="spinner"></div>
                <p>Loading...</p>
            </div>
        `;
    }

    function renderFoaGrid(container, items, showScore = false) {
        if (!items || items.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <i class="fa-solid fa-folder-open"></i>
                    <p>No opportunities found matching your criteria.</p>
                </div>
            `;
            return;
        }

        container.innerHTML = '';
        items.forEach(foa => {
            const card = document.createElement('div');
            card.className = 'foa-card';
            card.setAttribute('data-status', foa.status);
            
            const agencyStr = foa.agency_code || foa.agency || 'Unknown Agency';
            const dateStr = foa.close_date ? `Due ${formatDate(foa.close_date)}` : 'Continuous';
            const amountStr = foa.award_ceiling ? formatMoney(foa.award_ceiling) : 'Variable Amount';
            
            // Top 4 tags logic
            const tags = foa.tags || [];
            let tagsHtml = '';
            tags.slice(0, 4).forEach(t => {
                const typeClass = getTagClass(t.category);
                tagsHtml += `<span class="tag ${typeClass}" title="${t.context_snippet}">${t.label}</span>`;
            });
            if (tags.length > 4) {
                tagsHtml += `<span class="tag">+${tags.length - 4} more</span>`;
            }

            let scoreHtml = '';
            if (showScore && foa.similarity_score) {
                scoreHtml = `
                    <div class="match-score">
                        <i class="fa-solid fa-bolt"></i> ${(foa.similarity_score * 100).toFixed(0)}% Match
                    </div>
                `;
            }

            card.innerHTML = `
                ${scoreHtml}
                <div class="card-header">
                    <span class="card-agency">${agencyStr}</span>
                    <span class="card-number">${foa.opportunity_number || foa.foa_id.substring(0,8)}</span>
                </div>
                <h3 class="card-title">${foa.title}</h3>
                <div class="card-meta">
                    <div class="meta-item"><i class="fa-regular fa-calendar"></i> ${dateStr}</div>
                    <div class="meta-item"><i class="fa-solid fa-sack-dollar"></i> ${amountStr}</div>
                </div>
                <div class="card-tags">
                    ${tagsHtml}
                </div>
            `;

            card.addEventListener('click', () => openFoaModal(foa.foa_id));
            container.appendChild(card);
        });
    }

    async function openFoaModal(foaId) {
        elements.modalOverlay.classList.add('active');
        elements.modalBody.innerHTML = `
            <div style="display:flex; justify-content:center; align-items:center; height:200px;">
                <div class="spinner"></div>
            </div>
        `;

        try {
            const foa = await ApiClient.getOpportunityDetail(foaId);
            
            const amountStr = foa.award_ceiling 
                ? `${formatMoney(foa.award_floor || 0)} - ${formatMoney(foa.award_ceiling)}` 
                : 'Not specified';

            let tagsHtml = '';
            if (foa.tags && foa.tags.length > 0) {
                tagsHtml = `
                    <div class="modal-section">
                        <h3>Semantic Tags & Evidence</h3>
                        <div style="display:flex; flex-direction:column; gap:1rem;">
                            ${foa.tags.map(t => `
                                <div style="background:var(--bg-surface); padding:1rem; border-radius:var(--radius-md); border:1px solid var(--border-glass);">
                                    <div style="display:flex; justify-content:space-between; margin-bottom:0.5rem;">
                                        <span class="tag ${getTagClass(t.category)}">${t.label}</span>
                                        <span style="font-size:0.8rem; color:var(--text-muted)">
                                            ${formatLayer(t.source_layer)} • ${(t.confidence * 100).toFixed(0)}% conf
                                        </span>
                                    </div>
                                    <p style="font-size:0.9rem; font-style:italic; border-left:3px solid var(--border-glass); padding-left:1rem;">
                                        "...${t.context_snippet}..."
                                    </p>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                `;
            }

            elements.modalBody.innerHTML = `
                <span class="modal-agency">${foa.agency || foa.agency_code} • ${foa.opportunity_number || ''}</span>
                <h2 class="modal-title">${foa.title}</h2>
                
                <div class="modal-meta-grid">
                    <div class="meta-box">
                        <span class="meta-label">Status</span>
                        <span class="meta-value" style="text-transform:capitalize; color:var(--status-${foa.status})">${foa.status}</span>
                    </div>
                    <div class="meta-box">
                        <span class="meta-label">Close Date</span>
                        <span class="meta-value">${foa.close_date ? formatDate(foa.close_date) : 'Continuous'}</span>
                    </div>
                    <div class="meta-box">
                        <span class="meta-label">Award Range</span>
                        <span class="meta-value">${amountStr}</span>
                    </div>
                    <div class="meta-box">
                        <span class="meta-label">CFDA Numbers</span>
                        <span class="meta-value">${foa.cfda_numbers ? foa.cfda_numbers.join(', ') : 'N/A'}</span>
                    </div>
                </div>

                <div class="modal-section">
                    <h3>Program Description</h3>
                    <p>${foa.program_description || 'No description available.'}</p>
                </div>

                <div class="modal-section">
                    <h3>Eligibility</h3>
                    <p>${foa.eligibility_description || (foa.eligibility ? foa.eligibility.join(', ') : 'Not specified.')}</p>
                </div>

                ${tagsHtml}

                ${foa.source_url ? `
                    <div style="margin-top: 2rem; text-align: center;">
                        <a href="${foa.source_url}" target="_blank" class="btn-primary" style="display:inline-block; text-decoration:none;">
                            View Original on ${foa.source === 'grants_gov' ? 'Grants.gov' : 'Source'} <i class="fa-solid fa-external-link-alt" style="margin-left:8px;"></i>
                        </a>
                    </div>
                ` : ''}
            `;
            
        } catch (error) {
            elements.modalBody.innerHTML = `<div class="empty-state"><p>Error loading FOA details.</p></div>`;
        }
    }

    function closeModal() {
        elements.modalOverlay.classList.remove('active');
        setTimeout(() => { elements.modalBody.innerHTML = ''; }, 300);
    }

    // ── Formatting Helpers ──
    
    function formatDate(dateStr) {
        if (!dateStr) return '';
        const d = new Date(dateStr);
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    }

    function formatMoney(amount) {
        if (!amount && amount !== 0) return '';
        if (amount >= 1000000) return `$${(amount / 1000000).toFixed(1)}M`;
        if (amount >= 1000) return `$${(amount / 1000).toFixed(0)}K`;
        return `$${amount}`;
    }

    function formatCategory(cat) {
        return cat.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
    }

    function formatLayer(layer) {
        if (layer === 'layer_1_terminological') return 'L1 Exact';
        if (layer === 'layer_2_embedding') return 'L2 AI Match';
        if (layer === 'layer_3_llm') return 'L3 LLM Verified';
        return layer;
    }

    function getTagClass(category) {
        switch(category) {
            case 'research_domain': return 'tag-domain';
            case 'method': return 'tag-method';
            case 'population': return 'tag-population';
            case 'sponsor_theme': return 'tag-theme';
            default: return '';
        }
    }
});
