(function () {
    const READ_ALOUD_KEY = 'speaking.readAloud';

    // ---------- the speaker buttons read a question aloud (hidden when the browser cannot speak) ----------
    const speakButtons = Array.from(document.querySelectorAll('[data-speak]'));
    const synth = window.speechSynthesis;

    // An English voice if the computer has one (otherwise the browser would read English with its default voice).
    function englishVoice() {
        const voices = typeof synth.getVoices === 'function' ? synth.getVoices() : [];
        return voices.find(function (voice) { return /^en[-_]GB/i.test(voice.lang); })
            || voices.find(function (voice) { return /^en[-_]US/i.test(voice.lang); })
            || voices.find(function (voice) { return /^en/i.test(voice.lang); })
            || null;
    }

    if (!synth || typeof window.SpeechSynthesisUtterance === 'undefined') {
        speakButtons.forEach(function (button) { button.hidden = true; });
    } else {
        englishVoice(); // some browsers only start loading their voices when asked
        document.addEventListener('click', function (event) {
            const button = event.target.closest('[data-speak]');
            if (!button) {
                return;
            }
            synth.cancel();
            speakButtons.forEach(function (other) { other.classList.remove('is-speaking'); });
            const utterance = new window.SpeechSynthesisUtterance(button.dataset.speak);
            const voice = englishVoice();
            utterance.lang = voice ? voice.lang : 'en-GB';
            if (voice) {
                utterance.voice = voice;
            }
            const done = function () { button.classList.remove('is-speaking'); };
            utterance.onend = done;
            utterance.onerror = done;
            button.classList.add('is-speaking');
            synth.speak(utterance);
        });
        // leaving the page must not leave the voice talking
        window.addEventListener('pagehide', function () { synth.cancel(); });
    }

    // ---------- a recording made in the browser has no length in its header: ask for the end once so the player shows it ----------
    Array.from(document.querySelectorAll('audio[data-fix-duration]')).forEach(function (audio) {
        audio.addEventListener('loadedmetadata', function () {
            if (audio.duration !== Infinity) {
                return;
            }
            audio.currentTime = 1e101;
            audio.addEventListener('timeupdate', function reset() {
                audio.removeEventListener('timeupdate', reset);
                audio.currentTime = 0;
            });
        });
    });

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
