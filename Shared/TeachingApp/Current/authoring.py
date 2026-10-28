"""Unsaved question previews and read-only course document browsing."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime, timezone
import hashlib, json, os, re, secrets, shutil, subprocess, threading

from core import CODES, hash_file, save, tex_input, term
from universal import KINDS, uncomment, workspace_slots, question_properties
from taxonomy_model import validate_classifications, set_classifications


def preview_draft(universal, payload):
    """Compile a working copy without allocating a bank ID or revision."""
    desk = universal.desk
    with desk.lock:
        if desk.active:
            raise ValueError('Let the current compilation finish first.')
        code = str(payload.get('course', ''))
        module = desk.module(code)
        mode = payload.get('mode', 'solutions')
        layout = payload.get('layout', 'manual')
        version = payload.get('version', 'A')
        if mode not in ('student', 'solutions', 'developer'):
            raise ValueError('Choose student, solutions, or developer preview.')
        if layout not in ('manual', 'worksheet', 'assessment'):
            raise ValueError('Choose manual, worksheet, or assessment layout.')
        if not isinstance(version, str) or not re.fullmatch('[A-Z]', version):
            raise ValueError('Choose a preview version from A to Z.')
        if mode != 'student':
            version = 'A'
        workspace = payload.get('workspace_enabled', False)
        if not isinstance(workspace, bool):
            raise ValueError('Choose whether workspace is shown.')
        cat = universal._catalog()
        question = tex_input(payload.get('question', ''))
        solution = tex_input(payload.get('solution', ''))
        if not question:
            raise ValueError('Enter a question to preview.')
        if re.search(r'\\part\s*\[[^\]]+\]|\\(?:AssessmentAddPoints|AssessmentPartPointBox|AssessmentExercisePointBox|marpoints)\b', uncomment(question)):
            raise ValueError('Assign points to the whole question in the Handout Builder. Remove part point values and scoring commands from this question.')
        suitability = payload.get('suitability', {})
        if not isinstance(suitability, dict):
            raise ValueError('Choose valid course and use combinations.')
        for course, kinds in suitability.items():
            if course not in getattr(desk,'modules',CODES) or not isinstance(kinds, list) or any(kind not in KINDS for kind in kinds):
                raise ValueError('Choose valid course and use combinations.')
        suitability = {course: kinds for course, kinds in suitability.items() if kinds}
        if suitability or payload.get('suitability_none'):
            suitability = universal._suitability(suitability,payload.get('suitability_none') is True)
        if not isinstance(payload.get('manual', {}), dict):
            raise ValueError('Choose valid manual placements.')
        source_id = payload.get('id') or payload.get('copy_from_id')
        if payload.get('id') and payload.get('copy_from_id'):
            raise ValueError('Choose either an existing question or a new copy to preview.')
        if source_id:
            original = universal._question(cat, source_id)
            universal._check_source(original)
            expected = payload.get('expected_revision') if payload.get('id') else payload.get('copy_from_revision')
            if expected != original['revision']:
                raise ValueError('The source question changed. Reopen it before previewing this edit or copy.')
            q = deepcopy(original)
            if not payload.get('id'):
                q['id'] = 'Draft-Preview'
        else:
            q = {'id': 'Draft-Preview', 'metadata': {'status': 'draft'}}
        q.update({
            'question': question, 'solution': solution,
            'topics': universal._refs(cat, 'topics', payload.get('topics', [])),
            'objectives': universal._refs(cat, 'objectives', payload.get('objectives', [])),
            'suitability': suitability, 'manual': {},
            'workspace_slots': workspace_slots(question),
        })
        question_properties(q,payload)
        set_classifications(q,validate_classifications(cat,payload,suitability))
        q['tex'] = universal._render_question(q)
        tag = module.CONFIG['default_semester']
        kind = {'manual': 'preview', 'worksheet': 'worksheet', 'assessment': 'quiz'}[layout]
        folder = desk.temp / 'Drafts' / ('question-builder-' + secrets.token_hex(8))
        use = {'workspace_weights': [1 if workspace else 0] * len(q['workspace_slots'])}
        source = universal._compile_tex(cat, code, 'Question draft', tag, kind, mode,
                                        version, ord(version) - ord('A') + 1,
                                        [(q, use)], folder, workspace=workspace)
        return desk.start(code, tag, [], custom=[{
            'name': 'Question-draft-' + mode + '-' + version,
            'source': source, 'prefix': '', 'folder': folder,
            'kind': 'Question draft preview', 'mode': mode, 'version': version,
            'preview_only': True, 'universal': True, 'draft_question': True,
            'layout': layout,
            'source_question_id': source_id or None,
            'source_revision': original['revision'] if source_id else None,
        }])


class CourseLibrary:
    """Expose only listed PDFs from known course material locations."""

    def __init__(self, desk, universal):
        self.desk = desk
        self.universal = universal
        self.files = {}
        self.preview_lock = threading.RLock()

    @staticmethod
    def _safe_file(path, base):
        # Check both the lexical path and resolved path. Junctions and symlinks
        # must not turn an allowed course folder into a general file server.
        path, base = Path(path).absolute(), Path(base).absolute()
        if not path.is_relative_to(base):
            return False
        for component in (path, *path.parents):
            if component.is_symlink() or getattr(component, 'is_junction', lambda: False)():
                return False
            if component == base:
                break
        return path.suffix.lower() == '.pdf' and path.is_file() and path.resolve().is_relative_to(base.resolve())

    @staticmethod
    def _walk(folder):
        if not folder.is_dir() or folder.is_symlink() or getattr(folder, 'is_junction', lambda: False)():
            return
        for root, directories, names in os.walk(folder, followlinks=False):
            directories[:] = [d for d in directories if d.lower() not in ('build', 'builds', '.git', 'node_modules', 'history', 'assets', 'images', 'img', 'exercises')
                              and not re.search(r'(?:^|[ _-])(?:archive(?:d)?|historical|legacy|old(?:er)?|retired|previous)(?:$|[ _-])', d, re.I)
                              and not (Path(root) / d).is_symlink()
                              and not getattr(Path(root) / d, 'is_junction', lambda: False)()]
            for name in names:
                if name.lower().endswith('.pdf'):
                    yield Path(root) / name

    @staticmethod
    def _semesters(path, base):
        relative = path.relative_to(base).as_posix().lower()
        codes = set(re.findall(r'(?<![a-z0-9])((?:fa|sp|su|wi)\d{2})(?!\d)', relative))
        for season, year in re.findall(r'(fall|spring|summer|winter)[ -]+(20\d{2})', relative):
            codes.add({'fall': 'fa', 'spring': 'sp', 'summer': 'su', 'winter': 'wi'}[season] + year[2:])
        return codes

    @staticmethod
    def _kind(path):
        value = path.name.lower()
        if any(part.lower()=='coordination' for part in path.parts):return 'Coordination'
        if 'blank' in value and 'worksheet' in value:return 'Blank Worksheet'
        if re.search(r'(?<![a-z])final(?:[ _-]*exam)?(?=$|[^a-z])',value):return 'Final Exam'
        for word, label in [('manual', 'Manual'), ('quiz(?:zes)?', 'Quiz'),
                            ('exam(?:ination)?s?', 'Exam'), ('worksheets?', 'Worksheet'),
                            ('group[ _-]*work', 'Worksheet'), ('syllabus(?:es)?', 'Syllabus'),
                            ('schedule', 'Schedule'), ('reference', 'Reference sheet'),
                            ('formula', 'Reference sheet')]:
            if re.search(r'(?<![a-z])' + word + r'(?=$|[^a-z])', value):
                return label
        if any(re.fullmatch(r'lecture[ _-]*notes', part, re.I) for part in path.parts):
            return 'Lecture notes'
        return 'Support material'

    def _publishable_outputs(self, code, tag):
        """Exact destinations G-Whiz can produce, rather than nearby PDF files."""
        module = self.desk.module(code)
        outputs = {}

        def add(kind, name, number='', mode='student', version='A'):
            folder = self.desk.publish_folder(code, tag, kind, number, mode, version)
            path = (folder / (name + '.pdf')).resolve()
            outputs[str(path)] = {'path': path, 'kind': kind,
                                  'category': self.desk.material_category(kind)}

        items = module.discover(tag)
        keys = [item['key'] for item in items]
        if str(code) != '135' and (Path(module.COURSE) / 'assessment-manual/assessment-manual.tex').is_file():
            keys.append('assessment-manual')
        for key in dict.fromkeys(keys):
            try:
                jobs = self.desk.plan(code, tag, [key], mode='all')
            except (ValueError, FileNotFoundError):
                continue
            for job in jobs:
                add(job['kind'], job['name'], job.get('publish_number', ''),
                    job['mode'], job['version'])

        if self.universal.available():
            _, short = module.semester_info(tag)
            for assignment in self.universal.assignments():
                if assignment.get('course') != code or assignment.get('semester') != tag:
                    continue
                kind = assignment['kind']
                if kind not in ('exam', 'final', 'quiz', 'worksheet'):
                    continue
                count = max(1, min(26, int(assignment.get('versions', 1))))
                variants = [('student', chr(65 + i)) for i in range(count)]
                variants += [('solutions', 'A'), ('developer', 'A')]
                for mode, version in variants:
                    name = 'Final-Exam-'+short if kind=='final' else kind.title() + '-' + str(assignment['number']) + '-' + short
                    if count > 1:
                        name += '-' + version
                    name += {'solutions': '-sols', 'developer': '-Developer'}.get(mode, '')
                    add('Final Exam' if kind=='final' else kind.title(), name, '' if kind=='final' else assignment['number'], mode, version)
            for mode, suffix in [('student', ''), ('solutions', '-Sols'), ('developer', '-Developer')]:
                add('Manual', 'Manual-' + code + suffix, mode=mode)

        for kind in ('Syllabus', 'Schedule'):
            add(kind, kind + '-' + tag[:2].title() + tag[2:])
        return outputs

    def _candidates(self, code, tag, publishable):
        module = self.desk.module(code)
        course = Path(module.COURSE)
        for record in publishable.values():
            path = record['path']
            if path.is_file():
                yield path, path.parent, 'Published'
        # Some legacy course documents were already PDFs rather than TeX.
        for name in ('exams', 'quizzes', 'worksheets', 'groupwork', 'manual', 'assessment-bank' if str(code)=='135' else 'assessment-manual', 'support', 'syllabuses', 'coordination'):
            for path in self._walk(course / name):
                yield path, course, 'Source PDF'
        if course.is_dir():
            for path in course.glob('*.pdf'):
                yield path, course, 'Source PDF'

    def catalog(self, code, tag=None):
        with self.desk.lock:
            module = self.desk.module(code)
            tag = tag or module.CONFIG['default_semester']
            term(tag)
            publishable = self._publishable_outputs(code, tag)
            documents, seen = [], set()
            for path, base, origin in self._candidates(code, tag, publishable):
                semesters = self._semesters(path, base)
                if not self._safe_file(path, base) or (semesters and tag not in semesters):
                    continue
                canonical = str(path.resolve())
                if canonical in seen:
                    continue
                seen.add(canonical)
                identity = hashlib.sha256((code + '\0' + canonical).encode('utf8')).hexdigest()[:32]
                stat = path.stat()
                output = publishable.get(canonical, {}) if origin == 'Published' else {}
                self.files[(code, identity)] = (path.absolute(), base.absolute())
                documents.append({
                    'id': identity, 'title': path.stem.replace('-', ' '),
                    'category': output.get('category') or ('Coordination' if any(part.lower()=='coordination' for part in path.parts) else 'Support' if any(part.lower()=='support material' for part in path.parts) else self.desk.material_category(self._kind(path))),
                    'kind': output.get('kind', self._kind(path)), 'path': canonical, 'filename': path.name,
                    'modified': datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                    'bytes': stat.st_size, 'origin': origin,
                    'semester': tag if tag in semesters else None,
                    'pdf_url': '/api/course-library/' + code + '/' + identity + '/pdf',
                })
            assignments = [
                {key: a.get(key) for key in ('id', 'title', 'kind', 'course', 'semester', 'number', 'updated')}
                for a in self.universal.assignments()
                if a.get('course') == code and a.get('semester') == tag
            ] if self.universal.available() else []
            return {'course': code, 'semester': tag, 'output_folder': str(self.desk.output_root(code)),
                    'documents': sorted(documents, key=lambda d: (d['kind'], d['filename'].lower())),
                    'assignments': assignments}

    def pdf(self, code, identity):
        self.desk.module(code)
        if not re.fullmatch('[a-f0-9]{32}', identity):
            raise ValueError('Choose a PDF from the course library.')
        with self.desk.lock:
            record = self.files.get((code, identity))
            if not record or not self._safe_file(*record):
                raise ValueError('Refresh the course library and choose an available PDF.')
            return record[0]

    def _preview(self, code, identity):
        path = self.pdf(code, identity)
        version = hash_file(path)
        folder = self.desk.temp / 'PreviewCache' / 'course-library' / identity / version
        metadata = folder / 'info.json'
        if metadata.is_file():
            info = json.loads(metadata.read_text(encoding='utf8'))
        else:
            info = {'id': identity, 'filename': path.name, 'version': version,
                    'pages': self.desk._pages(path)}
            save(metadata, info)
        return path, folder, info

    def info(self, code, identity):
        with self.preview_lock:
            return self._preview(code, identity)[2]

    def page(self, code, identity, page):
        with self.preview_lock:
            source, folder, info = self._preview(code, identity)
            if not re.fullmatch(r'[1-9]\d*', str(page)) or int(page) > info['pages']:
                raise ValueError('Choose a valid preview page.')
            page = int(page)
            target = folder / ('page-' + str(page) + '.png')
            if not target.is_file():
                executable = self.desk.tool('pdftoppm')
                subprocess.run([executable, '-f', str(page), '-l', str(page), '-scale-to', '1500',
                                '-singlefile', '-png', str(source), str(target.with_suffix(''))],
                               check=True, capture_output=True, timeout=45,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            return target
