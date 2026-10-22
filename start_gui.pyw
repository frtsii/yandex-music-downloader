"""Double-click to start the desktop application without a console window."""
import sys

sys.dont_write_bytecode = True
try:
    from ymd.gui import main
    main()
except Exception as error:
    import tkinter as tk
    from tkinter import messagebox
    window = tk.Tk()
    window.withdraw()
    messagebox.showerror(
        "Не удалось запустить загрузчик",
        f"{type(error).__name__}: {error}\n\n"
        "Запустите «Запустить интерфейс.cmd» для проверки установки.\n"
        "Инструкция находится в README.md рядом с программой.",
    )
    window.destroy()
