document.querySelectorAll('form[onsubmit]').forEach(form => form.addEventListener('submit', event => { if (!confirm('Are you sure you want to delete this item?')) event.preventDefault(); }));
