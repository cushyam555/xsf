import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from xsf_converter import core
from tests.fixtures import encrypted, soundfont, write_pair

class ConverterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
    def test_exact_conversion_and_digest(self):
        source,plain=write_pair(self.folder,1024*1024)
        target=self.folder/'result.sf2'
        result=core.convert(source,target)
        self.assertEqual(target.read_bytes(),plain)
        self.assertEqual(result.sha256,hashlib.sha256(plain).hexdigest())
        self.assertEqual((result.info.presets,result.info.instruments,result.info.samples),(1,1,1))
    def test_second_key(self):
        data=soundfont(100000);source=self.folder/'other.xsf'
        source.write_bytes(encrypted(data,bytes(range(128))))
        out=self.folder/'out.sf2';core.convert(source,out)
        self.assertEqual(out.read_bytes(),data)
    def test_xor_phase_and_fallback(self):
        data=bytes(range(256))*79+b'last';key=bytes(range(128))
        expected=bytes(v^key[(i+37)%128] for i,v in enumerate(data))
        self.assertEqual(core.xor(data,key,37),expected)
        with patch.object(core,'np',None):
            self.assertEqual(core.xor(data,key,37),expected)
    def test_crosses_stream_boundary(self):
        source,plain=write_pair(self.folder,core.BLOCK_SIZE+550)
        out=self.folder/'out.sf2';progress=[]
        core.convert(source,out,progress=lambda *p:progress.append(p))
        self.assertEqual(out.read_bytes(),plain)
        self.assertGreater(len(progress),1)
    def test_invalid_container_and_corrupt_structure_rejected(self):
        for data in [b'not XSF',encrypted(b'bad data'*2048),encrypted(soundfont())[:-7]]:
            source=self.folder/'bad.xsf';source.write_bytes(data)
            with self.assertRaises(core.ConversionError):core.convert(source,self.folder/'bad.sf2')
            self.assertFalse((self.folder/'bad.sf2').exists())
    def test_same_file_and_hardlink_rejected(self):
        source,_=write_pair(self.folder)
        with self.assertRaises(core.ConversionError):core.convert(source,source,overwrite=True)
        alias=self.folder/'alias.sf2';os.link(source,alias)
        with self.assertRaises(core.ConversionError):core.convert(source,alias,overwrite=True)
    def test_no_clobber(self):
        source,_=write_pair(self.folder);out=self.folder/'existing.sf2';out.write_bytes(b'existing')
        with self.assertRaises(core.ConversionError):core.convert(source,out)
        self.assertEqual(out.read_bytes(),b'existing')
    def test_cancel_preserves_existing_and_removes_temp(self):
        source,_=write_pair(self.folder,core.BLOCK_SIZE+550)
        out=self.folder/'existing.sf2';out.write_bytes(b'existing');flag=[False]
        with self.assertRaises(core.Cancelled):
            core.convert(source,out,overwrite=True,cancel=lambda:flag[0],progress=lambda *_:flag.__setitem__(0,True))
        self.assertEqual(out.read_bytes(),b'existing')
        self.assertEqual(list(self.folder.glob('.xsf-*.tmp')),[])
    def test_source_modification_rejected(self):
        source,_=write_pair(self.folder)
        def change(*_):
            value=source.stat().st_mtime_ns+1000000000
            os.utime(source,ns=(value,value))
        with self.assertRaises(core.ConversionError):core.convert(source,self.folder/'out.sf2',progress=change)
        self.assertFalse((self.folder/'out.sf2').exists())
    def test_diagnostic_bounds_and_preservation(self):
        source,_=write_pair(self.folder);target=self.folder/'diagnostic.json'
        core.diagnostic(source,target);data=json.loads(target.read_text(encoding='utf-8'))
        actual=source.read_bytes()
        self.assertEqual(base64.b64decode(data['headBase64']),actual[:4096])
        self.assertEqual(base64.b64decode(data['tailBase64']),actual[data['tailOffset']:])
        with self.assertRaises(FileExistsError):core.diagnostic(source,target)
        with self.assertRaises(core.ConversionError):core.diagnostic(source,source)

if __name__=='__main__':unittest.main()
