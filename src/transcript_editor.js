// Session-only transcript editing. Stable diarization IDs and source text never change.
(() => {
    const dataElement = document.getElementById('transcript-editor-data');
    if (!dataElement || !dataElement.textContent) return;
    const initial = JSON.parse(dataElement.textContent);

    document.addEventListener('DOMContentLoaded', () => {
        const rows = Array.from(document.querySelectorAll('.transcript-chunk'));
        const phrases = initial.phrases.map(phrase => ({...phrase, correctedText: phrase.text}));
        const speakerNames = new Map();
        phrases.forEach(phrase => {
            if (phrase.speaker_id) speakerNames.set(phrase.speaker_id, phrase.speaker_name || phrase.speaker_id);
        });
        const snapshots = new WeakMap();
        const exportBox = document.getElementById('corrections-json');
        const feedbackStatus = document.getElementById('feedback-status');
        const copyStatus = document.getElementById('copy-status');
        const jsonCopyStatus = document.getElementById('json-copy-status');
        const cleanText = value => value.replace(/\s+/gu, ' ').trim();

        function wordHint(original, corrected) {
            const before = original.match(/\S+/gu) || [];
            const after = corrected.match(/\S+/gu) || [];
            let prefix = 0;
            while (prefix < before.length && prefix < after.length && before[prefix] === after[prefix]) prefix++;
            let suffix = 0;
            while (suffix < before.length - prefix && suffix < after.length - prefix &&
                   before[before.length - suffix - 1] === after[after.length - suffix - 1]) suffix++;
            return {
                original: before.slice(prefix, before.length - suffix).join(' '),
                replacement: after.slice(prefix, after.length - suffix).join(' ')
            };
        }

        function updateExport() {
            jsonCopyStatus.textContent = '';
            const regions = phrases.filter(p => p.correctedText !== p.text).map(p => ({
                segment_id: p.segment_id,
                start_seconds: p.start_seconds,
                end_seconds: p.end_seconds,
                speaker_id: p.speaker_id,
                speaker_name: p.speaker_id ? speakerNames.get(p.speaker_id) : null,
                original_text: p.text,
                corrected_text: p.correctedText,
                word_hints: [wordHint(p.text, p.correctedText)]
            }));
            const speakers = Array.from(speakerNames, ([speaker_id, name]) => ({speaker_id, name}));
            exportBox.value = JSON.stringify({
                schema_version: 1,
                type: 'video-auto-index.transcript-feedback',
                source: initial.source,
                speakers,
                regions
            }, null, 2);
            const renamed = speakers.filter(s => s.name !== s.speaker_id).length;
            feedbackStatus.textContent = `${renamed} renamed speakers; ${regions.length} corrected phrases. ` +
                'Copy the JSON before reloading to keep your feedback.';
        }

        function updateSpeaker(speakerId, name, editingChip = null) {
            speakerNames.set(speakerId, name);
            document.querySelectorAll('.speaker-chip').forEach(chip => {
                if (chip.dataset.speakerId === speakerId && chip !== editingChip) chip.textContent = name;
            });
            updateExport();
        }

        function synchronize(element, kind, index) {
            const text = cleanText(element.textContent);
            if (kind === 'speaker') {
                const id = element.dataset.speakerId;
                updateSpeaker(id, text.slice(0, 120) || id, element);
            } else {
                phrases[index].correctedText = text;
                element.classList.toggle('corrected', text !== phrases[index].text);
                updateExport();
            }
        }

        function startEditing(element, selectAll) {
            if (element.hasAttribute('contenteditable')) return;
            const selection = window.getSelection();
            const saved = [];
            if (!selectAll && selection) {
                for (let i = 0; i < selection.rangeCount; i++) {
                    const range = selection.getRangeAt(i);
                    if (element.contains(range.startContainer) && element.contains(range.endContainer)) {
                        saved.push(range.cloneRange());
                    }
                }
            }
            snapshots.set(element, element.textContent);
            element.setAttribute('contenteditable', 'plaintext-only');
            element.setAttribute('aria-readonly', 'false');
            element.focus({preventScroll: true});
            if (selection) {
                selection.removeAllRanges();
                if (selectAll) {
                    const range = document.createRange();
                    range.selectNodeContents(element);
                    selection.addRange(range);
                } else saved.forEach(range => selection.addRange(range));
            }
        }

        function finishEditing(element, kind, index, cancel = false) {
            if (!element.hasAttribute('contenteditable')) return;
            if (cancel) element.textContent = snapshots.get(element);
            let text = cleanText(element.textContent);
            if (kind === 'speaker') text = text.slice(0, 120) || element.dataset.speakerId;
            element.textContent = text;
            element.removeAttribute('contenteditable');
            element.setAttribute('aria-readonly', 'true');
            synchronize(element, kind, index);
        }

        function editable(element, kind, index) {
            element.addEventListener('keydown', event => {
                if (event.isComposing) return;
                if (!element.hasAttribute('contenteditable')) {
                    if (event.key === 'Enter' || event.key === 'F2') {
                        event.preventDefault();
                        startEditing(element, true);
                    }
                } else if (event.key === 'Enter' || event.key === 'Escape') {
                    event.preventDefault();
                    finishEditing(element, kind, index, event.key === 'Escape');
                    element.blur();
                }
            });
            element.addEventListener('input', () => synchronize(element, kind, index));
            element.addEventListener('blur', () => finishEditing(element, kind, index));
            element.addEventListener('paste', event => {
                if (!element.hasAttribute('contenteditable')) return;
                event.preventDefault();
                const text = (event.clipboardData.getData('text/plain') || '').replace(/\s+/gu, ' ');
                // insertText keeps browser undo behavior and never inserts clipboard HTML.
                if (!document.execCommand('insertText', false, text)) {
                    const selection = window.getSelection();
                    if (selection && selection.rangeCount) {
                        const range = selection.getRangeAt(0);
                        if (!element.contains(range.commonAncestorContainer)) return;
                        range.deleteContents();
                        const node = document.createTextNode(text);
                        range.insertNode(node);
                        range.setStartAfter(node);
                        range.collapse(true);
                        selection.removeAllRanges();
                        selection.addRange(range);
                    }
                }
                synchronize(element, kind, index);
            });
        }

        rows.forEach((row, index) => {
            const phrase = row.querySelector('.phrase-text');
            editable(phrase, 'phrase', index);
            phrase.addEventListener('dblclick', () => startEditing(phrase, false));
            const chip = row.querySelector('.speaker-chip');
            if (chip) {
                editable(chip, 'speaker', index);
                chip.addEventListener('click', () => startEditing(chip, true));
            }
        });

        function transcriptText(indices) {
            return indices.map(index => {
                const p = phrases[index];
                const speaker = p.speaker_id ? speakerNames.get(p.speaker_id) : 'Unknown speaker';
                return `[${p.start_time}] ${speaker}: ${p.correctedText}`;
            }).join('\n');
        }

        async function copyText(text, message, status = copyStatus) {
            try {
                if (!navigator.clipboard || !navigator.clipboard.writeText) throw new Error('Clipboard unavailable');
                await navigator.clipboard.writeText(text);
            } catch (_) {
                // File URLs and browsers with restricted clipboard access still support manual copying.
                const previousFocus = document.activeElement;
                const selection = window.getSelection();
                const ranges = selection ? Array.from({length: selection.rangeCount}, (_, i) =>
                    selection.getRangeAt(i).cloneRange()) : [];
                const temporary = document.createElement('textarea');
                temporary.value = text;
                temporary.style.cssText = 'position:fixed;opacity:0;left:-9999px;top:0';
                document.body.appendChild(temporary);
                temporary.select();
                let copied = false;
                try { copied = document.execCommand('copy'); } catch (_) { /* Manual copy remains available. */ }
                temporary.remove();
                if (previousFocus && previousFocus.focus) previousFocus.focus({preventScroll: true});
                if (selection) {
                    selection.removeAllRanges();
                    ranges.forEach(range => selection.addRange(range));
                }
                if (!copied) {
                    status.textContent = 'Clipboard access is unavailable. Select text and copy with Ctrl/Cmd+C.';
                    return;
                }
            }
            status.textContent = message;
        }

        const copyAll = document.getElementById('copy-transcript');
        const copySelected = document.getElementById('copy-selected-phrases');
        [copyAll, copySelected].forEach(button => button.addEventListener('mousedown', event => event.preventDefault()));
        copyAll.addEventListener('click', () => copyText(transcriptText(phrases.map((_, i) => i)), 'Transcript copied.'));
        copySelected.addEventListener('click', () => {
            const selection = window.getSelection();
            if (!selection || selection.isCollapsed || !selection.rangeCount) {
                copyStatus.textContent = 'Select transcript text first.';
                return;
            }
            const indices = rows.flatMap((row, index) => {
                for (let i = 0; i < selection.rangeCount; i++) {
                    if (selection.getRangeAt(i).intersectsNode(row)) return [index];
                }
                return [];
            });
            if (!indices.length) {
                copyStatus.textContent = 'Select transcript text first.';
                return;
            }
            copyText(transcriptText(indices), `${indices.length} selected phrases copied.`);
        });
        document.getElementById('copy-corrections-json').addEventListener('click', () =>
            copyText(exportBox.value, 'Correction JSON copied.', jsonCopyStatus));
        exportBox.addEventListener('focus', () => exportBox.select());
        updateExport();
    });
})();
