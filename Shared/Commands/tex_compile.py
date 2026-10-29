"""Bounded pdfLaTeX passes for the Math 135 MiKTeX setup; no Perl required."""
from pathlib import Path
import argparse,hashlib,os,re,subprocess,sys,time

def compile_document(compiler,source,output,*,miktex=True,install=False,cwd=None,env=None,timeout=240):
    source=Path(source).resolve();output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    args=[str(compiler),'-interaction=nonstopmode','-halt-on-error','-file-line-error','-no-shell-escape','-recorder','-output-directory='+str(output)]
    if miktex:args.insert(1,'--enable-installer' if install else '--disable-installer')
    previous=None;console=[];started=time.monotonic()
    for number in range(1,7):
        remaining=timeout-(time.monotonic()-started)
        if remaining<=0:raise subprocess.TimeoutExpired(args,timeout,output='\n'.join(console))
        try:result=subprocess.run(args+[str(source)],cwd=cwd,env=env,capture_output=True,text=True,errors='replace',timeout=remaining,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except subprocess.TimeoutExpired as exc:
            captured=lambda value:value.decode('utf-8',errors='replace') if isinstance(value,bytes) else str(value or '')
            raise subprocess.TimeoutExpired(args,timeout,output='\n'.join(console)+'\n'+captured(exc.stdout),stderr=captured(exc.stderr)) from exc
        console.append('G-Whiz pdfLaTeX pass '+str(number)+'\n'+result.stdout+result.stderr)
        if result.returncode:return subprocess.CompletedProcess(args,result.returncode,'\n'.join(console),'')
        # The supplied Math 135 documents use LaTeX cross references, not BibTeX.
        # Do not silently claim success for an unsupported external processor.
        if any(output.glob('*.bcf')) or any(b'\\bibdata' in p.read_bytes() for p in output.glob('*.aux')):
            return subprocess.CompletedProcess(args,1,'\n'.join(console)+'\nThis document requires a bibliography processor. Use the TeX Live setup for this document.','')
        files=sorted(p for p in output.iterdir() if p.suffix in {'.aux','.toc','.out','.lof','.lot'})
        fingerprint=hashlib.sha256(b''.join(p.name.encode()+p.read_bytes() for p in files)).hexdigest()
        log=(output/(source.stem+'.log')).read_text('utf-8',errors='replace') if (output/(source.stem+'.log')).is_file() else ''
        rerun=bool(re.search(r'Rerun to get|Rerun LaTeX|Please \(re\)run|Label\(s\) may have changed',log))
        if number>=2 and fingerprint==previous and not rerun:
            return subprocess.CompletedProcess(args,0,'\n'.join(console),'')
        previous=fingerprint
    return subprocess.CompletedProcess(args,1,'\n'.join(console)+'\nCross references did not stabilize after six passes.','')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--compiler',required=True);parser.add_argument('--source',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args()
    try:
        result=compile_document(args.compiler,args.source,args.output,cwd=Path.cwd())
        print(result.stdout);return result.returncode
    except subprocess.TimeoutExpired as exc:
        for value in (exc.stdout,exc.stderr):
            if value:print(value.decode('utf-8',errors='replace') if isinstance(value,bytes) else value)
        print('Compilation exceeded four minutes.');return 124

if __name__=='__main__':raise SystemExit(main())
