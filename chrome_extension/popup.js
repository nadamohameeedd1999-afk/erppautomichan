const $ = id => document.getElementById(id);
const out = (t, ok) => { $('out').textContent = t; $('out').className = ok ? 'ok' : 'no'; };
chrome.storage.local.get(['dash', 'tok'], v => { $('dash').value = v.dash || ''; $('tok').value = v.tok || ''; });
async function tab() { const [t] = await chrome.tabs.query({active: true, currentWindow: true}); return t; }

$('start').onclick = async () => {
  chrome.storage.local.set({dash: $('dash').value.trim(), tok: $('tok').value.trim()});
  const t = await tab();
  await chrome.scripting.executeScript({target: {tabId: t.id}, world: 'MAIN', files: ['recorder.js']});
  const [r] = await chrome.scripting.executeScript({target: {tabId: t.id}, world: 'MAIN', func: () => __nqStartRecording()});
  out(r && r.result === 'already' ? 'Already recording / التسجيل شغال' : '⏺ Recording — work on the screen / اشتغلي على الشاشة عادي', true);
};

$('send').onclick = async () => {
  const dash = $('dash').value.trim().replace(/\/$/, ''), tok = $('tok').value.trim();
  if (!dash || !tok) return out('Enter the dashboard link and token / اكتبي الرابط والكود');
  const t = await tab();
  const [r] = await chrome.scripting.executeScript({target: {tabId: t.id}, world: 'MAIN',
    func: () => { const e = window.__rec || []; window.__rec = []; window.__rec_on = false; const b = document.getElementById('__rec_bar'); if (b) b.remove(); return e; }});
  const events = (r && r.result) || [];
  if (!events.length) return out('No steps recorded / مفيش خطوات اتسجلت');
  try {
    const res = await fetch(dash + '/api/recorder/import', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Recorder-Token': tok},
      body: JSON.stringify({events, url: t.url, title: t.title, name: $('name').value.trim()})});
    const j = await res.json();
    if (!j.success) return out('❌ ' + (j.error || res.status));
    out(`✅ Saved as «${j.name}» (${j.fields} fields, ${j.actions} actions) — open the test builder / اتحفظ — افتحي منشئ الاختبارات`, true);
  } catch (e) { out('❌ ' + e); }
};
