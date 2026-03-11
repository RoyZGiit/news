// Timezone auto-detection and display
(function() {
    'use strict';
    
    // Detect user's timezone
    const userTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    console.log('User timezone detected:', userTimezone);
    
    // Update all elements with data-i18n-time attribute
    function updateTimes() {
        const timeElements = document.querySelectorAll('[data-i18n-time]');
        
        timeElements.forEach(function(el) {
            const utcTime = el.getAttribute('data-i18n-time');
            if (!utcTime) return;
            
            // Parse UTC time (format: "YYYY-MM-DD HH:MM UTC")
            const match = utcTime.match(/(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}) UTC/);
            if (!match) return;
            
            const dateStr = match[1];
            const timeStr = match[2];
            const utcDateTime = new Date(dateStr + 'T' + timeStr + ':00Z');
            
            // Format in user's timezone
            const localTime = utcDateTime.toLocaleString('zh-CN', {
                timeZone: userTimezone,
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                hour12: false
            });
            
            // Format timezone name
            const timezoneAbbr = new Intl.DateTimeFormat('en', {
                timeZone: userTimezone,
                timeZoneName: 'short'
            }).formatToParts(utcDateTime).find(p => p.type === 'timeZoneName')?.value || '';
            
            // Update text
            const count = el.getAttribute('data-i18n-count') || '';
            const baseText = el.getAttribute('data-i18n') || '';
            
            // Replace placeholder with local time
            const newText = el.textContent.replace(
                /\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC/,
                localTime + ' ' + timezoneAbbr
            );
            
            el.textContent = newText;
        });
    }
    
    // Run when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', updateTimes);
    } else {
        updateTimes();
    }
})();
