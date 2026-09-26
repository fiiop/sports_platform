const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const elements = new Map();
const element = id => {
  if (!elements.has(id)) elements.set(id, {classList: {add(){}, remove(){}}, style: {}});
  return elements.get(id);
};
const attack = '<img src=x onerror=alert(1)>';
const dashboard = {summary: {total_minutes: 60, active_days: 1, total_calories: 0},
  review: {status: 'ok', weekly_minutes: 60, target: 60, completion: 100, advice: 'ok'},
  chart: {labels: [], minutes: []}};
const context = vm.createContext({document: {getElementById: element},
  fetch: async url => ({ok: true, json: async () => {
    if (url === '/api/me') return {logged_in: false};
    if (url === '/api/dashboard') return dashboard;
    if (url === '/api/plans') return [{title: attack, target: attack, weekly_minutes: 60, start_date:'2026-01-01', end_date:'2026-12-31'}];
    if (url === '/api/records') return [{id: 1, exercise_date:'2026-01-01', exercise_type:attack, duration:60, distance:0, intensity:3, feeling:attack, note:attack}];
    throw new Error(url);
  }})});
vm.runInContext(fs.readFileSync('app/static/app.js', 'utf8'), context);
(async () => {
  await vm.runInContext('refresh()', context);
  for (const id of ['plans', 'records']) {
    assert.ok(!element(id).innerHTML.includes('<img'));
    assert.ok(element(id).innerHTML.includes('&lt;img'));
  }
  assert.equal(element('mMinutes').textContent, 60);
  assert.equal(element('progressBar').style.width, '100%');
  assert.equal(vm.runInContext('localDate(new Date(2026, 0, 2, 0, 1))', context), '2026-01-02');
  console.log('PASS: HTML escaping, dashboard without Chart CDN, local calendar date');
})().catch(error => { console.error(error); process.exitCode = 1; });
