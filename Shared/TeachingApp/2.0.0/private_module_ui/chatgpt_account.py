"""ChatGPT plan OAuth for general tasks. Credentials never enter the renderer.

Protocol: developers.openai.com/siwc/token-sharing-open-source/sign-in
Windows credentials use current-user DPAPI. This module never reads Codex's
account, browser profiles, API keys, or any student/module database.
"""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
from urllib.parse import urlencode,urlsplit,parse_qs
import re,base64,ctypes,hashlib,http.client,json,os,secrets,socket,sys,threading,time,uuid,webbrowser

from runtime_paths import application_root,settings_directory
ROOT=application_root()
AUTH='https://auth.openai.com'
API='https://api.openai.com/v1'
SCOPE='openid profile email offline_access resource.invoke chatgpt.tokens.use.direct'

def reasoning_efforts(row):
    values=[]
    for field in ('supported_reasoning_levels','supported_reasoning_efforts'):
        levels=row.get(field,[])
        if not isinstance(levels,list):continue
        for item in levels:
            value=(item.get('effort') or item.get('reasoning_effort')) if isinstance(item,dict) else item
            if value in ('none','minimal','low','medium','high','xhigh','max','ultra') and value not in values:values.append(value)
    return values

class ServiceError(ValueError):
    """A connection/plan failure shared by the whole batch, not one question."""
    pass

def b64(raw):return base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii')

def protect(raw,decode=False):
    """No plaintext credential fallback, including on unsupported platforms."""
    if os.name!='nt':raise ValueError('ChatGPT account storage currently requires the Windows desktop app.')
    from ctypes import wintypes
    class Blob(ctypes.Structure):_fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
    buffer=ctypes.create_string_buffer(raw);source=Blob(len(raw),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));target=Blob()
    method=ctypes.windll.crypt32.CryptUnprotectData if decode else ctypes.windll.crypt32.CryptProtectData
    if not method(ctypes.byref(source),None,None,None,None,1,ctypes.byref(target)):raise ValueError('Windows could not unlock this app’s ChatGPT connection. Sign in again on this Windows account.')
    try:return ctypes.string_at(target.data,target.size)
    finally:ctypes.windll.kernel32.LocalFree(target.data)

def atomic(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_name(path.name+'.'+secrets.token_hex(5)+'.tmp')
    try:
        with temp.open('xb') as stream:stream.write(protect(json.dumps(value,allow_nan=False).encode('utf-8')))
        os.replace(temp,path)
    finally:temp.unlink(missing_ok=True)

@contextmanager
def locked(path):
    """Serialize rotating-token refreshes across the separate module services."""
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as stream:
        if os.name=='nt':
            import msvcrt
            stream.seek(0);stream.write(b'0');stream.flush();deadline=time.monotonic()+45
            while True:
                try:stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1);break
                except OSError:
                    if time.monotonic()>deadline:raise ValueError('The ChatGPT connection is busy. Retry shortly.') from None
                    time.sleep(.05)
            try:yield
            finally:stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
        else:
            import fcntl
            fcntl.flock(stream,fcntl.LOCK_EX)
            try:yield
            finally:fcntl.flock(stream,fcntl.LOCK_UN)

def open_request(url,payload=None,*,token=None,form=False,timeout=30,cancellation=None):
    parsed=urlsplit(url)
    if parsed.scheme!='https' or parsed.netloc not in ('auth.openai.com','api.openai.com') or parsed.username or parsed.password:raise ValueError('Unsupported ChatGPT service address.')
    headers={'Accept':'text/event-stream' if isinstance(payload,dict) and payload.get('stream') is True else 'application/json','User-Agent':'G-Works/2.0.0'}
    raw=None
    if payload is not None:
        raw=(urlencode(payload) if form else json.dumps(payload,allow_nan=False)).encode('utf-8');headers['Content-Type']='application/x-www-form-urlencoded' if form else 'application/json'
    if token:headers['Authorization']='Bearer '+token
    connection=http.client.HTTPSConnection(parsed.hostname,timeout=timeout);abort=None
    try:
        connection.connect()
        if cancellation:
            sock=connection.sock
            def abort():
                try:sock.shutdown(socket.SHUT_RDWR)
                except OSError:pass
            cancellation.attach(abort);cancellation.check()
        connection.request('POST' if payload is not None else 'GET',parsed.path+('?' + parsed.query if parsed.query else ''),body=raw,headers=headers)
        response=connection.getresponse()
        if not 200<=response.status<300:
            status=response.status
            if status==429:raise ServiceError('ChatGPT usage limit reached. Review Manage usage in AI settings before retrying.')
            if status in (401,403):raise ServiceError('ChatGPT could not authorize this request. Reconnect the account and confirm plan access.')
            raise ServiceError('ChatGPT could not complete this request. Check the connection, model and thinking level, then retry.')
        return connection,response,abort
    except Exception:
        if abort:cancellation.detach(abort)
        connection.close();raise

def request(url,payload=None,**kwargs):
    connection=None
    try:
        connection,response,_=open_request(url,payload,**kwargs);raw=response.read(2000001)
        if len(raw)>2000000:raise ValueError('The ChatGPT service response is too large.')
        return json.loads(raw) if raw else {}
    except (OSError,http.client.HTTPException):raise ValueError('Cannot reach ChatGPT. Check your internet connection and retry.') from None
    finally:
        if connection:connection.close()

def identity(token,client_id,nonce=None):
    # Use the maintained JWT/cryptography libraries, never an unverified decode.
    dependencies=ROOT/'Dependencies/GeneralAI'
    if str(dependencies) not in sys.path:sys.path.insert(0,str(dependencies))
    try:import jwt
    except ImportError:raise ValueError('The ChatGPT sign-in components are unavailable. Repair the General AI installation.') from None
    discovery=request(AUTH+'/.well-known/openid-configuration')
    if discovery.get('issuer')!=AUTH:raise ValueError('Unexpected ChatGPT sign-in issuer.')
    keys=request(discovery['jwks_uri']);header=jwt.get_unverified_header(token)
    if header.get('alg')!='RS256':raise ValueError('Unsupported ChatGPT identity signature.')
    key=next((key for key in keys.get('keys',[]) if key.get('kid')==header.get('kid') and key.get('kty')=='RSA'),None)
    if key is None:raise ValueError('ChatGPT identity could not be verified. Start a new sign-in.')
    try:
        claims=jwt.decode(token,jwt.PyJWK.from_dict(key).key,algorithms=['RS256'],issuer=AUTH,audience=client_id,options={'require':['iss','sub','aud','exp','iat']})
        if nonce is not None and not secrets.compare_digest(str(claims.get('nonce','')),nonce):raise ValueError('Sign-in nonce mismatch.')
        if not isinstance(claims['sub'],str) or not claims['sub']:raise ValueError('Missing identity.')
        return claims
    except Exception:raise ValueError('ChatGPT identity verification failed. Start a new sign-in.') from None

class Account:
    def __init__(self,root=ROOT):
        self.agent_name=Path(root).name if re.fullmatch(r'G-[A-Za-z]+',Path(root).name) else 'G-Works'
        self.directory=settings_directory(root)/'ChatGPT';self.path=self.directory/'credentials.bin';self.lock_path=self.directory/'connection.lock';self.mutex=threading.RLock();self.pending=None;self.notice=''
    def read(self):
        if not self.path.exists():return {'host':'urn:uuid:'+str(uuid.uuid4()),'profiles':[],'active':''}
        if self.path.stat().st_size>2000000:raise ValueError('The ChatGPT connection record is too large.')
        return json.loads(protect(self.path.read_bytes(),decode=True))
    def status(self):
        with self.mutex,locked(self.lock_path):
            data=self.read();profiles=data['profiles'];active=next((p for p in profiles if p['id']==data.get('active')),None)
            return {'profiles':[{'id':p['id'],'label':p.get('label','ChatGPT account'),'connected':bool(p.get('refresh_token') or p.get('access_token')),'sharing':'chatgpt.tokens.use.direct' in p.get('scopes',[])} for p in profiles],
                    'active':data.get('active',''),'connected':bool(active and (active.get('access_token') or active.get('refresh_token'))),'sharing':bool(active and 'chatgpt.tokens.use.direct' in active.get('scopes',[])),
                    'models':active.get('models',[]) if active else [],'pending':bool(self.pending),'message':self.notice,'welcome':bool(active and active.get('welcome') and 'chatgpt.tokens.use.direct' in active.get('scopes',[]))}
    def start(self,profile_id=''):
        if not isinstance(profile_id,str):raise ValueError('Choose a ChatGPT connection.')
        with self.mutex,locked(self.lock_path):
            if self.pending:raise ValueError('Finish or cancel the current sign-in first.')
            data=self.read();profile=next((p for p in data['profiles'] if p['id']==profile_id),None)
            if profile_id and profile is None:raise ValueError('Choose a saved ChatGPT connection.')
            atomic(self.path,data);attempt={'state':secrets.token_urlsafe(32),'nonce':secrets.token_urlsafe(32),'verifier':secrets.token_urlsafe(64),'cancel':threading.Event(),'profile':dict(profile) if profile else None}
            owner=self
            class Callback(BaseHTTPRequestHandler):
                def log_message(self,*args):pass
                def do_GET(self):
                    parsed=urlsplit(self.path);values=parse_qs(parsed.query)
                    valid=parsed.path=='/auth/callback' and self.headers.get('Host')=='127.0.0.1:'+str(self.server.server_port) and len(values.get('state',[]))==1 and secrets.compare_digest(values['state'][0],attempt['state'])
                    if not valid:self.send_error(400,'Invalid sign-in callback');return
                    try:
                        owner.finish(attempt,values);message='Connected to '+owner.agent_name+'. Return to Settings → AI.'
                    except Exception:
                        with owner.mutex:owner.notice='Sign-in did not complete. Retry and approve ChatGPT plan access in the browser.'
                        message='Sign-in did not complete. Return to '+owner.agent_name+' to retry.'
                    attempt['cancel'].set();raw=('<!doctype html><meta charset="utf-8"><title>'+owner.agent_name+' · ChatGPT</title><p>'+message+'</p>').encode('utf-8')
                    self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Referrer-Policy','no-referrer');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
            listener=HTTPServer(('127.0.0.1',0),Callback);listener.timeout=1;attempt['redirect']='http://127.0.0.1:'+str(listener.server_port)+'/auth/callback';self.pending=attempt;self.notice='Continue in your browser to connect ChatGPT.'
            params={'client_id':profile['client_id'] if profile else 'dynamic_agent_client','ext_agent_host_id':data['host'],'response_type':'code','redirect_uri':attempt['redirect'],'scope':SCOPE,'resource':API,'state':attempt['state'],'nonce':attempt['nonce'],'code_challenge_method':'S256','code_challenge':b64(hashlib.sha256(attempt['verifier'].encode()).digest())}
            if profile:
                if profile.get('id_token'):params['id_token_hint']=profile['id_token']
            else:params['agent_name_hint']=self.agent_name
        def wait():
            try:
                deadline=time.monotonic()+300
                while not attempt['cancel'].is_set() and time.monotonic()<deadline:listener.handle_request()
            finally:
                listener.server_close()
                with self.mutex:
                    if self.pending is attempt:self.pending=None
                    if not attempt['cancel'].is_set():self.notice='ChatGPT sign-in timed out. Continue with ChatGPT to retry.'
        threading.Thread(target=wait,daemon=True,name='chatgpt-sign-in').start()
        if not webbrowser.open(AUTH+'/api/accounts/authorize?'+urlencode(params)):
            self.cancel();raise ValueError('The sign-in browser could not open. Check your default browser and retry.')
        return self.status()
    def finish(self,attempt,values):
        if attempt['cancel'].is_set():raise ValueError('Sign-in cancelled.')
        if values.get('error'):raise ValueError('Sign-in declined.')
        profile=attempt['profile'];client_id=values.get('client_id',[profile['client_id'] if profile else ''])[0]
        if not client_id or client_id=='dynamic_agent_client' or (profile and client_id!=profile['client_id']) or len(values.get('code',[]))!=1:raise ValueError('Incomplete ChatGPT registration.')
        # Retain the issued registration even if code exchange fails; no identity
        # or old credentials are replaced until verification succeeds.
        with locked(self.lock_path):
            data=self.read()
            if profile is None:
                profile={'id':secrets.token_hex(16),'client_id':client_id,'label':'ChatGPT connection '+str(len(data['profiles'])+1),'scopes':[]};data['profiles'].append(profile);atomic(self.path,data)
        tokens=request(AUTH+'/api/accounts/oauth/token',{'grant_type':'authorization_code','client_id':client_id,'code':values['code'][0],'code_verifier':attempt['verifier'],'redirect_uri':attempt['redirect'],'resource':API},form=True)
        claims=identity(tokens.get('id_token',''),client_id,attempt['nonce'])
        if profile.get('subject') and profile['subject']!=claims['sub']:raise ValueError('This connection belongs to another ChatGPT identity.')
        if tokens.get('token_type','').lower()!='bearer' or not tokens.get('access_token'):raise ValueError('ChatGPT did not grant a usable connection.')
        with self.mutex,locked(self.lock_path):
            if self.pending is not attempt or attempt['cancel'].is_set():raise ValueError('Sign-in cancelled.')
            data=self.read();saved=next(p for p in data['profiles'] if p['id']==profile['id']);scopes=tokens.get('scope','').split()
            saved.update(subject=claims['sub'],label=claims.get('email') or saved['label'],id_token=tokens['id_token'],access_token=tokens['access_token'],refresh_token=tokens.get('refresh_token',''),scopes=scopes,expires=time.time()+float(tokens.get('expires_in',3600)),models=[],welcome=not saved.get('welcomed',False));data['active']=saved['id'];atomic(self.path,data);self.notice='ChatGPT connected.' if 'chatgpt.tokens.use.direct' in scopes else 'Signed in. Reconnect and allow ChatGPT plan usage to enable General AI.'
    def cancel(self):
        with self.mutex:
            if self.pending:self.pending['cancel'].set();self.pending=None
            self.notice='Sign-in cancelled.'
        return self.status()
    def select(self,profile_id):
        with self.mutex,locked(self.lock_path):
            if self.pending:raise ValueError('Finish or cancel the current ChatGPT sign-in before switching accounts.')
            data=self.read()
            if not any(p['id']==profile_id for p in data['profiles']):raise ValueError('Choose a saved ChatGPT connection.')
            data['active']=profile_id;atomic(self.path,data);self.notice=''
        return self.status()
    def acknowledge(self):
        with locked(self.lock_path):
            data=self.read()
            for p in data['profiles']:
                if p['id']==data.get('active'):p.update(welcome=False,welcomed=True)
            atomic(self.path,data)
        return self.status()
    def credential(self):
        with locked(self.lock_path):
            data=self.read();profile=next((p for p in data['profiles'] if p['id']==data.get('active')),None)
            if not profile or 'chatgpt.tokens.use.direct' not in profile.get('scopes',[]):raise ValueError('Connect ChatGPT and allow plan usage in Settings → AI.')
            if float(profile.get('expires',0))<time.time()+90:
                if not profile.get('refresh_token'):raise ValueError('Reconnect ChatGPT in Settings → AI.')
                tokens=request(AUTH+'/api/accounts/oauth/token',{'grant_type':'refresh_token','client_id':profile['client_id'],'refresh_token':profile['refresh_token'],'resource':API},form=True)
                if not tokens.get('access_token') or tokens.get('token_type','').lower()!='bearer':raise ValueError('Reconnect ChatGPT in Settings → AI.')
                if tokens.get('id_token'):
                    claims=identity(tokens['id_token'],profile['client_id'])
                    if claims['sub']!=profile['subject']:raise ValueError('ChatGPT account identity changed. Reconnect the account.')
                    profile['id_token']=tokens['id_token']
                profile.update(access_token=tokens['access_token'],refresh_token=tokens.get('refresh_token',profile['refresh_token']),expires=time.time()+float(tokens.get('expires_in',3600)),scopes=tokens.get('scope',' '.join(profile['scopes'])).split());atomic(self.path,data)
            if not profile.get('access_token') or 'chatgpt.tokens.use.direct' not in profile['scopes']:raise ValueError('Reconnect ChatGPT and allow plan usage in Settings → AI.')
            return profile['id'],profile['access_token']
    def models(self):
        profile_id,token=self.credential();result=request(API+'/models',token=token);models=[]
        for row in result.get('models',[]):
            if not isinstance(row,dict) or row.get('visibility')!='list' or not isinstance(row.get('slug'),str):continue
            if len(row['slug'])>160:continue
            models.append({'id':row['slug'],'label':str(row.get('display_name') or row['slug'])[:200],'efforts':reasoning_efforts(row)})
        if not models:raise ValueError('No models are available for this ChatGPT connection.')
        with locked(self.lock_path):
            data=self.read();profile=next(p for p in data['profiles'] if p['id']==profile_id);profile['models']=models;atomic(self.path,data)
        return self.status()
    def logout(self):
        self.cancel();warning=''
        with locked(self.lock_path):
            data=self.read();profile=next((p for p in data['profiles'] if p['id']==data.get('active')),None)
            if profile:
                if profile.get('refresh_token'):
                    try:
                        discovery=request(AUTH+'/.well-known/openid-configuration');request(discovery['revocation_endpoint'],{'token':profile['refresh_token'],'token_type_hint':'refresh_token','client_id':profile['client_id']},form=True)
                    except Exception:warning='Remote sign-out could not be confirmed. You can disconnect this connection in ChatGPT settings.'
                for key in ('access_token','refresh_token','id_token','expires'):profile.pop(key,None)
                profile.update(scopes=[],models=[]);atomic(self.path,data)
        self.notice=warning or 'Signed out of ChatGPT on this computer.';return self.status()

def stream_result(token,body,cancellation=None):
    connection=None;abort=None
    try:
        connection,response,abort=open_request(API+'/responses',body,token=token,timeout=600,cancellation=cancellation)
        # Some approved transports omit this header while returning valid SSE.
        # Require a terminal response.completed event; never infer success from headers.
        media=response.getheader('Content-Type','').split(';',1)[0].strip().lower()
        if media and media!='text/event-stream':raise ServiceError('ChatGPT returned an unexpected response format. No partial solution was saved.')
        count=0;parts=[];event_lines=[]
        while True:
            if cancellation:cancellation.check()
            line=response.readline(1000001);count+=len(line)
            if count>8000000 or len(line)>1000000:raise ValueError('The ChatGPT result is too large.')
            if not line:break
            if line.strip():
                if line.startswith(b'data:'):event_lines.append(line[5:].strip())
                continue
            if not event_lines:continue
            raw=b'\n'.join(event_lines);event_lines=[]
            if raw==b'[DONE]':continue
            event=json.loads(raw);kind=event.get('type')
            if kind=='response.output_text.delta':parts.append(event.get('delta',''))
            elif kind in ('error','response.failed','response.incomplete'):raise ValueError('ChatGPT did not finish. No partial solution was saved. Check the model, thinking level and usage in Settings → AI.')
            elif kind=='response.completed':
                result=event.get('response',{})
                if result.get('status')!='completed':raise ValueError('ChatGPT did not finish. No partial result was saved.')
                output=result.get('output',[])
                if any(item.get('type') not in ('message','reasoning') for item in output):raise ValueError('ChatGPT requested an unsupported tool. No tool was run.')
                final=''.join(content.get('text','') for item in output if item.get('type')=='message' for content in item.get('content',[]) if content.get('type')=='output_text') or ''.join(parts)
                if not final.strip() or len(final)>100000:raise ValueError('ChatGPT returned an empty or oversized result.')
                return final.strip(),{'provider':'chatgpt','usage':result.get('usage',{})}
        raise ServiceError('The ChatGPT connection ended before completion. No partial result was saved.')
    except (OSError,http.client.HTTPException):
        if cancellation:cancellation.check()
        raise ServiceError('The ChatGPT connection was interrupted. No partial result was saved.') from None
    finally:
        if abort:cancellation.detach(abort)
        if connection:connection.close()
