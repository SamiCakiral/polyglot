// FlashCards - JavaScript

document.addEventListener('DOMContentLoaded', function () {
    // Auto-hide flash messages after 5 seconds
    const flashMessages = document.querySelectorAll('.flash');
    flashMessages.forEach(function (flash) {
        setTimeout(function () {
            flash.style.opacity = '0';
            flash.style.transition = 'opacity 0.5s';
            setTimeout(function () {
                flash.remove();
            }, 500);
        }, 5000);
    });

    // Confirm delete actions
    document.querySelectorAll('form[data-confirm]').forEach(function (form) {
        form.addEventListener('submit', function (e) {
            if (!confirm(this.dataset.confirm)) {
                e.preventDefault();
            }
        });
    });
});
