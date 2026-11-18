const v=document.getElementById('v'),shots=document.getElementById('shots'),msg=document.getElementById('msg');
let stream=null,imgs=[],list=[];
const $=i=>document.getElementById(i);
async function cam(){
    if(!stream){
        stream=await navigator.mediaDevices.getUserMedia({
            video:{width:640,height:480}});
            v.srcObject=stream
        }}
function camOff(){
    if(stream)stream.getTracks().forEach(t=>t.stop());
    stream=null;v.srcObject=null};
function snap(){if(!stream||!v.videoWidth)return;
    const c=document.createElement('canvas');c.width=v.videoWidth;c.height=v.videoHeight;
 c.getContext('2d').drawImage(v,0,0);
 const u=c.toDataURL('image/jpeg',.9);
 imgs.push(u);
 shots.insertAdjacentHTML('beforeend',`<img src="${u}">`)}
const api=(u,m,b)=>fetch(u,{method:m,headers:{'Content-Type':'application/json'},body:b&&JSON.stringify(b)}).then(r=>r.json());
async function save(){const r=await api('/api/students','POST',{student_no:$('no').value,full_name:$('nm').value,faculty:$('fc').value,fees_paid:$('fp').checked,images:imgs});
 msg.textContent=r.error||'تم الحفظ ✅';if(r.ok){imgs=[];shots.innerHTML='';['no','nm','fc'].forEach(i=>$(i).value='');load()}}
async function load(){list=await(await fetch('/api/students')).json();draw()}
function draw(){const k=$('s').value;$('tb').innerHTML=list.filter(s=>(s.full_name+s.student_no).includes(k)).map(s=>`<tr>
 <td>${s.student_no}</td><td>${s.full_name}</td><td>${s.faculty||''}</td><td>${s.fees_paid?'✅':'❌'}</td><td>${s.status}</td>
 <td><button onclick="upd(${s.id},'fees')">الرسوم</button><button onclick="upd(${s.id},'status')">الحالة</button>
 <button onclick="upd(${s.id},'name')">تعديل</button><button onclick="upd(${s.id},'face')">البصمة</button>
 <button class="danger" onclick="del(${s.id})">حذف</button></td></tr>`).join('')}
async function upd(id,w){const s={...list.find(x=>x.id===id)};
 if(w==='fees')s.fees_paid=!s.fees_paid;
 if(w==='status')s.status=s.status==='active'?'suspended':'active';
 if(w==='name'){s.full_name=prompt('الاسم',s.full_name)||s.full_name;s.faculty=prompt('الكلية',s.faculty||'')??s.faculty}
 if(w==='face'){if(!imgs.length)return alert('التقط صورًا جديدة أولاً من الكاميرا');s.images=imgs}
 const r=await api('/api/students/'+id,'PUT',s);if(r.error)alert(r.error);else{if(w==='face'){imgs=[];shots.innerHTML=''}load()}}
async function del(id){if(confirm('حذف الطالب نهائيًا؟')){await api('/api/students/'+id,'DELETE');load()}}
load();
