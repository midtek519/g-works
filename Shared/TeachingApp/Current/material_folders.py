"""Course-aware output folder categories shared by compilation and Settings."""
ORDER=('Exam','Final Exam','Quiz','Worksheet','Groupwork','Manual','Assessment Manual','Syllabus & Schedule','Support','Coordination')

def folder_kind(course,kind):
 text=str(kind).strip();lower=text.lower()
 if str(course)=='135' and lower=='assessment manual':return None
 if str(course)=='130' and lower=='groupwork':return 'Worksheet'
 if lower in ('syllabus','schedule','syllabus & schedule'):return 'Syllabus & Schedule'
 if lower in ('reference sheet','blank worksheet','support'):return 'Support'
 if lower in ('final','final exam'):return 'Final Exam'
 return next((name for name in ORDER if name.lower()==lower),text)

def ordered(values):
 return {key:values[key] for key in sorted(values,key=lambda key:(ORDER.index(key) if key in ORDER else len(ORDER),key.casefold()))}

def folder_patterns(course,patterns):
 """Existing category settings win when several document types share a folder."""
 result={}
 for key,value in patterns.items():
  target=folder_kind(course,key)
  if target is not None and (target not in result or target==key):result[target]=value
 return ordered(result)
