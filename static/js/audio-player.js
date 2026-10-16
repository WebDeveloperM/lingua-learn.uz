// The exercise audio widget (play button, seek bar, time). Used by the exercise page and by its results page.
(function () {
    function formatTime(seconds) {
        const whole = Math.floor(seconds || 0);
        return Math.floor(whole / 60) + ':' + String(whole % 60).padStart(2, '0');
    }

    document.querySelectorAll('[data-audio-player]').forEach(function (root) {
        const audio = root.querySelector('audio');
        const button = root.querySelector('.play-btn');
        const range = root.querySelector('.audio-range');
        const label = root.querySelector('.audio-time');
        let seeking = false;

        function paintRange() {
            range.style.setProperty('--fill', (range.value / 10) + '%');
        }

        button.addEventListener('click', function () {
            if (audio.paused) {
                const attempt = audio.play();
                if (attempt && attempt.catch) {
                    attempt.catch(function () {});
                }
            } else {
                audio.pause();
            }
        });

        audio.addEventListener('play', function () {
            button.textContent = '❚❚';
            button.classList.add('is-playing');
            button.setAttribute('aria-label', 'Pause audio');
        });

        function showStopped() {
            button.textContent = '▶';
            button.classList.remove('is-playing');
            button.setAttribute('aria-label', 'Play audio');
        }
        audio.addEventListener('pause', showStopped);
        audio.addEventListener('ended', showStopped);

        audio.addEventListener('timeupdate', function () {
            if (!seeking && audio.duration) {
                range.value = Math.round((audio.currentTime / audio.duration) * 1000);
            }
            label.textContent = formatTime(audio.currentTime);
            paintRange();
        });

        range.addEventListener('input', function () {
            seeking = true;
            if (audio.duration) {
                audio.currentTime = (range.value / 1000) * audio.duration;
                label.textContent = formatTime(audio.currentTime);
            }
            paintRange();
        });
        range.addEventListener('change', function () { seeking = false; });
    });
})();
