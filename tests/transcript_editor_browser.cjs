// Optional browser check: NODE_PATH=/path/to/node_modules PYTHON=python node tests/transcript_editor_browser.cjs
const assert = require('node:assert/strict');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const fs = require('node:fs');
const os = require('node:os');
const {spawnSync} = require('node:child_process');
const {chromium} = require('playwright');

(async () => {
    let browser, temporary;
    try {
        let htmlPath = process.argv[2];
        if (!htmlPath) {
            temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'transcript-editor-'));
            const source = {
                metadata: {backend: 'speechcpp', model: 'nemotron-3.5-transcribe'},
                chunks: [
                    {id: 'phrase-3', timestamp: [10, 14], speaker: 'Speaker 2', text: "And that's why the decorative button was not working."},
                    {id: 'phrase-4', timestamp: [12, 16], speaker: 'Speaker 1', text: 'An overlapping phrase.'},
                    {id: 'phrase-5', timestamp: [14, 18], speaker: 'Speaker 2', text: 'Another phrase from the same speaker.'},
                    {id: 'phrase-6', timestamp: [18, 20], speaker: null, text: 'An unknown voice.'}
                ]
            };
            const generated = spawnSync(process.env.PYTHON || 'python3', ['-c', [
                'import json, sys',
                'from pathlib import Path',
                'from src.web_generator import WebGenerator',
                'folder=Path(sys.argv[1])',
                '(folder/"analysis.json").write_text("[]")',
                '(folder/"video.mp4").touch()',
                '(folder/"transcript.json").write_text(json.dumps(json.load(sys.stdin)))',
                'print(WebGenerator(folder/"analysis.json",folder/"video.mp4",folder/"transcript.json").generate(folder))'
            ].join('\n'), temporary], {cwd: path.resolve(__dirname, '..'), input: JSON.stringify(source), encoding: 'utf8'});
            assert.equal(generated.status, 0, generated.stderr);
            htmlPath = generated.stdout.trim();
        }
        browser = await chromium.launch({channel: 'chrome', headless: true});
        const page = await browser.newPage();
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.addInitScript(() => {
            window.__copied = null;
            Object.defineProperty(navigator, 'clipboard', {configurable: true, value: {
                writeText: async text => { window.__copied = text; }
            }});
        });
        await page.goto(pathToFileURL(path.resolve(htmlPath)).href);
        const exported = () => page.locator('#corrections-json').inputValue().then(JSON.parse);
        assert.equal((await exported()).regions.length, 0);

        await page.evaluate(() => {
            const media = document.getElementById('meeting-video');
            window.__playCalls = 0;
            media.play = () => { window.__playCalls++; return Promise.resolve(); };
            Object.defineProperty(media, 'currentTime', {value: 0, writable: true});
        });
        const chips = page.locator('.speaker-chip[data-speaker-id="Speaker 2"]');
        await chips.first().click();
        await chips.first().fill('Jane');
        await chips.first().press('Enter');
        assert.deepEqual(await chips.allTextContents(), ['Jane', 'Jane']);
        assert.equal((await exported()).speakers.find(s => s.speaker_id === 'Speaker 2').name, 'Jane');

        // Escape restores the last committed name everywhere.
        await chips.first().click();
        await chips.first().fill('Wrong name');
        await chips.first().press('Escape');
        assert.deepEqual(await chips.allTextContents(), ['Jane', 'Jane']);

        const phrase = page.locator('.phrase-text').first();
        await phrase.focus();
        await phrase.press('Enter');
        await page.evaluate(() => {
            const text = document.querySelector('.phrase-text').firstChild;
            const start = text.textContent.indexOf('decorative');
            const range = document.createRange();
            range.setStart(text, start);
            range.setEnd(text, start + 'decorative'.length);
            window.getSelection().removeAllRanges();
            window.getSelection().addRange(range);
        });
        await page.keyboard.insertText('Data Record');
        await phrase.press('Enter');
        const feedback = await exported();
        assert.equal(feedback.regions.length, 1);
        const region = feedback.regions[0];
        assert.equal(region.segment_id, 'phrase-3');
        assert.deepEqual([region.start_seconds, region.end_seconds], [10, 14]);
        assert.equal(region.speaker_id, 'Speaker 2');
        assert.equal(region.speaker_name, 'Jane');
        assert.equal(region.original_text, "And that's why the decorative button was not working.");
        assert.equal(region.corrected_text, "And that's why the Data Record button was not working.");
        assert.deepEqual(region.word_hints, [{original: 'decorative', replacement: 'Data Record'}]);
        assert.equal(await page.evaluate(() => window.__playCalls), 0);

        // Natural text selection spans rows and includes the renamed speaker chips.
        await page.evaluate(() => {
            const rows = document.querySelectorAll('.transcript-chunk');
            const range = document.createRange();
            range.setStart(rows[0], 0);
            range.setEndAfter(rows[2].querySelector('.phrase-text'));
            window.getSelection().removeAllRanges();
            window.getSelection().addRange(range);
        });
        assert.match(await page.evaluate(() => window.getSelection().toString()), /Jane/);
        await page.locator('#copy-selected-phrases').click();
        const selected = await page.evaluate(() => window.__copied);
        assert.equal(selected.split('\n').length, 3);
        assert.match(selected, /Jane: And that's why the Data Record button/);
        assert.match(selected, /Jane: Another phrase from the same speaker/);
        assert.doesNotMatch(selected, /An unknown voice/);

        await page.locator('#copy-transcript').click();
        assert.equal((await page.evaluate(() => window.__copied)).split('\n').length, 4);
        await page.locator('#copy-corrections-json').click();
        assert.deepEqual(JSON.parse(await page.evaluate(() => window.__copied)), feedback);

        // Editing and renaming must not change overlap highlighting based on stable IDs.
        await page.evaluate(() => {
            const video = document.getElementById('meeting-video');
            video.currentTime = 12;
            video.dispatchEvent(new Event('timeupdate'));
        });
        assert.equal(await page.locator('.transcript-chunk.active').count(), 2);
        await page.locator('.transcript-timestamp').first().click();
        assert.equal(await page.evaluate(() => window.__playCalls), 1);

        // User-supplied names and corrections stay plain text.
        await chips.first().click();
        await chips.first().fill('<img src=x onerror=alert(1)>');
        await chips.first().press('Enter');
        assert.equal(await chips.first().locator('img').count(), 0);
        assert.match((await exported()).speakers.find(s => s.speaker_id === 'Speaker 2').name, /^<img/);

        // Clipboard fallback for browsers/file URLs that reject navigator.clipboard.
        await page.evaluate(() => {
            navigator.clipboard.writeText = async () => { throw new Error('Denied'); };
            const original = document.execCommand.bind(document);
            document.execCommand = (command, ...args) => {
                if (command === 'copy') { window.__copied = document.activeElement.value; return true; }
                return original(command, ...args);
            };
        });
        await page.locator('#copy-corrections-json').click();
        assert.equal(JSON.parse(await page.evaluate(() => window.__copied)).regions.length, 1);
        assert.deepEqual(errors, []);

        await page.reload();
        assert.deepEqual(await chips.allTextContents(), ['Speaker 2', 'Speaker 2']);
        assert.equal((await exported()).regions.length, 0);
        assert.match(await phrase.textContent(), /decorative button/);

        await phrase.dblclick();
        assert.equal(await phrase.getAttribute('contenteditable'), 'plaintext-only');
        assert.ok((await page.evaluate(() => window.getSelection().toString())).length > 0);
        await phrase.press('Escape');
        assert.equal((await exported()).regions.length, 0);

        await phrase.focus();
        await phrase.press('Enter');
        await page.evaluate(() => {
            const data = new DataTransfer();
            data.setData('text/plain', '<b>Corrected</b>\nData Record');
            data.setData('text/html', '<img src=x onerror=alert(1)>');
            document.querySelector('.phrase-text').dispatchEvent(new ClipboardEvent('paste', {
                bubbles: true, cancelable: true, clipboardData: data
            }));
        });
        await phrase.press('Enter');
        assert.equal(await phrase.textContent(), '<b>Corrected</b> Data Record');
        assert.equal(await phrase.locator('b, img').count(), 0);
        assert.equal((await exported()).regions[0].corrected_text, '<b>Corrected</b> Data Record');
        assert.deepEqual(errors, []);
        console.log('Speaker editing, selected-word corrections, copying, JSON, playback, escaping, and reload reset passed');
    } finally {
        if (browser) await browser.close();
        if (temporary) fs.rmSync(temporary, {recursive: true, force: true});
    }
})().catch(error => { console.error(error); process.exitCode = 1; });
