// Key vocabulary of a Part: the search box above the word cards. The cards themselves are plain HTML (they can be
// opened and read without this script); the box is shown only when it can work.
(function () {
    'use strict';

    // Lower case, without accents and without apostrophes: Uzbek words are typed with ' ʻ ’ ` and people mix them up,
    // so "og'riq", "ogʻriq" and "ogriq" all find the same word.
    function normalise(text) {
        let plain = text.toLowerCase();
        if (typeof plain.normalize === 'function') {
            plain = plain.normalize('NFD').replace(/[̀-ͯ]/g, '');
        }
        return plain.replace(/['ʻʼ’‘`´′‛]/g, '');
    }

    function setUp(box) {
        const search = box.querySelector('.vocab-search');
        const status = box.querySelector('.vocab-status');
        if (!search || !status) {
            return;
        }
        // what a student can search for on a card: the word, its meaning and the example (not the transcription)
        const cards = Array.from(box.querySelectorAll('.vocab-card')).map(function (card) {
            const text = ['.vocab-word strong', '.vocab-meaning', '.vocab-example'].map(function (selector) {
                const part = card.querySelector(selector);
                return part ? part.textContent : '';
            }).join(' ');
            return { element: card, text: normalise(text) };
        });

        function filter() {
            const wanted = normalise(search.value).split(/\s+/).filter(Boolean);
            let shown = 0;
            cards.forEach(function (card) {
                // every typed word must be somewhere on the card, in any order
                const found = wanted.every(function (word) { return card.text.indexOf(word) !== -1; });
                card.element.hidden = !found;
                if (found) {
                    shown += 1;
                }
            });
            if (!wanted.length) {
                status.textContent = '';
            } else if (!shown) {
                status.textContent = 'No words found. Try another spelling.';
            } else {
                status.textContent = shown + ' of ' + cards.length + ' word' + (cards.length === 1 ? '' : 's');
            }
        }

        search.addEventListener('input', filter);
        search.hidden = false;
    }

    document.querySelectorAll('.vocab').forEach(setUp);
})();
