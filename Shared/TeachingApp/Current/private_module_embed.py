"""Optional, nonce-bound embedding in the local personal G-Whiz shell."""
from urllib.parse import urlsplit,parse_qs
from pathlib import Path
import html,os,re,secrets,threading,json

def parent_origin():
    value=os.environ.get('GWHIZ_PARENT_ORIGIN','')
    parsed=urlsplit(value)
    return value if parsed.scheme=='http' and parsed.hostname=='127.0.0.1' and parsed.port and parsed.path in ('','/') and value.rstrip('/')==value else ''

def navigation(handler):
    key=os.environ.get('GWHIZ_EMBED_KEY','')
    if not key or not parent_origin() or handler.command!='GET':return False
    url=urlsplit(handler.path)
    supplied=parse_qs(url.query).get('gwhiz_embed',[''])[0]
    if url.path!='/' or not secrets.compare_digest(supplied,key):return False
    if handler.headers.get('Sec-Fetch-Dest')!='iframe':return False
    referer=handler.headers.get('Referer','').rstrip('/')
    return referer==parent_origin()

def csp(value):
    origin=parent_origin()
    return value.replace("frame-ancestors 'none'","frame-ancestors 'self' "+origin) if origin else value

def frame_headers():
    return {} if parent_origin() else {'X-Frame-Options':'DENY'}

def send_frame_headers(handler):
    for name,value in frame_headers().items():handler.send_header(name,value)

def serve_ui(handler,static):
    """Serve only public shell assets; the existing handler has already guarded GET."""
    origin=parent_origin();module=os.environ.get('GWHIZ_MODULE_ID','')
    if not origin or module not in ('grades','recommendations','integrity'):return False
    route=urlsplit(handler.path).path
    if route not in ('/','/index.html','/__gwhiz/shell.css','/__gwhiz/shell.js'):return False
    if route in ('/','/index.html'):
        content=(Path(static)/'index.html').read_text('utf-8-sig')
        content=re.sub(r'<html\b',r'<html class="gwhiz-native gwhiz-'+module+'"',content,count=1)
        tags='<link rel="stylesheet" href="/__gwhiz/shell.css"><script defer src="/__gwhiz/shell.js" data-gwhiz-module="'+module+'" data-gwhiz-parent="'+html.escape(origin,quote=True)+'"></script>'
        body=content.replace('</head>',tags+'</head>').encode('utf-8');mime='text/html; charset=utf-8'
    else:
        base=Path(os.environ.get('GWHIZ_SHELL_ASSETS',''))
        if not base.is_absolute():return False
        name='shell.css' if route.endswith('.css') else 'shell.js'
        body=(base/name).read_bytes();mime='text/css; charset=utf-8' if name.endswith('.css') else 'text/javascript; charset=utf-8'
    handler.send_response(200)
    for name,value in {'Content-Type':mime,'Content-Length':str(len(body)),'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','Content-Security-Policy':csp("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")}.items():handler.send_header(name,value)
    handler.end_headers();handler.wfile.write(body);return True

def stop_request(handler,store,busy=None):
    if urlsplit(handler.path).path!='/__gwhiz/stop':return False
    expected='127.0.0.1:'+str(handler.server.server_port)
    key=os.environ.get('GWHIZ_EMBED_KEY','')
    allowed=bool(key and handler.headers.get('Host')==expected and secrets.compare_digest(handler.headers.get('X-GWhiz-Module-Key',''),key) and not handler.headers.get('Origin') and not handler.headers.get('Sec-Fetch-Site'))
    status=403;body=b'{"error":"Unavailable action"}'
    if allowed:
        acquired=store.lock.acquire(blocking=False)
        if acquired:
            try:
                if busy and busy():status=409;body=b'{"error":"Local processing is still running"}'
                else:status=200;body=b'{"stopped":true}'
            finally:store.lock.release()
        else:status=409;body=b'{"error":"A module action is still running"}'
    handler.send_response(status);handler.send_header('Content-Type','application/json');handler.send_header('Cache-Control','no-store');handler.send_header('Content-Length',str(len(body)));handler.end_headers();handler.wfile.write(body)
    if status==200:threading.Thread(target=handler.server.shutdown,daemon=True).start()
    return True
