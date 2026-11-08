import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from tests.fixtures import write_pair

@unittest.skipUnless(sys.platform=='win32' or os.environ.get('DISPLAY'),'Requires a window system')
class GuiTests(unittest.TestCase):
    def test_conversion_from_window(self):
        import tkinter as tk
        from xsf_converter.gui import App
        with tempfile.TemporaryDirectory() as folder:
            source,plain=write_pair(folder);target=Path(folder)/'gui.sf2'
            root=tk.Tk();root.withdraw()
            try:
                app=App(root);app.path.set(str(source))
                with patch('xsf_converter.gui.filedialog.asksaveasfilename',return_value=str(target)):
                    app.start()
                deadline=time.monotonic()+30
                while app.busy and time.monotonic()<deadline:
                    root.update();time.sleep(.02)
                self.assertFalse(app.busy)
                self.assertEqual(target.read_bytes(),plain)
                self.assertIn('SHA-256',app.result.get('1.0','end'))
            finally:root.destroy()
