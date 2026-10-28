"""Conservative local suggestions, never inferred grades or identities."""
import re
COURSE=re.compile(r'\b(?:math(?:ematics)?\s*[: -]?\s*|(?:01[: -])?640[: -])([1-5]\d{2})\b',re.I)
TERM=re.compile(r'\b(Spring|Fall|Autumn|Summer|Winter)\s+(?:(?:semester|of|in)\s+)*(19\d{2}|20\d{2})\b',re.I)
RELATION=re.compile(r'\b(?:I\s+(?:first\s+)?taught|my\s+(?:\w+\s+){0,4}(?:class|course|student)|(?:was|were)\s+(?:a\s+)?student|took\s+(?:my|the)|enrolled)\b',re.I)
def suggestions(value):
    result=set()
    for paragraph in re.split(r'\n\s*\n',value):
        if len(paragraph)>3000:chunks=re.split(r'(?<=[.!?])\s+',paragraph)
        else:chunks=[paragraph,*re.split(r'(?<=[.!?])\s+',paragraph)]
        for chunk in chunks:
            if not RELATION.search(chunk):continue
            courses=set(COURSE.findall(chunk));terms={(m[1].lower(),m[2])for m in TERM.finditer(chunk)}
            if len(courses)!=1 or len(terms)!=1:continue
            term,year=next(iter(terms));code={'spring':'Sp','fall':'Fa','autumn':'Fa','summer':'Su','winter':'Wi'}[term]+year[-2:]
            result.add(('Math '+next(iter(courses)),code))
    return [{'course':c,'semester':s,'grade':'','average':None}for c,s in sorted(result)]
