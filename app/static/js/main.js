// Main JavaScript file

document.addEventListener('DOMContentLoaded', function() {
    // Mobile menu toggle
    const mobileMenuBtn = document.getElementById('mobileMenuBtn');
    const mobileMenu = document.getElementById('mobileMenu');
    
    if (mobileMenuBtn && mobileMenu) {
        mobileMenuBtn.addEventListener('click', function() {
            mobileMenu.classList.toggle('hidden');
        });
    }
    
    // Close mobile menu when clicking on a link
    const mobileLinks = mobileMenu ? mobileMenu.querySelectorAll('a') : [];
    mobileLinks.forEach(link => {
        link.addEventListener('click', function() {
            mobileMenu.classList.add('hidden');
        });
    });
    
    // Close alerts when button clicked
    const alertButtons = document.querySelectorAll('.alert button');
    alertButtons.forEach(button => {
        button.addEventListener('click', function() {
            this.parentElement.style.display = 'none';
        });
    });
    
    // Auto-close alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.transition = 'opacity 0.3s ease';
            alert.style.opacity = '0';
            setTimeout(() => {
                alert.style.display = 'none';
            }, 300);
        }, 5000);
    });
    
    // Form validation feedback
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            const inputs = this.querySelectorAll('input[required], select[required], textarea[required]');
            let isValid = true;
            
            inputs.forEach(input => {
                if (!input.value.trim()) {
                    isValid = false;
                    input.classList.add('border-red-500');
                } else {
                    input.classList.remove('border-red-500');
                }
            });
            
            if (!isValid) {
                e.preventDefault();
            }
        });
    });
    
    // Add active state to current nav link
    const currentPage = window.location.pathname;
    const navLinks = document.querySelectorAll('nav a');
    navLinks.forEach(link => {
        if (link.getAttribute('href') === currentPage) {
            link.classList.add('text-green-600', 'font-semibold');
        }
    });
    
    // Mobile menu toggle (if needed)
    const menuToggle = document.querySelector('[data-menu-toggle]');
    const menu = document.querySelector('[data-mobile-menu]');
    
    if (menuToggle && menu) {
        menuToggle.addEventListener('click', function() {
            menu.classList.toggle('hidden');
        });
    }
});

// Utility functions
const Utils = {
    // Format date
    formatDate: function(date) {
        return new Date(date).toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'long',
            day: 'numeric'
        });
    },
    
    // Validate email
    validateEmail: function(email) {
        const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return re.test(email);
    },
    
    // Show notification
    showNotification: function(message, type = 'info') {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type}`;
        alertDiv.innerHTML = `
            <i class="fas fa-check-circle"></i>
            <span>${message}</span>
            <button onclick="this.parentElement.style.display='none';" class="ml-auto">
                <i class="fas fa-times"></i>
            </button>
        `;
        
        const container = document.querySelector('[data-alert-container]') || document.body;
        container.insertBefore(alertDiv, container.firstChild);
        
        setTimeout(() => {
            alertDiv.style.opacity = '0';
            setTimeout(() => alertDiv.remove(), 300);
        }, 5000);
    }
};

// Export for use in other scripts
window.Utils = Utils;

// ===== Supply Item Usage Form - Dynamic Target Selection =====

/**
 * Handle related_model dropdown change
 * Fetches active crops/livestock from API and populates related_id dropdown
 */
async function onRelatedModelChange(relatedModel) {
    const container = document.getElementById('relatedIdContainer');
    const relatedIdSelect = document.getElementById('related_id');
    const relatedTypeLabel = document.getElementById('relatedTypeLabel');
    const errorMsg = document.getElementById('relatedIdError');
    
    // Hide container if not selecting livestock or crop
    if (!relatedModel || relatedModel === 'farm' || relatedModel === 'storage') {
        container.classList.add('hidden');
        relatedIdSelect.removeAttribute('required');
        return;
    }
    
    // Show container and make required
    container.classList.remove('hidden');
    relatedIdSelect.setAttribute('required', 'required');
    errorMsg.classList.add('hidden');
    
    // Get farm_id from the current context (stored in form data attribute or parent)
    const modal = document.getElementById('useItemModal');
    let farmId = modal ? modal.getAttribute('data-farm-id') : null;
    
    // Fallback: try to get from page context or parse from modal
    if (!farmId) {
        // Get from the current inventory item being used
        const itemElement = document.querySelector('[data-current-farm-id]');
        farmId = itemElement ? itemElement.getAttribute('data-current-farm-id') : null;
    }
    
    if (!farmId) {
        // Last resort: extract from visible text or use first farm
        const farmElements = document.querySelectorAll('[data-farm-id]');
        if (farmElements.length > 0) {
            farmId = farmElements[0].getAttribute('data-farm-id');
        }
    }
    
    if (!farmId) {
        errorMsg.textContent = 'Unable to determine farm ID';
        errorMsg.classList.remove('hidden');
        relatedIdSelect.innerHTML = '<option value="">Error loading items</option>';
        return;
    }
    
    // Set label
    relatedTypeLabel.textContent = relatedModel === 'livestock' ? 'Livestock' : 'Crop';
    
    // Show loading state
    relatedIdSelect.innerHTML = '<option value="">Loading active ' + (relatedModel === 'livestock' ? 'livestock' : 'crops') + '...</option>';
    relatedIdSelect.disabled = true;
    
    try {
        // Fetch active items from API
        const endpoint = relatedModel === 'livestock' ? '/livestock/api/active' : '/crop/api/active';
        const url = `${endpoint}?farm_id=${farmId}`;
        
        console.log('Fetching from:', url);
        
        const response = await fetch(url);
        
        if (!response.ok) {
            const errorBody = await response.text();
            console.error('API Error:', response.status, errorBody);
            throw new Error(`API returned ${response.status}: ${errorBody}`);
        }
        
        const items = await response.json();
        console.log('Received items:', items);
        
        if (!Array.isArray(items)) {
            throw new Error('Invalid response format - expected array');
        }
        
        if (items.length === 0) {
            relatedIdSelect.innerHTML = '<option value="">No active ' + (relatedModel === 'livestock' ? 'livestock' : 'crops') + ' available</option>';
            errorMsg.textContent = 'No active items available for this selection. Please add or activate ' + (relatedModel === 'livestock' ? 'livestock' : 'crops') + ' first.';
            errorMsg.classList.remove('hidden');
            relatedIdSelect.disabled = true;
        } else {
            // Populate dropdown
            const options = items.map(item => `<option value="${item.id}">${item.name}</option>`).join('');
            relatedIdSelect.innerHTML = '<option value="">Select a ' + (relatedModel === 'livestock' ? 'livestock' : 'crop') + '...</option>' + options;
            relatedIdSelect.disabled = false;
            errorMsg.classList.add('hidden');
        }
    } catch (error) {
        console.error('Error fetching items:', error);
        relatedIdSelect.innerHTML = '<option value="">Error loading items</option>';
        errorMsg.textContent = 'Error loading available items: ' + error.message;
        errorMsg.classList.remove('hidden');
        relatedIdSelect.disabled = true;
    }
}

/**
 * Open use item modal and set farm context
 * Called when user clicks "Use" button on an inventory item
 */
function openUseItemModal(itemId, itemName, farmId) {
    const modal = document.getElementById('useItemModal');
    const form = document.getElementById('useItemForm');
    
    // Store context in modal
    modal.setAttribute('data-farm-id', farmId);
    modal.setAttribute('data-item-id', itemId);
    document.getElementById('usageItemName').textContent = itemName;
    
    // Reset form
    form.reset();
    
    // Reset related model fields
    document.getElementById('related_model').value = '';
    document.getElementById('relatedIdContainer').classList.add('hidden');
    document.getElementById('related_id').removeAttribute('required');
    document.getElementById('relatedIdError').classList.add('hidden');
    
    // Set form action
    form.action = `/supply/farm-supply/${itemId}/use`;
    
    // Set usage_date to today
    const today = new Date().toISOString().split('T')[0];
    document.getElementById('usage_date').value = today;
    
    // Show modal
    modal.classList.remove('hidden');
}

/**
 * Close use item modal
 */
function closeUseItemModal() {
    const modal = document.getElementById('useItemModal');
    modal.classList.add('hidden');
}
