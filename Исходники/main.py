from __future__ import annotations

import sys
from pathlib import Path




def create_application(argv: list[str] | None = None) -> tuple[QApplication, MainWindow]:
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication
    from ui.main_window import MainWindow
    from ui.styles import APP_STYLESHEET
    from ui.fonts import configure_application_fonts, configure_platform_rendering
    configure_platform_rendering()
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    configure_application_fonts(app)
    app.setApplicationName("КвантАлмаз")
    app.setOrganizationName("HerdingLab")
    app.setWindowIcon(QIcon(str(Path(__file__).resolve().parent / "ui" / "resources" / "app.ico")))
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLESHEET)
    window = MainWindow()
    return app, window


def main() -> int:
    if '--build-worker' in sys.argv:
        from integration.frozen_runtime import restore_worker_streams
        restore_worker_streams()
        from integration.build_process import main as worker_main
        return worker_main()
    if '--bundle-smoke' in sys.argv:
        from integration.bundle_smoke import run
        return run(Path(sys.argv[sys.argv.index('--bundle-smoke')+1]))
    app, window = create_application()
    window.show()
    from PySide6.QtCore import QTimer
    from integration.frozen_runtime import close_startup_splash
    QTimer.singleShot(60,close_startup_splash)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
