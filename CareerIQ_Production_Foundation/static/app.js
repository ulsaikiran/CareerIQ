document.addEventListener('DOMContentLoaded',()=>{
  const token=document.querySelector('meta[name=csrf-token]')?.content;
  document.querySelectorAll('form[method=post],form:not([method])').forEach(form=>{if(token&&!form.querySelector('input[name=_csrf_token]')){const input=document.createElement('input');input.type='hidden';input.name='_csrf_token';input.value=token;form.appendChild(input);}});
  const roleSelect=document.getElementById('account-role'),roleHelp=document.getElementById('role-help');
  if(roleSelect&&roleHelp){const descriptions={student:'Enter your branch, section and roll number. Student access is enabled after registration.',faculty:'Enter your branch and subject. An administrator must approve faculty access.',company:'Company accounts require administrator approval before signing in.'};const studentFields=document.getElementById('student-fields'),facultyFields=document.getElementById('faculty-fields');const updateRoleHelp=()=>{const student=roleSelect.value==='student',faculty=roleSelect.value==='faculty';roleHelp.textContent=descriptions[roleSelect.value]||descriptions.student;if(studentFields){studentFields.hidden=!student;studentFields.querySelectorAll('input').forEach(x=>{x.disabled=!student;x.required=student;});}if(facultyFields){facultyFields.hidden=!faculty;facultyFields.querySelectorAll('input').forEach(x=>{x.disabled=!faculty;x.required=faculty;});}};roleSelect.addEventListener('change',updateRoleHelp);updateRoleHelp();}
  const registerForm=document.querySelector('form input[name=confirm_password]')?.closest('form');
  if(registerForm){registerForm.addEventListener('submit',event=>{const password=registerForm.querySelector('input[name=password]'),confirm=registerForm.querySelector('input[name=confirm_password]');if(password&&confirm&&password.value!==confirm.value){event.preventDefault();confirm.setCustomValidity('Passwords do not match.');confirm.reportValidity();}else if(confirm){confirm.setCustomValidity('');}});registerForm.querySelector('input[name=confirm_password]')?.addEventListener('input',event=>event.target.setCustomValidity(''));}
  document.querySelectorAll('[data-search]').forEach(input=>input.addEventListener('input',()=>{const t=document.getElementById(input.dataset.search);if(!t)return;const q=input.value.toLowerCase();t.querySelectorAll('tbody tr').forEach(r=>r.hidden=!r.innerText.toLowerCase().includes(q));}));

  // Exam monitoring: video is processed locally; only event metadata is sent to the server.
  const start=document.getElementById('start-exam');
  if(start){
    const consent=document.getElementById('exam-consent'),status=document.getElementById('exam-status'),video=document.getElementById('exam-camera'),gate=document.getElementById('exam-gate'),content=document.getElementById('exam-content');
    let stream=null,faceMesh=null,monitoring=false,neutralYaw=null,baselineSamples=[],turnStarted=0,lastTurnAlert=0,lastFaceAlert=0,faceLastSeen=Date.now(),processing=false;
    const postEvent=async(type,details)=>{try{await fetch('/exam/event',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':token||''},body:JSON.stringify({event_type:type,details}),keepalive:true});}catch(e){console.warn('Could not send exam event',e);}};
    const cleanup=()=>{monitoring=false;if(stream)stream.getTracks().forEach(track=>track.stop());stream=null;if(video)video.srcObject=null;};
    const startFaceDetection=async()=>{
      if(typeof window.FaceMesh!=='function'){status.textContent='Camera is on, but head-turn detection library could not load. Check internet access and reload; do not continue if monitoring is required.';return false;}
      faceMesh=new window.FaceMesh({locateFile:file=>`https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/${file}`});
      faceMesh.setOptions({maxNumFaces:1,refineLandmarks:false,minDetectionConfidence:0.55,minTrackingConfidence:0.55});
      faceMesh.onResults(results=>{
        if(!monitoring)return;
        const face=results.multiFaceLandmarks&&results.multiFaceLandmarks[0];
        if(!face){if(Date.now()-faceLastSeen>5000&&Date.now()-lastFaceAlert>15000){lastFaceAlert=Date.now();postEvent('face_not_detected','No face detected for several seconds.');}return;}
        faceLastSeen=Date.now();
        const left=face[33],right=face[263],nose=face[1];if(!left||!right||!nose)return;
        const eyeWidth=Math.abs(right.x-left.x)||0.001;const yaw=(nose.x-(left.x+right.x)/2)/eyeWidth;
        if(baselineSamples.length<18){baselineSamples.push(yaw);neutralYaw=baselineSamples.reduce((a,b)=>a+b,0)/baselineSamples.length;return;}
        const turned=Math.abs(yaw-neutralYaw)>0.19;
        if(turned){if(!turnStarted)turnStarted=Date.now();if(Date.now()-turnStarted>1800&&Date.now()-lastTurnAlert>15000){lastTurnAlert=Date.now();postEvent('head_turn','Possible sustained head turn detected by browser-based face landmarks. Faculty should review context.');}}
        else turnStarted=0;
      });
      const detectLoop=async()=>{if(!monitoring||!faceMesh||processing)return;processing=true;try{if(video.readyState>=2)await faceMesh.send({image:video});}catch(e){console.warn('Face detection frame failed',e);}finally{processing=false;if(monitoring)requestAnimationFrame(detectLoop);}};
      requestAnimationFrame(detectLoop);return true;
    };
    start.addEventListener('click',async()=>{
      if(!consent.checked){status.textContent='Please confirm the monitoring notice before starting.';return;}
      if(!navigator.mediaDevices?.getUserMedia){status.textContent='This browser does not support camera access. Use a current browser on HTTPS or localhost.';return;}
      start.disabled=true;status.textContent='Requesting camera permission…';
      try{
        stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:'user'},audio:false});video.srcObject=stream;await video.play();
        try{if(!document.fullscreenElement)await document.documentElement.requestFullscreen();}catch(e){status.textContent='Fullscreen was blocked by the browser. Use the fullscreen control or browser permission, then start again.';cleanup();start.disabled=false;return;}
        const started=await fetch('/exam/start',{method:'POST',headers:{'X-CSRF-Token':token||''}});if(!started.ok)throw new Error('Could not register exam start.');
        monitoring=true;content.hidden=false;status.textContent='Camera active. Keep your face visible and look toward the screen. Video stays on this device.';
        stream.getVideoTracks()[0].addEventListener('ended',()=>{if(monitoring){postEvent('camera_stopped','Camera stream ended during the assessment.');status.textContent='Camera stopped. Faculty has been alerted.';}});
        const faceReady=await startFaceDetection();if(!faceReady){cleanup();content.hidden=true;start.disabled=false;return;}
        gate.querySelector('h2').textContent='Monitoring active';start.hidden=true;
      }catch(e){cleanup();start.disabled=false;status.textContent=e.name==='NotAllowedError'?'Camera permission was denied. Allow camera access and try again.':'Could not start camera/fullscreen. Check browser permissions and try again.';}
    });
    document.addEventListener('fullscreenchange',()=>{if(monitoring&&!document.fullscreenElement){postEvent('fullscreen_exited','Assessment fullscreen mode was exited.');status.textContent='Fullscreen was exited. Faculty has been alerted; return to fullscreen to continue.';}});
    document.addEventListener('visibilitychange',()=>{if(monitoring&&document.hidden)postEvent('tab_hidden','Assessment tab became hidden.');});
    window.addEventListener('beforeunload',()=>{if(monitoring)postEvent('tab_hidden','Assessment page was closed or navigated away from.');cleanup();});
    document.getElementById('exam-form')?.addEventListener('submit',()=>{if(monitoring)postEvent('camera_stopped','Assessment submitted; monitoring ended.');cleanup();});
  }
});
