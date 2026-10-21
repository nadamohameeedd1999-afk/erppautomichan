/**
 * Test Runner - Live Progress
 */

class TestRunner {
    constructor(options) {
        this.modalId = options.modalId || 'runningModal';
        this.progressId = options.progressId || 'runProgress';
        this.statusId = options.statusId || 'runStatus';
        this.nameId = options.nameId || 'runTestName';
        this.timeId = options.timeId || 'runTime';
        this.logId = options.logId || 'runLog';
        this.pollInterval = 2000;
        this.startTime = null;
        this.pollTimer = null;
    }

    openModal(testName) {
        const nameEl = document.getElementById(this.nameId);
        if (nameEl) nameEl.textContent = testName;

        this.resetProgress();
        this.startTime = Date.now();
        this.startTimer();

        const modalEl = document.getElementById(this.modalId);
        if (modalEl) {
            this.modal = new bootstrap.Modal(modalEl);
            this.modal.show();
        }
    }

    resetProgress() {
        const bar = document.getElementById(this.progressId);
        if (bar) bar.style.width = '0%';

        const status = document.getElementById(this.statusId);
        if (status) status.textContent = 'جاري البدء...';

        const log = document.getElementById(this.logId);
        if (log) log.innerHTML = '';
    }

    startTimer() {
        if (this.timerInterval) clearInterval(this.timerInterval);
        this.timerInterval = setInterval(() => {
            const elapsed = Math.floor((Date.now() - this.startTime) / 1000);
            const mins = Math.floor(elapsed / 60);
            const secs = elapsed % 60;
            const timeEl = document.getElementById(this.timeId);
            if (timeEl) {
                timeEl.textContent = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
            }
        }, 1000);
    }

    stopTimer() {
        if (this.timerInterval) {
            clearInterval(this.timerInterval);
            this.timerInterval = null;
        }
    }

    setProgress(percent, statusText) {
        const bar = document.getElementById(this.progressId);
        if (bar) bar.style.width = percent + '%';

        const status = document.getElementById(this.statusId);
        if (status && statusText) status.textContent = statusText;
    }

    addLog(message, type = 'info') {
        const log = document.getElementById(this.logId);
        if (!log) return;

        const time = new Date().toLocaleTimeString('en-GB', { hour12: false });
        const colors = {
            info: 'text-muted',
            success: 'text-success',
            error: 'text-danger',
            warning: 'text-warning',
        };
        const icons = {
            info: 'bi-info-circle',
            success: 'bi-check-circle',
            error: 'bi-x-circle',
            warning: 'bi-exclamation-triangle',
        };

        const entry = document.createElement('div');
        entry.className = `small ${colors[type] || 'text-muted'} mb-1`;
        entry.innerHTML = `<i class="bi ${icons[type]}"></i> <span class="text-muted">[${time}]</span> ${message}`;
        log.appendChild(entry);
        log.scrollTop = log.scrollHeight;
    }

    async run(testPath, testName, repeat = 1) {
        this.repeat = Math.max(1, parseInt(repeat, 10) || 1);
        this._iter = 0;
        this._iterShown = 0;
        this.openModal(testName);
        this.setProgress(5, 'جاري إرسال الطلب...');
        this.addLog(`بدء تشغيل: ${testName}`);
        if (this.repeat > 1) this.addLog(`🔁 التكرار: ${this.repeat} مرة (متصفح جديد لكل مرة)`, 'info');

        try {
            const res = await fetch('/api/run-test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ test_path: testPath, test_name: testName, repeat: this.repeat })
            });

            const data = await res.json();

            if (!data.success) {
                this.addLog(`فشل: ${data.error}`, 'error');
                this.setProgress(100, 'فشل التشغيل');
                this.finish(false);
                return;
            }

            const taskId = data.task_id;
            this.addLog(`Task ID: ${taskId}`, 'info');
            this.setProgress(10, 'جاري التشغيل...');
            this.addLog('تم بدء الاختبار', 'success');

            // Start polling
            this.poll(taskId);

        } catch (e) {
            this.addLog(`خطأ: ${e.message}`, 'error');
            this.setProgress(100, 'خطأ');
            this.finish(false);
        }
    }

    poll(taskId) {
        let attempts = 0;
        const maxAttempts = Math.max(600, (this.repeat || 1) * 200); // 20 min minimum, +6.5 min per repeat
        let lastStatus = null;

        this.pollTimer = setInterval(async () => {
            attempts++;

            if (attempts > maxAttempts) {
                this.addLog('⏱️ انتهى الوقت المسموح', 'error');
                this.setProgress(100, 'انتهى الوقت');
                this.finish(false);
                return;
            }

            try {
                const res = await fetch(`/api/status/${taskId}`);
                const data = await res.json();

                // Progress
                const baseProgress = 15;
                const maxProgress = 95;
                const p = Math.min(baseProgress + (attempts * 1.5), maxProgress);
                if ((this.repeat || 1) > 1) {
                    await this.updateRepeatProgress(taskId, attempts);
                } else {
                    this.setProgress(p, 'جاري التشغيل...');
                }

                // لو الحالة اتغيرت، نطبع
                if (data.status !== lastStatus) {
                    lastStatus = data.status;
                    if (data.status === 'running') {
                        this.addLog('🔄 الاختبار شغال...', 'info');
                    }
                }

                // ===== الحالات النهائية =====
                if (data.status === 'completed') {
                    this.setProgress(100, '✅ اكتمل بنجاح');
                    this.addLog('🎉 الاختبار اكتمل بنجاح!', 'success');

                    if (data.duration_seconds) {
                        this.addLog(`⏱️ المدة: ${data.duration_seconds} ثانية`, 'info');
                    }

                    if (data.summary) {
                        const s = data.summary;
                        this.addLog(`📊 النتائج: ${s.passed || 0} نجح, ${s.failed || 0} فشل, ${s.errors || 0} خطأ`, 'info');
                    }

                    this.finish(true, taskId);
                    return;
                }

                if (data.status === 'failed') {
                    this.setProgress(100, '❌ فشل');
                    this.addLog('❌ الاختبار فشل', 'error');

                    if (data.summary) {
                        const s = data.summary;
                        this.addLog(`📊 النتائج: ${s.passed || 0} نجح, ${s.failed || 0} فشل`, 'error');
                    }

                    this.finish(false, taskId);
                    return;
                }

                if (data.status === 'stopped') {
                    this.setProgress(100, '⏹️ تم الإيقاف');
                    this.addLog('⏹️ تم إيقاف الاختبار', 'warning');
                    this.finish(false, taskId);
                    return;
                }

                if (data.status === 'error') {
                    this.setProgress(100, '⚠️ خطأ');
                    this.addLog(`⚠️ خطأ: ${data.error || 'غير معروف'}`, 'error');
                    this.finish(false, taskId);
                    return;
                }

                if (data.status === 'unknown') {
                    // لو الـ task مش موجود في QueueManager
                    // نستمر شوية كمان وبعدين نوقف
                    if (attempts > 15) {
                        this.addLog('⚠️ المهمة مش موجودة - يبدو أنها خلصت', 'warning');
                        this.setProgress(100, 'انتهى');
                        this.finish(true, taskId);
                        return;
                    }
                }

            } catch (e) {
                console.error('Poll error:', e);
            }
        }, this.pollInterval);
    }

    finish(success, taskId) {
        try { window.dispatchEvent(new CustomEvent('testFinished', { detail: { success, taskId } })); } catch (e) {}
        if (this.pollTimer) {
            clearInterval(this.pollTimer);
            this.pollTimer = null;
        }
        this.stopTimer();

        // Show finish buttons
        setTimeout(() => {
            const finishArea = document.getElementById('finishArea');
            if (finishArea) {
                finishArea.classList.remove('d-none');
                const viewBtn = document.getElementById('viewReportBtn');
                if (viewBtn) {
                    viewBtn.onclick = () => { window.location.href = taskId ? `/reports/${encodeURIComponent(taskId)}` : '/reports'; };
                }
            }
        }, 1500);
    }

    async stopTest(taskId) {
        this.addLog('⏹️ إيقاف الاختبار...', 'warning');
        try {
            const res = await fetch('/api/stop', { method: 'POST' });
            const data = await res.json();
            if (data.success) {
                this.addLog('تم إيقاف الاختبار', 'success');
                this.setProgress(100, 'تم الإيقاف');
                this.stopTimer();
                if (this.pollTimer) {
                    clearInterval(this.pollTimer);
                    this.pollTimer = null;
                }
            } else {
                this.addLog(data.message || 'فشل الإيقاف', 'error');
            }
        } catch (e) {
            this.addLog('خطأ في الإيقاف: ' + e.message, 'error');
        }
    }
}

// Extend poll to show stop button
const originalPoll = TestRunner.prototype.poll;
TestRunner.prototype.poll = function(taskId) {
    // Show stop button
    const stopBtn = document.getElementById('stopBtn');
    if (stopBtn) {
        stopBtn.classList.remove('d-none');
        stopBtn.onclick = () => this.stopTest(taskId);
    }
    originalPoll.call(this, taskId);
};

// Extend finish to hide stop button
const originalFinish = TestRunner.prototype.finish;
TestRunner.prototype.finish = function(success, taskId) {
    const stopBtn = document.getElementById('stopBtn');
    if (stopBtn) stopBtn.classList.add('d-none');
    originalFinish.call(this, success, taskId);
};

// ==================== Global Helper ====================
window.TestRunner = TestRunner;

window.runTest = function(testPath, testName, repeat) {
    const runner = new TestRunner({});
    runner.run(testPath, testName, repeat);
};



// ==================== Repeat progress ====================
// بيقرأ اللوج ويعرف إحنا في أنهي تكرار (pytest بيطبع [run2of5] في اسم كل اختبار)
TestRunner.prototype.updateRepeatProgress = async function(taskId, attempts) {
    const n = this.repeat || 1;
    try {
        if (attempts % 3 === 1 || !this._iter) {
            const res = await fetch(`/api/log/${taskId}?lines=1500`);
            const d = await res.json();
            if (d && d.success) {
                let cur = 0;
                for (const line of d.lines) {
                    for (const m of line.matchAll(/\[run(\d+)of(\d+)\]/g)) {
                        cur = Math.max(cur, parseInt(m[1], 10));
                    }
                }
                if (cur > 0) this._iter = cur;
            }
        }
    } catch (e) {
        console.error('Repeat progress error:', e);
    }
    const cur = this._iter || 1;
    if (cur !== this._iterShown) {
        this._iterShown = cur;
        this.addLog(`🔁 بدأ التكرار ${cur} من ${n}`, 'info');
    }
    const pct = Math.min(95, 10 + (85 * (cur - 1)) / n + 5);
    this.setProgress(pct, `🔁 تكرار ${cur} من ${n}`);
};
