import sys, struct, collections, re
sys.path.insert(0, __import__('os').path.dirname(__file__))
from swf import *
s=SWF(sys.argv[1])
def walk(tags, ctx, out):
    for t in tags:
        out.append((ctx,t))
        if t.code==39: walk(read_tags(t.data,4,len(t.data)), 'sprite%d'%struct.unpack_from('<H',t.data)[0], out)
allt=[]; walk(s.tags,'root',allt)
for ctx,t in allt:
    d=t.data
    if t.code==14:
        sid,fl=struct.unpack_from('<HB',d); cnt=struct.unpack_from('<I',d,3)[0]
        print('Sound',sid,'fmt',fl>>4,'rate',(fl>>2)&3,'16bit',(fl>>1)&1,'stereo',fl&1,'samples',cnt,'bytes',len(d))
    elif t.code==45: print('SoundStreamHead2',ctx,d.hex())
    elif t.code==19: print('StreamBlock',ctx,len(d))
    elif t.code in (6,21,35,20,36): print('Bitmap tag',t.code,'id',struct.unpack_from('<H',d)[0],len(d), d[2:6].hex())
    elif t.code==8: print('JPEGTables',len(d))
    elif t.code in (10,48): 
        fid=struct.unpack_from('<H',d)[0]
        if t.code==48:
            fl=d[2]; nl=d[4]; name=d[5:5+nl]; ng=struct.unpack_from('<H',d,5+nl)[0]
            print('Font2',fid,name,'glyphs',ng,'flags',hex(fl))
        else: print('Font1',fid,'glyphs',struct.unpack_from('<H',d,2)[0]//2)
    elif t.code==13: fid=struct.unpack_from('<H',d)[0]; nl=d[2]; print('FontInfo',fid,d[3:3+nl], 'flags',hex(d[3+nl]))
    elif t.code==37:
        r=Bits(d); cid=r.u16(); r.rect(); f1=r.u8(); f2=r.u8()
        fid=r.u16() if f1&1 else None; h=r.u16() if f1&1 else None
        col=r.rgba() if f1&4 else None
        mx=r.u16() if f1&2 else None
        if f2&0x20: al=r.u8(); r.u16();r.u16();r.u16();r.u16()
        var=r.cstr(); init=r.cstr() if f1&0x80 else b''
        print('EditText',cid,'font',fid,'h',h,'flags',hex(f1),hex(f2),'var',var,'init',init[:60])
    elif t.code==26 and d[0]&1 and 0: pass
    elif t.code==26:
        r=Bits(d); fl=r.u8(); dep=r.u16()
        if fl&2: r.u16()
        if fl&4: r.matrix()
        if fl&8: r.cxform(True)
        if fl&16: r.u16()
        if fl&64: print('ClipDepth used',ctx)
    elif t.code==4: print('PlaceObject1',ctx)
    elif t.code==15: print('StartSound',ctx,struct.unpack_from('<H',d)[0])
    elif t.code==17: print('ButtonSound',struct.unpack_from('<H',d)[0], [struct.unpack_from('<H',d,2+i*0)[0] for i in range(1)])
