from PyQtInspect.gui.mainwindow import MainWindow
from PyQt5.QtCore import QTimer

_orig_init = MainWindow.__init__

def _patched_init(self, *args, **kwargs):
    _orig_init(self, *args, **kwargs)
    QTimer.singleShot(0, self.start_server)

MainWindow.__init__ = _patched_init
