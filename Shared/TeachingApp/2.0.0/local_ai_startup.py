"""Metadata-only local AI startup probe shared by the launcher and desktop tools."""
from pathlib import Path
import json,sys
sys.path.insert(0,str(Path(__file__).resolve().parent/'private_module_ui'))
import local_ai_config
if __name__=='__main__':
    try:
        result=local_ai_config.startup_readiness() if '--start' in sys.argv else local_ai_config.readiness()
        print(json.dumps(result))
    except Exception:
        print(json.dumps({'state':'checking_failed','message':'Check the configured local AI engine in Settings.','canStart':False}))
