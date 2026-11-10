import sys, struct, collections
sys.path.insert(0, __import__('os').path.dirname(__file__))
from swf import *
s=SWF(sys.argv[1])
blocks=[]   # (ctx, bytes)
feat=collections.Counter()
def clipactions(b, ctx):
    r=Bits(b); r.u16()
    allf=r.u16() if s.version<=5 else r.u32()
    while True:
        fl=r.u16() if s.version<=5 else r.u32()
        if fl==0: break
        ln=r.u32()
        if s.version>5 and fl&0x20000: r.u8(); ln-=1
        blocks.append((f'{ctx} clipevent 0x{fl:x}', r.bytes(ln)))
def walk(tags, ctx):
    frame=0
    for t in tags:
        feat[t.code]+=1
        if t.code==1: frame+=1
        elif t.code in (12,):
            blocks.append((f'{ctx} frame{frame}', t.data))
        elif t.code==39:
            sid=struct.unpack_from('<H',t.data)[0]
            walk(read_tags(t.data,4,len(t.data)), f'sprite{sid}')
        elif t.code==26:
            r=Bits(t.data); fl=r.u8(); depth=r.u16()
            if fl&2: cid=r.u16()
            if fl&4: r.matrix()
            if fl&8: r.cxform(True)
            if fl&16: r.u16()
            if fl&32: nm=r.cstr()
            if fl&64: r.u16()
            if fl&128: clipactions(t.data[r.p:], f'{ctx} f{frame} depth{depth}')
        elif t.code==34:
            bid=struct.unpack_from('<H',t.data)[0]
            off=struct.unpack_from('<H',t.data,3)[0]
            if off:
                p=3+off
                while True:
                    off=struct.unpack_from('<H',t.data,p)[0]
                    cond=struct.unpack_from('<H',t.data,p+2)[0]
                    end=p+off if off else len(t.data)
                    blocks.append((f'button{bid} cond 0x{cond:x}', t.data[p+4:end]))
                    if not off: break
                    p+=off
        elif t.code==7:
            print('DefineButton1!')
walk(s.tags,'root')
ops=collections.Counter(); total=0
for ctx,b in blocks:
    a=parse_actions(b); total+=len(a)
    for x in a: ops[x.name]+=1
print('blocks',len(blocks),'actions',total)
for k,v in sorted(ops.items(),key=lambda x:-x[1]): print(f'  {k}:{v}')
if len(sys.argv)>2:
    with open(sys.argv[2],'w',encoding='utf-8') as f:
        for ctx,b in blocks:
            f.write(f'=== {ctx}\n')
            for x in parse_actions(b):
                a=x.args
                if x.name=='Push': a=[(t,v.decode('latin1') if isinstance(v,bytes) else v) for t,v in a]
                elif isinstance(a,bytes): a=a.decode('latin1')
                elif isinstance(a,list): a=[v.decode('latin1') if isinstance(v,bytes) else v for v in a]
                f.write(f'  {x.off:5d} {x.name} {a if a is not None else ""}\n')
