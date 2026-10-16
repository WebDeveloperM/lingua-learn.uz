(function () {
    const READ_ALOUD_KEY = 'speaking.readAloud';

    // ---------- the speaker buttons read a question aloud (hidden when the browser cannot speak) ----------
    const speakButtons = Array.from(document.querySelectorAll('[data-speak]'));
    const synth = window.speechSynthesis;
    if (!synth || typeof window.SpeechSynthesisUtterance === 'undefined') {
        speakButtons.forEach(function (button) { button.hidden = true; });
    } else {
        document.addEventListener('click', function (event) {
            const button = event.target.closest('[data-speak]');
            if (!button) {
                return;
            }
            synth.cancel();
            speakButtons.forEach(function (other) { other.classList.remove('is-speaking'); });
            const utterance = new window.SpeechSynthesisUtterance(button.dataset.speak);
            utterance.lang = 'en-GB';
            const done = function () { button.classList.remove('is-speaking'); };
            utterance.onend = done;
            utterance.onerror = done;
            button.classList.add('is-speaking');
            synth.speak(utterance);
        });
        // leaving the page must not leave the voice talking
        window.addEventListener('pagehide', function () { synth.cancel(); });
    }

    // ---------- "Read the questions aloud" is remembered between visits ----------
    const readAloud = document.getElementById('read-aloud');
    if (readAloud) {
        try {
            const saved = window.localStorage.getItem(READ_ALOUD_KEY);
            if (saved !== null) {
                readAloud.checked = saved === '1';
            }
        } catch (error) {
            // storage can be blocked: the box simply starts checked
        }
        readAloud.addEventListener('change', function () {
            try {
                window.localStorage.setItem(READ_ALOUD_KEY, readAloud.checked ? '1' : '0');
            } catch (error) {
                // nothing to do: the choice is only kept for this visit
            }
        });
    }
})();
