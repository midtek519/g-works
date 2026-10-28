"""Math 136 course compiler: select source documents; publish successful PDFs."""
from pathlib import Path
import argparse,json,os,re,shutil,subprocess,sys,time
APP_ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(APP_ROOT))
from toolchain import executable,open_folder
ROOT=Path(globals().get('MATERIALS_ROOT',Path(__file__).resolve().parents[3]/'mh-git'))
COURSE=ROOT/'mh-136-course-documents'
CONFIG=json.loads(Path(__file__).with_name('project.json').read_text(encoding='utf-8'))
OUTPUT=Path(CONFIG['course_directory'])
SETTINGS_PATH=Path(globals().get('GWORKS_ROOT',APP_ROOT.parent))/'Data/settings.json'
SETTINGS=json.loads(SETTINGS_PATH.read_text(encoding='utf-8')) if SETTINGS_PATH.is_file() else {}
if SETTINGS.get('portable_output'):OUTPUT=Path(globals().get('GWORKS_ROOT',APP_ROOT.parent))/'Published'/str(CONFIG['course_directory']).replace('\\','/').rstrip('/').rsplit('/',1)[-1]

def semester_info(tag):
    if not re.fullmatch(r'(fa|sp|su|wi)\d{2}',tag):raise ValueError('Use a semester code such as fa26 or sp27.')
    season={'fa':'Fall','sp':'Spring','su':'Summer','wi':'Winter'}[tag[:2]]
    return season+' 20'+tag[2:],tag[:2].title()+tag[2:]

from pathlib import Path
import re

def discover(tag):
    grouped={}
    for kind,folder in [('Exam','exams'),('Quiz','quizzes'),('Worksheet','worksheets'),('Groupwork','worksheets')]:
        for source in (COURSE/folder).glob('*.tex'):
            pattern=(r'groupwork-'+tag+r'-(\d+)(?:-([A-Z]))?\.tex'if kind=='Groupwork'else kind.lower()+r'(\d+)-'+tag+r'(?:-([A-Z]))?\.tex')
            match=re.fullmatch(pattern,source.name)
            if not match:continue
            body=source.read_text(encoding='utf-8')
            if '\\documentclass'not in body:continue
            number=int(match[1]);variant=match[2]or'A';key=(kind,number)
            item=grouped.setdefault(key,{'key':kind.lower()+':'+str(number),'kind':kind,'number':number,'sources':{},'versions':1})
            item['sources'][variant]=source
            count=re.search(r'\\SetExamVersions\{(\d+)\}',body)
            # A single source can expose a selection macro; other sources have separate version files.
            if count and int(count[1])>1 and not match[2]:
                macro='ExamBuildVersion'if'\\ExamBuildVersion'in body else'AssessmentBuildVersion'if'\\AssessmentBuildVersion'in body else None
                if not macro:raise ValueError('Multiple versions need separate source files or a selectable macro: '+source.name)
                item['macro']=macro
                item['sources']={chr(65+i):source for i in range(int(count[1]))}
    items=sorted(grouped.values(),key=lambda x:({'Exam':0,'Quiz':1,'Worksheet':2,'Groupwork':3}[x['kind']],x['number']))
    for item in items:
        item['versions']=len(item['sources'])
        if 'A'not in item['sources']:raise ValueError('Version A is missing: '+item['key'])
    for kind in ['Syllabus','Schedule']:
        candidates=[COURSE/'syllabuses'/f'{kind.lower()}-{tag}.tex',COURSE/'schedules'/f'{kind.lower()}-{tag}.tex']
        for source in candidates:
            body=source.read_text()if source.is_file()else''
            if '\\documentclass'in body or re.search(r'(?m)^\s*\\input\{',body):
                items.append({'key':kind.lower(),'kind':kind,'source':source,'versions':1});break
    items.append({'key':'manual','kind':'Manual','versions':1})
    reference=COURSE/'support/formula-sheet.tex'
    if reference.is_file()and'\\documentclass'in reference.read_text():items.append({'key':'reference','kind':'Reference Sheet','source':reference,'versions':1})
    blank=COURSE/'worksheets/worksheet-blank.tex'
    if blank.is_file()and'\\documentclass'in blank.read_text():items.append({'key':'worksheet:blank','kind':'Blank Worksheet','source':blank,'versions':1})
    return items

def plan(items,tag,mode='all',version='all'):
    label,short=semester_info(tag);jobs=[]
    for item in items:
        kind=item['kind']
        if kind in ['Reference Sheet','Blank Worksheet']:
            if mode!='solutions':jobs.append({'name':'Reference-Sheet'if kind=='Reference Sheet'else'Worksheet-Blank','source':item['source'],'prefix':'','folder':OUTPUT,'mode':'student','kind':kind,'version':'A'})
            continue
        if kind=='Manual':
            for m in ['student','solutions']:
                if mode!='all'and m!=mode:continue
                jobs.append({'name':'Manual-136'+('-Sols'if m=='solutions'else''),'source':COURSE/'manual'/('manual-sol.tex'if m=='solutions'else'manual-stu.tex'),'prefix':'','folder':OUTPUT,'mode':m,'kind':kind,'version':'A'})
            continue
        if kind in ['Syllabus','Schedule']:
            if mode!='solutions':jobs.append({'name':kind+'-'+short,'source':item['source'],'prefix':'\\def\\MathSemester{'+tag+'}\n','folder':OUTPUT/label,'mode':'student','kind':kind,'version':'A'})
            continue
        versions=sorted(item['sources']);selected=versions if version=='all'else[version]
        if any(v not in versions for v in selected):raise ValueError(item['key']+' supports '+', '.join(versions))
        for m in ['student','solutions']:
            if mode!='all'and mode!=m:continue
            for v in (['A']if m=='solutions'else selected):
                prefix='\\def\\CourseOutputMode{'+m+'}\n'
                if item.get('macro'):prefix+='\\def\\'+item['macro']+'{'+v+'}\n'
                name=f"{kind}-{item['number']}-{short}"+('-'+v if len(versions)>1 else'')+('-sols'if m=='solutions'else'')
                jobs.append({'name':name,'source':item['sources'][v],'prefix':prefix,'folder':OUTPUT/label,'mode':m,'kind':kind,'version':v})
    return jobs

def choose(items,text):
    text=text.strip().lower();groups={'a':None,'all':None,'e':'Exam','exams':'Exam','q':'Quiz','quizzes':'Quiz','w':'worksheets','worksheets':'worksheets','m':'Manual','manual':'Manual','s':'policies','policies':'policies','r':'Reference Sheet','reference':'Reference Sheet','b':'Blank Worksheet','blank':'Blank Worksheet'}
    if text in groups:
        group=groups[text]
        return [x for x in items if group is None or x['kind']==group or(group=='worksheets'and x['kind']in['Worksheet','Groupwork','Blank Worksheet'])or(group=='policies'and x['kind']in['Syllabus','Schedule'])]
    selected=[]
    for token in text.split(','):
        token=token.strip()
        if re.fullmatch(r'\d+-\d+',token):a,b=map(int,token.split('-'));numbers=range(a,b+1)
        elif token.isdigit():numbers=[int(token)]
        else:
            found=[x for x in items if x['key']==token]
            if not found:raise ValueError('Unknown selection: '+token)
            selected+=found;continue
        for n in numbers:
            if not 1<=n<=len(items):raise ValueError('Selection is out of range: '+str(n))
            selected.append(items[n-1])
    return list({x['key']:x for x in selected}.values())


def build(jobs,rebuild=False):
    latexmk=executable(APP_ROOT.parent,'latexmk')
    if not latexmk:raise ValueError('TeX Live latexmk was not found.')
    environment=os.environ.copy();environment['PATH']=str(Path(latexmk).parent)+os.pathsep+environment.get('PATH','')
    environment['TEXINPUTS']=(ROOT/'lib').as_posix()+'//'+os.pathsep+environment.get('TEXINPUTS','')+os.pathsep
    cache=APP_ROOT.parent/'Temp/Legacy/136/tex-cache';cache.mkdir(parents=True,exist_ok=True)
    environment['TEXMFVAR']=str(cache);environment['TEXMFCACHE']=environment['TEXMFVAR']
    records=[]
    for job in jobs:
        work=APP_ROOT.parent/'Temp/Legacy/136'/job['name'];work.mkdir(parents=True,exist_ok=True)
        source=job['source'];assert source.resolve().is_relative_to(COURSE)
        wrapper=work/(job['name']+'.tex')
        body=source.read_text(encoding='utf-8')
        if job['kind'] in ['Exam','Quiz','Worksheet','Groupwork'] and '\\CourseOutputMode' not in body:
            # Historical fixed-student sources are switched only in this private driver.
            body=re.sub(r'(\\documentclass\[)([^\]]*?)(\]\{mhdocument\})',lambda x:x[1]+re.sub(r'\bstudent\b',r'\\CourseOutputMode',x[2])+x[3],body,count=1)
            if job['mode']=='solutions':body=re.sub(r'\\SetMathCenterHeader\{([^{}\n]*)\}',lambda x:'\\SetMathCenterHeader{'+x[1]+' (Solutions)}',body,count=1)
            text=job['prefix']+body
        else:text=job['prefix']+'\\input{'+source.relative_to(ROOT).as_posix()+'}\n'
        if not wrapper.exists()or wrapper.read_text()!=text:wrapper.write_text(text,encoding='utf-8')
        command=[latexmk,'-norc','-r','latexmkrc','-pdf','-interaction=nonstopmode','-halt-on-error','-file-line-error','-latexoption=-no-shell-escape','-outdir='+work.as_posix(),wrapper.as_posix()]
        if rebuild:command.insert(1,'-g')
        print('Compiling '+job['name']+' ...',flush=True);started=time.monotonic()
        result=subprocess.run(command,cwd=ROOT,env=environment,capture_output=True,text=True,errors='replace')
        (work/'build-console.txt').write_text(result.stdout+result.stderr,encoding='utf-8')
        log=work/(job['name']+'.log');body=log.read_text(errors='replace')if log.exists()else''
        unresolved=bool(re.search(r'There were undefined references|There were undefined citations',body))
        pdf=work/(job['name']+'.pdf');ok=result.returncode==0 and pdf.is_file()and not unresolved
        destination=job['folder']/(job['name']+'.pdf');warnings=re.findall(r'Package mh-(?:syllabus|semester) Warning:[\s\S]*?(?=\n\s*\n|\Z)',body)
        record={'name':job['name'],'kind':job['kind'],'mode':job['mode'],'version':job['version'],'source':str(source),'pdf':str(destination),'success':ok,'exit_code':result.returncode,'undefined_references':unresolved,'seconds':round(time.monotonic()-started,2),'calendar_warnings':warnings}
        if ok:
            destination.parent.mkdir(parents=True,exist_ok=True)
            temporary=destination.with_suffix('.pdf.partial');shutil.copy2(pdf,temporary);os.replace(temporary,destination)
            print('Ready: '+str(destination),flush=True)
        else:
            print('FAILED. Any previous exported PDF was kept. Log: '+str(work/'build-console.txt'),flush=True);print((result.stdout+result.stderr)[-1800:])
        (work/'build-result.json').write_text(json.dumps(record,indent=2));records.append(record)
    output=APP_ROOT.parent/'Temp/Legacy/136/last-build.json';output.write_text(json.dumps(records,indent=2))
    issues=sum(not x['success']for x in records);print(f"Finished: {len(records)-issues} succeeded; {issues} failed.",flush=True)
    if any(x['calendar_warnings']for x in records):print('The syllabus/calendar reported pacing warnings; see the build report. No calendar or course content was changed.')
    return int(issues>0)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--semester',default=CONFIG['default_semester']);parser.add_argument('--select');parser.add_argument('--all',action='store_true');parser.add_argument('--list',action='store_true');parser.add_argument('--plan',action='store_true');parser.add_argument('--mode',choices=['all','student','solutions'],default='all');parser.add_argument('--version',default='all',type=lambda s:'all' if s.lower()=='all'else s.upper());parser.add_argument('--rebuild',action='store_true');args=parser.parse_args()
    try:
        tag=args.semester.lower();label,_=semester_info(tag);items=discover(tag)
        def listing():
            seasonal=any(x['kind']in['Exam','Quiz','Worksheet','Groupwork','Syllabus','Schedule']for x in items)
            print('\nMath 136 - '+(label+' (historical source semester)'if seasonal else'Universal documents')+'\n')
            for i,x in enumerate(items,1):
                detail=' (student + solutions; course folder)'if x['kind']=='Manual'else' (universal; course folder)'if x['kind']in['Reference Sheet','Blank Worksheet']else' (all student versions; A solutions)'if x.get('versions',1)>1 else' (student + solutions)'
                print(f"{i:2}. {x['kind']}"+(' '+str(x['number'])if'number'in x else'')+detail)
            shortcuts=['A: All','M: Manuals']
            if any(x['kind']=='Exam'for x in items):shortcuts.append('E: Exams')
            if any(x['kind']=='Quiz'for x in items):shortcuts.append('Q: Quizzes')
            if any(x['kind']in['Worksheet','Groupwork']for x in items):shortcuts.append('W: Worksheets / Groupwork')
            if any(x['kind']=='Reference Sheet'for x in items):shortcuts.append('R: Reference sheet')
            print('\n'+'   '.join(shortcuts)+'\nChoose item numbers, comma lists, or ranges. T: Change semester. O: Open semester folder. X: Exit.')
        if args.list:listing();return 0
        if args.all or args.select:
            selected=choose(items,'all'if args.all else args.select);jobs=plan(selected,tag,args.mode,args.version)
            if not jobs:raise ValueError('No documents match that selection.')
            if args.plan:
                print(json.dumps([{**j,'source':str(j['source']),'folder':str(j['folder'])}for j in jobs],indent=2));return 0
            return build(jobs,args.rebuild)
        while True:
            listing();answer=input('\nCompile: ').strip()
            if answer.lower()in['x','exit']:return 0
            if answer.lower()=='t':
                new=input('Semester code (for example fa26): ').strip().lower();semester_info(new);tag=new;label,_=semester_info(tag);items=discover(tag);continue
            if answer.lower()=='o':
                folder=OUTPUT/label;folder.mkdir(parents=True,exist_ok=True);open_folder(folder);continue
            try:
                selected=choose(items,answer);jobs=plan(selected,tag)
                if not jobs:raise ValueError('No documents are available for that selection.')
                build(jobs)
            except ValueError as e:print(str(e))
            input('\nPress Enter to return to the menu.')
    except (ValueError,OSError,subprocess.SubprocessError)as e:print('Compiler error: '+str(e));return 1
if __name__=='__main__':raise SystemExit(main())
