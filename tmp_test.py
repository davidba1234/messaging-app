from PyQt6.QtCore import Qt
print(Qt.WindowState.WindowMinimized)
try:
    print(~Qt.WindowState.WindowMinimized)
except Exception as e:
    print(repr(e))
try:
    print(Qt.WindowState.WindowNoState | Qt.WindowState.WindowActive)
except Exception as e:
    print(repr(e))
