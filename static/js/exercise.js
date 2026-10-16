(function () {
    const WARNING_SECONDS = 180;

    const form = document.getElementById('exercise-form');
    if (!form) {
        return;
    }
    const body = document.getElementById('exercise-body');
    const timerPill = document.getElementById('timer-pill');
    const timerLabel = document.getElementById('timer-label');
    const pauseButton = document.getElementById('pause-btn');
    const pausedNote = document.getElementById('paused-note');
    const submitButton = document.getElementById('submit-btn');
    const confirmBox = document.getElementById('submit-confirm');
    const confirmText = document.getElementById('submit-confirm-text');
    const confirmYes = document.getElementById('confirm-yes');
    const confirmNo = document.getElementById('confirm-no');
    const timeUsedField = document.getElementById('time-used');
    const audios = Array.from(document.querySelectorAll('audio'));

    const duration = parseInt(form.dataset.duration, 10);
    let remaining = duration;
    let paused = false;
    let submitted = false;
    let confirmed = false;
    let last = Date.now();

    function formatTimer(seconds) {
        const whole = Math.max(0, Math.ceil(seconds));
        return String(Math.floor(whole / 60)).padStart(2, '0') + ':' + String(whole % 60).padStart(2, '0');
    }

    function renderTimer() {
        timerLabel.textContent = formatTimer(remaining);
        timerPill.classList.toggle('is-low', remaining <= WARNING_SECONDS);
    }

    // Names of the questions (q<id>) that have no answer yet: radios count once per group.
    function unansweredNames() {
        const answered = {};
        form.querySelectorAll('input, select, textarea').forEach(function (field) {
            if (!/^q\d+$/.test(field.name)) {
                return;
            }
            if (!(field.name in answered)) {
                answered[field.name] = false;
            }
            const filled = field.type === 'radio' || field.type === 'checkbox' ? field.checked : field.value.trim() !== '';
            if (filled) {
                answered[field.name] = true;
            }
        });
        return Object.keys(answered).filter(function (name) { return !answered[name]; });
    }

    function hideConfirm() {
        confirmBox.hidden = true;
    }

    function askToSubmit() {
        const missing = unansweredNames().length;
        const ending = 'Submit all parts now? You cannot change answers after this.';
        if (missing === 0) {
            confirmText.textContent = ending;
        } else {
            confirmText.textContent = 'You still have ' + missing + ' unanswered question' + (missing === 1 ? '' : 's') + '. ' + ending;
        }
        confirmBox.hidden = false;
        confirmYes.focus();
        if (confirmBox.scrollIntoView) {
            confirmBox.scrollIntoView({ block: 'nearest' });
        }
    }

    function keepWorking() {
        hideConfirm();
        const first = unansweredNames()[0];
        const field = first && form.querySelector('[name="' + first + '"]');
        if (field && field.focus) {
            field.focus();
        } else {
            submitButton.focus();
        }
    }

    // Called right before the answers leave: remembers how long the student really worked (pauses excluded).
    function lockForm() {
        submitted = true;
        submitButton.disabled = true;
        confirmYes.disabled = true;
        confirmNo.disabled = true;
        if (timeUsedField) {
            timeUsedField.value = String(Math.max(0, Math.min(duration, Math.round(duration - remaining))));
        }
    }

    function submitNow() {
        if (submitted) {
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

    // The button only asks; the form really goes out after "Yes, submit" (or when the time is over).
    form.addEventListener('submit', function (event) {
        if (!confirmed) {
            event.preventDefault();
            askToSubmit();
            return;
        }
        lockForm();
    });

    confirmYes.addEventListener('click', submitNow);
    confirmNo.addEventListener('click', keepWorking);
    // Answering again makes the counted message stale, so the question simply goes away.
    form.addEventListener('change', hideConfirm);
    form.addEventListener('input', hideConfirm);
    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && !confirmBox.hidden) {
            keepWorking();
        }
    });

    // Enter inside a gap must not submit the whole exercise: it moves to the next gap instead.
    form.addEventListener('keydown', function (event) {
        if (event.key !== 'Enter' || !event.target.classList.contains('gap-input')) {
            return;
        }
        event.preventDefault();
        const gaps = Array.from(form.querySelectorAll('.gap-input'));
        const next = gaps[gaps.indexOf(event.target) + 1];
        if (next) {
            next.focus();
        }
    });

    const ticker = setInterval(function () {
        const now = Date.now();
        const elapsed = (now - last) / 1000;
        last = now;
        if (paused || submitted) {
            return;
        }
        remaining -= elapsed;
        renderTimer();
        if (remaining <= 0) {
            clearInterval(ticker);
            submitNow();
        }
    }, 250);

    pauseButton.addEventListener('click', function () {
        paused = !paused;
        last = Date.now();
        body.classList.toggle('is-paused', paused);
        pausedNote.hidden = !paused;
        pauseButton.textContent = paused ? '▶ Resume' : '⏸ Pause';
        if (paused) {
            audios.forEach(function (audio) { audio.pause(); });
        }
    });

    renderTimer();
})();
