"""Shared local AI configuration. Only literal loopback origins are accepted."""
from pathlib import Path
from urllib.parse import urlsplit
import hashlib,http.client,json,os,re,secrets,socket,threading,urllib.request,urllib.error
from contextlib import contextmanager
from runtime_paths import settings_directory
CONFIG_PATH=settings_directory()/'local-ai.json'
BUILTIN_MODEL='G-Scope:27b'
DEFAULT={'provider':'ollama','url':'http://127.0.0.1:11434','model':BUILTIN_MODEL,'revision':'','vision':True}
def validate(data):
    if not isinstance(data,dict) or set(data)!=set(DEFAULT):raise ValueError('Use the local AI connection fields.')
    if data['provider'] not in ('ollama','openai-local'):raise ValueError('Choose a supported local engine.')
    url=data['url'];parsed=urlsplit(url) if isinstance(url,str) else None
    if not parsed or parsed.scheme!='http' or parsed.hostname not in ('127.0.0.1','::1','localhost') or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/','/v1','/v1/') or not parsed.port:raise ValueError('Use an HTTP loopback address with a port, such as http://127.0.0.1:11434.')
    host='[::1]' if parsed.hostname=='::1' else '127.0.0.1';url='http://'+host+':'+str(parsed.port)
    model=data['model'];revision=data['revision']
    if not isinstance(model,str) or not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,160}',model) or 'cloud' in model.lower():raise ValueError('Choose an installed local model.')
    if not isinstance(revision,str) or len(revision)>200 or any(ord(c)<32 for c in revision) or not isinstance(data['vision'],bool):raise ValueError('Check the local model revision and vision setting.')
    if data['provider']=='openai-local' and not revision.strip():raise ValueError('Enter a model revision or fingerprint for this compatible local server.')
    return {**data,'url':url,'revision':revision.strip()}
def settings(path=None):
    path=Path(path) if path is not None else CONFIG_PATH
    if not path.exists():return dict(DEFAULT)
    if path.stat().st_size>16000:raise ValueError('The local AI configuration is too large.')
    return validate(json.loads(path.read_text('utf-8')))
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('The local AI server tried to redirect the request.')
class RequestCancelled(ValueError):pass
class Cancellation:
    """Abort only connections opened by this job, without stopping the engine."""
    def __init__(self):self.event=threading.Event();self.lock=threading.Lock();self.callbacks=set()
    def check(self):
        if self.event.is_set():raise RequestCancelled('Request cancelled.')
    def attach(self,callback):
        with self.lock:
            self.check();self.callbacks.add(callback)
    def detach(self,callback):
        with self.lock:self.callbacks.discard(callback)
    def cancel(self):
        with self.lock:self.event.set();callbacks=tuple(self.callbacks)
        for callback in callbacks:
            try:callback()
            except OSError:pass
_request_context=threading.local()
@contextmanager
def cancellation_scope(token):
    previous=getattr(_request_context,'cancellation',None);_request_context.cancellation=token
    try:yield
    finally:_request_context.cancellation=previous
def _cancellable_call(config,path,body,timeout,token):
    token.check();url=urlsplit(config['url']);connection=http.client.HTTPConnection(url.hostname,url.port,timeout=min(timeout,5));response=None;abort=None
    try:
        connection.connect();sock=connection.sock;sock.settimeout(timeout)
        def abort():
            try:sock.shutdown(socket.SHUT_RDWR)
            except OSError:pass
        token.attach(abort);token.check()
        connection.request('GET' if body is None else 'POST',path,body=body,headers={'Content-Type':'application/json'})
        response=connection.getresponse()
        if 300<=response.status<400:raise ValueError('The local AI server tried to redirect the request.')
        if response.status>=400:raise ValueError('The local AI server could not finish the request. Check the engine and retry.')
        raw=response.read(12000001);token.check()
        if len(raw)>12000000:raise ValueError('The local AI response is too large.')
        return json.loads(raw)
    except (OSError,http.client.HTTPException):
        token.check();raise ValueError('Cannot reach the configured local AI server. Check its address and start the engine.') from None
    finally:
        if abort:token.detach(abort)
        if response:response.close()
        connection.close()
def _call(config,path,payload=None,timeout=600):
    config=validate(config);body=None if payload is None else json.dumps(payload,allow_nan=False).encode()
    token=getattr(_request_context,'cancellation',None)
    if token is not None:return _cancellable_call(config,path,body,timeout,token)
    request=urllib.request.Request(config['url']+path,data=body,headers={'Content-Type':'application/json'})
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    try:
        with opener.open(request,timeout=timeout) as response:raw=response.read(12000001)
    except (urllib.error.URLError,TimeoutError,OSError):raise ValueError('Cannot reach the configured local AI server. Check its address and start the engine.') from None
    if len(raw)>12000000:raise ValueError('The local AI response is too large.')
    return json.loads(raw)
def request(path,payload=None,timeout=600,config=None):
    c=validate(config) if config is not None else settings()
    if path not in ('/api/show','/api/chat','/api/tags','/api/version'):raise ValueError('Unavailable local AI action.')
    if c['provider']=='ollama':return _call(c,path,payload,timeout)
    if path in ('/api/tags','/api/show'):
        records=_call(c,'/v1/models',timeout=timeout).get('data',[])
        models=[{'name':m['id'],'digest':hashlib.sha256(json.dumps([c,m['id']],sort_keys=True).encode()).hexdigest(),'size':0} for m in records if isinstance(m,dict) and isinstance(m.get('id'),str)]
        if path=='/api/tags':return {'models':models}
        if not payload or not any(m['name']==payload.get('model') for m in models):raise ValueError('This model is not available on the configured local server.')
        return {'capabilities':['vision'] if c['vision'] else [],'model_info':{'local_revision':c['revision']}}
    if path=='/api/version':return {'version':'local-compatible'}
    messages=[]
    for message in payload['messages']:
        content=message.get('content','')
        if message.get('images'):
            if not c['vision']:raise ValueError('The configured local model has no vision support.')
            content=[{'type':'text','text':content}]+[{'type':'image_url','image_url':{'url':'data:image/png;base64,'+image}} for image in message['images']]
        messages.append({'role':message['role'],'content':content})
    options=payload.get('options',{});body={'model':payload['model'],'stream':False,'messages':messages,'temperature':options.get('temperature',.7),'max_tokens':options.get('num_predict',1600),'seed':options.get('seed',42)}
    if 'format' in payload:body['response_format']={'type':'json_schema','json_schema':{'name':'local_result','strict':True,'schema':payload['format']}}
    data=_call(c,'/v1/chat/completions',body,timeout);choice=(data.get('choices') or [{}])[0]
    if choice.get('finish_reason')!='stop':raise ValueError('The local model did not return a complete answer.')
    usage=data.get('usage',{});return {'done':True,'done_reason':'stop','message':{'content':choice.get('message',{}).get('content','')},'prompt_eval_count':usage.get('prompt_tokens'),'eval_count':usage.get('completion_tokens')}
def check(data):
    c=validate(data);models=request('/api/tags',timeout=5,config=c).get('models',[])
    names=[m['name'] for m in models if isinstance(m.get('name'),str) and 'cloud' not in m['name'].lower()]
    if c['model'] not in names:raise ValueError('The configured model is not installed or loaded on this local server.')
    info=request('/api/show',{'model':c['model']},timeout=10,config=c)
    if info.get('remote_host') or info.get('remote_model') or info.get('model_info',{}).get('remote_host'):raise ValueError('Remote models are not supported.')
    return {'configuration':c,'models':names,'vision':'vision' in info.get('capabilities',[]),'connected':True}
def save(data,path=None):
    path=Path(path) if path is not None else CONFIG_PATH
    result=check(data);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.'+secrets.token_hex(6)+'.tmp')
    try:temp.write_text(json.dumps(result['configuration'],indent=2),'utf-8');os.replace(temp,path)
    finally:
        if temp.exists():temp.unlink()
    return result


def ollama_executable():
    import os
    roots=[Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData/Local')))/'Programs/Ollama',
           Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Ollama']
    return next((p/'ollama.exe' for p in roots if (p/'ollama.exe').is_file()),None)

def readiness(timeout=2):
    """Metadata only; no prompt, image, model loading or download."""
    try:c=settings()
    except (ValueError,OSError):return {'state':'configuration_error','message':'Check the local AI connection in Settings.','canStart':False}
    base={'model':c['model'],'provider':c['provider'],'canStart':False}
    try:
        models=request('/api/tags',timeout=timeout,config=c).get('models',[])
    except (ValueError,OSError):
        return {**base,'state':'engine_offline','message':'Local AI engine is not reachable. Start it or check Settings.',
                'canStart':c['provider']=='ollama' and ollama_executable() is not None}
    if not any(m.get('name')==c['model'] for m in models):
        return {**base,'state':'model_missing','message':'The selected local model is missing. Choose an installed vision model in Settings.'}
    try:
        info=request('/api/show',{'model':c['model']},timeout=timeout,config=c)
        if info.get('remote_host') or info.get('remote_model') or info.get('model_info',{}).get('remote_host'):
            return {**base,'state':'remote_model','message':'Choose a model that runs entirely on this computer.'}
        if 'vision' not in info.get('capabilities',[]):
            return {**base,'state':'vision_missing','message':'The selected model cannot read images. Choose a local vision model.'}
        loaded=None
        if c['provider']=='ollama':
            try:loaded=any(m.get('name')==c['model'] for m in _call(c,'/api/ps',timeout=timeout).get('models',[]))
            except (ValueError,OSError):pass
        return {**base,'state':'ready' if loaded else 'available','message':'Local vision model is loaded.' if loaded else 'Local vision model is available; it loads on first use.','loaded':loaded}
    except (ValueError,OSError):
        return {**base,'state':'checking_failed','message':'The engine responded but model information is unavailable. Recheck the connection.'}

def start_engine(*,confirmed=False):
    if confirmed is not True:raise ValueError('Choose Start Ollama to start the local engine.')
    c=settings()
    if c['provider']!='ollama':raise ValueError('Start the configured local engine using its own application.')
    current=readiness()
    if current['state']!='engine_offline':return current
    exe=ollama_executable()
    if exe is None:raise ValueError('Ollama is not installed in a known location. Install or start your configured engine.')
    import subprocess
    env=os.environ.copy();env['OLLAMA_HOST']=c['url']
    startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
    subprocess.Popen([str(exe),'serve'],env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                     creationflags=0x08000000,startupinfo=startup)
    return {'state':'starting','message':'Starting Ollama. Recheck in a moment.','canStart':False,'model':c['model']}

_START_LOCK=threading.Lock()
def startup_readiness(timeout=5):
    """Start configured local Ollama; never download or load weights."""
    import time
    with _START_LOCK:
        current=readiness(timeout=.5)
        if current['state']!='engine_offline' or not current.get('canStart'):
            return current
        current=start_engine(confirmed=True)
        deadline=time.monotonic()+timeout
        while current['state'] in ('starting','engine_offline') and time.monotonic()<deadline:
            time.sleep(.15);current=readiness(timeout=.5)
        return current
