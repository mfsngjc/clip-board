# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        (
            'clip_board/assets/icons',
            'clip_board/assets/icons',
        ),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Clip Board',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Clip Board',
)
app = BUNDLE(
    coll,
    name='Clip Board.app',
    icon=None,
    bundle_identifier='com.clipboard.workbench',
    info_plist={
        'CFBundleShortVersionString': '0.2.0',
        'CFBundleVersion': '2',
        'CFBundleDocumentTypes': [
            {
                'CFBundleTypeName': 'Clip Board Project',
                'CFBundleTypeRole': 'Editor',
                'LSHandlerRank': 'Owner',
                'LSItemContentTypes': [
                    'com.clipboard.workbench.project',
                ],
                'CFBundleTypeExtensions': [
                    'clipboard',
                ],
            },
        ],
        'UTExportedTypeDeclarations': [
            {
                'UTTypeIdentifier': 'com.clipboard.workbench.project',
                'UTTypeDescription': 'Clip Board Project',
                'UTTypeConformsTo': [
                    'public.data',
                    'public.archive',
                ],
                'UTTypeTagSpecification': {
                    'public.filename-extension': [
                        'clipboard',
                    ],
                    'public.mime-type': 'application/x-clip-board-project',
                },
            },
        ],
    },
)
