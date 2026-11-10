"""Minimal SWF (v5-era) parser: tags, sprites, actions, shapes, etc."""
import struct, zlib

class Bits:
    def __init__(s, d, p=0): s.d=d; s.p=p; s.b=0; s.n=0
    def ub(s, n):
        v=0
        for _ in range(n):
            if s.n==0: s.b=s.d[s.p]; s.p+=1; s.n=8
            s.n-=1; v=(v<<1)|((s.b>>s.n)&1)
        return v
    def sb(s, n):
        v=s.ub(n)
        if n and v&(1<<(n-1)): v-=1<<n
        return v
    def fb(s, n): return s.sb(n)/65536.0
    def align(s): s.n=0
    def u8(s): s.align(); v=s.d[s.p]; s.p+=1; return v
    def u16(s): s.align(); v=struct.unpack_from('<H',s.d,s.p)[0]; s.p+=2; return v
    def s16(s): s.align(); v=struct.unpack_from('<h',s.d,s.p)[0]; s.p+=2; return v
    def u32(s): s.align(); v=struct.unpack_from('<I',s.d,s.p)[0]; s.p+=4; return v
    def f16(s): return s.s16()/256.0
    def bytes(s,n): s.align(); v=s.d[s.p:s.p+n]; s.p+=n; return v
    def cstr(s):
        s.align(); e=s.d.index(b'\0',s.p); v=s.d[s.p:e]; s.p=e+1; return v
    def rect(s):
        s.align(); n=s.ub(5); r=[s.sb(n) for _ in range(4)]; s.align(); return r
    def matrix(s):
        s.align(); a=d=1.0; b=c=0.0
        if s.ub(1): n=s.ub(5); a=s.fb(n); d=s.fb(n)
        if s.ub(1): n=s.ub(5); b=s.fb(n); c=s.fb(n)
        n=s.ub(5); tx=s.sb(n); ty=s.sb(n); s.align()
        return (a,b,c,d,tx,ty)
    def cxform(s, alpha):
        s.align(); ha=s.ub(1); hm=s.ub(1); n=s.ub(4)
        m=[256,256,256,256]; a=[0,0,0,0]
        k=4 if alpha else 3
        if hm: m=[s.sb(n) for _ in range(k)]+([256] if not alpha else [])
        if ha: a=[s.sb(n) for _ in range(k)]+([0] if not alpha else [])
        s.align(); return (tuple(m),tuple(a))
    def rgb(s): return (s.u8(),s.u8(),s.u8(),255)
    def rgba(s): return (s.u8(),s.u8(),s.u8(),s.u8())

class Tag:
    def __init__(s,code,data,pos): s.code=code; s.data=data; s.pos=pos
    def __repr__(s): return f'Tag({s.code},{len(s.data)})'

def read_tags(d, p, end):
    tags=[]
    while p<end:
        h=struct.unpack_from('<H',d,p)[0]; p+=2
        c=h>>6; l=h&63
        if l==63: l=struct.unpack_from('<I',d,p)[0]; p+=4
        tags.append(Tag(c,d[p:p+l],p)); p+=l
        if c==0: break
    return tags

class SWF:
    def __init__(s, path):
        d=open(path,'rb').read()
        if d[:3]==b'CWS': d=d[:8]+zlib.decompress(d[8:])
        s.version=d[3]
        b=Bits(d,8); s.rect=b.rect(); s.rate=b.u16()/256.0; s.frames=b.u16()
        s.tags=read_tags(d,b.p,len(d))
        s.raw=d

# ---------------- AVM1 ----------------
ACTIONS={0x04:'NextFrame',0x05:'PrevFrame',0x06:'Play',0x07:'Stop',0x08:'ToggleQuality',0x09:'StopSounds',
0x0A:'Add',0x0B:'Subtract',0x0C:'Multiply',0x0D:'Divide',0x0E:'Equals',0x0F:'Less',0x10:'And',0x11:'Or',0x12:'Not',
0x13:'StringEquals',0x14:'StringLength',0x15:'StringExtract',0x17:'Pop',0x18:'ToInteger',0x1C:'GetVariable',0x1D:'SetVariable',
0x20:'SetTarget2',0x21:'StringAdd',0x22:'GetProperty',0x23:'SetProperty',0x24:'CloneSprite',0x25:'RemoveSprite',0x26:'Trace',
0x27:'StartDrag',0x28:'EndDrag',0x29:'StringLess',0x2A:'Throw',0x2B:'CastOp',0x2C:'ImplementsOp',0x30:'RandomNumber',
0x31:'MBStringLength',0x32:'CharToAscii',0x33:'AsciiToChar',0x34:'GetTime',0x35:'MBStringExtract',0x36:'MBCharToAscii',0x37:'MBAsciiToChar',
0x3A:'Delete',0x3B:'Delete2',0x3C:'DefineLocal',0x3D:'CallFunction',0x3E:'Return',0x3F:'Modulo',0x40:'NewObject',0x41:'DefineLocal2',
0x42:'InitArray',0x43:'InitObject',0x44:'TypeOf',0x45:'TargetPath',0x46:'Enumerate',0x47:'Add2',0x48:'Less2',0x49:'Equals2',
0x4A:'ToNumber',0x4B:'ToString',0x4C:'PushDuplicate',0x4D:'StackSwap',0x4E:'GetMember',0x4F:'SetMember',0x50:'Increment',
0x51:'Decrement',0x52:'CallMethod',0x53:'NewMethod',0x54:'InstanceOf',0x55:'Enumerate2',0x60:'BitAnd',0x61:'BitOr',0x62:'BitXor',
0x63:'BitLShift',0x64:'BitRShift',0x65:'BitURShift',0x66:'StrictEquals',0x67:'Greater',0x68:'StringGreater',0x69:'Extends',
0x81:'GotoFrame',0x83:'GetURL',0x87:'StoreRegister',0x88:'ConstantPool',0x8A:'WaitForFrame',0x8B:'SetTarget',0x8C:'GoToLabel',
0x8D:'WaitForFrame2',0x8E:'DefineFunction2',0x8F:'Try',0x94:'With',0x96:'Push',0x99:'Jump',0x9A:'GetURL2',0x9B:'DefineFunction',
0x9D:'If',0x9E:'Call',0x9F:'GotoFrame2'}

class Act:
    __slots__=('off','code','name','args','size','end')
    def __init__(s,off,code,args,size):
        s.off=off; s.code=code; s.name=ACTIONS.get(code,'0x%02X'%code); s.args=args; s.size=size; s.end=off+size
    def __repr__(s): return f'{s.off:5d} {s.name} {s.args if s.args is not None else ""}'

def parse_push(b, pool):
    vals=[]; r=Bits(b)
    while r.p<len(b):
        t=r.u8()
        if t==0: vals.append(('str',r.cstr()))
        elif t==1: vals.append(('num',struct.unpack_from('<f',b,r.p)[0])); r.p+=4
        elif t==2: vals.append(('null',None))
        elif t==3: vals.append(('undef',None))
        elif t==4: vals.append(('reg',r.u8()))
        elif t==5: vals.append(('bool',bool(r.u8())))
        elif t==6:
            lo,hi=struct.unpack_from('<II',b,r.p); r.p+=8
            vals.append(('num',struct.unpack('<d',struct.pack('<II',hi,lo))[0]))
        elif t==7: vals.append(('num',float(struct.unpack_from('<i',b,r.p)[0]))); r.p+=4
        elif t==8: vals.append(('cpool',r.u8()))
        elif t==9: vals.append(('cpool',r.u16()))
        else: raise ValueError('push type %d'%t)
    return vals

def parse_actions(d):
    """Linear decode of an action stream. Returns list of Act (offsets relative to start)."""
    out=[]; p=0
    while p<len(d):
        c=d[p]; off=p; p+=1
        if c==0: out.append(Act(off,0,None,1)); break
        args=None; ln=0
        if c>=0x80:
            ln=struct.unpack_from('<H',d,p)[0]; p+=2
            b=d[p:p+ln]; r=Bits(b)
            if c==0x81: args=r.u16()
            elif c==0x83: u=r.cstr(); args=(u,r.cstr())
            elif c==0x87: args=r.u8()
            elif c==0x88:
                n=r.u16(); args=[r.cstr() for _ in range(n)]
            elif c==0x8A: args=(r.u16(),r.u8())
            elif c==0x8B: args=r.cstr()
            elif c==0x8C: args=r.cstr()
            elif c==0x8D: args=r.u8()
            elif c==0x94: args=r.u16()
            elif c==0x96: args=parse_push(b,None)
            elif c in (0x99,0x9D): args=struct.unpack('<h',b[:2])[0]
            elif c==0x9A: args=r.u8()
            elif c==0x9B:
                name=r.cstr(); n=r.u16(); ps=[r.cstr() for _ in range(n)]; cs=r.u16()
                args=(name,ps,cs)
            elif c==0x8E:
                name=r.cstr(); n=r.u16(); rc=r.u8(); fl=r.u16(); ps=[]
                for _ in range(n): reg=r.u8(); ps.append((reg,r.cstr()))
                cs=r.u16(); args=(name,ps,cs,rc,fl)
            elif c==0x9F:
                f=r.u8(); args=(f, r.u16() if f&2 else 0)
            elif c==0x8F:
                fl=r.u8(); ts=r.u16(); cs=r.u16(); fs=r.u16()
                nm=r.u8() if fl&4 else r.cstr()
                args=(fl,ts,cs,fs,nm)
            else: args=b
            p+=ln
        out.append(Act(off,c,args,p-off))
    return out

def extract_blocks(s):
    """All action blocks: list of dict(kind, owner, frame, depth, event, cond, data)."""
    blocks=[]
    def clipactions(b, owner, frame, depth):
        r=Bits(b); r.u16()
        r.u16() if s.version<=5 else r.u32()
        while True:
            fl=r.u16() if s.version<=5 else r.u32()
            if fl==0: break
            ln=r.u32()
            blocks.append(dict(kind='clip',owner=owner,frame=frame,depth=depth,event=fl,data=r.bytes(ln)))
    def walk(tags, owner):
        frame=0
        for t in tags:
            if t.code==1: frame+=1
            elif t.code==12: blocks.append(dict(kind='frame',owner=owner,frame=frame,data=t.data,tagpos=t.pos))
            elif t.code==39:
                sid=struct.unpack_from('<H',t.data)[0]
                walk(read_tags(t.data,4,len(t.data)), sid)
            elif t.code==26:
                r=Bits(t.data); fl=r.u8(); depth=r.u16()
                if fl&2: r.u16()
                if fl&4: r.matrix()
                if fl&8: r.cxform(True)
                if fl&16: r.u16()
                if fl&32: r.cstr()
                if fl&64: r.u16()
                if fl&128: clipactions(t.data[r.p:], owner, frame, depth)
            elif t.code==34:
                bid=struct.unpack_from('<H',t.data)[0]
                off=struct.unpack_from('<H',t.data,3)[0]
                if off:
                    p=3+off
                    while True:
                        off=struct.unpack_from('<H',t.data,p)[0]
                        cond=struct.unpack_from('<H',t.data,p+2)[0]
                        end=p+off if off else len(t.data)
                        blocks.append(dict(kind='button',owner=bid,cond=cond,data=t.data[p+4:end]))
                        if not off: break
                        p+=off
    walk(s.tags, 0)
    return blocks
