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

    // A formset marked data-enter-next is typed through box after box (the key vocabulary): Enter moves to the next
    // box instead of sending the whole form, and from the last box of a filled-in last row it adds a new row.
    if (section.hasAttribute('data-enter-next')) {
        rows.addEventListener('keydown', function (event) {
            if (event.key !== 'Enter' || event.isComposing || event.target.type !== 'text') {
                return;
            }
            event.preventDefault();
            const boxes = Array.from(rows.querySelectorAll('input[type="text"]')).filter(function (box) {
                return !box.closest('[data-row]').hidden;
            });
            const next = boxes[boxes.indexOf(event.target) + 1];
            if (next) {
                next.focus();
                return;
            }
            const filled = Array.from(event.target.closest('[data-row]').querySelectorAll('input[type="text"]')).some(
                function (box) { return box.value.trim() !== ''; });
            if (filled) {
                section.querySelector('[data-add]').click();
            }
        });
    }
});
