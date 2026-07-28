/**
 * API Client for ISSR Funding Intelligence
 */

const API_BASE = '/api';

class ApiClient {
    /**
     * Fetch FOAs with pagination and filters
     */
    static async getOpportunities(page = 1, size = 20, status = 'open', agency = '') {
        const params = new URLSearchParams({
            page,
            size,
            sort: 'posted_date',
            order: 'DESC'
        });
        if (status) params.append('status', status);
        if (agency) params.append('agency', agency);

        const res = await fetch(`${API_BASE}/opportunities?${params}`);
        if (!res.ok) throw new Error('Failed to fetch opportunities');
        return res.json();
    }

    /**
     * Fetch a single FOA by ID
     */
    static async getOpportunityDetail(foaId) {
        const res = await fetch(`${API_BASE}/opportunities/${foaId}`);
        if (!res.ok) throw new Error('FOA not found');
        return res.json();
    }

    /**
     * Keyword Full-Text Search
     */
    static async searchKeyword(query, page = 1, size = 20, status = 'open', agency = '') {
        const payload = { query, page, size };
        if (status) payload.status = status;
        if (agency) payload.agency = agency;

        const res = await fetch(`${API_BASE}/search/keyword`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!res.ok) throw new Error('Search failed');
        return res.json();
    }

    /**
     * Semantic Profile Search via FAISS
     */
    static async searchSemantic(profileText, k = 10, threshold = 0.5, status = 'open') {
        const payload = {
            profile_text: profileText,
            k,
            threshold,
            status
        };

        const res = await fetch(`${API_BASE}/search/semantic`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!res.ok) throw new Error('Semantic search failed');
        return res.json();
    }

    /**
     * Get Tag Categories Summary
     */
    static async getTagCategories() {
        const res = await fetch(`${API_BASE}/tags/categories`);
        if (!res.ok) throw new Error('Failed to fetch tags');
        return res.json();
    }

    /**
     * Export URL builder
     */
    static getExportCsvUrl(status = 'open', agency = '') {
        const params = new URLSearchParams();
        if (status) params.append('status', status);
        if (agency) params.append('agency', agency);
        return `${API_BASE}/export/csv?${params}`;
    }
}
