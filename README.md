# 푸크로(Pucro)

## 실행 파일 빌드 (Windows PowerShell)

### 권장 빌드 방법 (tkinter 누락 방지)

`PyInstaller`는 작업 경로에 한글/특수문자가 포함된 경우 `tkinter installation is broken` 경고를 내고
`tkinter`를 제외해 빌드할 수 있습니다.

아래처럼 **영문 경로(예: `C:\Users\skarb`)에서 빌드 명령을 실행**하는 것을 권장합니다.

```powershell
$proj = "C:\Users\skarb\OneDrive\바탕 화면\개인작업실"

# 기존 빌드 산출물 정리
Remove-Item -Path "$proj\build" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "$proj\dist" -Recurse -Force -ErrorAction SilentlyContinue

# spec 빌드 (권장)
pyinstaller "$proj\Pucro.spec" --distpath "$proj\dist" --workpath "$proj\build" --noconfirm
```

빌드 로그에 아래 항목이 포함되면 정상입니다.
- `hook-_tkinter.py`
- `pyi_rth__tkinter.py`

### 실행파일 배포 (바탕화면 덮어쓰기)

실행파일을 최종 배포할 때는 아래처럼 `dist\Pucro.exe`를 바탕화면 `Pucro.exe`에 덮어씁니다.

```powershell
$src = "C:\Users\skarb\OneDrive\바탕 화면\개인작업실\dist\Pucro.exe"
$dst = "C:\Users\skarb\OneDrive\바탕 화면\Pucro.exe"
Copy-Item -Path $src -Destination $dst -Force
```

### 기존 빌드 방법

```powershell
# 기존 빌드 산출물 정리
Remove-Item -Path build -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path dist -Recurse -Force -ErrorAction SilentlyContinue

# 1) 스크립트 직접 빌드
pyinstaller --onefile --noconsole -n "Pucro" .\main.py

# 2) spec 사용(동일 결과)
# pyinstaller .\Pucro.spec
```

> 참고: 예전 문서에 있던 `total.py`/`total.spec`는 현재 엔트리포인트(main.py)로 통합되었습니다.
