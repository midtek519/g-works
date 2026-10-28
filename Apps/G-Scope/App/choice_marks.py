"""Locate printed choice boxes and recognize only strong added-ink marks.

Pillow-only, local and answer-key blind. Hints are relative to the approved
question crop. Ambiguous, missing, erased or conflicting evidence stays unread.
"""
from statistics import median
import math
from PIL import Image,ImageDraw,ImageChops,ImageFilter

READER='local-choice-marks-1'

def _binary(image):
    gray=image.convert('L');hist=gray.histogram();target=sum(hist)*.95;count=0;paper=255
    for value,n in enumerate(hist):
        count+=n
        if count>=target:paper=value;break
    threshold=max(45,min(190,int(paper*.72)))
    result=gray.point(lambda x:1 if x<threshold else 0).tobytes();gray.close()
    return result

def _rect(rect,width,height):
    x0=max(0,int(math.floor(rect[0])));y0=max(0,int(math.floor(rect[1])))
    x1=min(width,int(math.ceil(rect[2])));y1=min(height,int(math.ceil(rect[3])))
    return (x0,y0,x1,y1) if x1-x0>=4 and y1-y0>=4 else None

def _find_box(image,expected,*,all_boxes=False,search=None):
    ew=expected[2]-expected[0];eh=expected[3]-expected[1]
    if ew<5 or eh<7:return None
    roi=_rect(search or (expected[0]-ew*1.5,expected[1]-eh*1.5,expected[2]+ew*1.5,expected[3]+eh*1.5),*image.size)
    if not roi:return None
    cut=image.crop(roi);w,h=cut.size;mask=bytearray(_binary(cut));cut.close();original=bytes(mask);candidates=[]
    for start,pixel in enumerate(mask):
        if not pixel:continue
        mask[start]=0;pending=[start];xmin=xmax=start%w;ymin=ymax=start//w;area=0
        while pending:
            index=pending.pop();x=index%w;y=index//w;area+=1
            xmin=min(xmin,x);xmax=max(xmax,x);ymin=min(ymin,y);ymax=max(ymax,y)
            for other in (index-1 if x else -1,index+1 if x+1<w else -1,index-w if y else -1,index+w if y+1<h else -1):
                if other>=0 and mask[other]:mask[other]=0;pending.append(other)
        bw=xmax-xmin+1;bh=ymax-ymin+1
        if bw<max(8,ew*.35) or bh<max(10,eh*.35) or bw>ew*1.9 or bh>eh*1.9 or area<2*(bw+bh)*.55:continue
        band=max(2,int(min(bw,bh)*.12))
        def row_edge(top,bottom):return sum(any(original[yy*w+xx] for yy in range(top,bottom)) for xx in range(xmin,xmax+1))/bw
        def col_edge(left,right):return sum(any(original[yy*w+xx] for xx in range(left,right)) for yy in range(ymin,ymax+1))/bh
        edges=(row_edge(ymin,min(ymax+1,ymin+band)),row_edge(max(ymin,ymax-band+1),ymax+1),col_edge(xmin,min(xmax+1,xmin+band)),col_edge(max(xmin,xmax-band+1),xmax+1))
        if min(edges)<.72:continue
        box=(xmin+roi[0],ymin+roi[1],xmax+roi[0]+1,ymax+roi[1]+1)
        dx=((box[0]+box[2])-(expected[0]+expected[2]))/2;dy=((box[1]+box[3])-(expected[1]+expected[3]))/2
        score=(dx/ew)**2+(dy/eh)**2+.4*(math.log(bw/ew)**2+math.log(bh/eh)**2)
        candidates.append((score,box))
    if all_boxes:return [box for _,box in candidates]
    return min(candidates,key=lambda x:x[0])[1] if candidates else None

def _center(box):return ((box[0]+box[2])/2,(box[1]+box[3])/2)
def _frame_supported(image,box):
    cut=image.crop(box);w,h=cut.size;mask=_binary(cut);cut.close();band=max(2,round(min(w,h)*.15))
    edges=[sum(any(mask[y*w+x] for y in range(0,min(h,band))) for x in range(w))/w,
           sum(any(mask[y*w+x] for y in range(max(0,h-band),h)) for x in range(w))/w,
           sum(any(mask[y*w+x] for x in range(0,min(w,band))) for y in range(h))/h,
           sum(any(mask[y*w+x] for x in range(max(0,w-band),w)) for y in range(h))/h]
    return min(edges)>=.50

def locate(blank,student,hints):
    result={'reader':READER,'recognition':None,'reason':'box_layout_not_found','matched':0,'blankBoxes':[],'studentBoxes':[],'measurements':[]}
    if not 2<=len(hints)<=26:return result
    if blank.width*blank.height>8_000_000 or student.width*student.height>8_000_000:return result
    blank_boxes=[]
    for hint in hints:
        r=hint['rect']
        if len(r)!=4 or not all(isinstance(x,(int,float)) and math.isfinite(x) for x in r) or not (0<=r[0]<r[2]<=1 and 0<=r[1]<r[3]<=1):return result
        box=_find_box(blank,(r[0]*blank.width,r[1]*blank.height,r[2]*blank.width,r[3]*blank.height))
        if not box or box in blank_boxes:return result
        blank_boxes.append(box)
    result['blankBoxes']=blank_boxes
    kx=student.width/blank.width;ky=student.height/blank.height
    bw=median(b[2]-b[0] for b in blank_boxes)*kx;bh=median(b[3]-b[1] for b in blank_boxes)*ky
    search=(min(b[0] for b in blank_boxes)*kx-bw*2,min(b[1] for b in blank_boxes)*ky-bh*2,max(b[2] for b in blank_boxes)*kx+bw*2,max(b[3] for b in blank_boxes)*ky+bh*2)
    expected=(blank_boxes[0][0]*kx,blank_boxes[0][1]*ky,blank_boxes[0][0]*kx+bw,blank_boxes[0][1]*ky+bh)
    candidates=_find_box(student,expected,all_boxes=True,search=search) or []
    if not 2<=len(candidates)<=60:return result
    centers=[_center(b) for b in blank_boxes];spread=[max(c[i] for c in centers)-min(c[i] for c in centers) for i in (0,1)];axis=1 if spread[1]>=spread[0] else 0
    candidates.sort(key=lambda box:_center(box)[axis])
    template_pairs=[(i,j) for i in range(len(centers)) for j in range(i+1,len(centers)) if abs(centers[j][axis]-centers[i][axis])>=max(8,spread[axis]*.45)]
    template_pairs.sort(key=lambda pair:-abs(centers[pair[1]][axis]-centers[pair[0]][axis]));template_pairs=template_pairs[:12]
    required=2;best=None
    # Joint relative-layout matching avoids assigning labels by fixed page positions.
    # A hypothesis must explain the complete box pattern, including obscured boxes.
    for i,j in template_pairs:
        ca,cb=centers[i],centers[j]
        if cb[axis]<ca[axis]:ca,cb=cb,ca;i,j=j,i
        for u in range(len(candidates)):
            for v in range(u+1,len(candidates)):
                a,b=candidates[u],candidates[v];ta,tb=_center(a),_center(b)
                if axis==1:
                    sy=(tb[1]-ta[1])/(cb[1]-ca[1]);sx=median(((a[2]-a[0])/(blank_boxes[i][2]-blank_boxes[i][0]),(b[2]-b[0])/(blank_boxes[j][2]-blank_boxes[j][0])))
                    shearx=((tb[0]-sx*cb[0])-(ta[0]-sx*ca[0]))/(cb[1]-ca[1]);sheary=0;dx=ta[0]-sx*ca[0]-shearx*ca[1];dy=ta[1]-sy*ca[1]
                else:
                    sx=(tb[0]-ta[0])/(cb[0]-ca[0]);sy=median(((a[3]-a[1])/(blank_boxes[i][3]-blank_boxes[i][1]),(b[3]-b[1])/(blank_boxes[j][3]-blank_boxes[j][1])))
                    sheary=((tb[1]-sy*cb[1])-(ta[1]-sy*ca[1]))/(cb[0]-ca[0]);shearx=0;dx=ta[0]-sx*ca[0];dy=ta[1]-sy*ca[1]-sheary*ca[0]
                if not (.72*kx<=sx<=1.35*kx and .72*ky<=sy<=1.35*ky and abs(shearx)<.12 and abs(sheary)<.12):continue
                predicted=[]
                for box in blank_boxes:
                    x,y=_center(box);cx=sx*x+shearx*y+dx;cy=sy*y+sheary*x+dy;w=(box[2]-box[0])*sx;h=(box[3]-box[1])*sy
                    predicted.append((cx-w/2,cy-h/2,cx+w/2,cy+h/2))
                distances=[]
                for n,p in enumerate(predicted):
                    pc=_center(p);pw=p[2]-p[0];ph=p[3]-p[1]
                    for k,candidate in enumerate(candidates):
                        cc=_center(candidate);cw=candidate[2]-candidate[0];ch=candidate[3]-candidate[1]
                        if abs(pc[0]-cc[0])<=max(4,pw*.32) and abs(pc[1]-cc[1])<=max(4,ph*.32) and .7*pw<=cw<=1.4*pw and .7*ph<=ch<=1.4*ph:
                            distances.append((((pc[0]-cc[0])/pw)**2+((pc[1]-cc[1])/ph)**2,n,k))
                matches={};used=set();error=0
                for distance,n,k in sorted(distances):
                    if n not in matches and k not in used:matches[n]=k;used.add(k);error+=distance
                if len(matches)<required:continue
                aligned=[];valid=True
                for n,p in enumerate(predicted):
                    box=candidates[matches[n]] if n in matches else p;bounded=_rect(box,*student.size)
                    if not bounded or min(box)<0 or box[2]>student.width or box[3]>student.height or (n not in matches and not _frame_supported(student,bounded)):
                        valid=False;break
                    aligned.append(bounded)
                if not valid:continue
                score=(-len(matches),error)
                if best is None or score<best[0]:best=(score,aligned,len(matches))
    if best is None:return result
    result.update(studentBoxes=best[1],matched=best[2],reason='aligned')
    return result

def _density(image,box):
    w=box[2]-box[0];h=box[3]-box[1];px=max(2,round(w*.14));py=max(2,round(h*.12))
    inner=_rect((box[0]+px,box[1]+py,box[2]-px,box[3]-py),*image.size)
    if not inner:return None
    cut=image.crop(inner);mask=_binary(cut);cut.close();return sum(mask)/len(mask)

def _novel_ink(blank,student,a,b):
    masks=[]
    try:
        for image,box in ((blank,a),(student,b)):
            w=box[2]-box[0];h=box[3]-box[1]
            rect=_rect((box[0]-w*.25,box[1]-h*.08,box[2]+w*.25,box[3]+h*.08),*image.size)
            cut=image.crop(rect);scaled=cut.resize((96,96),Image.Resampling.BILINEAR);cut.close()
            mask=Image.frombytes('L',scaled.size,bytes(255*x for x in _binary(scaled)));scaled.close();masks.append(mask)
        tolerant=masks[0].filter(ImageFilter.MaxFilter(5))
        added=ImageChops.subtract(masks[1],tolerant);tolerant.close();count=added.histogram()[255];added.close()
        return count/(96*96)
    finally:
        for mask in masks:mask.close()

def analyze(blank,student,hints,*,multiple=False):
    result=locate(blank,student,hints)
    if not result['studentBoxes']:return result
    selected=[];ambiguous=False
    for hint,a,b in zip(hints,result['blankBoxes'],result['studentBoxes']):
        before=_density(blank,a);after=_density(student,b)
        if before is None or after is None:return {**result,'reason':'box_interior_too_small'}
        delta=after-before;novel=_novel_ink(blank,student,a,b)
        result['measurements'].append({'label':hint['label'],'blankInk':round(before,4),'studentInk':round(after,4),'addedInk':round(delta,4),'newInkBeyondPrint':round(novel,4)})
        if delta>=.065 and novel>=.02:selected.append(hint['label'])
        elif abs(delta)>.055 or novel>.035:ambiguous=True
    if ambiguous:result['reason']='ambiguous_added_ink'
    elif not selected:result['reason']='no_strong_mark_in_boxes'
    elif not multiple and len(selected)!=1:result['reason']='multiple_marks_need_review'
    else:result.update(recognition={'state':'clear','selected':selected},reason='clear_added_ink')
    return result

def comparison_sheet(blank,student,hints,result):
    rows=[]
    try:
        for i,hint in enumerate(hints):
            r=hint['rect'];a=result.get('blankBoxes',[]);b=result.get('studentBoxes',[])
            br=a[i] if len(a)==len(hints) else (r[0]*blank.width,r[1]*blank.height,r[2]*blank.width,r[3]*blank.height)
            sr=b[i] if len(b)==len(hints) else (r[0]*student.width,r[1]*student.height,r[2]*student.width,r[3]*student.height)
            def padded(image,rect):
                w=rect[2]-rect[0];h=rect[3]-rect[1];box=_rect((rect[0]-w*.25,rect[1]-h*.20,rect[2]+w*.25,rect[3]+h*.20),*image.size)
                return image.crop(box) if box else Image.new('RGB',(20,20),'white')
            rows.append((hint['label'],padded(blank,br),padded(student,sr)))
        scale=2;cell=max(90,max(max(a.width,b.width) for _,a,b in rows)*scale);heights=[max(50,max(a.height,b.height)*scale) for _,a,b in rows]
        sheet=Image.new('RGB',(50+2*cell+25,30+sum(h+16 for h in heights)),'white');draw=ImageDraw.Draw(sheet);draw.text((50,8),'Blank',fill='black');draw.text((65+cell,8),'Student',fill='black');y=30
        for (label,a,b),height in zip(rows,heights):
            draw.text((8,y+8),label,fill='black')
            for image,x in ((a,50),(b,65+cell)):
                enlarged=image.resize((image.width*scale,image.height*scale),Image.Resampling.LANCZOS);sheet.paste(enlarged,(x,y));enlarged.close()
            y+=height+16
        return sheet
    finally:
        for _,a,b in rows:a.close();b.close()
