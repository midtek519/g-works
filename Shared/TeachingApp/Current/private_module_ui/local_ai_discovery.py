"""Read-only discovery of running loopback model servers, without inference."""
from concurrent.futures import ThreadPoolExecutor
try:from . import local_ai_config as config
except ImportError:import local_ai_config as config

def connection(provider,url):
 return config.validate({'provider':provider,'url':url,'model':'discovery','revision':'discovery' if provider=='openai-local' else '', 'vision':False})
def models(provider,url):
 value=connection(provider,url)
 return config.request('/api/tags',timeout=2,config=value).get('models',[])
def discover(current):
 candidates=[(current['provider'],current['url']),('ollama','http://127.0.0.1:11434'),('openai-local','http://127.0.0.1:1234'),('openai-local','http://127.0.0.1:8080'),('openai-local','http://127.0.0.1:8000'),('openai-local','http://127.0.0.1:1337')]
 candidates=list(dict.fromkeys(candidates))
 def probe(item):
  provider,url=item
  try:
   found=models(provider,url)
   return {'provider':provider,'url':url,'label':('Ollama' if provider=='ollama' else 'Compatible local server')+' · '+url,'models':[{'id':x['name'],'label':x['name']} for x in found if isinstance(x,dict) and isinstance(x.get('name'),str) and 'cloud' not in x['name'].lower()]}
  except (OSError,ValueError,KeyError,TimeoutError):return None
 with ThreadPoolExecutor(max_workers=6) as pool:return [x for x in pool.map(probe,candidates) if x]
