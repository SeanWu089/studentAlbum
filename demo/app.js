const $ = selector => document.querySelector(selector);
const escapeText = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const questions = [
  {field:'origin',title:'你的籍贯是哪里？',copy:'填写到省、市或县都可以。',label:'籍贯',placeholder:'例如：江苏南京',limit:100},
  {field:'subject',title:'高中阶段，你最喜欢哪一门课？',copy:'写下第一时间想到的那一门即可。',label:'最喜欢的科目',placeholder:'例如：历史',limit:80},
  {field:'ability',title:'你最自豪的一项能力是什么？',copy:'也可以写一个希望老师了解的特点。',label:'能力或特点',placeholder:'例如：我擅长把复杂的事情整理清楚。',limit:1000},
  {field:'message',title:'想对老师说的话',copy:'你的期待、困惑，或任何想分享的事，都可以写在这里。',label:'想对老师说的话',placeholder:'写下你想说的话…',limit:2000},
  {field:'hasPhoto',title:'最后，上传一张个人照片',copy:'选择一张清晰的正面生活照。',label:'个人照片'},
];
let route = 'intro', classes = [], term = '', student = null, questionIndex = 0;
let token = '', code = '', registration = null, pending = {}, saving = null, saveTimer = null;
let photoUrl = '', photoBusy = false, loadError = '', actionBusy = false, saveMessage = '';
try { registration = JSON.parse(sessionStorage.getItem('album-registration') || 'null'); } catch {}

function remember(key, value) { try { if (value === null) sessionStorage.removeItem(key); else sessionStorage.setItem(key, value); } catch {} }
function makeRequestId() {
  if (globalThis.crypto && typeof globalThis.crypto.randomUUID === 'function') return globalThis.crypto.randomUUID();
  const values = new Uint32Array(5);
  if (globalThis.crypto && typeof globalThis.crypto.getRandomValues === 'function') {
    globalThis.crypto.getRandomValues(values);
    return Array.from(values, value => value.toString(16).padStart(8, '0')).join('');
  }
  let result = Date.now().toString(16);
  while (result.length < 40) result += Math.floor(Math.random() * 0x100000000).toString(16).padStart(8, '0');
  return result.slice(0, 40);
}
function makePasscode() {
  const values = new Uint32Array(1);
  if (globalThis.crypto && typeof globalThis.crypto.getRandomValues === 'function') {
    globalThis.crypto.getRandomValues(values);
    return String(values[0] % 1000000).padStart(6,'0');
  }
  return String(Math.floor(Math.random() * 1000000)).padStart(6,'0');
}
function rememberDraft() { if (student) remember('album-draft-' + student.id, JSON.stringify(pending)); }
async function api(path, data, raw = false, blob = false) {
  const response = await fetch(path, {method:data === undefined ? 'GET' : 'POST',
    headers:{...(token ? {Authorization:'Bearer ' + token} : {}), ...(data === undefined ? {} : {'Content-Type':raw ? 'image/jpeg' : 'application/json'})},
    body:data === undefined ? undefined : raw ? data : JSON.stringify(data), signal:AbortSignal.timeout(20000), cache:'no-store'});
  if (!response.ok) { const result = await response.json().catch(() => ({})); throw Error(result.error || '暂时无法连接老师电脑，请稍后再试。'); }
  return blob ? response.blob() : response.json();
}
function header(right = '') { return `<header class="screen-header"><p class="brand">学生档案</p>${right}</header>`; }
function shell(content) { return `<section class="device"><div class="screen">${content}</div></section>`; }
function classOptions() { return '<option value="">请选择班级</option>' + classes.map(c => `<option value="${c.id}">${escapeText(c.name)}</option>`).join(''); }
function introTemplate() {
  return shell(`${header('<p class="status">约 3 分钟</p>')}<div class="intro"><div class="intro-copy"><p class="section-label">${escapeText(term || '学生资料收集')}</p><h1>让老师<br>更了解你</h1><p>填写几项基本信息。中途退出后，可用口令继续填写。</p><p class="privacy-note">资料和照片仅供老师了解学生，不公开展示。</p></div><footer class="page-footer">${loadError ? `<p class="field-error">${escapeText(loadError)}</p><button class="secondary" data-action="reload">重新连接</button>` : !classes.length ? '<p class="waiting-note">老师还没有设置班级，请稍后再来。</p><button class="secondary" data-action="reload">刷新班级</button>' : '<button class="primary" data-action="create">开始填写</button><button class="secondary" data-action="resume">继续上次填写</button>'}</footer></div>`);
}
function identityTemplate() {
  const creating = route === 'create';
  return shell(`${header('<button class="text-button" data-action="intro">返回</button>')}<div class="identity"><div class="page-body"><h1>${creating ? '确认你的身份' : '继续填写'}</h1><p class="identity-copy">${creating ? '选择班级，填写学号和姓名。建档后请保存续填口令。' : '选择班级，输入学号和六位续填口令。'}</p><form id="identity-form"><div class="field"><label for="student-class">所在班级</label><select id="student-class" required>${classOptions()}</select></div><div class="field"><label for="student-number">学号</label><input id="student-number" maxlength="40" autocomplete="off" placeholder="请输入学号" required></div><div class="field"><label for="student-name">${creating ? '姓名' : '续填口令'}</label><input id="student-name" ${creating ? 'maxlength="60" autocomplete="name" placeholder="请输入姓名"' : 'maxlength="6" inputmode="numeric" autocomplete="one-time-code" placeholder="请输入六位数字"'} required></div><p class="field-error" id="identity-error" role="alert"></p></form></div><footer class="page-footer"><button class="primary" data-action="identity-submit">${creating ? '生成续填口令' : '进入档案'}</button></footer></div>`);
}
function passcodeTemplate() {
  return shell(`${header('<p class="status">请截图保存</p>')}<div class="passcode-page"><div class="page-body"><p class="section-label">续填凭证</p><h1>保存这组六位数字</h1><p class="identity-copy">${escapeText(student.className)} · 学号 ${escapeText(student.number)}<br>下次凭班级、学号和口令继续填写。</p><div class="passcode" aria-label="六位续填口令">${escapeText(code)}</div></div><footer class="page-footer"><button class="primary" data-action="begin">已保存，继续</button></footer></div>`);
}
function questionTemplate() {
  const q = questions[questionIndex];
  const value = escapeText(student[q.field]);
  let input;
  if (q.field === 'hasPhoto') {
    input = `${photoUrl ? `<img class="photo-preview" src="${photoUrl}" alt="已保存的个人照片">` : student.hasPhoto ? '<p class="field-hint">照片已保存</p>' : ''}<label class="file-input" for="question-file"><span><strong>${student.hasPhoto ? '更换照片' : '选择照片'}</strong><small>支持 JPG、PNG、WebP；自动优化照片大小</small></span><input id="question-file" type="file" accept="image/jpeg,image/png,image/webp"></label>`;
  } else {
    input = ['ability','message'].includes(q.field) ? `<textarea id="question-input" maxlength="${q.limit}" placeholder="${q.placeholder}">${value}</textarea>` : `<input id="question-input" maxlength="${q.limit}" value="${value}" placeholder="${q.placeholder}">`;
  }
  return shell(`${header(`<div class="progress" aria-label="第 ${questionIndex + 1} 步，共 ${questions.length} 步">${questions.map((_, i) => `<span class="${i <= questionIndex ? 'is-active' : ''}"></span>`).join('')}</div>`)}<div class="question"><div class="page-body"><p class="question-number">${questionIndex + 1} / ${questions.length} · ${escapeText(student.className)}</p><h1>${q.title}</h1><p class="question-copy">${q.copy}</p><div class="field"><label for="${q.field === 'hasPhoto' ? 'question-file' : 'question-input'}">${q.label}</label>${input}<p id="question-error" class="field-error" role="alert"></p></div></div><p id="save-state" class="save-state" role="status">${escapeText(saveMessage)}</p><footer class="page-footer"><button class="primary" data-action="next">${questionIndex === questions.length - 1 ? '完成填写' : '下一页'}</button><button class="text-button" data-action="${questionIndex ? 'previous' : 'exit'}">${questionIndex ? '上一页' : '暂存并退出'}</button></footer></div>`);
}
function completeTemplate() {
  return shell(`${header('<p class="status">已完成</p>')}<div class="complete-page"><div class="completed-summary"><h1>已完成作答</h1><p>${escapeText(student.className)} · ${escapeText(student.name)}</p><fieldset disabled aria-label="已完成的作答">${questions.map(q => q.field === 'hasPhoto' ? `<div class="field"><label>个人照片</label>${photoUrl ? `<img class="photo-preview" src="${photoUrl}" alt="个人照片">` : '<p>已上传</p>'}</div>` : `<div class="field"><label>${q.label}</label><textarea disabled>${escapeText(student[q.field])}</textarea></div>`).join('')}</fieldset></div><footer class="page-footer"><button class="primary" data-action="edit">返回修改</button></footer></div>`);
}
function render() {
  const templates = {intro:introTemplate,create:identityTemplate,resume:identityTemplate,passcode:passcodeTemplate,question:questionTemplate,complete:completeTemplate};
  $('#app').innerHTML = templates[route]();
  document.querySelectorAll('[data-action]').forEach(button => button.onclick = () => act(button));
  $('#identity-form')?.addEventListener('submit', event => { event.preventDefault(); $('[data-action="identity-submit"]').click(); });
  $('#question-input')?.addEventListener('input', event => {
    const field = questions[questionIndex].field;
    student[field] = event.target.value;
    pending[field] = event.target.value;
    rememberDraft(); setSaveMessage('尚未保存…');
    clearTimeout(saveTimer); saveTimer = setTimeout(() => save().catch(() => {}), 650);
  });
  $('#question-file')?.addEventListener('change', uploadPhoto);
}
function go(next) { route = next; render(); window.scrollTo(0, 0); }
function setSaveMessage(message) { saveMessage = message; if ($('#save-state')) $('#save-state').textContent = message; }

async function save() {
  clearTimeout(saveTimer);
  if (saving) { await saving; if (Object.keys(pending).length) return save(); return; }
  if (!student || !Object.keys(pending).length) return;
  const snapshot = {...pending};
  setSaveMessage('正在保存…');
  saving = (async () => {
    try {
      const result = await api('/api/student', snapshot);
      for (const [key, value] of Object.entries(snapshot)) if (pending[key] === value) delete pending[key];
      student = {...result.student, ...pending}; rememberDraft();
      setSaveMessage(Object.keys(pending).length ? '尚未保存…' : '');
    } catch (error) { setSaveMessage('未保存：' + (error.message || '网络中断，正在重试')); throw error; }
    finally { saving = null; }
  })();
  return saving;
}

async function enter(result) {
  token = result.token; student = result.student; pending = {};
  remember('album-session', token);
  try { pending = JSON.parse(sessionStorage.getItem('album-draft-' + student.id) || '{}'); } catch {}
  student = {...student, ...pending};
  setSaveMessage(Object.keys(pending).length ? '有内容等待保存' : '');
  if (photoUrl) URL.revokeObjectURL(photoUrl); photoUrl = '';
  if (student.hasPhoto) {
    try { photoUrl = URL.createObjectURL(await api('/api/student/photo', undefined, false, true)); } catch {}
  }
}
async function submitIdentity() {
  const classId = $('#student-class').value, number = $('#student-number').value.trim(), value = $('#student-name').value.trim();
  if (!classId || !number || !value) throw Error('请选择班级并填写完整信息。');
  if (route === 'create') {
    const identity = {classId, number, name:value};
    if (!registration || typeof registration.requestId !== 'string' || registration.requestId.length < 32 ||
        ['classId','number','name'].some(k => registration[k] !== identity[k])) {
      registration = {...identity, code:makePasscode(), requestId:makeRequestId()};
      remember('album-registration', JSON.stringify(registration));
    }
    code = registration.code;
    await enter(await api('/api/register', registration));
    go('passcode');
  } else {
    await enter(await api('/api/login', {classId,number,code:value}));
    questionIndex = Math.max(0, questions.findIndex(q => !student[q.field]));
    if (student.complete) questionIndex = 0;
    go('question');
  }
}

async function act(button) {
  if (actionBusy || photoBusy) return;
  actionBusy = true; button.disabled = true;
  try {
    const action = button.dataset.action;
    if (action === 'create' || action === 'resume') {
      await loadClasses();
      if (loadError) throw Error(loadError);
      go(action);
    } else if (action === 'intro') go(action);
    else if (action === 'reload') { await loadClasses(); render(); }
    else if (action === 'edit') {
      token = ''; remember('album-session', null); go('resume');
      $('#student-class').value = student.classId; $('#student-number').value = student.number;
    }
    else if (action === 'identity-submit') await submitIdentity();
    else if (action === 'begin') { remember('album-registration', null); registration = null; code = ''; questionIndex = 0; go('question'); }
    else if (action === 'next' || action === 'previous') {
      await save();
      if (action === 'next' && !String(student[questions[questionIndex].field] || '').trim()) throw Error(questionIndex === questions.length - 1 ? '请选择并上传一张照片。' : '填写后才能进入下一页。');
      if (action === 'next' && questionIndex === questions.length - 1) {
        const result = await api('/api/student'); student = result.student;
        if (!student.complete) throw Error('还有资料未保存完整，请返回检查。');
        go('complete');
      } else { questionIndex += action === 'next' ? 1 : -1; render(); window.scrollTo(0,0); }
    } else if (action === 'exit') {
      await save(); token = ''; student = null; remember('album-session', null); go('intro');
    }
  } catch (error) {
    const target = $('#identity-error') || $('#question-error');
    if (target) target.textContent = error.message || '网络连接中断，请稍后重试。';
    else { loadError = error.message; render(); }
  } finally { actionBusy = false; button.disabled = false; }
}

async function uploadPhoto(event) {
  const file = event.target.files[0];
  if (!file) return;
  if (!['image/jpeg','image/png','image/webp'].includes(file.type) || file.size > 20 * 1024 * 1024) { $('#question-error').textContent = '请选择 20MB 以内的 JPG、PNG 或 WebP 照片。'; return; }
  photoBusy = true; $('[data-action="next"]').disabled = true; setSaveMessage('正在优化并上传照片…');
  let sourceUrl;
  try {
    const image = new Image(); sourceUrl = URL.createObjectURL(file); image.src = sourceUrl; await image.decode();
    const scale = Math.min(1, 1800 / Math.max(image.naturalWidth, image.naturalHeight));
    const canvas = document.createElement('canvas'); canvas.width = Math.round(image.naturalWidth * scale); canvas.height = Math.round(image.naturalHeight * scale);
    const context = canvas.getContext('2d'); context.fillStyle = '#ffffff'; context.fillRect(0,0,canvas.width,canvas.height); context.drawImage(image,0,0,canvas.width,canvas.height);
    const blob = await new Promise(resolve => canvas.toBlob(resolve,'image/jpeg',0.88));
    if (!blob) throw Error('照片无法读取，请换一张 JPG 照片。');
    const result = await api('/api/student/photo', blob, true);
    student = {...result.student, ...pending};
    if (photoUrl) URL.revokeObjectURL(photoUrl); photoUrl = URL.createObjectURL(blob);
    setSaveMessage(''); render();
  } catch (error) { $('#question-error').textContent = error.message || '上传失败，请重新选择照片再试。'; setSaveMessage('照片上传失败，请重试'); }
  finally { if (sourceUrl) URL.revokeObjectURL(sourceUrl); photoBusy = false; const next = $('[data-action="next"]'); if (next) next.disabled = false; }
}
async function loadClasses() { try { const data = await api('/api/classes'); classes = data.classes; term = data.term; loadError = ''; } catch { loadError = '暂时无法连接老师电脑，请确认填写入口仍然开启。'; } }
async function start() {
  await loadClasses();
  if (token) {
    try {
      const result = await api('/api/student'); await enter({token,student:result.student});
      questionIndex = student.complete ? 3 : Math.max(0, questions.findIndex(q => !student[q.field]));
      if (registration && registration.classId === student.classId && registration.number === student.number) {
        code = registration.code; route = 'passcode';
      } else route = student.complete ? 'complete' : 'question';
    }
    catch { token = ''; remember('album-session', null); }
  }
  render();
}
window.addEventListener('online', () => save().catch(() => {}));
window.addEventListener('beforeunload', event => { if (Object.keys(pending).length || photoBusy) { event.preventDefault(); event.returnValue = ''; } });
document.addEventListener('visibilitychange', () => { if (document.hidden) save().catch(() => {}); });
setInterval(() => { if (Object.keys(pending).length && !saving) save().catch(() => {}); }, 5000);
$('#app').innerHTML = '<p class="waiting-note">正在连接老师的班级…</p>';
start();
