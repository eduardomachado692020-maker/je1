import PyInstaller.__main__

# One-file Windows build, bundling templates/static
PyInstaller.__main__.run([
    "app.py",
    "--name=StellaVisionMG",
    "--onefile",
    "--windowed",
    "--add-data=templates;templates",
    "--add-data=static;static",
    # Optional: if you create an .ico, uncomment below and set the path:
    # "--icon=static/favicon.ico",
])
