/**
 * Sidebar Toggle Functionality
 * Handles mobile sidebar drawer and desktop sidebar toggle
 */

// Get DOM elements
const sidebar = document.getElementById('sidebar');
const backdrop = document.getElementById('sidebarBackdrop');
const toggleBtn = document.getElementById('sidebarToggle');
const navbar = document.querySelector('.navbar');
const main = document.querySelector('main');

// Check if screen is mobile
function isMobileScreen() {
    return window.innerWidth < 768;
}

// Initialize sidebar state on page load
function initializeSidebar() {
    if (!sidebar) return;
    
    const isMobile = isMobileScreen();
    const wasSidebarOpen = localStorage.getItem('sidebarOpen') !== 'false';
    
    if (isMobile) {
        // Mobile: Start with sidebar closed (no classes)
        sidebar.classList.remove('collapsed');
        sidebar.classList.remove('open');
        if (navbar) navbar.classList.remove('collapsed');
        if (main) main.classList.remove('collapsed');
        if (backdrop) backdrop.classList.remove('active');
    } else {
        // Desktop/Tablet: Restore user preference
        if (!wasSidebarOpen) {
            sidebar.classList.add('collapsed');
            if (navbar) navbar.classList.add('collapsed');
            if (main) main.classList.add('collapsed');
        } else {
            sidebar.classList.remove('collapsed');
            if (navbar) navbar.classList.remove('collapsed');
            if (main) main.classList.remove('collapsed');
        }
        if (backdrop) backdrop.classList.remove('active');
    }
}

// Toggle sidebar
function toggleSidebar() {
    if (!sidebar) return;
    
    const isMobile = isMobileScreen();
    
    if (isMobile) {
        // Mobile: Toggle 'open' class
        const isOpen = sidebar.classList.contains('open');
        if (isOpen) {
            sidebar.classList.remove('open');
            if (backdrop) backdrop.classList.remove('active');
        } else {
            sidebar.classList.add('open');
            if (backdrop) backdrop.classList.add('active');
        }
    } else {
        // Desktop/Tablet: Toggle 'collapsed' class
        sidebar.classList.toggle('collapsed');
        if (navbar) navbar.classList.toggle('collapsed');
        if (main) main.classList.toggle('collapsed');
        localStorage.setItem('sidebarOpen', !sidebar.classList.contains('collapsed'));
    }
}

// Close sidebar (for nav clicks, backdrop clicks)
function closeSidebar() {
    if (!sidebar) return;
    
    const isMobile = isMobileScreen();
    
    if (isMobile) {
        sidebar.classList.remove('open');
        if (backdrop) backdrop.classList.remove('active');
    }
}

// Highlight active link based on current path
function highlightActiveLink() {
    const currentPath = window.location.pathname;
    const navLinks = document.querySelectorAll('#sidebar a');
    
    let bestMatch = null;
    let bestMatchLength = 0;
    
    navLinks.forEach(link => {
        link.classList.remove('active');
        const href = link.getAttribute('href');
        
        if (!href) return;
        
        let isMatch = false;
        
        // Exact match
        if (currentPath === href) {
            isMatch = true;
        }
        // Prefix match (longest wins to avoid parent matching)
        else if (href !== '/' && currentPath.startsWith(href)) {
            isMatch = true;
        }
        
        if (isMatch && href.length > bestMatchLength) {
            bestMatch = link;
            bestMatchLength = href.length;
        }
    });
    
    if (bestMatch) {
        bestMatch.classList.add('active');
    }
}

// Debounce helper
function debounce(func, delay) {
    let timeoutId;
    return function(...args) {
        clearTimeout(timeoutId);
        timeoutId = setTimeout(() => func(...args), delay);
    };
}

// On DOMContentLoaded initialize
document.addEventListener('DOMContentLoaded', function() {
    initializeSidebar();
    
    // Hamburger toggle button
    if (toggleBtn) {
        toggleBtn.addEventListener('click', function(e) {
            e.preventDefault();
            toggleSidebar();
        });
    }
    
    // Backdrop click closes sidebar (mobile)
    if (backdrop) {
        backdrop.addEventListener('click', closeSidebar);
    }
    
    // Nav links auto-close sidebar on mobile
    if (sidebar) {
        sidebar.querySelectorAll('a').forEach(link => {
            link.addEventListener('click', function() {
                if (isMobileScreen()) {
                    closeSidebar();
                }
            });
        });
    }
    
    // Highlight active link
    highlightActiveLink();
});

// Handle window resize
window.addEventListener('resize', debounce(function() {
    initializeSidebar();
    highlightActiveLink();
}, 250));

