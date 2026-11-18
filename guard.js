const v=document.getElementById('v'),box=document.getElementById('res'),info=document.getElementById('info');
let stream=null,timer=null,busy=false;
const set=(c,t,i='')=>{
  box.className='res '+c;box.textContent=t;info.textContent=i
};

async function start(){
  if(stream)return;
 try{
  stream=await 
  navigator.mediaDevices.getUserMedia({video:{facingMode:'user',width:640,height:480}
  })
}
 catch(e){
  set('bad','تعذر تشغيل الكاميرا (يتطلب HTTPS أو localhost)');
  return
};

 v.srcObject=stream;timer=setInterval(scan,1000);
 set('wait','بانتظار الطالب...')
}

function stop(){
  clearInterval(timer);
  if(stream)stream.getTracks().forEach(t=>t.stop());
  stream=null;v.srcObject=null;set('idle','الكاميرا مغلقة')
}

async function scan(){
  if(busy||!stream||!v.videoWidth)
    return;
  busy=true;
 const c = document.createElement('canvas');
 c.width=v.videoWidth;
 c.height=v.videoHeight;
 c.getContext('2d').drawImage(v,0,0);

 try{
  const r=await(await fetch('/api/verify',{
    method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({image:c.toDataURL('image/jpeg',.85)})
})).json();

  if(r.status!=='no_face'){
   if(r.status==='allowed')set('ok','مسموح بالدخول',`${r.name} - ${r.student_no}`);
   else set('bad',r.reason,r.name?`${r.name} - ${r.student_no}`:'');
   await new Promise(s=>setTimeout(s,4000));if(stream)set('wait','بانتظار الطالب...')}
 }
 catch(e){}
 busy=false}
