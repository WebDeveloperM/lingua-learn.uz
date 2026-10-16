document.addEventListener('submit', function (event) {
    const message = event.target.dataset && event.target.dataset.confirm;
    if (message && !window.confirm(message)) {
        event.preventDefault();
    }
});

document.querySelectorAll('[data-formset]').forEach(function (section) {
    const prefix = section.dataset.prefix;
    const total = section.querySelector('input[name="' + prefix + '-TOTAL_FORMS"]');
    const rows = section.querySelector('[data-rows]');
    const template = section.querySelector('template[data-empty]');

    section.querySelector('[data-add]').addEventListener('click', function () {
        const index = parseInt(total.value, 10);
        rows.insertAdjacentHTML('beforeend', template.innerHTML.replace(/__prefix__/g, index));
        total.value = index + 1;
        const input = rows.lastElementChild.querySelector('input[type="text"]');
        if (input) {
            input.focus();
        }
    });

    rows.addEventListener('click', function (event) {
        const button = event.target.closest('[data-remove]');
        if (!button) {
            return;
        }
        const row = button.closest('[data-row]');
        row.querySelector('input[name$="-DELETE"]').checked = true;
        row.hidden = true;
    });
});
