(function () {
    const WARNING_SECONDS = 300;

    const form = document.getElementById('writing-form');
    if (!form) {
        return;
    }
    const body = document.getElementById('writing-body');
    const timerPill = document.getElementById('timer-pill');
    const timerLabel = document.getElementById('timer-label');
    const pauseButton = document.getElementById('pause-btn');
    const pausedNote = document.getElementById('paused-note');
    const sendButton = document.getElementById('send-btn');
    const confirmBox = document.getElementById('send-confirm');
    const confirmText = document.getElementById('send-confirm-text');
    const confirmList = document.getElementById('send-confirm-list');
    const confirmYes = document.getElementById('confirm-yes');
    const confirmNo = document.getElementById('confirm-no');
    const timeUsedField = document.getElementById('time-used');
    const prevButton = document.getElementById('wt-prev');
    const nextButton = document.getElementById('wt-next');
    const panels = Array.from(form.querySelectorAll('[data-panel]'));
    const tabs = Array.from(form.querySelectorAll('[data-tab]'));
    const areas = Array.from(form.querySelectorAll('.wt-input'));

    const duration = parseInt(form.dataset.duration, 10);
    let remaining = duration;
    let paused = false;
    let sent = false;
    let confirmed = false;
    let last = Date.now();
    let current = 0;

    // ---------- words ----------
    function countWords(text) {
        const found = text.match(/\S+/g);
        return found ? found.length : 0;
    }

    function wordsLabel(count) {
        return count + (count === 1 ? ' word' : ' words');
    }

    function paint(area) {
        const words = countWords(area.value);
        const panel = area.closest('[data-panel]');
        panel.querySelector('.wt-words').textContent = wordsLabel(words);
        const goal = parseInt(area.dataset.goal, 10);
        const low = parseInt(area.dataset.low, 10);
        const high = parseInt(area.dataset.high, 10);
        const bar = panel.querySelector('.wc-bar span');
        bar.style.width = Math.min(100, (words / goal) * 100) + '%';
        bar.className = words > high ? 'is-over' : (words >= low ? 'is-ok' : '');
        const tabCount = form.querySelector('[data-tab-count="' + area.dataset.slot + '"]');
        if (tabCount) {
            tabCount.textContent = words;
        }
    }

    // ---------- tasks ----------
    function show(index) {
        current = Math.max(0, Math.min(panels.length - 1, index));
        panels.forEach(function (panel, position) { panel.hidden = position !== current; });
        tabs.forEach(function (tab, position) {
            tab.classList.toggle('is-active', position === current);
            tab.setAttribute('aria-selected', position === current ? 'true' : 'false');
        });
        prevButton.disabled = current === 0;
        nextButton.disabled = current === panels.length - 1;
    }

    tabs.forEach(function (tab, position) {
        tab.addEventListener('click', function () { show(position); });
    });
    prevButton.addEventListener('click', function () { show(current - 1); });
    nextButton.addEventListener('click', function () { show(current + 1); });

    // ---------- phrases: tapping one adds it to the answer being written ----------
    function addText(area, text) {
        const start = typeof area.selectionStart === 'number' ? area.selectionStart : area.value.length;
        const end = typeof area.selectionEnd === 'number' ? area.selectionEnd : start;
        const before = area.value.slice(0, start);
        const after = area.value.slice(end);
        const glue = before && !/\s$/.test(before) ? ' ' : '';
        area.value = before + glue + text + after;
        const caret = (before + glue + text).length;
        area.focus();
        area.setSelectionRange(caret, caret);
        area.dispatchEvent(new Event('input', { bubbles: true }));
    }

    form.addEventListener('click', function (event) {
        const phrase = event.target.closest('[data-phrase]');
        if (!phrase) {
            return;
        }
        addText(phrase.closest('[data-panel]').querySelector('.wt-input'), phrase.dataset.phrase);
    });

    // ---------- sending ----------
    function hideConfirm() {
        confirmBox.hidden = true;
    }

    function askToSend() {
        let empty = 0;
        confirmList.textContent = '';
        areas.forEach(function (area) {
            const words = countWords(area.value);
            if (words === 0) {
                empty += 1;
            }
            const item = document.createElement('li');
            item.textContent = area.dataset.label + ': ' + wordsLabel(words) + ' (target ' + area.dataset.target + ' words)';
            confirmList.appendChild(item);
        });
        confirmText.textContent = (empty ? 'Some tasks are still empty. ' : '')
            + 'Send your writing to your teacher? You cannot change it after this.';
        confirmBox.hidden = false;
        confirmYes.focus();
        if (confirmBox.scrollIntoView) {
            confirmBox.scrollIntoView({ block: 'nearest' });
        }
    }

    function keepWriting() {
        hideConfirm();
        areas[current].focus();
    }

    function lockForm() {
        sent = true;
        sendButton.disabled = true;
        confirmYes.disabled = true;
        confirmNo.disabled = true;
        timeUsedField.value = String(Math.max(0, Math.min(duration, Math.round(duration - remaining))));
    }

    function sendNow() {
        if (sent) {
            return;
        }
        confirmed = true;
        if (form.requestSubmit) {
            form.requestSubmit();
        } else {
            lockForm();
            form.submit();
        }
    }

    // The button only asks; the writing really goes out after "Yes, send" (or when the time is over).
    form.addEventListener('submit', function (event) {
        if (!confirmed) {
            event.preventDefault();
            askToSend();
            return;
        }
        lockForm();
    });
    confirmYes.addEventListener('click', sendNow);
    confirmNo.addEventListener('click', keepWriting);
    form.addEventListener('input', hideConfirm);
    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && !confirmBox.hidden) {
            keepWriting();
        }
    });

    // Leaving before sending throws the writing away, so ask first.
    window.addEventListener('beforeunload', function (event) {
        const wrote = areas.some(function (area) { return area.value.trim() !== ''; });
        if (!sent && wrote) {
            event.preventDefault();
            event.returnValue = '';
        }
    });

    // ---------- timer ----------
    function formatTimer(seconds) {
        const whole = Math.max(0, Math.ceil(seconds));
        return String(Math.floor(whole / 60)).padStart(2, '0') + ':' + String(whole % 60).padStart(2, '0');
    }

    function renderTimer() {
        timerLabel.textContent = formatTimer(remaining);
        timerPill.classList.toggle('is-low', remaining <= WARNING_SECONDS);
    }

    const ticker = setInterval(function () {
        const now = Date.now();
        const elapsed = (now - last) / 1000;
        last = now;
        if (paused || sent) {
            return;
        }
        remaining -= elapsed;
        renderTimer();
        if (remaining <= 0) {
            clearInterval(ticker);
            sendNow();
        }
    }, 250);

    pauseButton.addEventListener('click', function () {
        paused = !paused;
        last = Date.now();
        body.classList.toggle('is-paused', paused);
        body.inert = paused;
        pausedNote.hidden = !paused;
        pauseButton.textContent = paused ? '▶ Resume' : '⏸ Pause';
        if (paused && document.activeElement && document.activeElement.blur) {
            document.activeElement.blur();
        }
    });

    areas.forEach(function (area) {
        area.addEventListener('input', function () { paint(area); });
        paint(area);
    });
    show(0);
    renderTimer();
})();
