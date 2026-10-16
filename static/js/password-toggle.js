document.addEventListener('click', function (event) {
    const button = event.target.closest('.toggle-password');
    if (!button) return;
    const input = button.parentElement.querySelector('input');
    const show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    button.setAttribute('aria-pressed', String(show));
});
