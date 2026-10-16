(function () {
    'use strict';

    const configElement = document.getElementById('sp-config');
    const startButton = document.getElementById('start-btn');
    if (!configElement || !startButton) {
        return;
    }

    const byId = function (id) { return document.getElementById(id); };
    const intro = byId('sp-intro');
    const run = byId('sp-run');
    const startNote = byId('start-note');
    const secureNote = byId('secure-note'); // only there when the server has an https address for this page
    const micHelp = byId('mic-help');
    const micRecheck = byId('mic-recheck');
    const supportNote = byId('sp-support'); // not there when the server turns the recordings into text itself
    const readAloudBox = byId('read-aloud');
    const stage = byId('sp-stage');
    const circle = byId('sp-circle-text');
    const stageTitle = byId('sp-stage-title');
    const stageHint = byId('sp-stage-hint');
    const bar = byId('sp-bar');
    const questionBox = byId('sp-question');
    const steps = byId('sp-steps');
    const stepLabel = byId('sp-step-label');
    const stepCount = byId('sp-step-count');
    const actions = byId('sp-actions');
    const stopButton = byId('sp-stop');
    const nextButton = byId('sp-next');
    const stopConfirm = byId('sp-stop-confirm');
    const finishing = byId('sp-finishing');
    const finishingText = byId('sp-finishing-text');
    const finishingRetry = byId('sp-finishing-retry');

    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const synth = window.speechSynthesis;
    const canSpeak = Boolean(synth) && typeof window.SpeechSynthesisUtterance !== 'undefined';
    const RECORDING_TYPES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'];

    // What each stage shows: the circle, the title, the hint under it and what the button on the right does.
    const STAGES = {
        listen: { title: 'Listen to the question', hint: '', next: 'Skip →' },
        prepare: { title: '⏳ Prepare', hint: 'Think about what you will say.', next: 'Start speaking now →' },
        speak: { title: '🗣️ Speak now', hint: 'Speak until the timer ends.', next: "I'm done →" },
    };

    let config = null;
    let stream = null;
    let audioContext = null;
    let recordingType = '';
    let readAloud = false;
    let active = null; // the stage that is running: { finish(reason) } (what Skip / I'm done / Stop end)
    let running = false;
    let aborted = false;
    let sent = false;
    const answers = [];

    if (!Recognition && supportNote) {
        supportNote.hidden = false;
    }
    if (canSpeak && typeof synth.getVoices === 'function') {
        synth.getVoices(); // some browsers only start loading their voices when asked
    }

    // ---------- small helpers ----------
    function clock(seconds) {
        const whole = Math.max(0, Math.ceil(seconds));
        return Math.floor(whole / 60) + ':' + String(whole % 60).padStart(2, '0');
    }

    function showNote(text, kind) {
        startNote.textContent = text;
        startNote.className = 'sp-mic-note is-' + (kind || 'error');
        startNote.hidden = false;
    }

    function setBar(fraction) {
        bar.style.width = Math.round(Math.min(1, Math.max(0, fraction)) * 100) + '%';
    }

    function showStage(name) {
        stage.dataset.stage = name;
        stageTitle.textContent = STAGES[name].title;
        stageHint.textContent = STAGES[name].hint;
        nextButton.textContent = STAGES[name].next;
        circle.textContent = name === 'listen' ? '🔊' : '';
        setBar(0);
    }

    function showQuestion(index) {
        const total = config.questions.length;
        questionBox.textContent = config.questions[index].text;
        stepLabel.textContent = 'Question ' + (index + 1) + ' of ' + total;
        stepCount.textContent = (index + 1) + ' / ' + total;
        Array.from(steps.children).forEach(function (segment, position) {
            segment.className = position < index ? 'is-done' : (position === index ? 'is-current' : '');
        });
    }

    // Runs a stage that lasts `seconds`; the stage ends early when the button (or Stop) calls active.finish(reason).
    function countdown(seconds, onTick) {
        return new Promise(function (resolve) {
            const started = performance.now();
            let finished = false;
            let timer = null;
            function finish(reason) {
                if (finished) {
                    return;
                }
                finished = true;
                clearInterval(timer);
                active = null;
                resolve({ reason: reason, elapsed: Math.min(seconds, (performance.now() - started) / 1000) });
            }
            function tick() {
                const elapsed = (performance.now() - started) / 1000;
                onTick(Math.min(elapsed, seconds));
                if (elapsed >= seconds) {
                    finish('time');
                }
            }
            active = { finish: finish };
            timer = setInterval(tick, 100);
            tick();
        });
    }

    // ---------- the question is read aloud ----------
    // An English voice if the computer has one (otherwise the browser would read English with its default voice).
    function englishVoice() {
        const voices = canSpeak && typeof synth.getVoices === 'function' ? synth.getVoices() : [];
        return voices.find(function (voice) { return /^en[-_]GB/i.test(voice.lang); })
            || voices.find(function (voice) { return /^en[-_]US/i.test(voice.lang); })
            || voices.find(function (voice) { return /^en/i.test(voice.lang); })
            || null;
    }

    function listen(text) {
        return new Promise(function (resolve) {
            showStage('listen');
            const started = performance.now();
            const estimate = Math.max(1.5, text.split(/\s+/).length * 0.45); // seconds; the bar only needs to look right
            let finished = false;
            let timer = null;
            let safety = null;
            function finish(reason) {
                if (finished) {
                    return;
                }
                finished = true;
                clearInterval(timer);
                clearTimeout(safety);
                active = null;
                synth.cancel();
                setBar(1);
                resolve(reason);
            }
            active = { finish: finish };
            timer = setInterval(function () {
                setBar(Math.min(0.95, (performance.now() - started) / 1000 / estimate));
            }, 100);
            safety = setTimeout(function () { finish('timeout'); }, (estimate + 10) * 1000);
            const utterance = new window.SpeechSynthesisUtterance(text);
            const voice = englishVoice();
            utterance.lang = voice ? voice.lang : 'en-GB';
            if (voice) {
                utterance.voice = voice;
            }
            utterance.onend = function () { finish('end'); };
            utterance.onerror = function () { finish('error'); };
            synth.cancel();
            synth.speak(utterance);
        });
    }

    // ---------- the answer is recorded and turned into text ----------
    function beep() {
        return new Promise(function (resolve) {
            if (!audioContext) {
                resolve();
                return;
            }
            try {
                const oscillator = audioContext.createOscillator();
                const gain = audioContext.createGain();
                oscillator.type = 'sine';
                oscillator.frequency.value = 880;
                gain.gain.value = 0.15;
                oscillator.connect(gain);
                gain.connect(audioContext.destination);
                oscillator.onended = function () { setTimeout(resolve, 120); }; // do not record the beep itself
                oscillator.start();
                oscillator.stop(audioContext.currentTime + 0.25);
            } catch (error) {
                resolve();
            }
        });
    }

    function startRecording() {
        const none = { stop: function () { return Promise.resolve(null); } };
        if (!stream || typeof window.MediaRecorder === 'undefined') {
            return none;
        }
        const chunks = [];
        let recorder;
        try {
            recorder = recordingType ? new window.MediaRecorder(stream, { mimeType: recordingType }) : new window.MediaRecorder(stream);
        } catch (error) {
            return none;
        }
        const stopped = new Promise(function (resolve) {
            recorder.onstop = function () {
                resolve(chunks.length ? new Blob(chunks, { type: recorder.mimeType || recordingType || 'audio/webm' }) : null);
            };
        });
        recorder.ondataavailable = function (event) {
            if (event.data && event.data.size) {
                chunks.push(event.data);
            }
        };
        recorder.start();
        return {
            stop: function () {
                if (recorder.state !== 'inactive') {
                    recorder.stop();
                }
                return stopped;
            },
        };
    }

    // Chrome ends a recognition after a pause in speech, so it is started again until the answer is over.
    function startRecognition() {
        const heard = { text: '', confidence: null };
        if (!Recognition) {
            return { stop: function () { return Promise.resolve(heard); } };
        }
        const confidences = [];
        let listening = true;
        let ended = false; // the recogniser is over and will not report again
        let finishedWaiting = null;
        let recognition = null;

        function over() {
            ended = true;
            if (finishedWaiting) {
                finishedWaiting();
            }
        }

        function begin() {
            recognition = new Recognition();
            recognition.lang = 'en-US';
            recognition.continuous = true;
            recognition.interimResults = false;
            recognition.maxAlternatives = 1;
            recognition.onresult = function (event) {
                for (let index = event.resultIndex; index < event.results.length; index += 1) {
                    const result = event.results[index];
                    if (result.isFinal) {
                        heard.text += result[0].transcript + ' ';
                        if (typeof result[0].confidence === 'number' && result[0].confidence > 0) {
                            confidences.push(result[0].confidence);
                        }
                    }
                }
            };
            recognition.onerror = function (event) {
                if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
                    listening = false; // the browser will not let it listen: do not keep trying
                }
            };
            recognition.onend = function () {
                if (!listening) {
                    over();
                    return;
                }
                setTimeout(function () {
                    if (!listening) {
                        over();
                        return;
                    }
                    try {
                        begin();
                    } catch (error) {
                        listening = false;
                        over();
                    }
                }, 150);
            };
            recognition.start();
        }

        try {
            begin();
        } catch (error) {
            return { stop: function () { return Promise.resolve(heard); } };
        }
        return {
            stop: function () {
                return new Promise(function (resolve) {
                    listening = false;
                    if (ended) {
                        resolve();
                        return;
                    }
                    finishedWaiting = resolve;
                    setTimeout(resolve, 2500); // a recogniser that never reports back must not hold the practice up
                    try { recognition.stop(); } catch (error) { resolve(); }
                }).then(function () {
                    heard.text = heard.text.trim();
                    if (confidences.length) {
                        heard.confidence = confidences.reduce(function (sum, value) { return sum + value; }, 0) / confidences.length;
                    }
                    return heard;
                });
            },
        };
    }

    // ---------- one question: listen, prepare, speak ----------
    async function prepare() {
        showStage('prepare');
        await countdown(config.think, function (elapsed) {
            circle.textContent = clock(config.think - elapsed);
            setBar(elapsed / config.think);
        });
    }

    async function speak() {
        showStage('speak');
        circle.textContent = clock(config.talk);
        await beep();
        if (aborted) {
            return null;
        }
        const recording = startRecording();
        const recognition = startRecognition();
        const result = await countdown(config.talk, function (elapsed) {
            circle.textContent = clock(config.talk - elapsed);
            setBar(elapsed / config.talk);
        });
        const heard = await recognition.stop();
        const blob = await recording.stop();
        return {
            transcript: heard.text,
            confidence: heard.confidence,
            seconds: result.elapsed,
            early: result.reason === 'next' && config.talk - result.elapsed > 0.5,
            blob: blob,
        };
    }

    async function ask(index) {
        showQuestion(index);
        if (readAloud) {
            await listen(config.questions[index].text);
            if (aborted) {
                return;
            }
        }
        await prepare();
        if (aborted) {
            return;
        }
        const answer = await speak();
        if (aborted || !answer) {
            return;
        }
        answer.id = config.questions[index].id;
        answers.push(answer);
    }

    // ---------- sending the answers ----------
    // After the last answer only the "checking" card is left (and "Try again" when sending did not work).
    function showFinishing(text, canRetry) {
        finishingText.textContent = text;
        finishingRetry.hidden = !canRetry;
        finishing.hidden = false;
        stage.hidden = true;
        actions.hidden = true;
        stopConfirm.hidden = true;
        Array.from(steps.children).forEach(function (segment) { segment.className = 'is-done'; });
    }

    async function send() {
        const form = new FormData();
        answers.forEach(function (answer, index) {
            form.append('question_' + index, answer.id);
            form.append('transcript_' + index, answer.transcript);
            form.append('seconds_' + index, answer.seconds.toFixed(1));
            form.append('early_' + index, answer.early ? '1' : '0');
            if (answer.confidence !== null) {
                form.append('confidence_' + index, answer.confidence.toFixed(3));
            }
            if (answer.blob) {
                form.append('audio_' + index, answer.blob, 'answer.webm');
            }
        });
        showFinishing('🤖 Checking your answers… this takes a few seconds.', false);
        try {
            const response = await fetch(config.finishUrl, {
                method: 'POST',
                body: form,
                credentials: 'same-origin',
                headers: { 'X-CSRFToken': run.querySelector('[name=csrfmiddlewaretoken]').value },
            });
            const data = await response.json();
            if (!response.ok || !data.url) {
                throw new Error(data.error || 'Something went wrong.');
            }
            sent = true;
            window.location.href = data.url;
        } catch (error) {
            showFinishing((error.message || 'Something went wrong.') + ' Your answers are still here: press Try again.', true);
        }
    }

    function releaseDevices() {
        if (stream) {
            stream.getTracks().forEach(function (track) { track.stop(); });
            stream = null;
        }
        if (audioContext) {
            audioContext.close().catch(function () {});
            audioContext = null;
        }
        if (canSpeak) {
            synth.cancel();
        }
    }

    function abort() {
        aborted = true;
        running = false;
        if (active) {
            active.finish('abort');
        }
        releaseDevices();
    }

    // ---------- the microphone: the browser's own Allow / Block pop-up ----------
    let permission = null; // the browser's PermissionStatus of the microphone, when it can tell
    let starting = false;

    function microphoneMissing() {
        return !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia;
    }

    function microphoneState() {
        return permission ? permission.state : 'unknown';
    }

    // The browser has no microphone for this page. Over plain http (not localhost) that is always so: the page offers
    // the https address of the same page when the server has one.
    function showInsecure() {
        if (secureNote) {
            startNote.hidden = true;
            secureNote.hidden = false;
        } else {
            showNote('This page cannot use the microphone. Open the site at http://localhost or over https, in a recent Chrome or Edge.');
        }
    }

    function showAllowed() {
        micHelp.hidden = true;
        showNote('✓ The microphone is allowed. Press Start when you are ready.', 'ok');
    }

    // Asks the browser for the microphone: unless it was decided before, the browser opens its pop-up by itself.
    async function askForMicrophone() {
        showNote('Your browser is asking to use the microphone. Press Allow in its pop-up (near the address bar).', 'wait');
        try {
            const probe = await navigator.mediaDevices.getUserMedia({ audio: true });
            probe.getTracks().forEach(function (track) { track.stop(); });
            return null;
        } catch (error) {
            return error;
        }
    }

    // Says what went wrong in words the student can act on.
    function explain(error) {
        const name = error && error.name;
        if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
            showNote('No microphone was found. Plug in a microphone or headset and press Start again.');
        } else if (name === 'NotReadableError' || name === 'TrackStartError' || name === 'AbortError') {
            showNote('The microphone is busy or not answering. Close other apps that use it (Zoom, Teams, Telegram calls...) and press Start again.');
        } else if (name === 'NotAllowedError' || name === 'SecurityError' || name === 'PermissionDeniedError') {
            if (microphoneState() === 'prompt') {
                showNote('The permission pop-up was closed. Press Start again and choose Allow.');
            } else {
                micHelp.hidden = false;
                showNote(microphoneState() === 'denied'
                    ? 'The microphone is blocked: follow the steps below.'
                    : 'We could not use your microphone. Allow it in the browser (the icon next to the address bar) and press Start again.');
            }
        } else {
            showNote('We could not start the microphone' + (name ? ' (' + name + ')' : '') + '. Press Start again.');
        }
    }

    function reflectPermission() {
        const state = microphoneState();
        if (state === 'denied') {
            micHelp.hidden = false;
            showNote('The microphone is blocked: follow the steps below.');
        } else if (state === 'granted' && !starting && !running) {
            showAllowed();
        } else if (state === 'prompt') {
            micHelp.hidden = true;
        }
    }

    // On opening the page: see where the permission stands and, while it is undecided, ask for it right away so the
    // browser's pop-up is already open when the student gets to Start.
    async function checkMicrophone() {
        if (microphoneMissing()) {
            showInsecure();
            return;
        }
        if (navigator.permissions && navigator.permissions.query) {
            try {
                permission = await navigator.permissions.query({ name: 'microphone' });
                permission.onchange = reflectPermission;
            } catch (error) {
                permission = null; // this browser cannot tell
            }
        }
        reflectPermission();
        if (microphoneState() === 'prompt' || microphoneState() === 'unknown') {
            const error = await askForMicrophone();
            if (error) {
                explain(error);
            } else if (!starting && !running) {
                showAllowed();
            }
        }
    }

    // ---------- starting ----------
    async function start() {
        config = JSON.parse(configElement.textContent);
        if (microphoneMissing()) {
            showInsecure();
            return;
        }
        startButton.disabled = true;
        starting = true;
        if (microphoneState() === 'granted') {
            startNote.hidden = true;
        } else {
            showNote('Your browser is asking to use the microphone. Press Allow in its pop-up (near the address bar).', 'wait');
        }
        try {
            stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        } catch (error) {
            starting = false;
            startButton.disabled = false;
            explain(error);
            return;
        }
        starting = false;
        startNote.hidden = true;
        micHelp.hidden = true;
        if (typeof window.MediaRecorder !== 'undefined' && window.MediaRecorder.isTypeSupported) {
            recordingType = RECORDING_TYPES.filter(function (type) { return window.MediaRecorder.isTypeSupported(type); })[0] || '';
        }
        try {
            const Context = window.AudioContext || window.webkitAudioContext;
            audioContext = Context ? new Context() : null;
            if (audioContext && audioContext.resume) {
                audioContext.resume();
            }
        } catch (error) {
            audioContext = null;
        }
        readAloud = canSpeak && readAloudBox.checked;
        config.questions.forEach(function () { steps.appendChild(document.createElement('span')); });
        intro.hidden = true;
        run.hidden = false;
        window.scrollTo(0, 0);

        running = true;
        for (let index = 0; index < config.questions.length; index += 1) {
            await ask(index);
            if (aborted) {
                return;
            }
        }
        running = false;
        releaseDevices();
        await send();
    }

    startButton.addEventListener('click', start);
    micRecheck.addEventListener('click', async function () {
        const error = await askForMicrophone();
        if (error) {
            explain(error);
        } else {
            showAllowed();
        }
    });
    nextButton.addEventListener('click', function () {
        if (active) {
            active.finish('next');
        }
    });
    stopButton.addEventListener('click', function () {
        stopConfirm.hidden = false;
        byId('sp-stop-yes').focus();
    });
    byId('sp-stop-no').addEventListener('click', function () { stopConfirm.hidden = true; });
    byId('sp-stop-yes').addEventListener('click', function () {
        abort();
        window.location.href = config.backUrl;
    });
    finishingRetry.addEventListener('click', send);
    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && !stopConfirm.hidden) {
            stopConfirm.hidden = true;
        }
    });
    window.addEventListener('beforeunload', function (event) {
        if ((running || (answers.length && !sent)) && !aborted) {
            event.preventDefault();
            event.returnValue = '';
        }
    });

    checkMicrophone();
})();
