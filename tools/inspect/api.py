import sys, os, struct, collections
sys.path.insert(0, os.path.dirname(__file__))
from swf import *
blocks=[('',b['data']) for b in extract_blocks(SWF(sys.argv[1]))]
calls=collections.Counter(); meth=collections.Counter(); members=collections.Counter(); gvars=collections.Counter()
for ctx,b in blocks:
    acts=parse_actions(b); pool=[]; last=[]
    for a in acts:
        if a.name=='ConstantPool': pool=[x.decode('latin1') for x in a.args]
        if a.name=='Push':
            last=[]
            for t,v in a.args:
                if t=='cpool': last.append(pool[v] if v<len(pool) else '?')
                elif t=='str': last.append(v.decode('latin1'))
                else: last.append(None)
        elif a.name in('CallMethod','CallFunction','GetMember','SetMember','GetVariable','SetVariable','NewObject','NewMethod'):
            if a.name in('SetMember','SetVariable'):
                # name is 2nd from top; approximate: first string of last push
                nm=next((x for x in last if isinstance(x,str)),None)
            else:
                nm=last[-1] if last else None
            if isinstance(nm,str):
                {'CallMethod':meth,'CallFunction':calls,'NewObject':calls,'NewMethod':meth,'GetMember':members,'SetMember':members}.get(a.name,gvars)[nm]+=1
            last=[]
        else: last=[]
print('CALLFUNCTION/NEW:',dict(calls))
print('CALLMETHOD:',dict(meth))
print('MEMBERS starting with _ or known:',{k:v for k,v in members.items() if k.startswith('_') or k in('length','prototype','push')})
print('GVARS _*:',{k:v for k,v in gvars.items() if k.startswith('_') or k in ('Math','Key','Mouse','Sound','Color','Array','Object','String','Number','Date','Selection')})
