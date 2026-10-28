"""Conservative exact algebra for grouping. No eval, CAS, or guessed domains.

Only bounded rational polynomials are accepted. An equation is normalized up to
a nonzero rational factor. Variable denominators/functions stay manual so a
cancelled denominator can never hide a domain restriction.
"""
import ast
from fractions import Fraction
import re


def _clean(text):
    if not isinstance(text,str) or len(text)>500:raise ValueError('Unsupported mathematical answer.')
    text=text.strip().replace('\u2212','-')
    for token in (r'\(',r'\)',r'\[',r'\]','$',r'\left',r'\right'):text=text.replace(token,'')
    for _ in range(8):
        new=re.sub(r'\\(?:d?frac|tfrac)\s*\{([^{}]+)\}\s*\{([^{}]+)\}',r'((\1)/(\2))',text)
        if new==text:break
        text=new
    text=text.replace(r'\cdot','*').replace(r'\times','*').replace('{','(').replace('}',')').replace('^','**')
    text=re.sub(r'\s+','',text)
    if not text or len(text)>800 or not re.fullmatch(r'[0-9a-zA-Z+*/().=\-]+',text):raise ValueError('Unsupported mathematical answer.')
    # Single-letter variable names; identifiers/functions and scientific notation
    # are deliberately not inferred. Multiplication is explicit after tokenizing.
    tokens=re.findall(r'\d+(?:\.\d*)?|\.\d+|[A-Za-z]|\*\*|[-+*/()=]',text)
    if ''.join(tokens)!=text or re.search(r'[A-Za-z]{2,}',text):raise ValueError('Use a bounded polynomial expression.')
    result=[]
    for token in tokens:
        if result and (re.fullmatch(r'[0-9.]+|[A-Za-z]|\)',result[-1])) and (re.fullmatch(r'[A-Za-z]|\(',token) or (result[-1]==')' and re.fullmatch(r'[0-9.]+',token))):result.append('*')
        result.append(token)
    return ''.join(result)


def _bounded(poly):
    poly={k:v for k,v in poly.items() if v}
    if len(poly)>120 or any(sum(p for _,p in k)>12 or v.numerator.bit_length()>1024 or v.denominator.bit_length()>1024 for k,v in poly.items()):raise ValueError('Mathematical answer is too complex.')
    return poly


def _add(a,b,sign=1):
    out=dict(a)
    for k,v in b.items():out[k]=out.get(k,0)+sign*v
    return _bounded(out)


def _mul(a,b):
    out={}
    if len(a)*len(b)>600:raise ValueError('Mathematical answer is too complex.')
    for ka,va in a.items():
        for kb,vb in b.items():
            powers=dict(ka)
            for name,power in kb:powers[name]=powers.get(name,0)+power
            key=tuple(sorted(powers.items()));out[key]=out.get(key,0)+va*vb
    return _bounded(out)


def _polynomial(text):
    try:tree=ast.parse(text,mode='eval')
    except (SyntaxError,ValueError,RecursionError):raise ValueError('Unsupported mathematical answer.') from None
    if len(list(ast.walk(tree)))>100:raise ValueError('Mathematical answer is too complex.')
    def visit(node):
        if isinstance(node,ast.Constant) and type(node.value) in (int,float):
            raw=ast.get_source_segment(text,node)
            if len(raw)>50:raise ValueError('Number is too large.')
            return _bounded({():Fraction(raw)})
        if isinstance(node,ast.Name) and re.fullmatch(r'[A-Za-z]',node.id):return {((node.id,1),):Fraction(1)}
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):
            return {k:v*(1 if isinstance(node.op,ast.UAdd) else -1) for k,v in visit(node.operand).items()}
        if isinstance(node,ast.BinOp):
            a,b=visit(node.left),visit(node.right)
            if isinstance(node.op,ast.Add):return _add(a,b)
            if isinstance(node.op,ast.Sub):return _add(a,b,-1)
            if isinstance(node.op,ast.Mult):return _mul(a,b)
            if isinstance(node.op,ast.Div):
                if set(b)!={()} or not b[()]:raise ValueError('Variable denominators need instructor review.')
                return _bounded({k:v/b[()] for k,v in a.items()})
            if isinstance(node.op,ast.Pow):
                exponent=b.get((),Fraction(0))
                if set(b)-{()} or exponent.denominator!=1 or not 0<=exponent<=8:raise ValueError('Unsupported exponent.')
                out={():Fraction(1)}
                for _ in range(int(exponent)):out=_mul(out,a)
                return out
        raise ValueError('Unsupported mathematical answer.')
    try:return visit(tree.body)
    except (ZeroDivisionError,OverflowError,RecursionError):raise ValueError('Unsupported mathematical answer.') from None


def canonical_math(text):
    text=_clean(text);parts=text.split('=')
    if len(parts)>2 or any(not p for p in parts):raise ValueError('Use one expression or one equation.')
    poly=_polynomial(parts[0]);equation=len(parts)==2
    if equation:
        poly=_add(poly,_polynomial(parts[1]),-1)
        # Do not merge tautologies/contradictions with general equations.
        if set(poly)<= {()}:raise ValueError('Degenerate equation needs review.')
        first=poly[sorted(poly)[0]];poly={k:v/first for k,v in poly.items()}
    return ('equation' if equation else 'expression',tuple((k,str(v)) for k,v in sorted(poly.items())))


def equivalent(left,right):
    return canonical_math(left)==canonical_math(right)
