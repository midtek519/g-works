"""General AI only for named academic tasks and approved redacted briefs.

Never install this as Store.complete: that callback is reserved for private AI.
Call sites must select a named general task after their source/privacy checks.
"""
from pathlib import Path
import hashlib,json,os,re,secrets
import chatgpt_account,local_ai_config

from runtime_paths import application_root,settings_directory
ROOT=application_root()
DEFAULT={'provider':'local','model':'','effort':'default'}
PURPOSES=frozenset(('instructor-question-import','deidentified-free-response-grading','blank-exam-solution','blank-exam-rubric','redacted-recommendation-brief','redacted-integrity-brief'))

def describe(plan):return {'provider':plan['provider'],'model':plan['model'],'effort':plan.get('effort','default'),'label':'General AI · Using ChatGPT plan' if plan['provider']=='chatgpt' else 'General AI · local model'}

def path(root=ROOT):return settings_directory(root)/'general-ai.json'
def validate(value):
    if not isinstance(value,dict) or set(value)!=set(DEFAULT) or value.get('provider') not in ('local','chatgpt'):raise ValueError('Choose a General AI connection.')
    model=value.get('model');effort=value.get('effort')
    if not isinstance(model,str) or model and not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,160}',model):raise ValueError('Choose a General AI model.')
    if effort not in ('default','none','minimal','low','medium','high','xhigh','max','ultra'):raise ValueError('Choose a supported thinking level.')
    return dict(value)
def settings(root=ROOT):
    target=path(root)
    if not target.exists():return dict(DEFAULT)
    if target.stat().st_size>16000:raise ValueError('The General AI configuration is too large.')
    return validate(json.loads(target.read_text('utf-8')))
def save(value,root=ROOT):
    value=validate(value);target=path(root);target.parent.mkdir(parents=True,exist_ok=True);temp=target.with_name(target.name+'.'+secrets.token_hex(5)+'.tmp')
    try:temp.write_text(json.dumps(value,allow_nan=False),'utf-8');os.replace(temp,target)
    finally:temp.unlink(missing_ok=True)
    return value
def connection_info(root=ROOT):
    config=settings(root)
    if config['provider']=='local':return {**config,'model':config['model'] or local_ai_config.settings()['model'],'label':'General AI · local model'}
    try:status=chatgpt_account.Account(root).status()
    except ValueError:return {**config,'connected':False,'label':'General AI · reconnect ChatGPT in Settings → AI'}
    connected=status['connected'] and status['sharing']
    return {**config,'connected':connected,'label':'General AI · Using ChatGPT plan' if connected else 'General AI · ChatGPT not connected'}
def plan(purpose,*,fallback_model=None,root=ROOT,vision=False):
    if purpose not in PURPOSES:raise ValueError('This feature must use Private AI.')
    config=settings(root)
    if config['provider']=='local':
        import local_ai
        model=config['model'] or fallback_model or local_ai_config.settings()['model'];info=local_ai.validate_model(model,vision)
        return {**config,'model':model,'identity':hashlib.sha256(json.dumps([config,info],sort_keys=True).encode()).hexdigest()}
    account=chatgpt_account.Account(root);status=account.status()
    if not status['connected'] or not status['sharing']:raise ValueError('Connect ChatGPT and allow plan usage in Settings → AI.')
    model=next((m for m in status['models'] if m['id']==config['model']),None)
    if model is None:raise ValueError('Refresh ChatGPT models and select a General AI model in Settings → AI.')
    if config['effort']!='default' and model['efforts'] and config['effort'] not in model['efforts']:raise ValueError('Choose a thinking level supported by this General AI model.')
    return {**config,'account':status['active'],'identity':'chatgpt:'+hashlib.sha256(json.dumps([status['active'],config],sort_keys=True).encode()).hexdigest()}
def complete(purpose,system,text,*,plan,images=None,schema=None,max_tokens=2400,context=16384):
    if purpose not in PURPOSES:raise ValueError('This feature must use Private AI.')
    if not isinstance(system,str) or not isinstance(text,str) or len(text)>200000:raise ValueError('Use a shorter reviewed input.')
    if purpose.startswith('redacted-') and images:raise ValueError('General letter drafting accepts only the approved redacted text brief, never attachments.')
    if plan['provider']=='local':
        import local_ai
        return local_ai.complete(system,text,model=plan['model'],images=images,schema=schema,max_tokens=max_tokens,context=context,checked=True)
    account=chatgpt_account.Account();profile,token=account.credential()
    if profile!=plan['account']:raise ValueError('The ChatGPT account changed. Start the request again.')
    content=[{'type':'input_text','text':text}]
    if images:
        if not isinstance(images,list) or len(images)>30 or any(not isinstance(i,str) or len(i)>20000000 for i in images):raise ValueError('Use bounded reviewed PNG crops.')
        content += [{'type':'input_image','image_url':'data:image/png;base64,'+i} for i in images]
    body={'model':plan['model'],'instructions':system,'input':[{'role':'user','content':content}],'store':False,'stream':True}
    if plan['effort']!='default':body['reasoning']={'effort':plan['effort']}
    if schema:body['text']={'format':{'type':'json_schema','name':'general_result','schema':schema,'strict':True}}
    token_cancel=getattr(local_ai_config._request_context,'cancellation',None)
    result,stats=chatgpt_account.stream_result(token,body,token_cancel)
    return (json.loads(result) if schema else result),stats
