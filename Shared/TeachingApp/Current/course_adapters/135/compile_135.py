"""Math 135 course compiler: select source documents; publish successful PDFs."""
from pathlib import Path
import argparse,json,os,re,shutil,subprocess,sys,time
APP_ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(APP_ROOT))
from toolchain import executable,open_folder
ROOT=Path(globals().get('MATERIALS_ROOT',Path(__file__).resolve().parents[3]/'mh-git'))
COURSE=ROOT/'mh-135-course-documents'
CONFIG=json.loads(Path(__file__).with_name('project.json').read_text(encoding='utf-8'))
OUTPUT=Path(CONFIG['course_directory'])
SETTINGS_PATH=Path(globals().get('GWORKS_ROOT',APP_ROOT.parent))/'Data/settings.json'
SETTINGS=json.loads(SETTINGS_PATH.read_text(encoding='utf-8')) if SETTINGS_PATH.is_file() else {}
if SETTINGS.get('portable_output'):OUTPUT=Path(globals().get('GWORKS_ROOT',APP_ROOT.parent))/'Published'/str(CONFIG['course_directory']).replace('\\','/').rstrip('/').rsplit('/',1)[-1]

def semester_info(tag):
    if not re.fullmatch(r'(fa|sp|su|wi)\d{2}',tag):raise ValueError('Use a semester code such as fa26 or sp27.')
    season={'fa':'Fall','sp':'Spring','su':'Summer','wi':'Winter'}[tag[:2]]
    return season+' 20'+tag[2:],tag[:2].title()+tag[2:]


def discover(tag):
    items=[]
    for kind,folder in [('Exam','exams'),('Quiz','quizzes'),('Worksheet','worksheets')]:
        for source in (COURSE/folder).glob('*-'+tag+'.tex'):
            match=re.fullmatch(kind.lower()+r'(\d+)-'+tag+r'\.tex',source.name)
            if not match:continue
            text=source.read_text(encoding='utf-8');v=re.search(r'\\SetExamVersions\{(\d+)\}',text);count=int(v[1])if v else 1
            if not 1<=count<=26:raise ValueError('Unsupported version count: '+str(source))
            macro='ExamBuildVersion'if kind=='Exam'else'AssessmentBuildVersion'
            if count>1 and ('\\'+macro)not in text:raise ValueError('No selectable version macro in '+str(source))
            items.append({'key':kind.lower()+':'+match[1],'kind':kind,'number':int(match[1]),'source':source,'versions':count})
    items.sort(key=lambda x:({'Exam':0,'Quiz':1,'Worksheet':2}[x['kind']],x['number']))
    if (ROOT/'semesters'/f'{tag}.tex').is_file()and(COURSE/'syllabuses/semesters'/f'{tag}.tex').is_file():
        for kind in ['Syllabus','Schedule']:items.append({'key':kind.lower(),'kind':kind,'source':COURSE/'syllabuses'/f'{kind.lower()}.tex','versions':1})
    if all((COURSE/'manual'/s).is_file()for s in ['manual-stu.tex','manual-sol.tex']):
        items.append({'key':'manual','kind':'Manual','versions':1})
    for key,kind,source in [('reference','Reference Sheet','support/formula-sheet.tex'),('worksheet:blank','Blank Worksheet','worksheets/worksheet-blank.tex')]:
        if (COURSE/source).is_file():items.append({'key':key,'kind':kind,'source':COURSE/source,'versions':1})
    names={'first-recitation':'First-Recitation','first-recitation-mod':'First-Recitation-Facilitator-Guide','mylab-stu':'MyLab-Instructions','proctoring':'Proctoring-Instructions','proctoring-makeups':'Proctoring-Makeups','scanning':'Scanning-Instructions'}
    for stem,name in names.items():
        source=COURSE/'coordination'/(stem+'.tex')
        kind='Support' if stem in ('first-recitation','first-recitation-mod','mylab-stu') else 'Coordination'
        if source.is_file():items.append({'key':'coordination:'+stem,'kind':kind,'label':name.replace('-',' '),'output':name,'source':source,'versions':1})
    source=COURSE/'coordination'/('orientation-'+tag+'.tex')
    if source.is_file():items.append({'key':'coordination:orientation','kind':'Coordination','label':'Orientation Agenda','output':'Orientation-Agenda-'+semester_info(tag)[1],'source':source,'versions':1})
    return items

def plan(items,tag,mode='all',version='all'):
    label,short=semester_info(tag);jobs=[]
    def add(name,source,prefix,folder,m,kind,v='A'):
        jobs.append({'name':name,'source':source,'prefix':prefix,'folder':folder,'mode':m,'kind':kind,'version':v})
    for item in items:
        kind=item['kind']
        if kind in ['Blank Worksheet','Reference Sheet','Support','Coordination']:
            if mode!='solutions':
                name={'Blank Worksheet':'Worksheet-Blank','Reference Sheet':'Reference-Sheet'}.get(kind,item.get('output'))
                add(name,item['source'],'',OUTPUT/'Coordination'if kind=='Coordination'else OUTPUT,'student',kind)
            continue
        if kind=='Manual':
            for m in ['student','solutions']:
                if mode!='all'and m!=mode:continue
                source=COURSE/'manual'/('manual-sol.tex'if m=='solutions'else'manual-stu.tex')
                add('Manual-135'+('-Sols'if m=='solutions'else''),source,'',OUTPUT,m,kind)
            continue
        if kind in ['Syllabus','Schedule']:
            if mode!='solutions':add(kind+'-'+short,item['source'],'\\def\\MathSemester{'+tag+'}\n',OUTPUT/label,'student',kind)
            continue
        count=item['versions'];versions=[chr(65+i)for i in range(count)];selected=versions if version=='all'else[version]
        if any(v not in versions for v in selected):raise ValueError(item['key']+' supports '+', '.join(versions))
        for m in ['student','solutions']:
            if mode!='all'and mode!=m:continue
            # All solution keys use Version A, even when student selection requests another version.
            for v in (['A']if m=='solutions'else selected):
                macro='ExamSolutions'if kind=='Exam'else'AssessmentSolutions'
                prefix=('\\def\\'+macro+'{1}\n')if m=='solutions'else''
                if kind=='Exam':prefix+='\\def\\ExamBuildVersion{'+v+'}\n'
                elif count>1:prefix+='\\def\\AssessmentBuildVersion{'+v+'}\n'
                name=f"{kind}-{item['number']}-{short}"+('-'+v if count>1 else'')+('-sols'if m=='solutions'else'')
                add(name,item['source'],prefix,OUTPUT/label,m,kind,v)
    destinations=[str(j['folder']/j['name'])for j in jobs]
    if len(destinations)!=len(set(destinations)):raise ValueError('Conflicting output filenames.')
    return jobs

def choose(items,text):
    text=text.strip().lower()
    groups={'a':None,'all':None,'e':'Exam','exams':'Exam','q':'Quiz','quizzes':'Quiz','w':'Worksheet','worksheets':'Worksheet','m':'Manual','manual':'Manual','s':'policies','policies':'policies','b':'Blank Worksheet','blank':'Blank Worksheet','r':'Reference Sheet','reference':'Reference Sheet','c':'Coordination','coordination':'Coordination'}
    if text in groups:
        group=groups[text]
        return [x for x in items if group is None or x['kind']==group or(group=='Worksheet'and x['kind']=='Blank Worksheet')or(group=='policies'and x['kind']in['Syllabus','Schedule'])]
    selected=[]
    for token in text.split(','):
        token=token.strip()
        if re.fullmatch(r'\d+-\d+',token):
            a,b=map(int,token.split('-'));numbers=range(a,b+1)
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
    cache=APP_ROOT.parent/'Temp/Legacy/135/tex-cache';cache.mkdir(parents=True,exist_ok=True)
    environment['TEXMFVAR']=str(cache);environment['TEXMFCACHE']=environment['TEXMFVAR']
    records=[]
    for job in jobs:
        work=APP_ROOT.parent/'Temp/Legacy/135'/job['name'];work.mkdir(parents=True,exist_ok=True)
        source=job['source'];assert source.resolve().is_relative_to(COURSE)
        wrapper=work/(job['name']+'.tex');text=job['prefix']+'\\input{'+source.relative_to(ROOT).as_posix()+'}\n'
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
    output=APP_ROOT.parent/'Temp/Legacy/135/last-build.json';output.write_text(json.dumps(records,indent=2))
    issues=sum(not x['success']for x in records);print(f"Finished: {len(records)-issues} succeeded; {issues} failed.",flush=True)
    if any(x['calendar_warnings']for x in records):print('The syllabus/calendar reported pacing warnings; see the build report. No calendar or course content was changed.')
    return int(issues>0)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--semester',default=CONFIG['default_semester']);parser.add_argument('--select');parser.add_argument('--all',action='store_true');parser.add_argument('--list',action='store_true');parser.add_argument('--plan',action='store_true');parser.add_argument('--mode',choices=['all','student','solutions'],default='all');parser.add_argument('--version',default='all',type=lambda s:'all' if s.lower()=='all'else s.upper());parser.add_argument('--rebuild',action='store_true');args=parser.parse_args()
    try:
        tag=args.semester.lower();label,_=semester_info(tag);items=discover(tag)
        def listing():
            print('\nMath 135 - '+label+'\n')
            for i,x in enumerate(items,1):
                detail=' (universal; course folder)'if x['kind']in['Blank Worksheet','Reference Sheet']else' (student + solutions; course folder)'if x['kind']=='Manual'else' (A-'+chr(64+x['versions'])+' students; A solutions)'if x['versions']>1 else' (student + solutions)'if x['kind']in['Exam','Quiz','Worksheet']else''
                print(f"{i:2}. {x.get('label',x['kind'])}"+(' '+str(x['number'])if'number'in x else'')+detail)
            print('\nA: All   E: Exams   Q: Quizzes   W: Worksheets   S: Syllabus + Schedule   M: Manuals   R: Reference sheet   B: Blank worksheet\nC: Coordination\nEnter individual numbers, comma lists, or ranges. T: Change semester. O: Open semester folder. X: Exit.')
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
                selected=choose(items,answer)
                answer_mode=input('Copies: [Enter] both student and solutions, S student only, K solutions only: ').strip().lower()
                if answer_mode not in ['', 's', 'k']:raise ValueError('Choose Enter, S, or K.')
                jobs=plan(selected,tag,{'':'all','s':'student','k':'solutions'}[answer_mode]);build(jobs)
            except ValueError as e:print(str(e))
            input('\nPress Enter to return to the menu.')
    except (ValueError,OSError,subprocess.SubprocessError)as e:print('Compiler error: '+str(e));return 1
if __name__=='__main__':raise SystemExit(main())
