"""Shared dependency detection and setup for the G-Works wizard."""
from pathlib import Path
import contextlib, importlib.util, json, os, re, shutil, struct, subprocess, sys, tempfile, time, urllib.request, zlib
from engine import json_write, emit

def run(args, **kwargs):
    flags = {'creationflags': 134217728} if os.name == 'nt' else {}
    return subprocess.run([str(x) for x in args], check=True, **flags, **kwargs)

def local_json(url, payload=None, timeout=3):
    if not re.fullmatch('http://127\\.0\\.0\\.1:\\d+/(?:api/(?:tags|show|pull)|v1/models)', url):
        raise ValueError('Local AI must use a literal loopback address.')
    request = urllib.request.Request(url, data=None if payload is None else json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=timeout) as response:
        return json.load(response)

def settings_owner(root):
    """Match TeachingApp private_module_ui.runtime_paths.canonical_settings_root.

    Bootstrap remains standalone; never import mutable installed app code here.
    A personal setup may read the shared choice but cannot journal external writes.
    """
    root = Path(root).resolve()
    professional = root.parent / 'G-Works'
    registered = (professional / '.gworks/root.json').is_file() and (professional / 'Apps').is_dir() and (professional / 'Shared').is_dir()
    return professional if root.name == 'Application' and registered else root

def validate_ai_ownership(root, options):
    external = settings_owner(root) != Path(root).resolve()
    if external and options.get('ai_choice', 'keep') not in ('', 'keep'):
        raise ValueError('Shared AI is managed by G-Works. Use G-Works Settings or Install / update to change it. Application setup can maintain TeX while keeping the shared AI choice.')
    return external

def configured_settings(root):
    result = {}
    if root is None:
        return result
    root = Path(root)
    if not (root / '.gworks/root.json').is_file():
        return result
    owner = settings_owner(root)
    external = owner != root.resolve()
    result['shared_ai_managed_externally'] = external
    shared = owner / 'Shared/Settings/local-ai.json'
    if shared.is_file():
        value = json.loads(shared.read_text('utf-8-sig'))
        if set(value) == {'provider', 'url', 'model', 'revision', 'vision'}:
            result['local_ai'] = value
    from engine import APPS, APP_SUITES, root_suite
    suite = root_suite(root)
    for ident, name in APPS.items():
        if suite and APP_SUITES[ident] != suite:
            continue
        app = root / 'Apps' / name
        settings = app / 'Data/settings.json'
        if settings.is_file():
            value = json.loads(settings.read_text('utf-8-sig'))
            tex = value.get('tex_bin') or value.get('texlive_bin')
            if tex and 'tex_bin' not in result:
                result['tex_bin'] = str((app / tex).resolve())
    return result

def local_origin(value):
    match = re.fullmatch('http://(?:127\\.0\\.0\\.1|localhost):(\\d{1,5})(?:/v1/?)?/?', value or '')
    if not match or not 1 <= int(match[1]) <= 65535:
        raise ValueError('Use a local HTTP server address, such as http://127.0.0.1:1234.')
    return 'http://127.0.0.1:' + str(int(match[1]))

def discover(root=None):
    candidates = []
    configured = configured_settings(root)
    if configured.get('tex_bin'):
        candidates.append(Path(configured['tex_bin']))
    if root is not None:
        for base in (Path(root) / 'Shared/TeXLive').glob('*/bin/windows'):
            candidates.append(base)
    for name in ('pdflatex', 'latexmk'):
        if shutil.which(name):
            candidates.append(Path(shutil.which(name)).parent)
    if os.name == 'nt':
        candidates.extend(Path('C:/texlive').glob('*/bin/windows'))
        candidates.extend((Path(p) for p in ('A:/G-Works/Apps/G-Vault/Dependencies/texlive/bin/windows',) if Path(p).is_dir()))
    tex = next((str(p.resolve()) for p in candidates if (p / ('pdflatex.exe' if os.name == 'nt' else 'pdflatex')).is_file()), '')
    local = []
    for base, provider, route in [('http://127.0.0.1:11434', 'ollama', '/api/tags'), ('http://127.0.0.1:1234', 'openai-local', '/v1/models')]:
        try:
            value = local_json(base + route)
            models = [x.get('name') or x.get('id') for x in value.get('models', value.get('data', []))]
            if models:
                local.append({'url': base, 'provider': provider, 'models': models})
        except Exception:
            pass
    managed = Path(root) / 'Shared/Ollama/ollama.exe' if root is not None else None
    ollama = str(managed) if managed is not None and managed.is_file() else shutil.which('ollama') or str(Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs/Ollama/ollama.exe')
    return {'tex_bin': tex, 'local_ai': local, 'ollama': ollama if Path(ollama).is_file() else '', 'configured': configured}

def verify_publisher(executable, publisher):
    if os.name != 'nt':
        raise ValueError('Windows dependency setup must run on Windows.')
    import base64
    encoded = base64.b64encode(str(Path(executable).resolve()).encode()).decode()
    script = "$p=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + encoded + "'));$s=Get-AuthenticodeSignature -LiteralPath $p;if($s.Status -ne 'Valid'){exit 2};[Console]::Write($s.SignerCertificate.Subject)"
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', base64.b64encode(script.encode('utf-16-le')).decode()], capture_output=True, text=True, creationflags=134217728)
    if result.returncode or publisher.casefold() not in result.stdout.casefold():
        raise ValueError('The dependency installer publisher could not be verified.')

def select_tools(packages, options):
    if set(options.get('apps', [])) <= {'mods', 'spot'}:
        return packages
    found = discover(options.get('root'))
    result = []
    webview_roots = [Path(os.environ.get('PROGRAMFILES(X86)', 'C:/Program Files (x86)')) / 'Microsoft/EdgeWebView/Application', Path(os.environ.get('LOCALAPPDATA', '')) / 'Microsoft/EdgeWebView/Application']
    has_webview = any((next(base.glob('*/msedgewebview2.exe'), None) is not None for base in webview_roots))
    for package in packages:
        tool = package.get('tool')
        if tool == 'ollama' and options.get('root') and (settings_owner(options['root']) != Path(options['root']).resolve()):
            continue
        if tool == 'texlive' and options.get('tex_choice', 'existing') == 'existing':
            continue
        wants_ollama = options.get('ai_choice') == 'ollama' if options.get('ai_choice') else options.get('install_ollama', not found['local_ai'])
        has_ollama = found['ollama'] or any((item['provider'] == 'ollama' for item in found['local_ai']))
        if tool == 'ollama' and (not wants_ollama or has_ollama):
            continue
        if tool == 'webview2' and has_webview:
            continue
        result.append(package)
    return result

def installed_support(root, staged, options, role):
    found = next((root / package['target'] for package, _, _ in staged if package.get('runtime_role') == role), None)
    if found is not None or not options.get('dependencies_only'):
        return found
    from engine import APPS
    dependency = 'TeachingApp' if role == 'Commands' else role
    required = 'tex_requirements.json' if role == 'Commands' else 'lib/mhdocument.cls'
    return next((root / 'Apps' / APPS[app] / 'Dependencies' / dependency for app in options['apps'] if (root / 'Apps' / APPS[app] / 'Dependencies' / dependency / required).is_file()), None)

def configure(root, staged, options, report):
    if os.name != 'nt':
        raise ValueError('The desktop installer currently supports Windows.')
    if set(options['apps']) <= {'mods', 'spot'}:
        report('Application uses its own local settings; no TeX or AI setup is required.')
        return
    validate_ai_ownership(root, options)
    found = discover(root)
    tex = options.get('tex_bin') or found['tex_bin']
    choice = options.get('tex_choice', 'existing')
    tools = {p.get('tool'): (p, folder, archive) for p, folder, archive in staged if p['kind'] == 'tool-installer'}
    if choice in ('full', 'essentials'):
        if 'texlive' not in tools:
            raise ValueError('The verified TeX Live installer is missing from this release.')
        report('Installing TeX Live. This can take a while; keep the wizard open.')
        helpers = installed_support(root, staged, options, 'Commands')
        if helpers is None:
            raise ValueError('This release must include its shared TeX setup helper.')
        if choice == 'essentials' and set(options['apps']) - {'whiz', 'scope'}:
            raise ValueError('TeX Live Essentials is for G-Whiz. Choose Full for G-Vault or Application.')
        sys.path.insert(0, str(helpers))
        spec = importlib.util.spec_from_file_location('gworks_tex', helpers / 'tex_install.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _, _, archive = tools['texlive']
        target = root / 'Shared/TeXLive' / ('2026-' + choice)
        if target.exists() and any(target.iterdir()):
            raise ValueError('That TeX installation already exists. Choose Use existing to reuse it.')
        installer = module.extract_installer(archive, root / '.gworks/tex-installer' / str(time.time_ns()))
        profile = installer / 'g-works.profile'
        profile.write_text(module.profile_text(target, choice), encoding='ascii')
        perl = installer / 'tlpkg/tlperl/bin/perl.exe'
        env = {k: v for k, v in os.environ.items() if not k.upper().startswith('PERL')}
        env.update({'PERL5LIB': str(installer / 'tlpkg/tlperl/lib'), 'TEXLIVE_PREFER_OWN': '1'})
        env['PATH'] = str(perl.parent) + os.pathsep + env.get('PATH', '')
        run([perl, installer / 'install-tl', '-no-gui', '-profile', profile], cwd=installer, env=env, stdout=sys.stderr, stderr=sys.stderr)
        tex = str(target / 'bin/windows')
        if choice == 'essentials':
            requirements = json.loads((helpers / 'tex_requirements.json').read_text('utf-8'))
            run([target / 'tlpkg/tlperl/bin/perl.exe', target / 'texmf-dist/scripts/texlive/tlmgr.pl', 'install', *requirements['texlive_packages']], env=env, stdout=sys.stderr, stderr=sys.stderr)
    if not tex or not (Path(tex) / 'pdflatex.exe').is_file():
        raise ValueError('A working TeX installation is required. Choose its bin folder or install TeX Live.')
    version = run([Path(tex) / 'pdflatex.exe', '--version'], capture_output=True, text=True).stdout
    options['_tex_distribution'] = 'miktex' if 'miktex' in version.casefold() else 'texlive'
    if set(options['apps']) & {'vault', 'willikers'}:
        if not (Path(tex) / 'latexmk.exe').is_file():
            raise ValueError('G-Vault and Application require latexmk. Choose TeX Live Full or a compiler installation that includes it.')
        run([Path(tex) / 'latexmk.exe', '--version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    options['_tex_bin'] = tex
    if options.get('verify_packages'):
        verify_tex(root, staged, options, report)
    configure_ai(root, tools, options, report, found)
    if 'webview2' in tools:
        package, folder, _ = tools['webview2']
        exe = folder / 'setup.exe'
        verify_publisher(exe, package['publisher'])
        report('Checking Microsoft WebView2.')
        run([exe, '/silent', '/install'], stdout=sys.stderr, stderr=sys.stderr)

def tex_requirements(root, staged, options):
    helpers = installed_support(root, staged, options, 'Commands')
    if helpers is None:
        raise ValueError('The shared TeX checking tools are missing from this release.')
    manifest = json.loads((helpers / 'tex_requirements.json').read_text('utf-8'))
    required = set(manifest['required_files']) if set(options['apps']) & {'vault', 'whiz', 'scope'} else {'article.cls'}
    libraries = []
    math_libraries = []
    if set(options['apps']) & {'vault', 'whiz', 'scope'}:
        support = installed_support(root, staged, options, 'TeachingSupport')
        if support is None or not (support / 'lib/mhdocument.cls').is_file():
            raise ValueError('The shared MathHouse support library is missing from this release.')
        math_libraries = [support / 'lib']
    if 'willikers' in options['apps']:
        for package, unpacked, _ in staged:
            library = unpacked / 'Content/dnd-git/lib'
            if package.get('app') == 'willikers' and library.is_dir():
                libraries.append(library)
        if not libraries and (root / 'Apps/Application/dnd-git/lib').is_dir():
            libraries.append(root / 'Apps/Application/dnd-git/lib')
        if not libraries:
            raise ValueError('The Application TeX library is missing from this release.')
        owned = {p.stem for library in libraries for p in library.iterdir() if p.suffix in ('.sty', '.cls')}
        for library in libraries:
            for source in library.iterdir():
                if source.suffix not in ('.sty', '.cls'):
                    continue
                for group in re.findall('\\\\RequirePackage(?:\\[[^\\]]*\\])?\\{([^{}]+)\\}', source.read_text('utf-8')):
                    required.update((name + '.sty' for name in group.split(',') if re.fullmatch('[A-Za-z][A-Za-z0-9-]*', name) and name not in owned))
    return (helpers, manifest, sorted(required), libraries, math_libraries)

def verify_tex(root, staged, options, report):
    helpers, manifest, required, libraries, math_libraries = tex_requirements(root, staged, options)
    folder = Path(options['_tex_bin'])
    kpse = folder / 'kpsewhich.exe'
    if not kpse.is_file():
        raise ValueError('The compiler needs kpsewhich for package checks. Choose its complete bin folder.')
    env = dict(os.environ)
    env['PATH'] = str(folder) + os.pathsep + env.get('PATH', '')
    env['TEXINPUTS'] = os.pathsep.join((p.as_posix() + '//' for p in libraries + math_libraries)) + os.pathsep + env.get('TEXINPUTS', '') + os.pathsep

    def missing():
        return [name for name in required if not subprocess.run([str(kpse), name], capture_output=True, text=True, env=env, timeout=30, creationflags=134217728).stdout.strip()]
    report('Checking required TeX packages.')
    absent = missing()
    repair = bool(options.get('repair_packages'))
    miktex = options['_tex_distribution'] == 'miktex'
    if absent and repair and (not miktex):
        texroot = folder.parents[1]
        perl = texroot / 'tlpkg/tlperl/bin/perl.exe'
        manager = texroot / 'texmf-dist/scripts/texlive/tlmgr.pl'
        if not perl.is_file() or not manager.is_file():
            raise ValueError('Use TeX Live Manager to repair this installation, then retry the check.')
        packages = set()
        for name in absent:
            result = run([perl, manager, 'search', '--global', '--file', '/' + re.escape(name) + '$'], capture_output=True, text=True, env=env, timeout=180)
            packages.update(re.findall('(?m)^([A-Za-z0-9][A-Za-z0-9._+-]*):\\s*$', result.stdout))
        if not packages:
            raise ValueError('TeX Live could not identify the missing packages: ' + ', '.join(absent))
        report('Installing missing TeX packages.')
        run([perl, manager, 'install', *sorted(packages)], env=env, stdout=sys.stderr, stderr=sys.stderr, timeout=1800)
        absent = missing()
    if absent and (not (repair and miktex)):
        raise ValueError('Missing TeX packages: ' + ', '.join(absent) + '. Enable Install missing TeX packages, or choose another compiler.')
    spec = importlib.util.spec_from_file_location('gworks_compile_check', helpers / 'tex_compile.py')
    compiler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(compiler)
    documents = []
    checks = []
    if 'willikers' in options['apps']:
        if not (folder / 'lualatex.exe').is_file():
            raise ValueError('Application requires LuaLaTeX. Choose a complete TeX installation.')
        documents.append(('lualatex', '\\documentclass[graphics=final,paper=false,art=false,ornaments=false]{dndbook}\\begin{document}G-Works publication compiler check.\\end{document}'))
    report('Compiling dependency test documents.')
    with tempfile.TemporaryDirectory(prefix='dependency-check-', dir=root / '.gworks') as directory:
        if set(options['apps']) & {'vault', 'whiz', 'scope'}:
            if not math_libraries:
                raise ValueError('The MathHouse TeX library is missing from this release.')
            workspace = Path(directory) / 'math'
            shutil.copytree(math_libraries[0].parent, workspace / 'mh-git', ignore=shutil.ignore_patterns('.gworks-package.json'))
            sys.path.insert(0, str(helpers))
            try:
                spec = importlib.util.spec_from_file_location('gworks_math_smoke', helpers / 'instructor_tex.py')
                math = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(math)
                try:
                    checks.extend(math.smoke(workspace, folder, options['_tex_distribution'], install=repair))
                except ValueError:
                    logs = list((workspace / 'Temp').rglob('console.txt'))
                    (root / '.gworks/last-dependency-check.log').write_text('\n'.join((p.read_text('utf-8') for p in logs)), 'utf-8')
                    raise ValueError('The MathHouse compiler check failed. See .gworks/last-dependency-check.log or choose another compiler.') from None
            finally:
                sys.path.remove(str(helpers))
        for engine, text in documents:
            work = Path(directory) / engine
            work.mkdir()
            source = work / 'check.tex'
            source.write_text(text, 'utf-8')

            def png_chunk(kind, data):
                return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 4294967295)
            image = work / 'img/banner_hline.png'
            image.parent.mkdir()
            image.write_bytes(b'\x89PNG\r\n\x1a\n' + png_chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)) + png_chunk(b'IDAT', zlib.compress(b'\x00\xff\xff\xff')) + png_chunk(b'IEND', b''))
            result = compiler.compile_document(folder / (engine + '.exe'), source, work, miktex=miktex, install=repair, cwd=work, env=env, timeout=900 if repair else 240)
            if result.returncode or not (work / 'check.pdf').is_file():
                (root / '.gworks/last-dependency-check.log').write_text(result.stdout, 'utf-8')
                raise ValueError('The ' + engine + ' dependency test failed. See .gworks/last-dependency-check.log or choose a complete TeX Live installation.')
            checks.append(engine)
    absent = missing()
    if absent:
        raise ValueError('TeX package checks remain incomplete: ' + ', '.join(absent))
    options['_tex_checks'] = {'verified': True, 'checks': checks, 'requirements_version': manifest['version']}
    (root / '.gworks/last-dependency-check.log').unlink(missing_ok=True)
    report('Compiler and required package checks passed.')

def configure_ai(root, tools, options, report, found):
    if validate_ai_ownership(root, options):
        options['_local_ai'] = found.get('configured', {}).get('local_ai')
        report('Keeping shared AI unchanged. Manage it in G-Works Settings or Install / update.')
        return
    choice = options.get('ai_choice', '')
    if choice not in ('', 'keep', 'ollama', 'openai-local'):
        raise ValueError('Choose a supported local AI provider.')
    current = found.get('configured', {}).get('local_ai')
    if choice == 'keep' and current:
        current = dict(current)
        current['url'] = local_origin(current['url'])
        if current['provider'] not in ('ollama', 'openai-local') or not current.get('model'):
            raise ValueError('The saved local AI configuration needs repair.')
        options['_local_ai'] = current
        report('Keeping the configured local AI connection.')
        return
    chosen = found['local_ai'][0] if found['local_ai'] else None
    if choice == 'openai-local':
        url = local_origin(options.get('local_ai_url', ''))
        values = local_json(url + '/v1/models').get('data', [])
        chosen = {'provider': 'openai-local', 'url': url, 'models': [m['id'] for m in values if isinstance(m, dict) and m.get('id')]}
    wants_ollama = choice == 'ollama' if choice else options.get('install_ollama', not chosen)
    if wants_ollama:
        if not found['ollama'] and (not any((item['provider'] == 'ollama' for item in found['local_ai']))):
            if 'ollama' not in tools:
                raise ValueError('The verified Ollama installer is missing from this release.')
            package, folder, _ = tools['ollama']
            exe = folder / 'setup.exe'
            verify_publisher(exe, package['publisher'])
            report('Installing Ollama.')
            models = str(root / 'Models/Ollama')
            env = dict(os.environ)
            env.update(OLLAMA_MODELS=models, OLLAMA_HOST='127.0.0.1:11434')
            import winreg
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, 'Environment') as environment:
                winreg.SetValueEx(environment, 'OLLAMA_MODELS', 0, winreg.REG_SZ, models)
                winreg.SetValueEx(environment, 'OLLAMA_HOST', 0, winreg.REG_SZ, '127.0.0.1:11434')
            run([exe, '/VERYSILENT', '/NORESTART', '/DIR=' + str(root / 'Shared/Ollama')], env=env, stdout=sys.stderr, stderr=sys.stderr)
        ollama = root / 'Shared/Ollama/ollama.exe'
        if not ollama.is_file() and found['ollama']:
            ollama = Path(found['ollama'])
        if ollama.is_file():
            try:
                local_json('http://127.0.0.1:11434/api/tags')
            except Exception:
                env = dict(os.environ)
                env['OLLAMA_HOST'] = '127.0.0.1:11434'
                if Path(ollama).resolve().is_relative_to((root / 'Shared/Ollama').resolve()):
                    env['OLLAMA_MODELS'] = str(root / 'Models/Ollama')
                subprocess.Popen([str(ollama), 'serve'], env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=134217728)
                for _ in range(60):
                    try:
                        local_json('http://127.0.0.1:11434/api/tags')
                        break
                    except Exception:
                        time.sleep(0.5)
        chosen = {'provider': 'ollama', 'url': 'http://127.0.0.1:11434', 'models': []}
    if not chosen:
        raise ValueError('A local LLM is required. Install Ollama or start an existing local model server.')
    model = options.get('model', '').strip() or next(iter(chosen['models']), '')
    if not re.fullmatch('[A-Za-z0-9_.:/-]{1,160}', model) or 'cloud' in model.casefold():
        raise ValueError('Choose a local model to finish setup.')
    if chosen['provider'] == 'ollama':
        installed = local_json(chosen['url'] + '/api/tags').get('models', [])
        if model not in [m.get('name') for m in installed]:
            report('Downloading the selected local model. Model files may be several gigabytes.')
            request = urllib.request.Request(chosen['url'] + '/api/pull', data=json.dumps({'name': model, 'stream': True}).encode(), headers={'Content-Type': 'application/json'})
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=7200) as response:
                for line in response:
                    value = json.loads(line)
                    if value.get('error'):
                        raise ValueError('Local model download failed: ' + value['error'])
                    if value.get('status'):
                        report(value['status'])
        details = local_json(chosen['url'] + '/api/show', {'name': model}, timeout=30)
        vision = 'vision' in details.get('capabilities', [])
    else:
        if model not in chosen['models']:
            raise ValueError('The selected model is not available on this local server.')
        vision = False
        if not options.get('model_revision', '').strip():
            raise ValueError('Enter the actual model revision or fingerprint for this compatible local server.')
    options['_local_ai'] = {'provider': chosen['provider'], 'url': chosen['url'], 'model': model, 'revision': options.get('model_revision', '').strip() if chosen['provider'] == 'openai-local' else '', 'vision': vision}
    if 'scope' in options['apps'] and (not vision):
        report('The selected model is text-only. Grading images will require a vision-capable local model.')

def seed_configuration(root, apps, options, transaction):
    if set(apps) <= {'mods', 'spot'}:
        return
    external = validate_ai_ownership(root, options)
    local = root / 'Shared/Settings/local-ai.json'
    if not external and (not local.exists() or options.get('change_dependencies')):
        current = configured_settings(root).get('local_ai')
        selected = options['_local_ai'] if options.get('change_dependencies') or current is None else current
        temp = transaction.folder / 'shared-local-ai.json'
        json_write(temp, selected)
        transaction.put(temp, 'Shared/Settings/local-ai.json')
    for app in apps:
        if app in ('mods', 'spot'):
            continue
        from engine import APPS
        prefix = 'Apps/' + APPS[app]
        settings = root / prefix / 'Data/settings.json'
        value = json.loads(settings.read_text('utf-8-sig')) if settings.is_file() else {}
        selected = {'texlive_bin': options['_tex_bin'], 'tex_bin': options['_tex_bin'], 'tex_distribution': options.get('_tex_distribution', 'texlive')}
        for key, item in selected.items():
            if options.get('change_dependencies') or key not in value:
                value[key] = item
        if options.get('_tex_checks'):
            value['tex_setup'] = options['_tex_checks']
        elif options.get('change_dependencies'):
            value.pop('tex_setup', None)
        if app in ('vault', 'whiz'):
            value.setdefault('portable_output', True)
        if app == 'willikers' and (options.get('change_dependencies') or 'latexmk' not in value):
            value['latexmk'] = str(Path(options['_tex_bin']) / 'latexmk.exe')
        temp = transaction.folder / (app + '-settings.json')
        json_write(temp, value)
        transaction.put(temp, prefix + '/Data/settings.json')
        if app == 'vault':
            source = root / prefix / 'Data/PrivateSource'
            compiler = str(Path(options['_tex_bin']) / 'pdflatex.exe')
            module_defaults = {'Recommendations': {'grade_database': '', 'mh_git': str(source), 'pdflatex': compiler, 'academic_year_start_month': 7}, 'Integrity': {'sender': {'name': '', 'title': '', 'department': 'Department of Mathematics, Rutgers University', 'contact_lines': []}, 'signature_file': str(source / 'img/signature.png'), 'renderer': str(source / 'professional-correspondence/recommendations/render_letter.py'), 'pdflatex': compiler, 'integrity_catalog': str(source / 'professional-correspondence/integrity/catalog.json')}}
            for module, settings_value in module_defaults.items():
                relative = prefix + '/Data/PrivateModules/' + module + '/tools/settings.json'
                existing = root / relative
                if existing.exists():
                    if not options.get('change_dependencies'):
                        continue
                    settings_value = json.loads(existing.read_text('utf-8-sig'))
                    settings_value['pdflatex'] = compiler
                temp = transaction.folder / (module + '-settings.json')
                json_write(temp, settings_value)
                transaction.put(temp, relative)
        ready = transaction.folder / (app + '-ready.json')
        json_write(ready, {'ready': True, 'installer': 'G-Works'})
        transaction.put(ready, prefix + '/Data/Setup/windows.json', True)
        if options.get('connect_chatgpt') and app in ('vault', 'whiz', 'scope'):
            pending = transaction.folder / (app + '-ai-setup.json')
            json_write(pending, {'open': True})
            transaction.put(pending, prefix + '/Data/Setup/general-ai.json')
