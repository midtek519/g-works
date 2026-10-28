"""Fast private version-marker reading. No source page, image or OCR text is persisted."""
from pathlib import Path
import base64,hashlib,io,json,os,queue,re,subprocess,threading,time,unicodedata
from PIL import Image,ImageEnhance,ImageFilter,ImageOps
import pypdfium2 as pdfium

READER_VERSION='local-ocr-v2'
def _marker_values(text):
    return re.findall(r'\b(?:VERSION|VERSlON|VER\.?)\s*[:=.\-]*\s*[\(\[\{]?\s*([A-Za-z0-9_-]{1,30})\b',unicodedata.normalize('NFKC',text),re.I)

def marker_conflict(text):
    values={v.casefold() for v in _marker_values(text)}
    if len(values)>1:return True
    return bool(values and re.search(r'\b(?:or|and)\s+[A-Za-z0-9]|[/|]\s*[A-Za-z0-9]',text,re.I))

def canonical_label(text,labels):
    """Accept surrounding Version/punctuation, never a guessed or adjacent label."""
    if not isinstance(text,str) or len(text)>500:return ''
    allowed={unicodedata.normalize('NFKC',str(v)).casefold():str(v) for v in labels}
    text=unicodedata.normalize('NFKC',text).strip()
    # A readable Version marker has priority over unrelated text in an oversized box.
    explicit=_marker_values(text)
    if explicit:
        values=[allowed.get(value.casefold(),'') for value in explicit]
        if not values or not all(values) or len(set(values))!=1:return ''
        residual=re.sub(r'\b(?:VERSION|VERSlON|VER\.?)\s*[:=.\-]*\s*[\(\[\{]?\s*([A-Za-z0-9_-]{1,30})\b','',text,flags=re.I)
        residual=re.sub(r'\b(?:EXAM|PAGE)\b','',residual,flags=re.I)
        # After removing explicit markers, only page numbers and punctuation
        # may remain. A/B and A or B are not a single observed version.
        if any(character.isalpha() for character in residual):return ''
        if re.search(r'[/|]',residual) and len(explicit)<2:return ''
        return values[0]
    stripped=re.sub(r'^[\s\(\[\{<:;.,-]+|[\s\)\]\}>:;.,-]+$','',text)
    return allowed.get(stripped.casefold(),'')

def prepared_png(raw):
    with Image.open(io.BytesIO(raw)) as original:
        image=ImageOps.autocontrast(original.convert('L'))
        if image.height<90:
            scale=min(5,90/max(1,image.height));image=image.resize((round(image.width*scale),round(image.height*scale)),Image.Resampling.LANCZOS)
        image.thumbnail((2048,2048),Image.Resampling.LANCZOS)
        image=ImageOps.expand(image,border=12,fill=255)
        output=io.BytesIO();image.save(output,'PNG');return output.getvalue()

class WindowsOcr:
    """One bounded, cancellable local Windows OCR process for a whole batch."""
    def __init__(self,checkpoint=lambda *args:None):
        self.checkpoint=checkpoint;self.process=None;self.responses=queue.Queue();self.ready=False
        executable=Path(os.environ.get('WINDIR','C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
        if os.name!='nt' or not executable.is_file():return
        try:
            self.process=subprocess.Popen([str(executable),'-NoLogo','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(Path(__file__).with_suffix('.ps1'))],
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8',bufsize=1,creationflags=0x08000000)
            def receive():
                try:
                    for line in self.process.stdout:
                        if len(line)>2000000:break
                        try:self.responses.put(json.loads(line))
                        except ValueError:self.responses.put({})
                except (OSError,ValueError):pass
                finally:self.responses.put(None)
            threading.Thread(target=receive,daemon=True).start()
            self.ready=self._wait(8).get('ready') is True
        except (OSError,ValueError,TimeoutError):self.close()
    def _wait(self,seconds):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            self.checkpoint()
            try:
                value=self.responses.get(timeout=min(.1,max(.001,deadline-time.monotonic())))
                if value is None:raise ValueError('OCR helper stopped.')
                return value
            except queue.Empty:pass
        raise TimeoutError('OCR metadata request timed out.')
    def read(self,raw):
        if not self.ready:return ''
        try:
            self.checkpoint()
            self.process.stdin.write(json.dumps({'image':base64.b64encode(prepared_png(raw)).decode('ascii')})+'\n');self.process.stdin.flush()
            result=self._wait(5)
            return result.get('text','') if result.get('ok') else ''
        except (OSError,ValueError,TimeoutError):self.close();return ''
    def close(self):
        if self.process is not None:
            try:
                if self.process.poll() is None:self.process.terminate()
                self.process.wait(timeout=2)
            except (OSError,subprocess.TimeoutExpired):
                try:self.process.kill()
                except OSError:pass
            for stream in (self.process.stdin,self.process.stdout):
                try:stream.close()
                except (OSError,AttributeError):pass
        self.ready=False
    def __enter__(self):return self
    def __exit__(self,*args):self.close()

class MarkerDocument:
    """One PDF handle/page, with the Store's shared PDFium lock."""
    def __init__(self,raw,lock=None):
        self.lock=lock or threading.RLock();self.page_key=None;self.image=None
        with self.lock:self.doc=pdfium.PdfDocument(raw)
    def crops(self,page,rotation,regions):
        with self.lock:
            if self.page_key!=(page,rotation):
                if self.image is not None:self.image.close()
                p=self.doc[page]
                try:
                    bitmap=p.render(scale=3,rotation=rotation)
                    try:self.image=bitmap.to_pil().copy()
                    finally:bitmap.close()
                finally:p.close()
                self.page_key=(page,rotation)
        # PIL encoding and OCR waits do not hold the Store/PDFium lock.
        for rect in regions:
            w,h=self.image.size;image=self.image.crop((int(rect[0]*w),int(rect[1]*h),round(rect[2]*w),round(rect[3]*h)))
            try:
                output=io.BytesIO();image.convert('RGB').save(output,'PNG');yield output.getvalue()
            finally:image.close()
    def text(self,page,rotation,rect):
        if rotation:return ''
        with self.lock:
            p=self.doc[page]
            try:
                if p.get_rotation():return ''
                w,h=p.get_size();text=p.get_textpage()
                try:return text.get_text_bounded(left=rect[0]*w,bottom=(1-rect[3])*h,right=rect[2]*w,top=(1-rect[1])*h)
                finally:text.close()
            finally:p.close()
    def close(self):
        with self.lock:
            if self.image is not None:self.image.close();self.image=None
            self.doc.close()

class VersionReader:
    def __init__(self,checkpoint=lambda *args:None):
        self.checkpoint=checkpoint;self.ocr=None;self.documents={};self.rendered=0;self.ocr_calls=0;self.text_hits=0
    def document(self,key,raw):
        if key not in self.documents:
            for document in self.documents.values():document.close()
            self.documents.clear();self.documents[key]=MarkerDocument(raw,getattr(self,'pdf_lock',None))
        return self.documents[key]
    def read(self,key,raw,page_start,rotation,regions,labels):
        doc=self.document(key,raw);seen=[];images=[];conflict=False;unknown_marker=False
        for region in regions:
            self.checkpoint()
            page=page_start+region['page']-1;rect=region['rect']
            text=doc.text(page,rotation,rect);label=canonical_label(text,labels)
            if label:self.text_hits+=1;seen.append(label);continue
            crop=next(doc.crops(page,rotation,[rect]));images.append(crop);self.rendered+=1
            if self.ocr is None:self.ocr=WindowsOcr(self.checkpoint)
            self.ocr_calls+=1;text=self.ocr.read(crop);label=canonical_label(text,labels)
            values={v.casefold() for v in _marker_values(text)}
            if marker_conflict(text):conflict=True
            if values and not label:unknown_marker=True
            if label:seen.append(label)
        # Scanner translation can clip a marker against an edge of the saved
        # blank-exam box. A small surrounding area is examined by deterministic
        # local OCR only. Expanded crops are NEVER passed to the vision model.
        if not seen and not conflict:
            for region in regions:
                self.checkpoint()
                x0,y0,x1,y1=region['rect'];dx=min(.03,(x1-x0)*.3);dy=min(.03,(y1-y0)*.9)
                padded=[max(0,x0-dx),max(0,y0-dy),min(1,x1+dx),min(1,y1+dy)]
                crop=next(doc.crops(page_start+region['page']-1,rotation,[padded]))
                if self.ocr is None:self.ocr=WindowsOcr(self.checkpoint)
                self.ocr_calls+=1;text=self.ocr.read(crop)
                # Outside the approved box, require an explicit Version marker;
                # an isolated nearby letter can never supply a version.
                label=canonical_label(text,labels) if _marker_values(text) else ''
                values={v.casefold() for v in _marker_values(text)}
                if marker_conflict(text):conflict=True
                candidates=[label] if label else []
                if not label and not conflict:
                    # Faint/halftone scan backgrounds can confuse Windows OCR.
                    # Retry two bounded contrast masks, never substitute a label.
                    with Image.open(io.BytesIO(crop)) as source:
                        gray=source.convert('L')
                        try:
                            for threshold in (120,160):
                                binary=gray.point(lambda value:0 if value<threshold else 255)
                                try:
                                    output=io.BytesIO();binary.save(output,'PNG')
                                    self.ocr_calls+=1;retry=self.ocr.read(output.getvalue())
                                finally:binary.close()
                                value=canonical_label(retry,labels) if _marker_values(retry) else ''
                                if marker_conflict(retry):conflict=True
                                if value:candidates.append(value)
                        finally:gray.close()
                if len(set(candidates))>1:conflict=True
                if candidates and not conflict:seen.append(candidates[0]);unknown_marker=False
        unique=set(seen);conflict=conflict or len(unique)>1 or bool(unique and unknown_marker)
        if len(unique)==1 and not conflict:return {'versionLabel':seen[0],'needsReview':False,'reason':'Printed version read locally.','method':'ocr' if images else 'pdf-text'},images
        # The large model sees every approved marker region, including a region
        # whose PDF text was readable. It never receives a whole page.
        images=[]
        for region in regions:images.extend(doc.crops(page_start+region['page']-1,rotation,[region['rect']]))
        return {'versionLabel':'','needsReview':True,'reason':'Conflicting version markers.' if conflict else 'Version marker needs review.','method':'ocr','conflict':conflict},images
    def close(self):
        if self.ocr:self.ocr.close()
        for doc in self.documents.values():doc.close()
        self.documents.clear()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
