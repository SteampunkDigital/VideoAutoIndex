// Execute the actual generated script with controllable media and DOM elements.
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const {script, rows} = JSON.parse(fs.readFileSync(0, 'utf8'));
const events = {};
const video = {
    currentTime: 0, paused: true, ended: false,
    addEventListener(name, callback) { events[name] = callback; },
    play() { this.paused = false; events.play(); }
};
function makeRow(row) {
    const classes = new Set();
    return {
        dataset: row, attributes: {},
        classList: {
            toggle(name, enabled) { enabled ? classes.add(name) : classes.delete(name); },
            remove(name) { classes.delete(name); },
            contains(name) { return classes.has(name); }
        },
        setAttribute(name, value) { this.attributes[name] = value; },
        removeAttribute(name) { delete this.attributes[name]; }
    };
}
const chunks = rows.map(makeRow);
const status = {hidden: true};
let ready, nextFrame = null, pendingFrames = 0;
const context = {
    document: {
        getElementById(id) { return id === 'meeting-video' ? video : status; },
        querySelectorAll() { return chunks; },
        addEventListener(name, callback) { ready = callback; }
    },
    requestAnimationFrame(callback) { nextFrame = callback; pendingFrames++; return 1; },
    cancelAnimationFrame() { nextFrame = null; pendingFrames--; }
};
vm.createContext(context);
vm.runInContext(script, context);
ready();
function at(time, event = 'timeupdate') {
    video.currentTime = time;
    events[event]();
    return chunks.flatMap((chunk, index) => chunk.classList.contains('active') ? [index] : []);
}
assert.deepEqual(at(9), []);
assert.deepEqual(at(10), [0]);
assert.deepEqual(at(12), [0, 1]);
assert.equal(status.hidden, false);
assert.equal(chunks[0].classList.contains('overlapping'), true);
assert.equal(chunks[1].attributes['aria-current'], 'true');
assert.deepEqual(at(12.5), [0, 1, 2]); // nested, third speaker
assert.deepEqual(at(13), [0, 1]);
assert.deepEqual(at(14), [1, 3]); // A ended; next A starts at this boundary
assert.equal(chunks[0].classList.contains('active'), false);
assert.deepEqual(at(15), [1]);
assert.equal(status.hidden, true);
assert.equal(chunks[1].classList.contains('overlapping'), false);
assert.deepEqual(at(16), [4, 5]); // same speaker on two overlapping segments
assert.equal(status.hidden, true);
assert.deepEqual(at(18), [6, 7]); // unknown speakers: active, no inferred identities
assert.equal(status.hidden, true);
assert.deepEqual(at(20), []);
assert.deepEqual(at(12.5, 'seeking'), [0, 1, 2]);
assert.deepEqual(at(10, 'seeked'), [0]);
assert.equal(status.hidden, true);
assert.equal(chunks[1].attributes['aria-current'], undefined);
context.seekToTime(12);
assert.equal(video.currentTime, 12);
assert.equal(pendingFrames, 1);
events.play(); // duplicate play events must not create multiple loops
assert.equal(pendingFrames, 1);
video.currentTime = 12.5;
pendingFrames--; // the browser consumes the scheduled callback
nextFrame();
assert.equal(chunks.filter(chunk => chunk.classList.contains('active')).length, 3);
video.paused = true;
events.pause();
assert.equal(pendingFrames, 0);
assert.equal(nextFrame, null);
context.seekVideo('00:00:10,000');
assert.equal(video.currentTime, 10);
console.log('Overlap, boundaries, seeks, keyboard-native controls, and animation loop passed');
