"""Generate a tiny, original SoundFont with one preset/instrument/sample."""
import struct
from pathlib import Path
from xsf_converter.core import xor, HEADER_SIZE

def chunk(name, body):
    return name+struct.pack('<I',len(body))+body+b'\0'*(len(body)%2)
def name(text):
    return text.encode().ljust(20,b'\0')
def soundfont(audio_size=8192):
    info=chunk(b'LIST',b'INFO'+chunk(b'ifil',struct.pack('<HH',2,1))+
               chunk(b'INAM',b'Generated test bank\0'))
    audio=b'\0'*audio_size
    sdta=chunk(b'LIST',b'sdta'+chunk(b'smpl',audio))
    phdr=name('Sine')+struct.pack('<HHHIII',0,0,0,0,0,0)+name('EOP')+struct.pack('<HHHIII',0,0,1,0,0,0)
    inst=name('Test')+struct.pack('<H',0)+name('EOI')+struct.pack('<H',1)
    shdr=name('Silent test')+struct.pack('<IIIIIBbHH',0,max(0,audio_size//2-46),0,16,44100,60,0,0,1)+name('EOS')+b'\0'*26
    pdta=chunk(b'LIST',b'pdta'+b''.join(chunk(t,b) for t,b in [
        (b'phdr',phdr),(b'pbag',struct.pack('<HHHH',0,0,1,0)),
        (b'pmod',b'\0'*10),(b'pgen',struct.pack('<HHHH',41,0,0,0)),
        (b'inst',inst),(b'ibag',struct.pack('<HHHH',0,0,1,0)),
        (b'imod',b'\0'*10),(b'igen',struct.pack('<HHHH',53,0,0,0)),(b'shdr',shdr)]))
    return chunk(b'RIFF',b'sfbk'+info+sdta+pdta)

def encrypted(data, key=None, prefix=b''):
    key=key or bytes((i*73+19)%256 for i in range(128))
    return b'XSTM\x01\0\0\0'+b'\0'*(HEADER_SIZE-8)+xor(prefix+data,key)

def write_pair(folder, audio_size=8192):
    original=soundfont(audio_size)
    source=Path(folder)/'test.xsf';source.write_bytes(encrypted(original))
    return source,original
