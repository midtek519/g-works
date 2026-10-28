"""Distribution-aware setup used exclusively by the Math 135 G-Whiz edition."""
from pathlib import Path
import argparse,json,os,shutil,subprocess,sys,secrets
sys.path.insert(0,str(Path(__file__).resolve().parent))
from tex_compile import compile_document

def enabled(root):
    for path in (Path(root)/'Data/edition.json',Path(root)/'edition.json'):
        if path.is_file():return json.loads(path.read_text('utf-8-sig')).get('edition')=='math135-instructor'
    return False

def requirements():return json.loads(Path(__file__).with_name('tex_requirements.json').read_text('utf-8'))

def settings(root):
    path=Path(root)/'Data/settings.json'
    return json.loads(path.read_text('utf-8-sig')) if path.is_file() else {}

def program(folder,name):
    path=Path(folder)/(name+('.exe' if os.name=='nt' and not name.endswith(('.exe','.bat')) else ''))
    return str(path) if path.is_file() else None

def environment(root,folder):
    env=os.environ.copy();env['PATH']=str(folder)+os.pathsep+env.get('PATH','')
    env['TEXINPUTS']=(Path(root)/'mh-git/lib').as_posix()+'//'+os.pathsep+env.get('TEXINPUTS','')+os.pathsep
    return env

def run(args,**kwargs):
    return subprocess.run(args,capture_output=True,text=True,errors='replace',timeout=kwargs.pop('timeout',30),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),**kwargs)

def probe(root,folder):
    folder=Path(folder).resolve();compiler=program(folder,'pdflatex');kpse=program(folder,'kpsewhich')
    if not compiler or not kpse:return None
    env=environment(root,folder)
    try:
        version=run([compiler,'--version'],env=env)
        if version.returncode:return None
        distribution='miktex' if 'miktex' in version.stdout.lower() else 'texlive' if 'TeX Live' in version.stdout else None
        if not distribution:return None
        missing=[]
        for file in requirements()['required_files']:
            # MiKTeX's compatibility kpsewhich is a lookup-only command and
            # does not accept the compiler's --disable-installer option.
            query=[kpse,file]
            result=run(query,env=env)
            if result.returncode or not result.stdout.strip():missing.append(file)
        if distribution=='texlive':
            latexmk=program(folder,'latexmk')
            if not latexmk or run([latexmk,'-version'],env=env).returncode:missing.append('latexmk')
        return {'bin':str(folder),'distribution':distribution,'missing':missing,'source':'existing','usable':not missing}
    except (OSError,subprocess.TimeoutExpired):return None

def candidates(root,explicit=None):
    root=Path(root).resolve();config=settings(root);folders=[]
    if explicit:return [Path(explicit).expanduser().resolve()]
    for key in ('tex_bin','texlive_bin'):
        if config.get(key):folders.append((root/config[key]).resolve())
    for name in ('pdflatex','miktex-pdflatex','latexmk'):
        found=shutil.which(name)
        if found:folders.append(Path(found).parent)
    if os.name=='nt':
        local=Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData/Local')))
        folders += [local/'Programs/MiKTeX/miktex/bin/x64',Path(os.environ.get('ProgramFiles','C:/Program Files'))/'MiKTeX/miktex/bin/x64']
        folders += sorted(Path('C:/texlive').glob('*/bin/windows'),reverse=True)
    else:
        folders += [Path('/Library/TeX/texbin'),Path.home()/'bin',Path('/usr/local/bin'),Path('/opt/homebrew/bin')]
    folders += [root/'Dependencies/texlive/bin/windows',*sorted((root/'Dependencies/texlive/bin').glob('*darwin*'))]
    return list(dict.fromkeys(p.resolve() for p in folders))

def discover(root,explicit=None):
    found=[p for folder in candidates(root,explicit) if (p:=probe(root,folder))]
    selected=next((p for p in found if p['usable']),found[0] if found else None)
    return selected or {'source':'missing','usable':False,'missing':[],'message':'No TeX Live or MiKTeX installation was found.'}

def smoke(root,folder,distribution,install=False):
    root=Path(root).resolve();work=root/'Temp/SetupChecks'/secrets.token_hex(5);work.mkdir(parents=True)
    texts={
      'question':r'''\documentclass[worksheet,student]{mhdocument}
\usepackage{mathpazo}
\begin{document}\section*{G-Whiz setup check}
\begin{exercise}Differentiate $f(x)=x^2$. $\displaystyle\int_0^1 x^2\,dx$.
\begin{tikzpicture}\draw[->] (0,0)--(1,1);\end{tikzpicture}
\end{exercise}\end{document}''',
      'handout':r'''\documentclass[worksheet,solutions]{mhdocument}
\begin{document}\section*{Handout setup check}\label{sec:check}
\begin{exercise}Compute $2+2$.\end{exercise}
\begin{solution}$2+2=4$.\end{solution}
\begin{tabular}{ll}\toprule Item & Value\\\midrule One & 1\\\bottomrule\end{tabular}
Section~\ref{sec:check}.\end{document}''',
      'syllabus':r'''\documentclass{mhdocument}\usepackage{mh-135-syllabus}
\begin{document}\section*{Syllabus setup check}
\begin{longtable}{ll}\toprule Week & Topic\\\midrule 1 & Limits\\2 & Derivatives\\\bottomrule\end{longtable}
\begin{tcolorbox}Course policy.\end{tcolorbox}
\begin{tikzpicture}\begin{axis}[width=5cm,height=4cm]\addplot {x^2};\end{axis}\end{tikzpicture}
\end{document}'''}
    # Exercise every directly required style as well as actual fonts/graphics.
    packages=[Path(file).stem for file in requirements()['required_files'] if file.endswith('.sty')]
    texts['question']=texts['question'].replace('\\begin{document}', '\\usepackage{'+','.join(packages)+'}\n\\begin{document}',1)
    texts['question']=texts['question'].replace('\\end{document}',r'{\fontfamily{ppl}\selectfont Palatino.} {\sffamily Sans.} {\fontfamily{lmr}\selectfont Latin Modern.}\end{document}')
    env=environment(root,folder);results=[]
    for name,text in texts.items():
        directory=work/name;directory.mkdir();source=directory/'check.tex';source.write_text(text,'utf-8')
        result=compile_document(program(folder,'pdflatex'),source,directory,miktex=distribution=='miktex',install=install,cwd=root/'mh-git',env=env,timeout=900 if install else 240)
        (directory/'console.txt').write_text(result.stdout,'utf-8')
        if result.returncode or not (directory/'check.pdf').is_file():
            errors=[line for line in result.stdout.splitlines() if 'Error' in line or 'not found' in line or line.startswith('!')]
            raise ValueError('The '+name+' PDF check failed. '+(' '.join(errors[-3:]) if errors else 'See '+str(directory/'console.txt')))
        results.append(name)
    return results

def ensure(root,folder,install=False):
    if not enabled(root):raise ValueError('Compiler choices are available only in the G-Whiz teaching distribution.')
    item=probe(root,folder)
    if not item:raise ValueError('Choose a bin folder containing pdflatex and kpsewhich from TeX Live or MiKTeX.')
    if install and item['distribution']=='texlive':
        manager=program(folder,'tlmgr') or program(folder,'tlmgr.bat')
        if not manager:raise ValueError('The TeX Live package manager is missing. Choose G-Whiz Essentials instead.')
        # Windows TeX Live provides tlmgr.bat; invoke its Perl script directly.
        if os.name=='nt':
            tlroot=Path(folder).parents[1];perl=tlroot/'tlpkg/tlperl/bin/perl.exe'
            command=[str(perl),str(tlroot/'texmf-dist/scripts/texlive/tlmgr.pl')]
        else:command=[manager]
        result=run(command+['install',*requirements()['texlive_packages']],env=environment(root,folder),timeout=1800)
        if result.returncode:raise ValueError('TeX Live could not install the required packages: '+(result.stdout+result.stderr)[-1400:])
    elif item['missing'] and not install:
        raise ValueError('Missing requirements: '+', '.join(item['missing'])+'. Run setup and allow required packages to be installed.')
    # MiKTeX resolves and installs the actual transitive dependencies during these
    # setup-only checks; no global automatic-install setting is changed.
    checks=smoke(root,folder,item['distribution'],install=install)
    verified=probe(root,folder)
    if not verified or verified['missing']:raise ValueError('Required package checks are incomplete: '+', '.join((verified or item)['missing']))
    root=Path(root).resolve();config=settings(root);folder=Path(folder).resolve()
    value=folder.relative_to(root).as_posix() if folder.is_relative_to(root) else str(folder)
    config.update(tex_bin=value,texlive_bin=value,tex_distribution=item['distribution'])
    config['tex_setup']={'verified':True,'checks':checks,'requirements_version':requirements()['version']}
    path=root/'Data/settings.json';path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_suffix('.json.new')
    temporary.write_text(json.dumps(config,indent=2)+'\n','utf-8');os.replace(temporary,path)
    return {**verified,'source':'existing','checks':checks,'message':'Using '+('MiKTeX' if item['distribution']=='miktex' else 'TeX Live')+': '+str(folder)}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--bin');parser.add_argument('--configure',action='store_true');parser.add_argument('--install-missing',action='store_true')
    args=parser.parse_args()
    try:
        if not enabled(args.root):raise ValueError('These setup choices belong to the G-Whiz teaching edition.')
        selected=discover(args.root,args.bin)
        if args.configure:
            if selected['source']=='missing':raise ValueError(selected['message'])
            selected=ensure(args.root,selected['bin'],args.install_missing)
        print(json.dumps(selected));return 0 if selected.get('usable') else 2
    except Exception as exc:print(json.dumps({'source':'missing','usable':False,'message':str(exc)}));return 2

if __name__=='__main__':raise SystemExit(main())
