const students = [
  {id:'2026001',name:'林晓禾',origin:'浙江 · 杭州',subject:'语文',ability:'把日常写成故事',complete:true},
  {id:'2026002',name:'陈一帆',origin:'江苏 · 苏州',subject:'物理',ability:'喜欢动手，修好小物件',complete:true},
  {id:'2026003',name:'周沐晴',origin:'四川 · 成都',subject:'历史',ability:'善于倾听，也热爱表达',complete:true},
  {id:'2026004',name:'许知远',origin:'安徽 · 合肥',subject:'数学',ability:'总能发现另一种解法',complete:false},
  {id:'2026005',name:'沈书宁',origin:'福建 · 厦门',subject:'英语',ability:'用画笔记录身边的人',complete:true},
  {id:'2026006',name:'陆星野',origin:'山东 · 青岛',subject:'待填写',ability:'等待发现',complete:false},
];
let filter='all', publicUrl='';
const escapeText=(value)=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function render(){
  const query=document.querySelector('#search').value.trim().toLowerCase();
  const visible=students.filter(s=>(filter==='all'||s.complete===(filter==='complete'))&&[s.name,s.id,s.origin].some(v=>v.toLowerCase().includes(query)));
  document.querySelector('#rows').innerHTML=visible.map(s=>`<tr><td><div class="student"><span class="avatar tone${students.indexOf(s)%4}">${s.name.slice(-2)}</span><div><strong>${s.name}</strong><small>${s.id}</small></div></div></td><td>${s.origin}</td><td>${s.subject}</td><td>${s.ability}</td><td><span class="badge ${s.complete?'':'pending'}">${s.complete?'资料完整':'待补充'}</span></td><td><button class="view" data-id="${s.id}" aria-label="查看${s.name}的档案">查看 ↗</button></td></tr>`).join('');
  document.querySelector('#count').textContent=`共 ${visible.length} 位`;
  document.querySelector('#empty').hidden=visible.length>0;
  document.querySelectorAll('[data-id]').forEach(b=>b.onclick=()=>showDetail(b.dataset.id));
}
function showDetail(id){const s=students.find(s=>s.id===id);document.querySelector('#detail-content').innerHTML=`<span class="avatar detail-avatar">${s.name.slice(-2)}</span><h2>${s.name}</h2><p class="detail-note">学号 ${s.id} · 虚构示例</p><dl><dt>籍贯</dt><dd>${s.origin}</dd><dt>喜欢的科目</dt><dd>${s.subject}</dd><dt>我的闪光点</dt><dd>${s.ability}</dd><dt>资料状态</dt><dd>${s.complete?'资料完整':'待补充照片或个人资料'}</dd></dl><p class="detail-note">示例头像使用姓名，不代表已上传个人照片。</p>`;document.querySelector('#detail').showModal();}
document.querySelector('#search').oninput=render;
document.querySelectorAll('[data-filter]').forEach(b=>b.onclick=()=>{filter=b.dataset.filter;document.querySelectorAll('[data-filter]').forEach(x=>x.classList.toggle('selected',x===b));render();});
let toastTimer;
function toast(message){const el=document.querySelector('#toast');el.textContent=message;el.style.display='block';clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.style.display='none',3000);}
document.querySelector('#copy').onclick=async()=>{try{await navigator.clipboard.writeText(publicUrl);toast('填写链接已复制，可发送到手机');}catch{toast('复制失败，请手动复制上方链接');}};
document.querySelector('#export').onclick=()=>{const csv='\ufeff学号,姓名,籍贯,科目,闪光点,状态\n'+students.map(s=>[s.id,s.name,s.origin,s.subject,s.ability,s.complete?'完整':'待补充'].join(',')).join('\n');const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='学生档案-虚构示例.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('示例名单已导出');};
async function connection(){try{const response=await fetch('/api/status',{cache:'no-store'});if(!response.ok)throw Error();const status=await response.json();publicUrl=status.publicUrl||status.localUrl||'';document.querySelector('#connection').textContent=status.publicUrl || (status.localUrl ? `同一 Wi-Fi 可访问：${status.localUrl}（${status.message}）` : status.message);document.querySelector('#copy').disabled=!publicUrl;}catch{document.querySelector('#connection').textContent='请双击「启动演示.command」以生成手机访问链接。';}}
render();connection();setInterval(connection,5000);
