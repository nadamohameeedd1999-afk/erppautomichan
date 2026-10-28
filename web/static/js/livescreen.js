/*
 * LiveScreen — shows the test browser's screen (a picture every ~0.4s) inside any element,
 * and, when control is on, sends clicks / typing / scrolling to it (/api/live/input).
 * Works without websockets, so it works on Railway too.
 *
 *   const ls = new LiveScreen(el, {control: true, onError: msg => ...});
 *   ls.start(); ls.stop(); ls.setControl(false);
 */
(function () {
    function LiveScreen(el, opts) {
        this.el = el;
        this.opts = opts || {};
        this.control = !!this.opts.control;
        this.on = false;
        this.img = document.createElement('img');
        this.img.alt = '';
        this.img.draggable = false;
        this.img.tabIndex = 0;
        this.img.style.cssText = 'width:100%;height:100%;object-fit:contain;display:block;background:#0b0d12;outline:none;user-select:none';
        el.appendChild(this.img);
        // typing goes through a hidden box, so every keyboard (Arabic, IME, phone) works: we read what was typed
        this.kb = document.createElement('textarea');
        this.kb.setAttribute('autocomplete', 'off'); this.kb.setAttribute('autocorrect', 'off'); this.kb.spellcheck = false;
        this.kb.style.cssText = 'position:absolute;opacity:0;width:1px;height:1px;left:0;top:0;border:0;padding:0;resize:none;pointer-events:none';
        el.appendChild(this.kb);
        this._bind();
        this.setControl(this.control);
    }

    LiveScreen.prototype.setControl = function (on) {
        this.control = !!on;
        this.img.style.cursor = this.control ? 'crosshair' : 'default';
        this.img.title = this.control ? 'دوسي على الصورة واكتبي — الحركة بتروح للمتصفح اللي بيختبر' : '';
    };

    // where in the real screen the user clicked (the picture is "contain"-fitted, so remove the bars)
    LiveScreen.prototype._pos = function (e) {
        const r = this.img.getBoundingClientRect(), nw = this.img.naturalWidth || 16, nh = this.img.naturalHeight || 9;
        const s = Math.min(r.width / nw, r.height / nh), w = nw * s, h = nh * s;
        const ox = r.left + (r.width - w) / 2, oy = r.top + (r.height - h) / 2;
        const fx = (e.clientX - ox) / w, fy = (e.clientY - oy) / h;
        return (fx < 0 || fx > 1 || fy < 0 || fy > 1) ? null : {fx, fy};
    };

    // requests go one after the other, in order; plain typing is buffered and sent as one piece of text
    LiveScreen.prototype._send = function (body) {
        const self = this;
        if (body.type !== 'char') this._flushText();
        if (body.type === 'char') {
            this._buf = (this._buf || '') + body.key;
            clearTimeout(this._bufT);
            this._bufT = setTimeout(() => this._flushText(), 150);
            return;
        }
        this._q = (this._q || Promise.resolve()).then(() =>
            fetch('/api/live/input', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)})
                .then(r => r.json()).then(j => { if (!j.success && self.opts.onError) self.opts.onError(j.error); self._kick(); })
                .catch(() => {}));
        return this._q;
    };
    LiveScreen.prototype._flushText = function () {
        clearTimeout(this._bufT);
        const t = this._buf; this._buf = '';
        if (t) this._send({type: 'text', text: t});
    };

    LiveScreen.prototype._bind = function () {
        const self = this, img = this.img;
        let clickTimer = null;
        img.addEventListener('click', e => {
            if (!self.control) return;
            self.kb.focus({preventScroll: true});
            const p = self._pos(e); if (!p) return;
            clearTimeout(clickTimer);
            clickTimer = setTimeout(() => self._send({type: 'click', ...p}), 220);   // wait: maybe a double click
        });
        img.addEventListener('dblclick', e => {
            if (!self.control) return;
            clearTimeout(clickTimer);
            const p = self._pos(e); if (p) self._send({type: 'dblclick', ...p});
        });
        img.addEventListener('contextmenu', e => {
            if (!self.control) return;
            e.preventDefault();
            const p = self._pos(e); if (p) self._send({type: 'rclick', ...p});
        });
        img.addEventListener('wheel', e => {
            if (!self.control) return;
            e.preventDefault();
            self._send({type: 'scroll', dy: e.deltaY});
        }, {passive: false});
        const kb = this.kb;
        kb.addEventListener('keydown', e => {
            if (!self.control) return;
            if (e.isComposing || e.key === 'Process' || e.key === 'Unidentified') return;     // text comes in "input"
            if (e.key === 'Shift' || e.key === 'Control' || e.key === 'Alt' || e.key === 'Meta' || e.key === 'CapsLock') return;
            if (e.ctrlKey && (e.key === 'v' || e.key === 'V')) return;                        // paste event below
            const special = e.key.length > 1 || e.ctrlKey || e.altKey;
            if (!special) return;                                                             // letters / digits / spaces -> "input"
            e.preventDefault();
            self._send({type: 'key', key: e.key, ctrl: e.ctrlKey, shift: e.shiftKey, alt: e.altKey});
        });
        kb.addEventListener('input', e => {
            if (!self.control || e.isComposing) { return; }
            const t = kb.value; kb.value = '';
            if (t) self._send({type: 'char', key: t});
        });
        kb.addEventListener('compositionend', () => {
            const t = kb.value; kb.value = '';
            if (t && self.control) self._send({type: 'char', key: t});
        });
        kb.addEventListener('paste', e => {
            if (!self.control) return;
            const t = (e.clipboardData || window.clipboardData).getData('text');
            if (t) { e.preventDefault(); self._send({type: 'text', text: t}); }
        });
    };

    LiveScreen.prototype._kick = function () { this._fast = Date.now(); };

    LiveScreen.prototype.start = function () {
        if (this.on) return;
        this.on = true;
        const self = this;
        (async function loop() {
            while (self.on) {
                const t0 = Date.now();
                try {
                    const r = await fetch('/api/live/frame.jpg?t=' + t0, {cache: 'no-store'});
                    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || ('HTTP ' + r.status));
                    const url = URL.createObjectURL(await r.blob());
                    const old = self.img.src; self.img.src = url;
                    if (old && old.startsWith('blob:')) setTimeout(() => URL.revokeObjectURL(old), 1000);
                    if (self.opts.onFrame) self.opts.onFrame();
                } catch (e) {
                    if (self.opts.onError) self.opts.onError(String(e.message || e));
                    await new Promise(r => setTimeout(r, 2500));
                }
                const quick = Date.now() - (self._fast || 0) < 3000;      // right after a click: refresh faster
                await new Promise(r => setTimeout(r, Math.max(80, (quick ? 200 : 450) - (Date.now() - t0))));
            }
        })();
    };

    LiveScreen.prototype.stop = function () { this.on = false; };
    LiveScreen.prototype.destroy = function () { this.stop(); this.img.remove(); };

    window.LiveScreen = LiveScreen;
})();
