let trash = [], snapshots = [], editing = false;
let students = [], classes = [], filter = 'all', publicUrl = '', lanUrl = '', adminKey = '', currentTerm = '';
let loaded = false, refreshBusy = false, detailId = null, photoUrl = '', detailVersion = '';
const $ = (selector) => document.querySelector(selector);
const escapeText = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));

function setConnectionStatus(selector, text, tone) {
  const node = $(selector);
  node.textContent = text;
  node.className = `connection-status ${tone}`;
}

async function api(path, data, blob = false) {
  if (!adminKey) {
    const response = await fetch('/api/admin/bootstrap', {cache:'no-store'});
    if (!response.ok) throw Error('无法连接本机管理服务。');
    adminKey = (await response.json()).key;
  }
  const response = await fetch(path, {method:data === undefined ? 'GET' : 'POST',
    headers:{'X-Admin-Key':adminKey, ...(data === undefined ? {} : {'Content-Type':data instanceof Blob ? 'image/jpeg' : 'application/json'})},
    body:data === undefined ? undefined : data instanceof Blob ? data : JSON.stringify(data), signal:AbortSignal.timeout(12000), cache:'no-store'});
  if (response.status === 401) adminKey = '';
  if (!response.ok) {
    const result = await response.json().catch(() => ({}));
    throw Error(result.error || '暂时无法连接，请检查启动窗口。');
  }
  return blob ? response.blob() : response.json();
}

function renderStudents() {
  const classId = $('#class-filter').value;
  const scoped = students.filter(s => s.classId === classId);
  $('#class-title').textContent = classes.find(c => c.id === classId)?.name || '学生档案';
  $('#class-tabs').innerHTML = classes.map(c => `<button class="button ${c.id === classId ? 'solid' : ''}" data-class="${c.id}">${escapeText(c.name)} <small>${students.filter(s => s.classId === c.id).length} 人</small></button>`).join('');
  document.querySelectorAll('[data-class]').forEach(b => b.onclick = () => { $('#class-filter').value = b.dataset.class; $('#search').value = ''; renderStudents(); });
  const query = $('#search').value.trim().toLowerCase();
  const visible = scoped.filter(s => (filter === 'all' || s.complete === (filter === 'complete')) &&
    [s.name, s.number, s.origin, s.className].some(v => v.toLowerCase().includes(query)));
  const completed = scoped.filter(s => s.complete).length;
  const percent = scoped.length ? Math.round(completed / scoped.length * 100) : 0;
  $('#total').textContent = scoped.length;
  $('#completed').textContent = completed;
  $('#pending').textContent = scoped.length - completed;
  $('#percent').textContent = percent;
  $('#progress').value = percent;
  $('#nav-count').textContent = students.length;
  $('#export').disabled = !visible.length;
  $('#rows').innerHTML = visible.map(s => `<tr><td><div class="student"><span class="avatar">${escapeText(s.name.slice(-2))}</span><div><strong>${escapeText(s.name)}</strong><small>${escapeText(s.number)}</small></div></div></td><td>${escapeText(s.className)}</td><td>${escapeText(s.origin || '待填写')}</td><td>${escapeText(s.subject || '待填写')}</td><td class="ability-cell">${escapeText(s.ability || '待填写')}</td><td><span class="badge ${s.complete ? '' : 'pending'}">${s.complete ? '资料完整' : '待补充'}</span></td><td><button class="view" data-id="${s.id}" aria-label="查看${escapeText(s.name)}的档案">查看 ↗</button></td></tr>`).join('');
  $('#count').textContent = `共 ${visible.length} 位`;
  $('#table-wrap').hidden = !visible.length;
  $('#empty').hidden = !!visible.length;
  $('#empty').innerHTML = scoped.length ? '<h3>没有符合条件的档案</h3><p>试试其他状态或关键词。</p>' : '<span class="empty-mark" aria-hidden="true">册</span><h3>这个班级还没有学生档案</h3><p>学生提交后会显示在这里。</p>';
  document.querySelectorAll('[data-id]').forEach(b => b.onclick = () => showDetail(b.dataset.id));
  return visible;
}

async function refresh() {
  if (refreshBusy) return;
  refreshBusy = true;
  try {
    const data = await api('/api/admin/overview');
    students = data.students;
    trash = data.trash || [];
    snapshots = data.snapshots?.items || [];
    renderTrash();
    renderHistory(data.snapshots?.error || '');
    data.classes.sort((a,b) => a.name.localeCompare(b.name, 'zh-CN', {numeric:true}));
    if (JSON.stringify(classes) !== JSON.stringify(data.classes) || !loaded) {
      classes = data.classes;
      const selected = $('#class-filter').value;
      $('#class-filter').innerHTML = classes.map(c => `<option value="${c.id}">${escapeText(c.name)}</option>`).join('');
      $('#class-filter').value = classes.some(c => c.id === selected) ? selected : (classes[0]?.id || '');
      $('#class-chips').innerHTML = classes.length ? classes.map(c => `<span class="class-chip"><span>${escapeText(c.name)}</span><button type="button" data-delete-class="${c.id}" aria-label="删除班级 ${escapeText(c.name)}" title="删除班级">×</button></span>`).join('') : '<p class="muted">尚未添加班级</p>';
      document.querySelectorAll('[data-delete-class]').forEach(button => button.onclick = () => requestClassDelete(button.dataset.deleteClass));
      $('#class-count').textContent = `${classes.length} 个班级`;
    }
    currentTerm = data.term;
    if (!loaded) $('#term').value = data.term;
    $('#roster-term').textContent = data.term;
    const connection = data.connection || {};
    const lanOnline = connection.lanStatus === 'online' && !!connection.lanUrl;
    const publicOnline = connection.tunnelStatus === 'online' && !!connection.publicUrl;
    lanUrl = lanOnline ? connection.lanUrl : '';
    publicUrl = publicOnline ? connection.publicUrl : '';
    $('#lan-address').textContent = lanOnline ? lanUrl : '尚未获取到局域网地址';
    setConnectionStatus('#lan-status', lanOnline ? '可用' : '不可用', lanOnline ? 'online' : 'offline');
    $('#copy-lan').disabled = !lanOnline;
    $('#public-address').textContent = connection.configuredPublicUrl || (connection.tunnelStatus === 'connecting' ? '正在获取固定公网地址…' : '尚未获取固定公网地址');
    $('#public-message').textContent = connection.message || '公网状态暂不可用。';
    const publicStatus = {
      online: ['已连接', 'online'],
      connecting: ['连接中', 'pending'],
      error: ['连接异常', 'error'],
      not_configured: ['尚未配置', 'offline'],
      off: ['未启动', 'offline'],
    }[connection.tunnelStatus] || ['状态未知', 'offline'];
    setConnectionStatus('#public-status', publicStatus[0], publicStatus[1]);
    $('#copy-public').disabled = !publicOnline;
    $('#reconnect').disabled = connection.tunnelStatus === 'connecting';
    $('#sync-state').textContent = '已连接 · 每 3 秒更新';
    $('#sync-state').classList.remove('form-error');
    renderStudents();
    renderView();
    const detail = students.find(s => s.id === detailId);
    if (!editing && $('#detail').open && detail && detailVersion !== String(detail.updatedAt)) await showDetail(detailId);
    loaded = true;
  } catch {
    $('#sync-state').textContent = '连接中断 · 正在重试';
    $('#sync-state').classList.add('form-error');
    setConnectionStatus('#lan-status', '不可用', 'error');
    setConnectionStatus('#public-status', '不可用', 'error');
    $('#lan-address').textContent = '无法连接本机服务';
    $('#public-message').textContent = '无法连接本机服务，请重新打开学生小档案。';
    $('#copy-lan').disabled = true;
    $('#copy-public').disabled = true;
  } finally { refreshBusy = false; }
}

async function showDetail(id) {
  const s = students.find(s => s.id === id);
  if (!s) return;
  detailId = id;
  detailVersion = String(s.updatedAt);
  if (photoUrl) { URL.revokeObjectURL(photoUrl); photoUrl = ''; }
  $('#detail-content').innerHTML = `<div id="portrait">${s.hasPhoto ? '<p class="detail-note">正在读取照片…</p>' : `<span class="avatar detail-avatar">${escapeText(s.name.slice(-2))}</span>`}</div><h2>${escapeText(s.name)}</h2><p class="detail-note">${escapeText(s.className)} · 学号 ${escapeText(s.number)}</p><dl>${[['籍贯',s.origin],['喜欢的科目',s.subject],['我的闪光点',s.ability],['想对老师说的话',s.message]].map(([k,v]) => `<dt>${k}</dt><dd>${escapeText(v || '待填写')}</dd>`).join('')}<dt>最近保存</dt><dd>${new Date(s.updatedAt * 1000).toLocaleString('zh-CN')}</dd><dt>资料状态</dt><dd>${s.complete ? '资料完整' : '待补充'}</dd></dl><div class="detail-actions"><button id="edit-student" class="button solid">编辑资料</button><button id="delete-student" class="button">移入回收站</button></div><button id="reset-code" class="button">重置续填口令</button><p id="reset-result" class="detail-note" role="status"></p>`;
  if (!$('#detail').open) $('#detail').showModal();
  $('#edit-student').onclick = () => editStudent(s);
  $('#delete-student').onclick = async () => { if (!confirm(`将 ${s.className} · ${s.name}（${s.number}）移入回收站？30 天内可恢复。`)) return; try { await api('/api/admin/delete', {id}); $('#detail').close(); await refresh(); toast('已移入回收站'); } catch(e) { toast(e.message); } };
  $('#reset-code').onclick = async () => {
    if (!confirm(`为 ${s.name} 重置续填口令？旧口令会立即失效。`)) return;
    try { const result = await api('/api/admin/reset-code', {id}); $('#reset-result').textContent = `新口令：${result.code}。请保存并告知学生，关闭后不再显示。`; }
    catch (error) { $('#reset-result').textContent = error.message; }
  };
  if (s.hasPhoto) {
    try {
      const blob = await api(`/api/admin/photos/${id}`, undefined, true);
      if (detailId !== id || !$('#detail').open) return;
      photoUrl = URL.createObjectURL(blob);
      $('#portrait').innerHTML = `<a href="${photoUrl}" target="_blank" rel="noopener"><img class="student-photo" src="${photoUrl}" alt="${escapeText(s.name)}的照片"></a>`;
    } catch { if (detailId === id) $('#portrait').textContent = '照片读取失败，请关闭后重试。'; }
  }
}

$('#detail').addEventListener('close', () => { editing = false; detailId = null; if (photoUrl) URL.revokeObjectURL(photoUrl); photoUrl = ''; });
$('#search').oninput = renderStudents;
$('#class-filter').onchange = renderStudents;
document.querySelectorAll('[data-filter]').forEach(b => b.onclick = () => {
  filter = b.dataset.filter;
  document.querySelectorAll('[data-filter]').forEach(x => x.classList.toggle('selected', x === b));
  renderStudents();
});
$('#class-form').onsubmit = async event => {
  event.preventDefault();
  const button = $('#save-classes'); button.disabled = true; $('#class-error').textContent = '';
  const names = $('#class-names').value.split(/[\n,，、;；]+/).map(s => s.trim()).filter(Boolean);
  try { await api('/api/admin/classes', {term:$('#term').value.trim(), names}); $('#class-names').value = ''; await refresh(); toast('班级设置已保存，学生页面已可选择'); }
  catch (error) { $('#class-error').textContent = error.message; }
  finally { button.disabled = false; }
};
$('#reconnect').onclick = async () => { $('#reconnect').disabled = true; try { await api('/api/admin/tunnel', {}); await refresh(); } catch (error) { toast(error.message); } finally { $('#reconnect').disabled = false; } };
let toastTimer;
function toast(message) { $('#toast').textContent = message; $('#toast').classList.add('visible'); clearTimeout(toastTimer); toastTimer = setTimeout(() => $('#toast').classList.remove('visible'), 3500); }
async function copyLink(url, label) { try { await navigator.clipboard.writeText(url); toast(`${label}已复制`); } catch { toast('复制失败，请手动复制上方网址'); } }
$('#copy-lan').onclick = () => copyLink(lanUrl, '局域网链接');
$('#copy-public').onclick = () => copyLink(publicUrl, '公网链接');
$('#export').onclick = () => {
  // Quote cells and neutralize spreadsheet formula prefixes.
  const cell = value => '"' + String(value ?? '').replace(/^[=+@\-\t\r]/, "'$&").replaceAll('"','""') + '"';
  const rows = [['班级','学号','姓名','籍贯','科目','闪光点','想对老师说的话','状态'], ...renderStudents().map(s => [s.className,s.number,s.name,s.origin,s.subject,s.ability,s.message,s.complete?'完整':'待补充'])];
  const url = URL.createObjectURL(new Blob(['\ufeff' + rows.map(row => row.map(cell).join(',')).join('\r\n')], {type:'text/csv;charset=utf-8'}));
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = '学生档案.csv'; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
};
refresh();
setInterval(refresh, 3000);

function renderTrash() {
  $('#trash-count').textContent = `${trash.length} 份档案`;
  const groups = [...trash.reduce((map, student) => {
    if (!map.has(student.classId)) map.set(student.classId, {id:student.classId, name:student.className, students:[]});
    map.get(student.classId).students.push(student);
    return map;
  }, new Map()).values()].sort((a,b) => a.name.localeCompare(b.name, 'zh-CN', {numeric:true}));
  $('#trash-list').innerHTML = groups.length ? groups.map(group => `<section class="trash-group"><header><div><h3>${escapeText(group.name)}</h3><span>${group.students.length} 位学生</span></div><button class="button" data-restore-class="${group.id}">恢复本班全部</button></header><div>${group.students.map(s => `<div class="trash-row"><div><strong>${escapeText(s.name)}</strong><p>学号 ${escapeText(s.number)} · 剩余 ${Math.max(0,Math.ceil((s.deletedAt + 30*86400 - Date.now()/1000)/86400))} 天</p></div><button class="button" data-restore="${s.id}">恢复档案</button></div>`).join('')}</div></section>`).join('') : '<p class="muted">回收站为空</p>';
  document.querySelectorAll('[data-restore]').forEach(b => b.onclick = async () => { b.disabled = true; try { await api('/api/admin/restore',{id:b.dataset.restore}); await refresh(); toast('已恢复到原班级'); } catch(e) { toast(e.message); b.disabled = false; } });
  document.querySelectorAll('[data-restore-class]').forEach(b => b.onclick = async () => { b.disabled = true; try { const result = await api('/api/admin/restore-class',{id:b.dataset.restoreClass}); await refresh(); toast(`已恢复 ${result.restored} 位学生`); } catch(e) { toast(e.message); b.disabled = false; } });
}

function formatSnapshotTime(value) {
  return new Date(value * 1000).toLocaleString('zh-CN', {month:'long', day:'numeric', hour:'2-digit', minute:'2-digit'});
}

function renderHistory(error = '') {
  $('#history-count').textContent = `${snapshots.length} 个版本`;
  $('#history-error').textContent = error;
  $('#history-list').innerHTML = snapshots.length ? snapshots.map((snapshot, index) => `<article class="history-item">
    <div class="history-marker" aria-hidden="true">${index === 0 ? '今' : '史'}</div>
    <div class="history-copy"><div class="history-heading"><strong>${escapeText(formatSnapshotTime(snapshot.createdAt))}</strong><span>${escapeText(snapshot.reason)}</span></div><p>${snapshot.classes} 个班级 · ${snapshot.students} 位学生</p></div>
    <button class="button" type="button" data-restore-snapshot="${snapshot.id}">恢复</button>
  </article>`).join('') : '<div class="history-empty"><span aria-hidden="true">史</span><h3>还没有历史版本</h3><p>资料发生变化后，系统会自动保留最近的版本。</p></div>';
  document.querySelectorAll('[data-restore-snapshot]').forEach(button => button.onclick = () => requestSnapshotRestore(button.dataset.restoreSnapshot));
}

let pendingSnapshotRestore = null;
function requestSnapshotRestore(id) {
  const snapshot = snapshots.find(item => item.id === id);
  if (!snapshot) return;
  pendingSnapshotRestore = id;
  $('#history-restore-title').textContent = `恢复到${formatSnapshotTime(snapshot.createdAt)}？`;
  $('#history-restore-copy').textContent = `该版本包含 ${snapshot.classes} 个班级、${snapshot.students} 位学生。当前资料会先自动保存。`;
  $('#history-restore-dialog').showModal();
}

$('#history-restore-cancel').onclick = () => $('#history-restore-dialog').close();
$('#history-restore-dialog').addEventListener('close', () => { pendingSnapshotRestore = null; $('#history-restore-confirm').disabled = false; });
$('#history-restore-confirm').onclick = async () => {
  if (!pendingSnapshotRestore) return;
  const id = pendingSnapshotRestore;
  $('#history-restore-confirm').disabled = true;
  try {
    const result = await api('/api/admin/restore-snapshot', {id});
    $('#history-restore-dialog').close();
    await refresh();
    toast(`已恢复 ${result.classes} 个班级、${result.students} 位学生`);
  } catch (error) {
    toast(error.message);
    $('#history-restore-confirm').disabled = false;
  }
};

let pendingClassDelete = null;
async function deleteClass(id) {
  try {
    const result = await api('/api/admin/delete-class', {id});
    await refresh();
    toast(result.moved ? `班级已删除，${result.moved} 位学生已移入回收站` : '空班级已删除');
  } catch (error) { toast(error.message); }
}

function requestClassDelete(id) {
  const current = classes.find(item => item.id === id);
  if (!current) return;
  const count = students.filter(student => student.classId === id).length;
  if (!count) { deleteClass(id); return; }
  pendingClassDelete = id;
  $('#class-delete-title').textContent = `确认删除“${current.name}”吗？`;
  $('#class-delete-dialog').showModal();
}

$('#class-delete-cancel').onclick = () => $('#class-delete-dialog').close();
$('#class-delete-dialog').addEventListener('close', () => { pendingClassDelete = null; $('#class-delete-confirm').disabled = false; });
$('#class-delete-confirm').onclick = async () => {
  if (!pendingClassDelete) return;
  const id = pendingClassDelete;
  $('#class-delete-confirm').disabled = true;
  await deleteClass(id);
  $('#class-delete-dialog').close();
};

function activeView() {
  const hash = location.hash.slice(1);
  if (hash === 'trash') return 'trash';
  if (hash === 'classes' || hash === 'class-settings') return 'classes';
  if (hash === 'history') return 'history';
  return 'students';
}

function renderView() {
  const view = activeView();
  document.querySelectorAll('[data-view-panel]').forEach(panel => { panel.hidden = panel.dataset.viewPanel !== view; });
  document.querySelectorAll('.nav[data-view]').forEach(link => {
    const selected = link.dataset.view === view;
    link.classList.toggle('active', selected);
    if (selected) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
  });
  const labels = {students:'学生档案', trash:'回收站', classes:'本学期班级', history:'资料历史'};
  $('#term-title').textContent = `${currentTerm || '我的班级'} / ${labels[view]}`;
}

function setSidebarCollapsed(collapsed) {
  document.body.classList.toggle('sidebar-collapsed', collapsed);
  $('#sidebar-toggle').setAttribute('aria-expanded', String(!collapsed));
  $('#sidebar-toggle').setAttribute('aria-label', collapsed ? '展开侧栏' : '收起侧栏');
  try { localStorage.setItem('admin-sidebar-collapsed', collapsed ? '1' : '0'); } catch {}
}

let sidebarCollapsed = false;
try { sidebarCollapsed = localStorage.getItem('admin-sidebar-collapsed') === '1'; } catch {}
setSidebarCollapsed(sidebarCollapsed);
$('#sidebar-toggle').onclick = () => {
  sidebarCollapsed = !document.body.classList.contains('sidebar-collapsed');
  setSidebarCollapsed(sidebarCollapsed);
};
window.addEventListener('hashchange', renderView);
renderView();
function editStudent(s) {
  editing = true;
  $('#detail-content').innerHTML = `<h2>编辑学生资料</h2><form id="edit-form" class="edit-form"><label>班级<select name="classId">${classes.map(c => `<option value="${c.id}" ${c.id===s.classId?'selected':''}>${escapeText(c.name)}</option>`).join('')}</select></label>${[['number','学号',40],['name','姓名',60],['origin','籍贯',100],['subject','喜欢的科目',80],['ability','闪光点',1000],['message','想对老师说的话',2000]].map(([key,label,max]) => `<label>${label}<textarea name="${key}" maxlength="${max}" ${['number','name'].includes(key)?'required':''}>${escapeText(s[key])}</textarea></label>`).join('')}<label>更换照片<input id="edit-photo" type="file" accept="image/jpeg,image/png,image/webp"></label><p id="edit-error" role="alert" class="form-error"></p><div class="detail-actions"><button class="button solid" type="submit">保存修改</button><button class="button" id="edit-cancel" type="button">取消</button></div></form>`;
  $('#edit-cancel').onclick = () => { editing = false; showDetail(s.id); };
  $('#edit-form').onsubmit = async event => {
    event.preventDefault(); const button = event.target.querySelector('[type=submit]'); button.disabled = true;
    try {
      const file = $('#edit-photo').files[0];
      if (file && file.size > 8*1024*1024) throw Error('请选择 8MB 以内的照片。');
      await api('/api/admin/edit', {id:s.id,...Object.fromEntries(new FormData(event.target))});
      if(file) await api('/api/admin/photo-upload/'+s.id,file);
      editing = false; $('#detail').close(); await refresh(); toast('资料已更新');
    } catch(e) { $('#edit-error').textContent = e.message; } finally { button.disabled = false; }
  };
}
