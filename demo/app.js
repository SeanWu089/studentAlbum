const STORAGE_KEY = 'student-album-student-demo-v2';

const questions = [
  {
    field: 'origin',
    title: '你的籍贯是哪里？',
    copy: '填写到省、市或县都可以。',
    label: '籍贯',
    placeholder: '例如：江苏南京',
    type: 'text',
  },
  {
    field: 'subject',
    title: '高中阶段，你最喜欢哪一门课？',
    copy: '写下第一时间想到的那一门即可。',
    label: '最喜欢的科目',
    placeholder: '例如：历史',
    type: 'text',
  },
  {
    field: 'ability',
    title: '你最自豪的一项能力是什么？',
    copy: '也可以写一个希望老师了解的特点。',
    label: '能力或特点',
    placeholder: '例如：我擅长把复杂的事情整理清楚。',
    type: 'textarea',
  },
  {
    field: 'photoName',
    title: '最后，上传一张个人照片',
    copy: '建议选择一张清晰的正面生活照。',
    label: '个人照片',
    type: 'file',
  },
];

let database = loadDatabase();
let route = 'intro';
let activeStudentId = null;
let questionIndex = 0;

function loadDatabase() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || { students: [] };
  } catch {
    return { students: [] };
  }
}

function saveDatabase() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(database));
}

function activeStudent() {
  return database.students.find((student) => student.id === activeStudentId);
}

function makePasscode() {
  return String(Math.floor(100000 + Math.random() * 900000));
}

function escapeHtml(value) {
  return String(value || '').replace(/[&<>'"]/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    "'": '&#39;',
    '"': '&quot;',
  })[character]);
}

function appShell(content) {
  return `<main class="device"><section class="screen">${content}</section></main>`;
}

function header(right = '') {
  return `<header class="screen-header"><p class="brand">学生档案</p>${right}</header>`;
}

function introTemplate() {
  return appShell(`
    ${header('<p class="status">约 3 分钟</p>')}
    <div class="intro">
      <div class="intro-copy">
        <p class="section-label">学生资料收集</p>
        <h1>让老师<br>更了解你</h1>
        <p>填写几项基本信息。演示内容保存在当前浏览器，中途退出后也可以继续。</p>
      </div>
      <footer class="page-footer">
        <button class="primary" data-action="create">开始填写</button>
        <button class="secondary" data-action="resume">继续上次填写</button>
      </footer>
    </div>
  `);
}

function identityTemplate(mode) {
  const creating = mode === 'create';
  return appShell(`
    ${header('<button class="text-button" data-action="intro">返回</button>')}
    <div class="identity">
      <div class="page-body">
        <h1>${creating ? '确认你的身份' : '继续填写'}</h1>
        <p class="identity-copy">${creating ? '首次填写后会生成一个六位续填口令。' : '输入学号和续填口令，继续未完成的内容。'}</p>
        <form id="identity-form" novalidate>
          <div class="field">
            <label for="student-id">学号</label>
            <input id="student-id" inputmode="numeric" autocomplete="off" placeholder="请输入学号">
          </div>
          ${creating ? `
            <div class="field">
              <label for="student-name">姓名</label>
              <input id="student-name" autocomplete="name" placeholder="请输入姓名">
            </div>
          ` : `
            <div class="field">
              <label for="student-code">续填口令</label>
              <input id="student-code" inputmode="numeric" maxlength="6" autocomplete="one-time-code" placeholder="请输入六位数字">
            </div>
          `}
          <p class="field-error" id="identity-error"></p>
        </form>
      </div>
      <footer class="page-footer">
        <button class="primary" data-action="identity-submit" data-mode="${mode}">${creating ? '生成续填口令' : '进入档案'}</button>
      </footer>
    </div>
  `);
}

function passcodeTemplate() {
  const student = activeStudent();
  return appShell(`
    ${header('<p class="status">请截图保存</p>')}
    <div class="passcode-page">
      <div class="page-body">
        <p class="section-label">续填凭证</p>
        <h1>保存这组六位数字</h1>
        <p class="identity-copy">下次继续填写时，需要同时输入学号和续填口令。</p>
        <div class="passcode" aria-label="六位续填口令">${student.code}</div>
      </div>
      <footer class="page-footer">
        <button class="primary" data-action="begin-questions">已保存，继续</button>
      </footer>
    </div>
  `);
}

function progressTemplate() {
  return `<div class="progress" aria-label="填写进度">${questions.map((_, index) => `<span class="${index <= questionIndex ? 'is-active' : ''}"></span>`).join('')}</div>`;
}

function questionTemplate() {
  const student = activeStudent();
  const question = questions[questionIndex];
  const value = escapeHtml(student[question.field]);
  let input;

  if (question.type === 'textarea') {
    input = `<textarea id="question-input" data-field="${question.field}" placeholder="${question.placeholder}">${value}</textarea>`;
  } else if (question.type === 'file') {
    input = `<label class="file-input" for="question-file">
      <span><strong>${value || '选择照片'}</strong><small>${value ? '点击可重新选择' : '支持 JPG、PNG，演示版仅记录文件名'}</small></span>
      <input id="question-file" type="file" accept="image/jpeg,image/png,image/webp" data-file>
    </label>`;
  } else {
    input = `<input id="question-input" data-field="${question.field}" value="${value}" placeholder="${question.placeholder}">`;
  }

  return appShell(`
    ${header(progressTemplate())}
    <div class="question">
      <div class="page-body">
        <p class="question-number">${questionIndex + 1} / ${questions.length}</p>
        <h1>${question.title}</h1>
        <p class="question-copy">${question.copy}</p>
        <div class="field">
          <label for="${question.type === 'file' ? 'question-file' : 'question-input'}">${question.label}</label>
          ${input}
          <p class="field-error" id="question-error"></p>
        </div>
      </div>
      <p class="save-state" id="save-state">${student.updatedAt ? '已自动保存' : ''}</p>
      <footer class="page-footer">
        <button class="primary" data-action="next-question">${questionIndex === questions.length - 1 ? '完成填写' : '下一页'}</button>
        ${questionIndex > 0 ? '<button class="text-button" data-action="previous-question">上一页</button>' : '<button class="text-button" data-action="intro">暂存并退出</button>'}
      </footer>
    </div>
  `);
}

function completeTemplate() {
  return appShell(`
    ${header('<p class="status">已完成</p>')}
    <div class="complete-page">
      <div class="page-body">
        <div class="complete-mark" aria-hidden="true">✓</div>
        <h1>资料已保存</h1>
        <p class="complete-copy">演示资料已保存在当前浏览器，暂未同步给老师。请在同一浏览器用学号和续填口令继续填写。</p>
      </div>
      <footer class="page-footer">
        <button class="primary" data-action="intro">返回首页</button>
      </footer>
    </div>
  `);
}

function render() {
  const templates = {
    intro: introTemplate,
    create: () => identityTemplate('create'),
    resume: () => identityTemplate('resume'),
    passcode: passcodeTemplate,
    question: questionTemplate,
    complete: completeTemplate,
  };
  document.getElementById('app').innerHTML = templates[route]();
  bindEvents();
}

function go(nextRoute) {
  route = nextRoute;
  render();
}

function bindEvents() {
  document.querySelectorAll('[data-action]').forEach((button) => {
    button.addEventListener('click', () => handleAction(button));
  });

  document.querySelectorAll('[data-field]').forEach((input) => {
    input.addEventListener('input', () => updateField(input.dataset.field, input.value));
  });

  document.querySelector('[data-file]')?.addEventListener('change', handleFile);

  document.getElementById('identity-form')?.addEventListener('submit', (event) => {
    event.preventDefault();
    document.querySelector('[data-action="identity-submit"]')?.click();
  });
}

function handleAction(button) {
  const action = button.dataset.action;
  if (action === 'create' || action === 'resume' || action === 'intro') return go(action === 'intro' ? 'intro' : action);
  if (action === 'identity-submit') return submitIdentity(button.dataset.mode);
  if (action === 'begin-questions') {
    questionIndex = 0;
    return go('question');
  }
  if (action === 'next-question') return nextQuestion();
  if (action === 'previous-question') {
    questionIndex -= 1;
    return render();
  }
}

function submitIdentity(mode) {
  const id = document.getElementById('student-id').value.trim();
  const error = document.getElementById('identity-error');
  if (!id) {
    error.textContent = '请输入学号。';
    return;
  }

  if (mode === 'create') {
    const name = document.getElementById('student-name').value.trim();
    if (!name) {
      error.textContent = '请输入姓名。';
      return;
    }
    if (database.students.some((student) => student.id === id)) {
      error.textContent = '这个学号已经有档案，请选择继续填写。';
      return;
    }
    database.students.push({
      id,
      name,
      code: makePasscode(),
      origin: '',
      subject: '',
      ability: '',
      photoName: '',
      updatedAt: Date.now(),
    });
    activeStudentId = id;
    saveDatabase();
    go('passcode');
    return;
  }

  const code = document.getElementById('student-code').value.trim();
  const student = database.students.find((item) => item.id === id && item.code === code);
  if (!student) {
    error.textContent = '学号或续填口令不正确。';
    return;
  }
  activeStudentId = student.id;
  const missingIndex = questions.findIndex((question) => !student[question.field]);
  questionIndex = missingIndex === -1 ? questions.length - 1 : missingIndex;
  go('question');
}

function updateField(field, value) {
  const student = activeStudent();
  student[field] = value;
  student.updatedAt = Date.now();
  saveDatabase();
  const saveState = document.getElementById('save-state');
  if (saveState) saveState.textContent = '已自动保存';
}

function handleFile(event) {
  const file = event.target.files[0];
  if (!file) return;
  if (file.size > 8 * 1024 * 1024) {
    document.getElementById('question-error').textContent = '请选择 8MB 以内的照片。';
    return;
  }
  updateField('photoName', file.name);
  render();
}

function nextQuestion() {
  const student = activeStudent();
  const question = questions[questionIndex];
  if (!String(student[question.field] || '').trim()) {
    document.getElementById('question-error').textContent = question.type === 'file' ? '请选择一张照片。' : '填写后才能进入下一页。';
    return;
  }
  if (questionIndex < questions.length - 1) {
    questionIndex += 1;
    render();
    return;
  }
  go('complete');
}

render();
