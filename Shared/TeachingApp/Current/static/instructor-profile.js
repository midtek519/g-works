'use strict';
const InstructorProfile={
 async open(){
  const p=await api('/api/instructor-profile');
  modal('Your instructor details',`<p>Rutgers University · Department of Mathematics</p><form id="instructor-profile-form"><div class="grid">${[['name','Name'],['title','Title'],['email','Email'],['phone','Phone'],['office','Office'],['website','Website']].map(([key,label])=>field(label,`<input name="${key}" value="${esc(p[key])}" maxlength="300" ${key==='name'?'required':''}>`)).join('')}</div><button class="primary">Save details</button></form>`);
  document.getElementById('instructor-profile-form').addEventListener('submit',event=>{event.preventDefault();run(async()=>{await api('/api/instructor-profile',Object.fromEntries(new FormData(event.target)));dialog.close();toast('Instructor details saved.');});});
 },
 async addCourse(){
  modal('Add a course',`<form id="new-course-form"><div class="grid">${field('Math course number','<input name="code" inputmode="numeric" pattern="[0-9]{3}" maxlength="3" required placeholder="e.g. 300">')}${field('Course name','<input name="name" maxlength="100" placeholder="Optional">')}</div><p class="help">Starts an empty workspace. Add questions, topics, handouts and syllabuses using the existing tools.</p><button class="primary">Create course</button></form>`);
  document.getElementById('new-course-form').addEventListener('submit',event=>{event.preventDefault();run(async()=>{const result=await api('/api/courses/create',Object.fromEntries(new FormData(event.target)));S.courses=result.courses;S.course=result.course.code;S.semester=S.courses.find(c=>c.code===S.course).default_semester;S.configuration=await api('/api/configuration');await loadUniversal();await loadCatalog();dialog.close();render();toast('Course created.');});});
 }
};
document.addEventListener('click',event=>{const target=event.target.closest('[data-instructor-action]');if(!target)return;run(()=>target.dataset.instructorAction==='course'?InstructorProfile.addCourse():InstructorProfile.open());});
