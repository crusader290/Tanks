import sys, struct, collections
TAGS={0:'End',1:'ShowFrame',2:'DefineShape',4:'PlaceObject',5:'RemoveObject',6:'DefineBits',7:'DefineButton',8:'JPEGTables',9:'SetBackgroundColor',10:'DefineFont',11:'DefineText',12:'DoAction',13:'DefineFontInfo',14:'DefineSound',15:'StartSound',17:'DefineButtonSound',18:'SoundStreamHead',19:'SoundStreamBlock',20:'DefineBitsLossless',21:'DefineBitsJPEG2',22:'DefineShape2',23:'DefineButtonCxform',24:'Protect',26:'PlaceObject2',28:'RemoveObject2',32:'DefineShape3',33:'DefineText2',34:'DefineButton2',35:'DefineBitsJPEG3',36:'DefineBitsLossless2',37:'DefineEditText',39:'DefineSprite',43:'FrameLabel',45:'SoundStreamHead2',46:'DefineMorphShape',48:'DefineFont2',56:'ExportAssets',57:'ImportAssets',58:'EnableDebugger',59:'DoInitAction',62:'DefineFontInfo2'}
d=open(sys.argv[1],'rb').read()
print(d[:3],d[3],struct.unpack('<I',d[4:8]))
nb=d[8]>>3
bits=''.join(f'{b:08b}' for b in d[8:8+((5+4*nb+7)//8)])
vals=[int(bits[5+i*nb:5+(i+1)*nb],2) for i in range(4)]
print('rect',vals)
p=8+((5+4*nb+7)//8)
print('rate',d[p+1],d[p],'frames',struct.unpack('<H',d[p+2:p+4]))
p+=4
def walk(p,end,depth):
  c=collections.Counter(); frames=0
  while p<end:
    h=struct.unpack('<H',d[p:p+2])[0];p+=2
    t=h>>6;l=h&63
    if l==63: l=struct.unpack('<I',d[p:p+4])[0];p+=4
    c[TAGS.get(t,t)]+=1
    if t==1: frames+=1
    if t==39 and depth==0:
      pass
    if depth==0 and t in (12,59,43,56,57,9,24,58):
      extra=''
      if t==43: extra=d[p:p+l].split(b'\0')[0]
      if t==56: extra=d[p:p+min(l,200)]
      print(f' frame{frames} {TAGS.get(t,t)} len={l} {extra}')
    p+=l
    if t==0: break
  return c,frames
c,f=walk(p,len(d),0)
print(f,c)
